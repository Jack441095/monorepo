"""A minimal, real MCP stdio server used only by
tests/test_mcp_client.py's integration test -- not part of Thursday
itself. Exercises thursday/mcp_client.py against an actual `mcp` SDK
server process, not a mock, so a future SDK upgrade that changes the
client-facing shapes (Tool.input_schema, CallToolResult.content, etc.)
gets caught here instead of silently drifting.
"""

import asyncio

from mcp.server.mcpserver import MCPServer

server = MCPServer("thursday-test-server")


@server.tool()
def draft_post(platform: str, topic: str) -> str:
    """Draft a short social media post."""
    return f"[{platform}] Exciting news about {topic}!"


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
