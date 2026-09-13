"""CLR-free public runtime interfaces for ZOS-API access.

Public names are imported lazily. This keeps ordinary package import lightweight,
avoids configuration/discovery cycles, and never imports ``pythonnet`` or ``clr``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "ApplicationOwnership": ("protocol", "ApplicationOwnership"),
    "ConnectionMode": ("protocol", "ConnectionMode"),
    "ZOSBackend": ("protocol", "ZOSBackend"),
    "ZOSInstallation": ("discovery", "ZOSInstallation"),
    "discover_installation": ("discovery", "discover_installation"),
    "ZOSExecutor": ("executor", "ZOSExecutor"),
    "HandleStore": ("handles", "HandleStore"),
    "ObjectHandle": ("handles", "ObjectHandle"),
    "ZOSSession": ("session", "ZOSSession"),
    "LifecycleState": ("state", "LifecycleState"),
    "SessionState": ("state", "SessionState"),
    "StateSnapshot": ("state", "StateSnapshot"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *_EXPORTS))
