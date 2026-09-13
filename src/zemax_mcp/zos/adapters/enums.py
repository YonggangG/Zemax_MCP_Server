"""Name-tolerant adapters for pythonnet and test-double enum containers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


def normalize_name(value: object) -> str:
    """Normalize API/user spelling without losing enum semantics."""

    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def enum_name(value: Any) -> str:
    """Return a stable enum member name for CLR enums and Python fakes."""

    name = getattr(value, "name", None) or getattr(value, "Name", None)
    if name:
        return str(name)
    text = str(value)
    return text.rsplit(".", 1)[-1]


def _candidate_names(container: Any) -> Iterable[str]:
    if isinstance(container, Mapping):
        return (str(name) for name in container)
    names = getattr(container, "__members__", None)
    if isinstance(names, Mapping):
        return (str(name) for name in names)
    try:
        from System import Enum  # type: ignore[import-not-found]

        if bool(getattr(container, "IsEnum", False)):
            return (str(name) for name in Enum.GetNames(container))
    except (ImportError, AttributeError, TypeError):
        pass
    return (name for name in dir(container) if not name.startswith("_"))


def enum_names(container: Any) -> tuple[str, ...]:
    """List the declared names of a CLR/Python enum container."""

    return tuple(_candidate_names(container))


def enum_member(
    container: Any,
    value: Any,
    *,
    aliases: Mapping[str, str] | None = None,
) -> Any:
    """Resolve ``value`` against a CLR/Python enum using forgiving spelling.

    ``aliases`` maps normalized public spellings to actual enum member names.
    Existing enum values pass through unchanged when they compare by identity or
    normalized display name to a member.
    """

    names = tuple(_candidate_names(container))
    if not names:
        raise ValueError(f"{container!r} exposes no enum members")
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            return container(value)
        except (TypeError, ValueError):
            try:
                from System import Enum

                if bool(getattr(container, "IsEnum", False)):
                    return Enum.ToObject(container, value)
            except (ImportError, AttributeError, TypeError):
                pass
    lookup = {normalize_name(name): name for name in names}
    if aliases:
        for public, member in aliases.items():
            lookup[normalize_name(public)] = member
    key = normalize_name(enum_name(value))
    name = lookup.get(key)
    if name is None:
        options = ", ".join(names)
        raise ValueError(f"unknown enum value {value!r}; expected one of: {options}")
    if isinstance(container, Mapping):
        return container[name]
    members = getattr(container, "__members__", None)
    if isinstance(members, Mapping):
        return members[name]
    return getattr(container, name)
