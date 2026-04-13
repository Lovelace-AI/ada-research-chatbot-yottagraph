"""
Elemental MCP client for Ada's domain tools.

Provides a thin async wrapper around the mcp library's streamable HTTP client
so domain tools can call Elemental MCP tools directly without going through
ADK's McpToolset.  Each domain tool creates a session via elemental_session(),
makes one or more call_tool() invocations, and closes the session when the
async-with block exits.
"""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml


def _load_mcp_url() -> str:
    """Resolve the Elemental MCP server URL from environment or broadchurch.yaml."""
    url = os.environ.get("ELEMENTAL_MCP_URL")
    if url:
        return url

    for candidate in [
        Path("broadchurch.yaml"),
        Path(__file__).parent / "broadchurch.yaml",
        Path(__file__).parent.parent / "broadchurch.yaml",
    ]:
        if candidate.exists():
            with open(candidate) as f:
                config = yaml.safe_load(f) or {}
            gw = config.get("gateway", {}).get("url", "")
            org = config.get("tenant", {}).get("org_id", "")
            if gw and org:
                return f"{gw.rstrip('/')}/api/mcp/{org}/elemental/mcp"

    return ""


MCP_URL = _load_mcp_url()


class ElementalSession:
    """Wraps a live MCP ClientSession with convenience helpers."""

    def __init__(self, session):
        self._session = session

    async def call(self, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call an MCP tool and return its concatenated text output."""
        try:
            result = await self._session.call_tool(tool_name, arguments or {})
            texts = []
            for content in result.content:
                if hasattr(content, "text"):
                    texts.append(content.text)
            return "\n".join(texts) if texts else json.dumps(result, default=str)
        except Exception as e:
            return f"Error calling {tool_name}: {e}"


@asynccontextmanager
async def elemental_session():
    """Open a short-lived MCP session for one domain-tool invocation.

    Usage::

        async with elemental_session() as es:
            text = await es.call("elemental_get_entity", {"entity": "Intel"})
    """
    if not MCP_URL:
        raise RuntimeError(
            "Elemental MCP URL not configured.  Set ELEMENTAL_MCP_URL or "
            "ensure broadchurch.yaml is present with gateway.url and tenant.org_id."
        )

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(MCP_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield ElementalSession(session)
