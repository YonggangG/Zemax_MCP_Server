"""Conservative conversion helpers for CLR values."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from zemax_mcp.errors import BackendError

_SIMPLE = (str, int, bool, type(None))
PLANO_RADIUS_COMPAT = 1e20


def compatible_radius(value: Any) -> float:
    """Return a finite numeric radius suitable for JSON/MCP round trips.

    OpticStudio exposes a plane sequential surface as ``+Infinity`` through
    ``ILDERow.Radius``.  JSON cannot represent infinity, and the public surface
    inputs are numeric, so use the established large-radius compatibility value.
    """

    radius = float(value)
    if math.isinf(radius):
        return math.copysign(PLANO_RADIUS_COMPAT, radius)
    return radius


def to_python(value: Any, *, max_depth: int = 8, _depth: int = 0) -> Any:
    """Convert common CLR/Python containers to transport-safe Python values.

    Unknown live objects are not reflected recursively; callers should return an
    opaque handle for those instead.
    """
    if _depth > max_depth:
        raise BackendError("serialize", "maximum conversion depth exceeded")
    if isinstance(value, _SIMPLE):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return value
    if isinstance(value, Enum):
        return to_python(value.value, max_depth=max_depth, _depth=_depth + 1)
    if isinstance(value, (Path, date, datetime)):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return to_python(asdict(value), max_depth=max_depth, _depth=_depth + 1)
    if isinstance(value, Mapping):
        return {
            str(key): to_python(item, max_depth=max_depth, _depth=_depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_python(item, max_depth=max_depth, _depth=_depth + 1) for item in value]
    # pythonnet arrays and basic collection proxies generally expose iteration.
    if isinstance(value, Iterable):
        try:
            return [to_python(item, max_depth=max_depth, _depth=_depth + 1) for item in value]
        except (TypeError, RuntimeError):
            pass
    full_name = getattr(getattr(value, "GetType", lambda: None)(), "FullName", None)
    if isinstance(full_name, str) and full_name.startswith("System."):
        try:
            return str(value)
        except Exception as exc:
            raise BackendError("serialize", f"cannot convert CLR value {full_name}: {exc}") from exc
    raise BackendError(
        "serialize",
        f"unsupported live object {type(value).__module__}.{type(value).__qualname__}; "
        "store it as a handle instead",
    )


def get_member(obj: Any, *names: str) -> Any:
    """Return the first available member, tolerating API casing/version changes."""
    for name in names:
        try:
            return getattr(obj, name)
        except (AttributeError, TypeError):
            continue
    raise AttributeError(f"none of {names!r} exist on {type(obj).__name__}")


def call_member(obj: Any, names: tuple[str, ...], /, *args: Any) -> Any:
    member = get_member(obj, *names)
    if not callable(member):
        raise TypeError(f"{names[0]} on {type(obj).__name__} is not callable")
    return member(*args)
