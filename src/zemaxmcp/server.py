"""
Stdio MCP server.
"""

import mcp.server

__all__ = [
    'SERVER_NAME',
    'create_server',
    'main',
]

SERVER_NAME = "ZemaxMCP"


def create_server() -> mcp.server.MCPServer:
    """Return a server with no tools registered."""

    return mcp.server.MCPServer(SERVER_NAME)


def main() -> None:
    """Serve MCP over stdio until the host closes the connection."""

    create_server().run()
