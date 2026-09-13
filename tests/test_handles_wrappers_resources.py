from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any

import pytest

from zemax_mcp.contracts.models import ToolSpec
from zemax_mcp.errors import InvalidHandleError
from zemax_mcp.prompts.workflows import register_prompts
from zemax_mcp.resources.catalog import register_resources
from zemax_mcp.tools.wrappers import dispatch_tool, make_tool_wrapper
from zemax_mcp.zos.handles import HandleStore


def test_handle_store_lifecycle_kind_checks_and_dict_shape() -> None:
    store = HandleStore()
    value = object()
    handle = store.put(value, kind="analysis")
    assert handle.as_dict() == {"handle": handle.id, "kind": "analysis"}
    assert len(store) == 1
    assert store.get(handle) is value
    assert store.get(handle.id, kind="analysis") is value
    with pytest.raises(InvalidHandleError):
        store.get(handle, kind="surface")
    assert store.release(handle) is True
    assert store.release(handle) is False
    with pytest.raises(InvalidHandleError):
        store.get(handle)
    store.put(object())
    store.clear()
    assert len(store) == 0


class Session:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def connect(self, mode: str | None = None, *, instance_id: int | None = None) -> dict[str, Any]:
        return {"connected": True, "mode": mode, "instance_id": instance_id}

    def disconnect(self, *, save: bool = False) -> dict[str, Any]:
        return {"connected": False, "saved": save, "released": True}

    def restart(self) -> dict[str, Any]:
        return {"connected": True, "restarted": True}

    def status(self) -> dict[str, Any]:
        return {"connected": True}

    def dispatch(self, operation: str, **params: Any) -> dict[str, Any]:
        self.calls.append((operation, params))
        return {"operation": operation, "params": params}


def test_wrapper_signature_argument_cleaning_and_dispatch() -> None:
    spec = ToolSpec(
        name="zemax_sample",
        description="Sample wrapper.",
        category="test",
        operation="sample_operation",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer", "default": 0},
                "enabled": {"type": "boolean"},
                "values": {"type": "array"},
                "options": {"type": "object"},
            },
            "required": ["name"],
        },
    )
    session = Session()
    wrapper = make_tool_wrapper(spec, session)
    signature = inspect.signature(wrapper)
    assert list(signature.parameters) == ["name", "count", "enabled", "values", "options"]
    assert wrapper.__name__ == "zemax_sample"
    result = asyncio.run(wrapper(name="x", count=0, enabled=False, values=[], options=None))
    assert result["operation"] == "sample_operation"
    assert session.calls == [
        ("sample_operation", {"name": "x", "count": 0, "enabled": False, "values": []})
    ]


def test_wrapper_maps_lifecycle_and_camel_case_arguments() -> None:
    session = Session()
    connect = ToolSpec(
        name="zemax_connect",
        description="Connect.",
        category="test",
        input_schema={"type": "object", "properties": {}},
    )
    result = asyncio.run(dispatch_tool(session, connect, {"mode": "standalone", "instanceId": 3}))
    assert result == {"connected": True, "mode": "standalone", "instance_id": 3}

    disconnect = ToolSpec(
        name="zemax_disconnect",
        description="Disconnect.",
        category="test",
        input_schema={"type": "object", "properties": {}},
    )
    assert asyncio.run(dispatch_tool(session, disconnect, {"save": True}))["saved"] is True

    restart = ToolSpec(
        name="zemax_restart",
        description="Restart.",
        category="test",
        input_schema={"type": "object", "properties": {}},
    )
    assert asyncio.run(dispatch_tool(session, restart, {}))["restarted"] is True

    generic = ToolSpec(
        name="zemax_get_system",
        description="Get system.",
        category="test",
        input_schema={"type": "object", "properties": {}},
    )
    asyncio.run(dispatch_tool(session, generic, {"includeSurfaces": False}))
    assert session.calls[-1] == ("get_system", {"include_surfaces": False})


def test_scaffolded_wrapper_reports_precise_reason_without_dispatch() -> None:
    spec = ToolSpec(
        name="zemax_constrained_optimize",
        description="Constrained optimization.",
        category="optimization",
        input_schema={"type": "object", "properties": {}},
        implementation_status="scaffolded",
        capability_status="scaffolded",
        unsupported_reason="No verified variable-vector and rollback contract.",
    )
    session = Session()
    with pytest.raises(NotImplementedError, match="variable-vector"):
        asyncio.run(dispatch_tool(session, spec, {}))
    assert session.calls == []


def test_eval_wrapper_is_intentionally_unsupported() -> None:
    spec = ToolSpec(
        name="zemax_eval",
        description="Eval.",
        category="escape-hatch",
        input_schema={"type": "object", "properties": {}},
        implementation_status="unsupported",
        capability_status="unsupported",
        unsupported_reason="Arbitrary backend evaluation is not exposed.",
    )
    session = Session()
    with pytest.raises(NotImplementedError, match="unsupported"):
        asyncio.run(dispatch_tool(session, spec, {}))
    assert session.calls == []


class RegistrationServer:
    def __init__(self) -> None:
        self.resources: dict[str, Any] = {}
        self.prompts: dict[str, Any] = {}

    def resource(self, uri: str, **_metadata: Any) -> Any:
        return lambda function: self.resources.setdefault(uri, function) or function

    def prompt(self, *, name: str, **_metadata: Any) -> Any:
        return lambda function: self.prompts.setdefault(name, function) or function


@dataclass
class SnapshotSession:
    snapshot: dict[str, Any]


def test_resources_register_and_render_catalog_and_session_json() -> None:
    server = RegistrationServer()
    register_resources(server, SnapshotSession({"connected": True}))
    manifest = json.loads(server.resources["zemax://catalog/manifest"]())
    capabilities = json.loads(server.resources["zemax://catalog/capabilities"]())
    status = json.loads(server.resources["zemax://session/status"]())
    assert manifest["toolCount"] >= 50
    assert len(manifest["tools"]) == manifest["toolCount"]
    assert capabilities["capabilities"] == manifest["capabilities"]
    assert capabilities["evidence"] == manifest["evidence"]
    assert status == {"connected": True}


def test_session_resource_supports_callable_snapshot_and_status_fallback() -> None:
    server = RegistrationServer()

    class CallableSession:
        def snapshot(self) -> None:
            return None

        def status(self) -> dict[str, Any]:
            return {"connected": False, "state": "idle"}

    register_resources(server, CallableSession())
    status = json.loads(server.resources["zemax://session/status"]())
    assert status == {"connected": False, "state": "idle"}


def test_prompts_register_expected_workflows_and_include_user_goals() -> None:
    server = RegistrationServer()
    register_prompts(server)
    assert set(server.prompts) == {
        "zemax_analyze_system",
        "zemax_optimize_system",
        "zemax_build_nsc_system",
    }
    assert "contrast" in server.prompts["zemax_analyze_system"]("measure contrast")
    assert "low distortion" in server.prompts["zemax_optimize_system"](
        "sharp corners", "low distortion"
    )
    assert "stray light" in server.prompts["zemax_build_nsc_system"]("reduce stray light")
