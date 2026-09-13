from __future__ import annotations

import inspect
import json
from collections.abc import Iterable, Mapping
from typing import Any

import pytest

from tests.conftest import first_attribute, import_optional

REQUIRED_REPRESENTATIVE_TOOLS = {
    "zemax_connect",
    "zemax_disconnect",
    "zemax_status",
    "zemax_new_system",
    "zemax_open_file",
    "zemax_save_file",
    "zemax_get_system",
    "zemax_get_surface",
    "zemax_add_surface",
    "zemax_set_surface",
    "zemax_set_fields",
    "zemax_set_wavelengths",
    "zemax_ray_trace",
    "zemax_rms_spot",
    "zemax_fft_mtf",
    "zemax_add_operand",
    "zemax_optimize",
    "zemax_get_glass_catalogs",
    "zemax_get_configuration",
}


def _catalog() -> tuple[Any, ...]:
    registry = import_optional("zemax_mcp.registry")
    iterator = getattr(registry, "iter_tool_specs", None)
    if iterator is not None:
        return tuple(iterator())
    value = first_attribute(registry, "TOOL_CATALOG", "TOOLS", "CATALOG")
    if isinstance(value, Mapping):
        return tuple(value.values())
    assert isinstance(value, Iterable)
    return tuple(value)


def _get(spec: Any, *names: str, default: Any = None) -> Any:
    if isinstance(spec, Mapping):
        for name in names:
            if name in spec:
                return spec[name]
    for name in names:
        if hasattr(spec, name):
            return getattr(spec, name)
    return default


def _name(spec: Any) -> str:
    value = _get(spec, "name", "tool_name")
    assert isinstance(value, str) and value
    return value


def test_catalog_has_unique_stable_mcp_names_and_representative_domains() -> None:
    specs = _catalog()
    assert len(specs) >= 50, "the public MCP catalog should not silently lose broad tool coverage"
    names = [_name(spec) for spec in specs]
    assert len(names) == len(set(names))
    assert all(name.startswith("zemax_") and name.isascii() for name in names)
    assert set(names) >= REQUIRED_REPRESENTATIVE_TOOLS


def test_every_catalog_entry_has_description_and_object_input_schema() -> None:
    for spec in _catalog():
        description = _get(spec, "description", "help", "summary")
        assert isinstance(description, str) and description.strip(), _name(spec)
        schema = _get(spec, "input_schema", "schema", "parameters", "json_schema")
        if callable(schema):
            schema = schema()
        if hasattr(schema, "model_json_schema"):
            schema = schema.model_json_schema()
        assert isinstance(schema, Mapping), _name(spec)
        assert schema.get("type", "object") == "object", _name(spec)
        json.dumps(schema)


def test_catalog_manifest_is_json_serializable_and_deterministic() -> None:
    registry = import_optional("zemax_mcp.registry")
    manifest_function = first_attribute(registry, "catalog_manifest")
    first = manifest_function()
    second = manifest_function()
    assert first == second
    assert json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(
        second, sort_keys=True, allow_nan=False
    )


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((operation, arguments))
        return {"operation": operation, "arguments": arguments}

    def dispatch(self, operation: str, **arguments: Any) -> dict[str, Any]:
        self.calls.append((operation, arguments))
        return {"operation": operation, "arguments": arguments}


def test_tool_specs_delegate_to_session_without_hidden_live_dependencies() -> None:
    session = RecordingSession()
    tested = 0
    for spec in _catalog():
        name = _name(spec)
        if name not in {"zemax_status", "zemax_new_system", "zemax_get_system"}:
            continue
        callable_ = _get(spec, "handler", "function", "callable", "invoke")
        if callable_ is None:
            continue
        signature = inspect.signature(callable_)
        kwargs: dict[str, Any] = {}
        if "session" in signature.parameters:
            kwargs["session"] = session
        result = callable_(**kwargs)
        assert not inspect.isawaitable(result), (
            "offline registry handlers should be directly testable"
        )
        assert session.calls
        tested += 1
    if tested == 0:
        pytest.skip("catalog handlers are registered only when create_server is called")
