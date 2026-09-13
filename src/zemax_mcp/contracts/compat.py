"""Compatibility policy shared by the CLI, registry, and server."""

from __future__ import annotations

from typing import Any

SERVER_NAME = "zemax-mcp"
MCP_SDK_REQUIREMENT = ">=2.2,<3"
MCP_API = "MCPServer"
INPUT_NAMING = "camelCase"
TOOL_NAME_PREFIX = "zemax_"
COMPATIBILITY_CONTRACT_VERSION = "1.0"

UPSTREAMS: dict[str, dict[str, str]] = {
    "zym": {
        "repository": "https://github.com/zym1998year/OpticStudioMCPServer",
        "commit": "8c9e3499f8d35db9a7383f7d2d0089ff92980a0a",
    },
    "jaruiz-nsc": {
        "repository": "https://github.com/jaruiz6363/OpticStudioMCPServer",
        "commit": "efc4d441796f5c1d5ae3e31759bbadfe3505b109",
    },
    "webworn": {
        "repository": "https://github.com/webworn/zemax-mcp-server",
        "commit": "3797d97492723f385988d47f8b183479bc172dd0",
    },
}


def compatibility_manifest() -> dict[str, Any]:
    """Return machine-readable invariants for compatibility consumers."""
    return {
        "contractVersion": COMPATIBILITY_CONTRACT_VERSION,
        "mcpSdk": MCP_SDK_REQUIREMENT,
        "mcpApi": MCP_API,
        "toolNamePrefix": TOOL_NAME_PREFIX,
        "inputNaming": INPUT_NAMING,
        "clrFreeImport": True,
        "dispatchContract": "session.dispatch(operation, **arguments)",
        "statusVocabulary": [
            "scaffolded",
            "offline-implemented",
            "live-verified",
            "unsupported",
        ],
        "capabilityVocabulary": ["production", "scaffolded", "unsupported"],
        "evidenceVocabulary": ["live-verified", "offline-only", "none"],
        "upstreams": UPSTREAMS,
    }
