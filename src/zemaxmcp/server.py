"""
Stdio MCP server.
"""

import mcp.server

__all__ = [
    'SERVER_NAME',
    'create_server',
    'main',
]

#: Name announced to an MCP host.
SERVER_NAME: str = "ZemaxMCP"


def create_server() -> mcp.server.MCPServer:
    """Create an MCP server with no tools registered.

    :returns: The server. It does not connect to OpticStudio.
    :rtype: mcp.server.MCPServer
    """

    return mcp.server.MCPServer(SERVER_NAME)


def main() -> None:
    """Serve MCP over stdio until the host closes the connection."""

    create_server().run()
