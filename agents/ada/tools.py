"""
Ada's domain tools — orchestrate Elemental MCP calls into research workflows.

Each function is a self-contained research action: it opens an MCP session,
makes the necessary calls, formats the results as readable Markdown, caches
reports in ADK session state, and returns a string the LLM can synthesise from.
"""

import json
import re
from typing import Any

from google.adk.tools import ToolContext

try:
    from elemental import MCP_URL, elemental_session
except ImportError:
    from .elemental import MCP_URL, elemental_session


# ---------------------------------------------------------------------------
# Property-name presets (fuzzy-matched by the MCP server)
# ---------------------------------------------------------------------------

ORG_PROPERTIES = [
    "company_cik",
    "ticker",
    "exchange",
    "sic_code",
    "sic_description",
    "state_of_incorporation",
    "ein",
    "board_size",
    "former_name",
]

PERSON_PROPERTIES = [
    "job_title",
    "board_committee",
    "is_independent",
    "director_since",
    "total_compensation",
    "person_cik",
]


# ---------------------------------------------------------------------------
# Session-state helpers
# ---------------------------------------------------------------------------


def _skey(neid: str, suffix: str = "") -> str:
    return f"entity:{neid}:{suffix}" if suffix else f"entity:{neid}"


def _cache_get(ctx: Any, key: str) -> str | None:
    if ctx and hasattr(ctx, "state"):
        return ctx.state.get(key)
    return None


def _cache_set(ctx: Any, key: str, value: str) -> None:
    if ctx and hasattr(ctx, "state"):
        ctx.state[key] = value


# ---------------------------------------------------------------------------
# Response-parsing helpers
# ---------------------------------------------------------------------------


def _try_parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_neid(data: dict, text: str) -> str | None:
    if isinstance(data, dict):
        entity = data.get("entity", data)
        if isinstance(entity, dict) and "neid" in entity:
            return entity["neid"]
    match = re.search(r"\b(\d{18,20})\b", text)
    return match.group(1) if match else None


def _extract_field(data: dict, field: str) -> str | None:
    if isinstance(data, dict):
        entity = data.get("entity", data)
        if isinstance(entity, dict) and field in entity:
            return str(entity[field])
    return None


# ---------------------------------------------------------------------------
# Core tools
# ---------------------------------------------------------------------------


