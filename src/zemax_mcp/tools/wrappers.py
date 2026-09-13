"""CLR-free MCP wrapper factory for the data-driven registry."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from ..contracts import OperationSession, ToolSpec


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _clean_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Drop only absent values; preserve false, zero, and empty containers."""
    return {key: value for key, value in arguments.items() if value is not None}


def _snake_case(name: str) -> str:
    characters: list[str] = []
    for character in name:
        if character.isupper():
            if characters:
                characters.append("_")
            characters.append(character.lower())
        else:
            characters.append(character)
    return "".join(characters)


def _backend_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {_snake_case(key): value for key, value in arguments.items()}


async def dispatch_tool(
    session: OperationSession, spec: ToolSpec, arguments: Mapping[str, Any]
) -> Any:
    """Validate policy gates and delegate one catalog operation."""
    clean = _backend_arguments(_clean_arguments(arguments))
    if spec.capability_status == "unsupported":
        reason = spec.unsupported_reason or "operation is intentionally unsupported"
        raise NotImplementedError(f"{spec.name} is unsupported: {reason}")
    if spec.capability_status == "scaffolded" and spec.unsupported_reason:
        raise NotImplementedError(f"{spec.name} is scaffolded: {spec.unsupported_reason}")
    operation = spec.dispatch_operation
    if operation == "connect":
        return await _await_if_needed(
            session.connect(clean.get("mode"), instance_id=clean.get("instance_id"))
        )
    if operation == "disconnect":
        return await _await_if_needed(session.disconnect(save=bool(clean.get("save", False))))
    if operation == "restart":
        return await _await_if_needed(session.restart())
    if operation == "status":
        return await _await_if_needed(session.status())
    return await _await_if_needed(session.dispatch(operation, **clean))


def _annotation(schema: Mapping[str, Any], *, required: bool) -> Any:
    kind = schema.get("type")
    if kind == "string":
        base: Any = str
    elif kind == "integer":
        base = int
    elif kind == "number":
        base = float
    elif kind == "boolean":
        base = bool
    elif kind == "array":
        base = list[Any]
    elif kind == "object":
        base = dict[str, Any]
    else:
        base = Any
    return base if required else base | None


def make_tool_wrapper(spec: ToolSpec, session: OperationSession) -> Callable[..., Any]:
    """Create an async callable whose signature produces the catalog JSON schema."""
    required = set(spec.input_schema.get("required", ()))
    parameters = []
    annotations: dict[str, Any] = {}
    for name, schema in spec.input_schema.get("properties", {}).items():
        is_required = name in required
        annotation = _annotation(schema, required=is_required)
        annotations[name] = annotation
        default = inspect.Parameter.empty if is_required else schema.get("default", None)
        parameters.append(
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=annotation,
            )
        )

    async def wrapper(**kwargs: Any) -> Any:
        return await dispatch_tool(session, spec, kwargs)

    wrapper.__name__ = spec.name
    wrapper.__qualname__ = spec.name
    wrapper.__doc__ = spec.description
    wrapper.__annotations__ = {**annotations, "return": Any}
    wrapper.__signature__ = inspect.Signature(parameters, return_annotation=Any)  # type: ignore[attr-defined]
    return wrapper


__all__ = ["dispatch_tool", "make_tool_wrapper"]
