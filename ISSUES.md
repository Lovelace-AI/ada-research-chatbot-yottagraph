What caused the confusion:

SseConnectionParams vs StreamableHTTPConnectionParams — This was the critical mistake. The agents-data rule says to "wire MCP into ADK agents by declaring an McpToolset that points to the Elemental MCP server" but doesn't specify which transport class to use. The ADK docs online show SseConnectionParams in most examples (it's the older, more documented pattern). The Elemental MCP server uses Streamable HTTP, which is newer. Nothing in the project's docs mentions this distinction. An agent building from the rules alone will default to SseConnectionParams because that's what search results and most ADK examples show.

The missing elemental-mcp-patterns skill — The agents-data rule explicitly says: "Read the elemental-mcp-patterns skill (skills/elemental-mcp-patterns/) before writing tool code." But that skill doesn't exist in the project. It's referenced but was never installed or doesn't exist in the @yottagraph-app/aether-instructions package yet. This is where the transport type, working code examples, and MCP-specific patterns should live. If it existed and contained the correct import (StreamableHTTPConnectionParams), I'd have gotten it right on the first try.

No working MCP agent example — The example_agent uses REST via broadchurch_auth. There's no example of an agent using McpToolset. When I hit trouble with MCP, the path of least resistance was falling back to the REST pattern I could see working.

Silent failure mode — When McpToolset with SseConnectionParams fails to connect, it doesn't crash at agent startup. The agent just has zero tools. The LLM then hallucinates code. There's nothing in the docs warning about this silent failure, so it took multiple rounds to diagnose.

Concrete doc/skill changes I'd recommend:

Create the elemental-mcp-patterns skill (or add to the existing elemental-api/mcp.md): Include the correct import (StreamableHTTPConnectionParams), a copy-paste agent snippet that works, and a note that SseConnectionParams is the wrong transport for this server.

Add to the agents-data rule under the "MCP-based agents" section: Specify the transport class explicitly, e.g.: "Use StreamableHTTPConnectionParams (not SseConnectionParams) — the Elemental MCP server uses Streamable HTTP transport." Include a minimal working snippet.

Add an MCP agent example — either replace example_agent or add a second example (example_mcp_agent) that demonstrates McpToolset with StreamableHTTPConnectionParams and the broadchurch.yaml URL resolution pattern.

Add to broadchurch.yaml or the aether config section a field like mcp_transport: streamable_http so agents can programmatically know which transport to use.

Note the silent failure — somewhere in the agents rule or agents-data rule, warn that if McpToolset can't connect, the agent starts with zero tools and the LLM will hallucinate. Suggest checking tool count at startup.
