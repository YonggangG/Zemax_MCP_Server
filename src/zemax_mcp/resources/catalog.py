"""MCP resource registrations."""

from __future__ import annotations

import json
from typing import Any

from ..registry import catalog_manifest


def register_resources(server: Any, session: Any) -> None:
    """Register stable catalog and live-session resources."""

    @server.resource(  # type: ignore[untyped-decorator]
        "zemax://catalog/manifest",
        name="zemax-tool-manifest",
        description="Complete Zemax MCP union tool manifest.",
        mime_type="application/json",
    )
    def tool_manifest() -> str:
        return json.dumps(catalog_manifest(), indent=2, sort_keys=True)

    @server.resource(  # type: ignore[untyped-decorator]
        "zemax://catalog/capabilities",
        name="zemax-capability-evidence",
        description="Derived production capability and live-evidence summary.",
        mime_type="application/json",
    )
    def capability_evidence() -> str:
        manifest = catalog_manifest()
        value = {
            "name": manifest["name"],
            "version": manifest["version"],
            "toolCount": manifest["toolCount"],
            "capabilities": manifest["capabilities"],
            "evidence": manifest["evidence"],
        }
        return json.dumps(value, indent=2, sort_keys=True)

    @server.resource(  # type: ignore[untyped-decorator]
        "zemax://session/status",
        name="zemax-session-status",
        description="Current CLR-free session status snapshot.",
        mime_type="application/json",
    )
    def session_status() -> str:
        value = getattr(session, "snapshot", None)
        if callable(value):
            value = value()
        if value is None:
            value = getattr(session, "status", {"connected": False})
        if callable(value):
            value = value()
        return json.dumps(value, indent=2, sort_keys=True, default=str)
