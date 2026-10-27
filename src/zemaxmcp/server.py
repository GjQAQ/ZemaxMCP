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

    def _read(ctx, read):
        # Drop the shared session when OpticStudio cannot answer, so the next call can reconnect.
        connection = ctx.request_context.lifespan_context

        try:
            return read(connection.open())
        except zemaxmcp.opticstudio.OpticStudioError as exc:
            connection.close()
            raise mcp.server.mcpserver.exceptions.ToolError(str(exc)) from exc

    @server.tool()
    def get_opticstudio_version(ctx: mcp.server.mcpserver.Context) -> dict[str, str | int]:
        """
        Return version details for the OpticStudio window waiting on Interactive Extension.

        - product_name: Product name from OpticStudio.exe.
        - product_version: Product version, such as 24.2.00.0. The first two parts identify the release, so 24.2 is 2024 R2.
        - file_version: File version of OpticStudio.exe.
        - file_description: File description of OpticStudio.exe.
        - opticstudio_version: Integer version reported by ZOS-API.
        - zos_major_version: ZOS-API major version.
        - zos_minor_version: ZOS-API minor version.
        - zos_service_pack: ZOS-API service pack number. 0 means no service pack.
        - license_status: License type, such as PremiumEdition.
        - mode: Connection mode. Interactive Extension reports Plugin.
        - installation_directory: Directory that contains OpticStudio.exe.
        - supported_release: Release this server supports. This value is fixed by the server.
        """

        return _read(ctx, lambda session: session.version())

    @server.tool()
    def get_lens_metadata(ctx: mcp.server.mcpserver.Context) -> dict[str, str | bool]:
        """
        Return identity details for the lens open in the OpticStudio window.

        - file: Full path of the lens file. Empty when the lens has not been saved.
        - name: System name.
        - title: Lens title from System Explorer Title/Notes.
        - author: Author from System Explorer Title/Notes.
        - notes: Notes from System Explorer Title/Notes.
        - mode: Sequential or NonSequential.
        - needs_save: True when the window has unsaved changes.
        - is_project_directory: True when the lens is stored as a project directory rather than a single file.
        """

        return _read(ctx, lambda session: session.lens_file())

    return server


def main() -> None:
    """Serve MCP over stdio until the host closes the connection."""

    create_server().run()
