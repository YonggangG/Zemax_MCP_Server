"""Thread-safe session state independent of pythonnet."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import RLock

from .protocol import ApplicationOwnership, ConnectionMode


class LifecycleState(StrEnum):
    NEW = "new"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    FAULTED = "faulted"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    lifecycle: LifecycleState
    mode: ConnectionMode | None
    ownership: ApplicationOwnership
    instance_id: int | None
    error: str | None


class SessionState:
    """Mutable lifecycle state with atomic snapshots."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._lifecycle = LifecycleState.NEW
        self._mode: ConnectionMode | None = None
        self._ownership = ApplicationOwnership.NONE
        self._instance_id: int | None = None
        self._error: str | None = None

    def snapshot(self) -> StateSnapshot:
        with self._lock:
            return StateSnapshot(
                self._lifecycle,
                self._mode,
                self._ownership,
                self._instance_id,
                self._error,
            )

    def transition(
        self,
        lifecycle: LifecycleState,
        *,
        mode: ConnectionMode | None = None,
        ownership: ApplicationOwnership | None = None,
        instance_id: int | None = None,
        error: str | None = None,
    ) -> StateSnapshot:
        with self._lock:
            self._lifecycle = lifecycle
            if mode is not None:
                self._mode = mode
            if ownership is not None:
                self._ownership = ownership
            self._instance_id = instance_id
            self._error = error
            return self.snapshot()

    def reset_connection(self, lifecycle: LifecycleState = LifecycleState.DISCONNECTED) -> None:
        with self._lock:
            self._lifecycle = lifecycle
            self._mode = None
            self._ownership = ApplicationOwnership.NONE
            self._instance_id = None
            self._error = None
