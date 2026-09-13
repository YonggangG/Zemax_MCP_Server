"""Opaque handle storage for worker-owned interop objects."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any
from uuid import uuid4

from zemax_mcp.errors import InvalidHandleError


@dataclass(frozen=True, slots=True)
class ObjectHandle:
    id: str
    kind: str

    def as_dict(self) -> dict[str, str]:
        return {"handle": self.id, "kind": self.kind}


class HandleStore:
    """Keeps CLR objects private while exposing opaque string identifiers."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._objects: dict[str, tuple[str, Any]] = {}

    def put(self, value: Any, *, kind: str = "object") -> ObjectHandle:
        handle = uuid4().hex
        with self._lock:
            self._objects[handle] = (kind, value)
        return ObjectHandle(handle, kind)

    def get(self, handle: str | ObjectHandle, *, kind: str | None = None) -> Any:
        key = handle.id if isinstance(handle, ObjectHandle) else handle
        with self._lock:
            try:
                stored_kind, value = self._objects[key]
            except KeyError as exc:
                raise InvalidHandleError(key) from exc
        if kind is not None and stored_kind != kind:
            raise InvalidHandleError(key)
        return value

    def release(self, handle: str | ObjectHandle) -> bool:
        key = handle.id if isinstance(handle, ObjectHandle) else handle
        with self._lock:
            return self._objects.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._objects.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._objects)
