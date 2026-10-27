"""
Stdio MCP server.
"""

import contextlib

import mcp.server
import mcp.server.mcpserver
import mcp.server.mcpserver.exceptions

import zemaxmcp.opticstudio

__all__ = [
    'SERVER_NAME',
    'create_server',
    'main',
]

#: Name announced to an MCP host.
SERVER_NAME: str = "ZemaxMCP"


class OpticStudioConnection:
    """Keep one Interactive Extension session for this server process."""

    def __init__(self) -> None:
        #: The shared OpticStudio session. ``None`` before the first tool call and after a failed call.
        self.session: zemaxmcp.opticstudio.OpticStudioSession | None = None

    def open(self) -> zemaxmcp.opticstudio.OpticStudioSession:
        """
        Return the shared session, connecting on first use.

        :returns: The Interactive Extension session.
        :rtype: zemaxmcp.opticstudio.OpticStudioSession
        :raises zemaxmcp.opticstudio.OpticStudioError: OpticStudio cannot be connected.
        """

        if self.session is None:
            self.session = zemaxmcp.opticstudio.OpticStudioSession()

        return self.session

    def close(self) -> None:
        """Disconnect the shared session.

        Calling this again does nothing.
        """

        session = self.session
        self.session = None

        if session is not None:
            session.close()


@contextlib.asynccontextmanager
async def _lifespan(server: mcp.server.MCPServer):
    # Close the OpticStudio connection when the host stops this process.
    connection = OpticStudioConnection()

    try:
        yield connection
    finally:
        connection.close()


def create_server() -> mcp.server.MCPServer:
    """
    Create an MCP server.

    The server connects to Interactive Extension on the first call that needs it.

    :returns: The server.
    :rtype: mcp.server.MCPServer
    """

    server = mcp.server.MCPServer(SERVER_NAME, lifespan=_lifespan)

    @server.tool()
    def opticstudio_version(ctx: mcp.server.mcpserver.Context) -> dict[str, str | int]:
        """
        Return version details for the OpticStudio window waiting on Interactive Extension.

        :returns: Product, file, and ZOS-API versions, the license, and the connection mode.
        :rtype: dict[str, str | int]
        """

        connection = ctx.request_context.lifespan_context

        try:
            return connection.open().version()
        except zemaxmcp.opticstudio.OpticStudioError as exc:
            connection.close()
            raise mcp.server.mcpserver.exceptions.ToolError(str(exc)) from exc

    return server


def main() -> None:
    """Serve MCP over stdio until the host closes the connection."""

    create_server().run()
