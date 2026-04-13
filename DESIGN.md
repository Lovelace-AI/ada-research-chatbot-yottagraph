# Ada  Research Chatbot

## Vision

# Ada — Research Chatbot

Build a sophisticated research chatbot called **Ada** that helps analysts
investigate companies, executives, government entities, and the relationships
and events connecting them. Ada is powered by the Lovelace Elemental knowledge
graph, accessed entirely through Elemental MCP tools.

This project includes **two deliverables**:

1. **An ADK agent** (`agents/ada/`) — a Python agent built with Google ADK
   that uses Elemental MCP tools to fetch, format, and cache knowledge graph
   data, then composes natural-language research responses.
2. **A chat UI** (the Nuxt app) — a polished chat interface that streams
   Ada's responses in real time and renders rich content (citations, entity
   cards, structured data).

Both are built and deployed as part of this project. The agent is not a
pre-existing service to connect to — it must be developed here.

---

## Architecture

**Single-LLM, tool-driven.** Ada is the only LLM in the request path. It
uses Gemini with thinking/planning enabled to decide which tools to call.
All data fetching is handled by deterministic Python tool functions that
call Elemental MCP, format the results into readable reports, and cache
them in session state. Ada reads the reports and composes responses for
the user.

**All data flows through Elemental MCP.** No tool should make direct HTTP
calls, database queries, or call third-party APIs. The Elemental MCP
server is the single data access layer — it handles entity resolution,
properties, relationships, events, sentiment, and more.

**Session-scoped state.** Each conversation maintains its own entity cache.
When a tool fetches data about an entity, the results are stored in session
state keyed by entity ID. Subsequent questions about the same entity reuse
cached data without redundant MCP calls. Related entities discovered during
relationship scans are registered as stubs so they can be resolved
efficiently later.

### Non-Negotiable Runtime Invariants

These are implementation constraints observed in the production Ada stack.
Keep flexibility elsewhere, but do not violate these:

1. **Always resolve first.** If an entity has not been resolved in this
   session, the first call must be `entity_search` for that entity.
2. **Use NEIDs internally, never externally.** If a NEID is known from
   prior tool output, pass it to `entity_search(..., neid="...")` and
   downstream calls for precision. Do not show NEIDs in user-facing text.
3. **Domain tools are data-gathering tools.** They should fetch, format,
   and save reports to session state, then return a short status signal.
   They should not be treated as the final user answer.
4. **Compose from state before answering.** After domain tools complete,
   read saved reports (`read_from_state`) and synthesize from those reports.
5. **Prefer canonical MCP semantics over heuristics.** For events, use
   `elemental_get_events` behavior and its typed fields (category/date/etc.).
   Do not infer event meaning from PID-name substring matching.
6. **Handle reference-typed properties correctly.** `data_nindex`-style
   values are entity references/IDs; resolve them to display names before
   rendering user-facing output.
7. **Citation refs are strict.** Preserve real `ref_*` hashes exactly as
   returned by tools. Never fabricate or transform refs.
8. **Cache behavior is part of correctness.** Repeated `entity_search` for
   an already-resolved entity should be idempotent and return cached results.

---

## Ada's Identity and Behavior

Ada is a knowledgeable, precise research assistant. Key behavioral traits:

- **Research-oriented.** Ada treats every question as a research task.
  It gathers relevant data via tools before answering, rather than
  speculating from general knowledge.
- **Entity-first workflow.** Most interactions start with entity resolution.
  When a user mentions "Apple" or "Janet Yellen," Ada first resolves the
  entity in the knowledge graph, then fetches relevant data based on what
  the user is asking about.
