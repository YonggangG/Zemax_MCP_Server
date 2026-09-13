"""Official MCP Python SDK v2 server assembly."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from .prompts import register_prompts
from .registry import TOOL_CATALOG
from .resources import register_resources
from .tools import make_tool_wrapper
from .version import __version__

SERVER_INSTRUCTIONS = """Operate Ansys Zemax OpticStudio through explicit zemax_* tools.
Connect before operations. Inputs use camelCase. Prefer specific wrappers over zemax_eval.
The catalog is CLR-free at import time; live operations require Windows, OpticStudio, a valid
ZOS-API license, and a configured backend session.
"""


def _default_session() -> Any:
    from .zos import ZOSSession

    return ZOSSession()


def create_server(session: Any | None = None) -> MCPServer[Any]:
    """Create and fully register the Zemax MCP server."""
    active_session = session if session is not None else _default_session()
    server: MCPServer[Any] = MCPServer(
        name="zemax-mcp",
        title="Zemax OpticStudio MCP",
        description="Union MCP tool catalog for Ansys Zemax OpticStudio through ZOS-API.",
        instructions=SERVER_INSTRUCTIONS,
        version=__version__,
    )
    for spec in TOOL_CATALOG:
        wrapper = make_tool_wrapper(spec, active_session)
        server.add_tool(
            wrapper,
            name=spec.name,
            title=spec.name.replace("zemax_", "").replace("_", " ").title(),
            description=spec.description,
            meta={
                "category": spec.category,
                "operation": spec.dispatch_operation,
                "implementationStatus": spec.implementation_status,
                "capabilityStatus": spec.capability_status,
                "evidenceStatus": spec.evidence_status,
                "evidence": list(spec.evidence),
                "unsupportedReason": spec.unsupported_reason,
                "provenance": list(spec.provenance),
            },
            structured_output=False,
        )
        # MCPServer builds its invocation validator from the Python signature, while the
        # public wire schema is the compatibility contract (including descriptions,
        # enums, and additionalProperties=false). Keep both: the dynamic signature
        # validates calls and this assignment preserves the exact advertised schema.
        registered = server._tool_manager.get_tool(spec.name)
        if registered is not None:
            registered.parameters = dict(spec.input_schema)
    register_resources(server, active_session)
    register_prompts(server)
    return server


def main() -> None:
    create_server().run("stdio")


__all__ = ["SERVER_INSTRUCTIONS", "create_server", "main"]