async def entity_search(
    name: str,
    flavor: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Search for an entity and return a comprehensive research briefing.

    Resolves the entity in the Lovelace knowledge graph, then fetches key
    properties, influential connections, and recent events — all in one call.
    This is the recommended starting point for any entity question.

    Args:
        name: Entity name (e.g. "Intel Corporation", "Elon Musk", "Russia").
        flavor: Optional type hint for disambiguation ("organization", "person", etc.).
    """
    if not MCP_URL:
        return "Error: Elemental MCP server is not configured."

    try:
        async with elemental_session() as es:
            # 1. Resolve the entity (no properties — just resolution)
            resolve_args: dict[str, Any] = {"entity": name}
            if flavor:
                resolve_args["flavor"] = flavor
            resolve_text = await es.call("elemental_get_entity", resolve_args)

            parsed = _try_parse_json(resolve_text)
            neid = _extract_neid(parsed, resolve_text)
            entity_flavor = _extract_field(parsed, "flavor")
            entity_name = _extract_field(parsed, "name") or name

            if not neid:
                return f"Entity resolution for '{name}':\n\n{resolve_text}"

            # Cache basic identity
            _cache_set(tool_context, _skey(neid), resolve_text)
            _cache_set(tool_context, f"neid:{name.lower()}", neid)
            _cache_set(tool_context, f"name:{neid}", entity_name)
            _cache_set(tool_context, f"flavor:{neid}", entity_flavor or "unknown")

            # 2. Fetch properties (use flavor-appropriate list)
            if entity_flavor in ("person",):
                props = PERSON_PROPERTIES
            elif entity_flavor in ("organization", "company"):
                props = ORG_PROPERTIES
            else:
                props = ORG_PROPERTIES + PERSON_PROPERTIES

            props_text = await es.call(
                "elemental_get_entity",
                {"entity": neid, "properties": props},
            )
            _cache_set(tool_context, _skey(neid, "properties"), props_text)

            # 3. Influential neighbours
            neighbors_text = await es.call(
                "elemental_graph_neighborhood",
                {"entity": neid, "size": 10},
            )
            _cache_set(tool_context, _skey(neid, "neighbors"), neighbors_text)

            # 4. Recent events
            events_text = await es.call(
                "elemental_get_events",
                {"entity": neid, "limit": 5, "include_participants": True},
            )
            _cache_set(tool_context, _skey(neid, "events"), events_text)

            report = "\n\n".join(
                [
                    f"# Entity Research: {entity_name}",
                    "## Resolution",
                    resolve_text,
                    "## Properties",
                    props_text,
                    "## Key Connections",
                    neighbors_text,
                    "## Recent Events",
                    events_text,
                ]
            )
            _cache_set(tool_context, _skey(neid, "briefing"), report)
            return report

    except Exception as e:
        return f"Error during entity search for '{name}': {e}"


async def corporate_structure(
    entity_name: str,
    tool_context: ToolContext = None,
) -> str:
    """Fetch board of directors, officers, and major shareholders for a company.

    Args:
        entity_name: Company name or NEID.
    """
    if not MCP_URL:
        return "Error: Elemental MCP server is not configured."

    try:
        async with elemental_session() as es:
            directors_text = await es.call(
                "elemental_get_related",
                {
                    "entity": entity_name,
                    "related_flavor": "person",
                    "relationship_types": ["is_director"],
                    "direction": "incoming",
                    "related_properties": [
                        "job_title",
                        "board_committee",
                        "is_independent",
                        "director_since",
                    ],
                    "limit": 30,
                },
            )

            officers_text = await es.call(
                "elemental_get_related",
                {
                    "entity": entity_name,
                    "related_flavor": "person",
                    "relationship_types": ["is_officer"],
                    "direction": "incoming",
                    "related_properties": ["job_title"],
                    "limit": 30,
                },
            )

            owners_text = await es.call(
                "elemental_get_related",
                {
                    "entity": entity_name,
                    "related_flavor": "person",
                    "relationship_types": ["is_ten_percent_owner"],
                    "direction": "incoming",
                    "related_properties": ["job_title"],
                    "limit": 20,
                },
            )

            report = "\n\n".join(
                [
                    f"# Corporate Structure: {entity_name}",
                    "## Board of Directors",
                    directors_text,
                    "## Officers",
                    officers_text,
                    "## Major Shareholders (10%+ Owners)",
                    owners_text,
                ]
            )

            cached_neid = _cache_get(tool_context, f"neid:{entity_name.lower()}")
            if cached_neid:
                _cache_set(tool_context, _skey(cached_neid, "corporate_structure"), report)

            return report

    except Exception as e:
        return f"Error fetching corporate structure for '{entity_name}': {e}"


async def event_monitor(
    entity_name: str,
    categories: str = "",
    time_range_after: str = "",
    time_range_before: str = "",
    limit: int = 10,
    tool_context: ToolContext = None,
) -> str:
    """Get an event timeline — filings, announcements, regulatory actions, corporate events.

    Args:
        entity_name: Entity name or NEID.
        categories: Comma-separated category filter (e.g. "Bankruptcy,IPO,Mergers & acquisitions").
        time_range_after: Start date (ISO, e.g. "2025-01-01").
        time_range_before: End date (ISO, e.g. "2026-04-01").
        limit: Max events (default 10).
    """
    if not MCP_URL:
        return "Error: Elemental MCP server is not configured."

    try:
        async with elemental_session() as es:
            args: dict[str, Any] = {
                "entity": entity_name,
                "limit": limit,
                "include_participants": True,
            }
            if categories:
                args["categories"] = [c.strip() for c in categories.split(",")]

            tr: dict[str, str] = {}
            if time_range_after:
                tr["after"] = time_range_after
            if time_range_before:
                tr["before"] = time_range_before
            if tr:
                args["time_range"] = tr

            events_text = await es.call("elemental_get_events", args)

            report = f"# Events: {entity_name}\n\n{events_text}"

            cached_neid = _cache_get(tool_context, f"neid:{entity_name.lower()}")
            if cached_neid:
                _cache_set(tool_context, _skey(cached_neid, "events_detail"), report)

            return report

    except Exception as e:
        return f"Error fetching events for '{entity_name}': {e}"


async def relations(
    entity_name: str,
    related_flavor: str = "",
    relationship_types: str = "",
    direction: str = "both",
    limit: int = 20,
    tool_context: ToolContext = None,
) -> str:
    """Explore an entity's relationships — ownership, corporate links, affiliations.

    Args:
        entity_name: Entity name or NEID.
        related_flavor: Required — type of related entities ("person", "organization", "event", "location", etc.).
        relationship_types: Comma-separated filter (e.g. "owns,subsidiary_of").
        direction: "outgoing" (entity is subject), "incoming" (entity is object), or "both" (default).
        limit: Max results (default 20).
    """
    if not MCP_URL:
        return "Error: Elemental MCP server is not configured."

    if not related_flavor:
        return (
            "Error: related_flavor is required.  Specify the type of related "
            "entity you want (e.g. 'person', 'organization', 'event', 'location')."
        )

    try:
        async with elemental_session() as es:
            args: dict[str, Any] = {
                "entity": entity_name,
                "related_flavor": related_flavor,
                "direction": direction,
                "limit": limit,
            }
            if relationship_types:
                args["relationship_types"] = [r.strip() for r in relationship_types.split(",")]

            text = await es.call("elemental_get_related", args)

            report = f"# Relationships: {entity_name} → {related_flavor}\n\n{text}"

            cached_neid = _cache_get(tool_context, f"neid:{entity_name.lower()}")
            if cached_neid:
                rel_key = ",".join(args.get("relationship_types", ["all"]))
                _cache_set(
                    tool_context,
                    _skey(cached_neid, f"relations:{related_flavor}/{rel_key}"),
                    report,
                )

            return report

    except Exception as e:
        return f"Error fetching relationships for '{entity_name}': {e}"


async def sentiment_analysis(
    entity_name: str,
    tool_context: ToolContext = None,
) -> str:
    """Get news-sentiment analysis for an entity — time series, statistics, and trend.

    Args:
        entity_name: Entity name or NEID.
    """
    if not MCP_URL:
        return "Error: Elemental MCP server is not configured."

    try:
        async with elemental_session() as es:
            text = await es.call("elemental_graph_sentiment", {"entity": entity_name})

            report = f"# Sentiment Analysis: {entity_name}\n\n{text}"

            cached_neid = _cache_get(tool_context, f"neid:{entity_name.lower()}")
            if cached_neid:
                _cache_set(tool_context, _skey(cached_neid, "sentiment"), report)

            return report

    except Exception as e:
        return f"Error fetching sentiment for '{entity_name}': {e}"


# ---------------------------------------------------------------------------
# Domain tools
# ---------------------------------------------------------------------------


async def fsi_data(
    entity_name: str,
    tool_context: ToolContext = None,
) -> str:
    """Fetch SEC filings and financial documents for a company.

    Retrieves recent filings (8-K, 10-K, DEF 14A, Form 3/4, etc.) by
    searching for related document entities.

    Args:
        entity_name: Company name or NEID.
    """
    if not MCP_URL:
        return "Error: Elemental MCP server is not configured."

    try:
        async with elemental_session() as es:
            filings_text = await es.call(
                "elemental_get_related",
                {
                    "entity": entity_name,
                    "related_flavor": "document",
                    "relationship_types": ["filed", "filer"],
                    "direction": "both",
                    "limit": 15,
                },
            )

            report = f"# SEC Filings & Financial Data: {entity_name}\n\n{filings_text}"

            cached_neid = _cache_get(tool_context, f"neid:{entity_name.lower()}")
            if cached_neid:
                _cache_set(tool_context, _skey(cached_neid, "filings"), report)

            return report

    except Exception as e:
        return f"Error fetching filings for '{entity_name}': {e}"


async def stock_data(
    entity_name: str,
    tool_context: ToolContext = None,
) -> str:
    """Get ticker, exchange, and stock-related information for a company.

    Args:
        entity_name: Company name or NEID.
    """
    if not MCP_URL:
        return "Error: Elemental MCP server is not configured."

    try:
        async with elemental_session() as es:
            text = await es.call(
                "elemental_get_entity",
                {
                    "entity": entity_name,
                    "properties": ["ticker", "exchange", "sic_code", "sic_description"],
                },
            )

            report = f"# Stock & Market Data: {entity_name}\n\n{text}"

            cached_neid = _cache_get(tool_context, f"neid:{entity_name.lower()}")
            if cached_neid:
                _cache_set(tool_context, _skey(cached_neid, "stock"), report)

            return report

    except Exception as e:
        return f"Error fetching stock data for '{entity_name}': {e}"


async def schema_lookup(
    flavor: str = "",
    query: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Discover entity types, properties, and relationships in the knowledge graph.

    Call with no arguments to list all entity types.  Pass a flavor to see its
    properties and relationships.  Add a query to search within a flavor's
    schema (e.g. query="revenue" with flavor="organization").

    Args:
        flavor: Entity type to inspect (e.g. "organization", "person").  Omit to list all.
        query: Natural-language search within a flavor's schema.  Requires flavor.
    """
    if not MCP_URL:
        return "Error: Elemental MCP server is not configured."

    try:
        async with elemental_session() as es:
            args: dict[str, Any] = {}
            if flavor:
                args["flavor"] = flavor
            if query:
                args["query"] = query
            return await es.call("elemental_get_schema", args)
    except Exception as e:
        return f"Error looking up schema: {e}"


async def inspect_citations(
    tool_context: ToolContext = None,
) -> str:
    """Retrieve the bibliography of all sources cited in the current session.

    Returns titles, URLs, and dates for citation markers ([1], [2], etc.) that
    appear in tool results.
    """
    if not MCP_URL:
        return "Error: Elemental MCP server is not configured."

    try:
        async with elemental_session() as es:
            return await es.call("elemental_get_bibliography", {})
    except Exception as e:
        return f"Error fetching bibliography: {e}"


# ---------------------------------------------------------------------------
# Utility tools (no MCP calls needed)
# ---------------------------------------------------------------------------


def read_from_state(
    entity_name: str = "",
    report_type: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Read previously cached entity data from session state.

    Avoids redundant API requests by returning data fetched by earlier tools.

    Args:
        entity_name: Entity name.  Omit to list all cached entities.
        report_type: Cache section — "briefing", "properties", "events",
                     "corporate_structure", "sentiment", "neighbors", "filings".
                     Omit to list available sections for the entity.
    """
    if not tool_context or not hasattr(tool_context, "state"):
        return "No session state available."

    state = tool_context.state

    if not entity_name:
        entities = set()
        for key in state:
            if isinstance(key, str) and key.startswith("name:"):
                neid = key[5:]
                entities.add(f"- {state[key]} (NEID: {neid})")
        if entities:
            return "Cached entities:\n" + "\n".join(sorted(entities))
        return "No entities cached in this session yet."

    neid = state.get(f"neid:{entity_name.lower()}")
    if not neid:
        return f"Entity '{entity_name}' not found in cache. Use entity_search first."

    if report_type:
        cached = state.get(_skey(neid, report_type))
        if cached:
            return cached
        return (
            f"No '{report_type}' data cached for {entity_name}. "
            "Available types: briefing, properties, events, events_detail, "
            "corporate_structure, sentiment, neighbors, filings, stock."
        )

    prefix = f"entity:{neid}:"
    available = [key[len(prefix) :] for key in state if isinstance(key, str) and key.startswith(prefix)]
    if available:
        return f"Cached data for {entity_name}: {', '.join(available)}"
    return f"No detailed data cached for {entity_name}."


def about_lovelace() -> str:
    """Return information about the Lovelace platform and knowledge graph.

    Use when a user asks what Lovelace is, what data is available, or how the
    knowledge graph works.
    """
    return (
        "# About Lovelace\n\n"
        "Lovelace is a knowledge graph platform that aggregates and connects data "
        "from multiple authoritative sources:\n\n"
        "## Data Sources\n"
        "- **SEC EDGAR** — Corporate filings (8-K, 10-K, 10-Q, DEF 14A, Form 3/4), "
        "insider transactions, corporate governance\n"
        "- **News** — Real-time news articles with entity extraction, sentiment "
        "analysis, and event classification\n"
        "- **FRED** — Federal Reserve Economic Data (GDP, interest rates, employment, "
        "consumer sentiment)\n"
        "- **FDIC** — Banking institution data\n"
        "- **LEI** — Legal Entity Identifiers and corporate hierarchies\n"
        "- **SIC** — Standard Industrial Classification codes and industry taxonomy\n"
        "- **Wikipedia** — Biographical and organizational background data\n"
        "- **Polymarket** — Prediction market data and forecasts\n\n"
        "## Entity Types\n"
        "Organizations, people, government entities, locations, industries, financial "
        "instruments, legal entities, articles, filings, events, sanctions programs, "
        "and more.\n\n"
        "## Key Capabilities\n"
        "- Entity resolution and disambiguation\n"
        "- Relationship traversal (ownership, governance, employment, affiliations)\n"
        "- Event timelines (filings, announcements, regulatory actions)\n"
        "- News sentiment analysis with trend tracking\n"
        "- Citation and provenance tracking for all facts"
    )


def ada_help() -> str:
    """Return a usage guide for Ada's research capabilities.

    Use when a user asks what Ada can do or how to get started.
    """
    return (
        "# Ada Research Assistant — Help Guide\n\n"
        "I'm Ada, a research analyst assistant.  I investigate companies, executives, "
        "government entities, and the connections between them using the Lovelace "
        "Elemental knowledge graph.\n\n"
        "## What I Can Do\n\n"
        "### Entity Research\n"
        '- **"Tell me about JPMorgan Chase"** — comprehensive briefing\n'
        '- **"Who is Janet Yellen?"** — person profile\n\n'
        "### Corporate Governance\n"
        '- **"Who are the board members of Apple?"** — directors, officers, shareholders\n'
        '- **"What\'s the corporate structure of Berkshire Hathaway?"** — leadership\n\n'
        "### Events & Filings\n"
        '- **"What recent events involve Tesla?"** — event timeline\n'
        '- **"Show me Intel\'s recent SEC filings"** — filing data\n\n'
        "### Relationships\n"
        '- **"How are JPMorgan and Goldman Sachs connected?"** — relationship map\n'
        '- **"Who owns stakes in this company?"** — ownership\n\n'
        "### Sentiment\n"
        '- **"What\'s the news sentiment for Apple?"** — sentiment trends\n\n'
        "### Comparisons\n"
        '- **"Compare the board structures of Google and Microsoft"** — side-by-side\n\n'
        "### Industry & Economic Data\n"
        '- **"What companies are in the semiconductor industry?"** — classification\n'
        '- **"What\'s the current GDP growth rate?"** — FRED data\n\n'
        "## Tips\n"
        "- I always verify data from the knowledge graph — I never guess\n"
        "- I cite sources with reference markers so you can verify\n"
        "- For complex questions I gather data from multiple tools before synthesising\n"
        "- If I can't find data, I'll say so clearly"
    )
