"""
Ada — Research Chatbot Agent

An ADK agent that queries the Lovelace Elemental Knowledge Graph via
broadchurch_auth REST calls. Each tool function resolves entities, fetches
data, formats a readable report, and returns it as a string for the LLM
to synthesize into a user-facing response.

Local testing:
    cd agents
    pip install -r ada/requirements.txt
    export GOOGLE_CLOUD_PROJECT=broadchurch
    export GOOGLE_CLOUD_LOCATION=us-central1
    export GOOGLE_GENAI_USE_VERTEXAI=1
    export ELEMENTAL_API_URL=https://stable-query.lovelace.ai
    export ELEMENTAL_API_TOKEN=<your-token>
    adk web

Deployment:
    Use the /deploy_agent Cursor command or trigger the deploy-agent workflow.
"""

import json
from datetime import date

from google.adk.agents import Agent

try:
    from broadchurch_auth import elemental_client
except ImportError:
    from .broadchurch_auth import elemental_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_schema_cache: dict | None = None


def _get_schema() -> dict:
    """Fetch and cache the knowledge graph schema."""
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache
    try:
        resp = elemental_client.get("/elemental/metadata/schema")
        resp.raise_for_status()
        data = resp.json()
        _schema_cache = data.get("schema", data)
        return _schema_cache
    except Exception:
        return {}


def _pid_map() -> dict[str, int]:
    """Map property names to their numeric PIDs."""
    schema = _get_schema()
    props = schema.get("properties", [])
    return {p["name"]: p.get("pid", p.get("pindex", 0)) for p in props}


def _pid_types() -> dict[int, str]:
    """Map PIDs to their data types (data_str, data_nindex, etc.)."""
    schema = _get_schema()
    props = schema.get("properties", [])
    return {p.get("pid", p.get("pindex", 0)): p.get("type", "") for p in props}


def _flavor_map() -> dict[str, int]:
    """Map flavor names to their numeric FIDs."""
    schema = _get_schema()
    flavors = schema.get("flavors", [])
    return {f["name"]: f.get("fid", f.get("findex", 0)) for f in flavors}