- **Multi-step reasoning.** For complex questions ("Compare the board
  structures of JPMorgan and Goldman Sachs"), Ada plans multiple tool
  calls, gathers data for each entity, and synthesizes a comparative
  response.
- **Citations and provenance.** Ada cites its sources. When presenting
  facts from the knowledge graph, responses should reference where the
  data came from so analysts can verify.
- **Structured output.** Ada uses tables, bullet lists, and clear section
  headers to present data. Financial figures, dates, and entity names
  are formatted precisely.

---

## Tool Suite

Ada's tools are Python functions registered with the ADK agent. Each tool
calls one or more Elemental MCP tools, formats the response, and saves a
report to session state. Build these tools to cover Ada's research domains:

### Core Tools

| Tool | Purpose | Key MCP tools used |
|---|---|---|
| `entity_search` | Resolve an entity by name, fetch its properties and basic relationships. This is the entry point for most queries. | `elemental_get_entity`, `elemental_get_related` |
| `relations` | Explore an entity's relationships — who owns it, who it's connected to, corporate links. | `elemental_get_relationships`, `elemental_get_related` |
| `corporate_structure` | Fetch board members, executives, corporate hierarchy, and ownership chains. | `elemental_get_related` |
| `event_monitor` | Get event timelines — filings, announcements, regulatory actions, corporate events. | `elemental_get_events` |
| `fsi_data` | SEC filings, financial statements, quarterly data. Fetches multiple filing types in one call. | `elemental_get_entity`, `elemental_get_related` |

### Domain Tools

| Tool | Purpose | Key MCP tools used |
|---|---|---|
| `sanctions` | Sanctions programs, enforcement actions, designated entities. | `elemental_get_entity`, `elemental_get_related`, `elemental_get_events` |
| `stock_data` | Ticker information, stock prices, market data. | `elemental_get_related`, `elemental_get_entity` |
| `prediction_markets` | Prediction market contracts and related events. | `elemental_get_related`, `elemental_get_events` |
| `company_industry` | SIC industry classification for a company. | `elemental_get_related` |
| `industry_companies` | List companies within a given SIC industry code. | `elemental_get_entity`, `elemental_get_related` |
| `search_industries` | Fuzzy search across SIC industry categories. | `elemental_get_entity`, `elemental_get_related` |
| `lei_data` | LEI (Legal Entity Identifier) lookups and parent/subsidiary chains. | `elemental_get_entity`, `elemental_get_related` |
| `fred_data` | FRED economic time series data (GDP, interest rates, employment, etc.). | `elemental_get_related`, `elemental_get_entity` |

### Utility Tools

| Tool | Purpose |
|---|---|
| `inspect_citations` | Retrieve provenance details for cited facts (uses `elemental_get_citations`). |
| `read_from_state` | Read a previously cached entity report from session state without making new MCP calls. |
| `about_lovelace` | Return information about the Lovelace platform (bundled text, no MCP call needed). |
| `ada_help` | Return a usage guide for Ada (bundled text, no MCP call needed). |

### Tool Design Principles

- Each tool should **resolve the entity first** (via `elemental_get_entity`)
  if it hasn't been resolved yet in this session.
- Tool outputs should be **formatted as readable Markdown reports** that
  Ada can incorporate directly into responses.
- Tools should **save their reports to session state** so Ada can reference
  them later without re-fetching.
- Use **compound cache keys** for relationship data (e.g.,
  `"person/is_director,is_officer"`) to avoid collisions between different
  relationship queries for the same entity.

### Known Pitfalls (from previous builds)

These are concrete mistakes that previous agents made when building Ada.
Learn from them:

1. **Properties have types — check them.** Use `elemental_get_schema` to
   build a map of PID (property ID) to type. Properties with type
   `data_nindex` are entity references, not display text. If you render
   them raw, the user sees a meaningless 19-digit number instead of
   "United States" or "Semiconductor Industry." Build a `_pid_types()`
   helper and a `_format_properties_smart()` function that auto-detects
   `data_nindex` properties and resolves them to display names.

2. **Events come from event APIs, not PID name matching.** A previous
   agent tried to find events by searching for PIDs with "event" or
   "filing" in the name. This matched "filed" (a document relationship
   PID) and returned raw filing NEIDs as "events." The correct approach
   is to use `elemental_get_events` (which returns typed event entities
   with category, date, and description fields) or traverse the
   participant relationship to find `schema::flavor::event` entities.

3. **Entity search should return rich data.** When a user asks "tell me
   about Intel," the response should be comprehensive — not just a
   single paragraph. Fetch properties, key relationships, financial
   data, and recent events in a single `entity_search` call (or chain
   of calls), then compose a thorough briefing. The user expects Ada
   to be a research tool, not a Wikipedia summary.

---

## Session State Design

Maintain an entity store in the agent's session state. Each entity entry:

```
{
  "neid": "...",            // Resolved entity ID
  "flavor": "...",          // Entity type (organization, person, government, etc.)
  "name": "...",            // Display name
  "properties": {...},      // Fetched property values
  "relationships": {...},   // Cached relationship data (compound keys)
  "reports": {...}          // Tool outputs keyed by tool name
}
```

Additional state to track:
- **Provenance** — accumulated citation sources from MCP response metadata
- **Tool log** — ordered list of tool invocations for the session

The `entity_search` tool should be idempotent: repeat calls for the same
entity return cached data.

---

## Chat UI

Build a polished chat interface as the main (and likely only) page. Key
requirements:

- **SSE streaming** — Use `useAgentChat` to stream agent responses in real
  time. Show partial text as it arrives.
- **Rich message rendering** — Ada's responses contain Markdown with
  tables, headers, lists, and citations. Render them properly.
- **Entity context** — When Ada resolves an entity, consider showing a
  compact entity card or header so the user knows what entity is in focus.
- **Tool activity indicators** — While Ada is calling tools (which can
  take a few seconds per MCP round-trip), show the user what's happening
  (e.g., "Searching for entity...", "Fetching financial data...").
- **Citation links** — If Ada cites sources, make them interactive or at
  least visually distinct.
- **Conversation starters** — Provide example queries to help new users
  get started. Good examples:
  - "Tell me about JPMorgan Chase"
  - "Who are the board members of Apple?"
  - "What sanctions are associated with Russia?"
  - "Compare the recent SEC filings of Tesla and Ford"
  - "What's the corporate structure of Berkshire Hathaway?"

---

## Agent System Prompt Guidance

Ada's system prompt should establish:

1. **Identity** — Ada is a research analyst assistant that uses the
   Lovelace Elemental knowledge graph to answer questions about entities,
   relationships, and events.
2. **Tool-first approach** — Always use tools to fetch data before
   answering. Never fabricate entity data or financial figures.
3. **Entity resolution strategy** — When a user mentions an entity by
   name, resolve it first with `entity_search`. Use the resolved entity
   ID for all subsequent tool calls.
4. **Multi-entity handling** — For comparative questions, resolve and
   fetch data for each entity, then synthesize.
5. **Response formatting** — Use Markdown tables for structured data,
   cite sources, and organize long responses with clear headings.
6. **Date awareness** — Include today's date so Ada can interpret
   relative time expressions ("last quarter", "recent filings").

---

## Tech Notes

- **Data pattern:** This is a "channeling" app — the agent invokes MCP
  tools and returns natural-language answers. No Postgres needed for
  graph data.
- **MCP is mandatory.** The agent's tool functions must call Elemental
  **MCP tools** (`elemental_get_entity`, `elemental_get_related`, etc.)
  — do NOT use `useElementalClient()`, the Elemental REST API, or any
  direct HTTP calls to the Query Server. A key goal of this project is
  to demonstrate that Broadchurch agents can orchestrate sophisticated
  workflows through MCP servers. Read the `agents-data` rule for MCP
  wiring patterns.
- **Schema discovery:** Use the `data-model` skill docs for entity types,
  properties, and relationship schemas. The `elemental_get_schema` MCP
  tool is also available for runtime schema introspection.
- **LLM:** Use Gemini with thinking/planning enabled. The agent should
  reason about which tools to call before acting.
- **Auth:** Default dev bypass (`NUXT_PUBLIC_USER_NAME`) is fine for
  initial development.


## Status

Project just created. Run `/build_my_app` in Cursor to start building.

## Modules

*None yet — the agent will populate this as features are built.*
