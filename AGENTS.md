# ZemaxMCP

ZemaxMCP is a distributable MCP server for Ansys Zemax OpticStudio. The supported release is OpticStudio 2024 R2. Supporting another release is a separate change.

## Decisions

Lasting choices are recorded in `docs/adr`. Read the accepted records before changing the interface, the process model, or the external behavior. Add a new record to reverse an accepted decision.

## Development

Use the uv environment in `.venv`. Keep the server able to find OpticStudio on a user's machine. A machine-specific installation path does not belong in the project.

Write commit messages with [Conventional Commits](https://www.conventionalcommits.org/).