def _resolve_entity(name: str) -> dict | None:
    """Resolve an entity by name. Returns {neid, name, flavor} or None."""
    try:
        resp = elemental_client.post(
            "/entities/search",
            json={
                "queries": [{"queryId": 1, "query": name}],
                "maxResults": 5,
                "includeNames": True,
                "includeFlavors": True,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        matches = data.get("results", [{}])[0].get("matches", [])
        if not matches:
            return None
        top = matches[0]
        return {
            "neid": top.get("neid", ""),
            "name": top.get("name", name),
            "flavor": top.get("flavor", ""),
            "score": top.get("score", 0),
            "all_matches": matches[:5],
        }
    except Exception as e:
        return None


def _get_entity_name(neid: str) -> str:
    """Look up display name for a NEID."""
    try:
        resp = elemental_client.get(f"/entities/{neid}/name")
        resp.raise_for_status()
        return resp.json().get("name", neid)
    except Exception:
        return neid


def _pad_neid(value) -> str:
    """Zero-pad a numeric entity ID to 20 characters."""
    return str(value).padStart(20, "0") if hasattr(str(value), "padStart") else str(value).zfill(20)


def _get_properties(neid: str, pids: list[int]) -> dict[int, str]:
    """Fetch property values for an entity. Returns {pid: display_value}."""
    try:
        resp = elemental_client.post(
            "/elemental/entities/properties",
            data={
                "eids": json.dumps([neid]),
                "pids": json.dumps(pids),
                "include_attributes": "true",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        types = _pid_types()
        result = {}
        for v in data.get("values", []):
            pid = v.get("pid", 0)
            val = v.get("value", "")
            if types.get(pid) == "data_nindex" and val:
                val = _get_entity_name(_pad_neid(val))
            result[pid] = str(val)
        return result
    except Exception:
        return {}


def _format_properties(neid: str, prop_names: list[str]) -> str:
    """Fetch and format properties as readable text."""
    pm = _pid_map()
    pids = [pm[n] for n in prop_names if n in pm]
    if not pids:
        return "No matching properties found in schema."
    values = _get_properties(neid, pids)
    inv_pm = {v: k for k, v in pm.items()}
    lines = []
    for pid, val in values.items():
        name = inv_pm.get(pid, f"pid_{pid}")
        lines.append(f"- **{name}**: {val}")
    return "\n".join(lines) if lines else "No property values found."


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def entity_search(name: str) -> str:
    """Search for an entity by name and return a comprehensive summary.

    Use this as the first step for any question about a specific entity
    (company, person, government body, etc.). Returns the entity's basic
    info and key properties.

    Args:
        name: The entity name to search for (e.g., "Apple", "Janet Yellen",
              "Federal Reserve").

    Returns:
        A formatted report with the entity's name, type, and properties,
        or an error message if not found.
    """
    try:
        entity = _resolve_entity(name)
        if not entity:
            return f"No entities found matching '{name}'. Try a different spelling or more specific name."

        neid = entity["neid"]
        lines = [
            f"## Entity: {entity['name']}",
            f"- **Type**: {entity.get('flavor', 'unknown')}",
            f"- **Confidence**: {entity.get('score', 0):.0%}",
        ]

        if len(entity.get("all_matches", [])) > 1:
            lines.append("\n**Other matches:**")
            for m in entity["all_matches"][1:]:
                lines.append(f"- {m.get('name', '?')} ({m.get('flavor', '?')}, score: {m.get('score', 0):.0%})")

        common_props = ["name", "country", "industry", "lei_code", "nationality",
                        "organization_type", "total_revenue", "total_assets",
                        "number_of_employees", "founded_date", "website"]
        pm = _pid_map()
        available = [p for p in common_props if p in pm]
        if available:
            props_text = _format_properties(neid, available)
            if props_text and "No property" not in props_text:
                lines.append(f"\n### Properties\n{props_text}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error searching for '{name}': {e}"


def get_relationships(entity_name: str, related_type: str = "person", relationship_filter: str = "") -> str:
    """Find entities related to a given entity.

    Use this for questions about board members, executives, subsidiaries,
    parent companies, owners, or any connected entities.

    Args:
        entity_name: Name of the center entity (e.g., "Apple").
        related_type: Type of related entities to find. Common values:
            "person" (for board members, executives),
            "organization" (for subsidiaries, parents),
            "location" (for headquarters, offices).
        relationship_filter: Optional comma-separated relationship types to
            filter by (e.g., "is_director,is_officer" or "owns,subsidiary_of").

    Returns:
        A formatted list of related entities with their relationship types.
    """
    try:
        entity = _resolve_entity(entity_name)
        if not entity:
            return f"Could not find entity '{entity_name}'."

        neid = entity["neid"]
        fm = _flavor_map()
        pm = _pid_map()

        related_fid = fm.get(related_type)
        if related_fid is None:
            for fname, fid in fm.items():
                if related_type.lower() in fname.lower():
                    related_fid = fid
                    related_type = fname
                    break

        if related_fid is None:
            return f"Unknown entity type '{related_type}'. Available types: {', '.join(sorted(fm.keys()))}"

        pids = []
        if relationship_filter:
            for rf in relationship_filter.split(","):
                rf = rf.strip()
                if rf in pm:
                    pids.append(pm[rf])

        expression: dict
        if pids:
            expression = {
                "type": "linked",
                "linked": {
                    "to_entity": neid,
                    "distance": 1,
                    "pids": pids,
                    "direction": "incoming",
                },
            }
        else:
            expression = {
                "type": "and",
                "and": [
                    {"type": "is_type", "is_type": {"fid": related_fid}},
                    {
                        "type": "linked",
                        "linked": {
                            "to_entity": neid,
                            "distance": 1,
                            "direction": "both",
                        },
                    },
                ],
            }

        resp = elemental_client.post(
            "/elemental/find",
            data={"expression": json.dumps(expression), "limit": "50"},
        )
        resp.raise_for_status()
        result = resp.json()
        eids = result.get("eids", [])

        if not eids:
            return f"No {related_type} entities found connected to {entity['name']}."

        lines = [f"## {related_type.title()} entities related to {entity['name']}", f"Found {len(eids)} result(s):\n"]
        for eid in eids[:30]:
            ename = _get_entity_name(eid)
            lines.append(f"- {ename}")

        if len(eids) > 30:
            lines.append(f"\n... and {len(eids) - 30} more.")

        return "\n".join(lines)
    except Exception as e:
        return f"Error finding relationships for '{entity_name}': {e}"


def get_events(entity_name: str, category: str = "", limit: int = 20) -> str:
    """Get event timelines for an entity — filings, announcements, regulatory
    actions, corporate events.

    Args:
        entity_name: Name of the entity to get events for.
        category: Optional event category filter (e.g., "Bankruptcy", "IPO",
                  "SEC Filing", "Merger").
        limit: Maximum number of events to return (default 20).

    Returns:
        A formatted timeline of events with dates and descriptions.
    """
    try:
        entity = _resolve_entity(entity_name)
        if not entity:
            return f"Could not find entity '{entity_name}'."

        neid = entity["neid"]
        fm = _flavor_map()
        event_fid = fm.get("event")
        if event_fid is None:
            for fname, fid in fm.items():
                if "event" in fname.lower():
                    event_fid = fid
                    break

        if event_fid is None:
            return "Event entity type not found in schema."

        expression = {
            "type": "and",
            "and": [
                {"type": "is_type", "is_type": {"fid": event_fid}},
                {
                    "type": "linked",
                    "linked": {
                        "to_entity": neid,
                        "distance": 1,
                        "direction": "both",
                    },
                },
            ],
        }

        resp = elemental_client.post(
            "/elemental/find",
            data={"expression": json.dumps(expression), "limit": str(limit)},
        )
        resp.raise_for_status()
        result = resp.json()
        eids = result.get("eids", [])

        if not eids:
            return f"No events found for {entity['name']}."

        pm = _pid_map()
        name_pid = pm.get("name", 8)
        desc_pids = [name_pid]
        for pname in ["description", "event_date", "event_category", "date"]:
            if pname in pm:
                desc_pids.append(pm[pname])

        lines = [f"## Events for {entity['name']}", f"Found {len(eids)} event(s):\n"]
        for eid in eids[:limit]:
            ename = _get_entity_name(eid)
            lines.append(f"- {ename}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching events for '{entity_name}': {e}"


def get_sentiment(entity_name: str) -> str:
    """Get market/news sentiment analysis for an entity.

    Args:
        entity_name: Name of the entity to analyze sentiment for.

    Returns:
        A formatted sentiment report with trend analysis.
    """
    try:
        entity = _resolve_entity(entity_name)
        if not entity:
            return f"Could not find entity '{entity_name}'."

        return (
            f"## Sentiment for {entity['name']}\n\n"
            f"Sentiment analysis requires the graph sentiment endpoint. "
            f"Entity resolved as: {entity['name']} ({entity.get('flavor', 'unknown')}), "
            f"NEID: {entity['neid']}.\n\n"
            f"Use entity_search to get detailed property data for this entity."
        )
    except Exception as e:
        return f"Error analyzing sentiment for '{entity_name}': {e}"


def get_schema_info(entity_type: str = "") -> str:
    """Discover what entity types and properties exist in the knowledge graph.

    Call with no arguments to list all entity types. Call with an entity_type
    to see its properties.

    Args:
        entity_type: Optional entity type name (e.g., "organization", "person").
                     Leave empty to list all available types.

    Returns:
        Schema information about entity types or a specific type's properties.
    """
    try:
        schema = _get_schema()
        flavors = schema.get("flavors", [])
        properties = schema.get("properties", [])

        if not entity_type:
            lines = ["## Available Entity Types\n"]
            for f in sorted(flavors, key=lambda x: x.get("name", "")):
                name = f.get("name", "unknown")
                fid = f.get("fid", f.get("findex", "?"))
                lines.append(f"- **{name}** (ID: {fid})")
            return "\n".join(lines)

        target = None
        for f in flavors:
            if f.get("name", "").lower() == entity_type.lower():
                target = f
                break
        if not target:
            for f in flavors:
                if entity_type.lower() in f.get("name", "").lower():
                    target = f
                    break

        if not target:
            return f"Entity type '{entity_type}' not found. Use get_schema_info() to list available types."

        fid = target.get("fid", target.get("findex", 0))
        lines = [f"## Properties for {target['name']} (FID: {fid})\n"]
        for p in properties[:80]:
            pname = p.get("name", "?")
            ptype = p.get("type", "?")
            pid = p.get("pid", p.get("pindex", "?"))
            lines.append(f"- **{pname}** (PID: {pid}, type: {ptype})")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching schema: {e}"


def about_ada() -> str:
    """Return information about Ada and how to use her.

    Returns:
        A help guide explaining Ada's capabilities.
    """
    return """## About Ada

Ada is a research assistant powered by the **Lovelace Elemental Knowledge Graph**.
She can help you investigate companies, executives, government entities, and the
relationships and events connecting them.

### What you can ask:
- **Entity lookup**: "Tell me about JPMorgan Chase" or "Who is Janet Yellen?"
- **Relationships**: "Who are the board members of Apple?" or "What companies does BlackRock own?"
- **Corporate structure**: "What's the corporate structure of Berkshire Hathaway?"
- **Events**: "What are the recent events for Tesla?"
- **Comparisons**: "Compare the board structures of JPMorgan and Goldman Sachs"
- **Schema discovery**: "What entity types are in the knowledge graph?"

### Tips:
- Be specific with entity names for better results
- Ask follow-up questions — Ada remembers context within a conversation
- Request specific data types: financials, governance, regulatory, etc.
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

TODAY = date.today().strftime("%B %d, %Y")

INSTRUCTION = f"""You are **Ada**, a research analyst assistant powered by the
Lovelace Elemental Knowledge Graph. Today is {TODAY}.

## Your Workflow
1. **Always use tools to fetch data before answering.** Never fabricate entity
   data or financial figures.
2. **Resolve entities first.** When a user mentions an entity by name, call
   entity_search first to resolve it.
3. **For comparisons**, call entity_search and get_relationships for each
   entity, then synthesize a comparative response.
4. **Compose from tool results.** After tools return data, synthesize a
   comprehensive research-grade answer.

## Response Formatting
- Use Markdown tables for structured/comparative data
- Use headers (##, ###) to organize long responses
- Use bullet lists for enumerations
- Format numbers with commas, currency with symbols ($1.2B), dates consistently
- Never show raw entity IDs (NEIDs) in user-facing text

## Important Rules
- Never guess. If you cannot find data, say so clearly.
- Handle ambiguity: if a name matches multiple entities, show options.
- Be comprehensive: provide properties, relationships, and events where relevant.
"""

root_agent = Agent(
    model="gemini-2.0-flash",
    name="ada",
    instruction=INSTRUCTION,
    tools=[
        entity_search,
        get_relationships,
        get_events,
        get_sentiment,
        get_schema_info,
        about_ada,
    ],
)
