"""High-level lifecycle coordinator for one dedicated ZOS worker."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from threading import RLock
from typing import Any

from zemax_mcp.config import RuntimeConfig
from zemax_mcp.errors import SessionClosedError, SessionError

from .executor import ZOSExecutor
from .protocol import ApplicationOwnership, ConnectionMode, ZOSBackend
from .real_backend import RealZOSBackend
from .state import LifecycleState, SessionState, StateSnapshot

BackendFactory = Callable[[RuntimeConfig], ZOSBackend]


class ZOSSession:
    """Serialize backend access and enforce ownership-aware cleanup."""

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        *,
        backend_factory: BackendFactory | None = None,
        executor: ZOSExecutor | None = None,
    ) -> None:
        self.config = config or RuntimeConfig.from_env()
        self._backend_factory = backend_factory or RealZOSBackend
        self._executor = executor or ZOSExecutor(name=self.config.worker_name)
        self._owns_executor = executor is None
        self._backend: ZOSBackend | None = None
        self._state = SessionState()
        self._lock = RLock()

    @property
    def snapshot(self) -> StateSnapshot:
        return self._state.snapshot()

    @property
    def connected(self) -> bool:
        return self.snapshot.lifecycle is LifecycleState.CONNECTED

    def _ensure_open(self) -> None:
        if self.snapshot.lifecycle is LifecycleState.CLOSED:
            raise SessionClosedError("ZOS session is closed")

    def _get_backend_on_worker(self) -> ZOSBackend:
        if self._backend is None:
            self._backend = self._backend_factory(self.config)
        return self._backend

    def connect(
        self,
        mode: ConnectionMode | str | None = None,
        *,
        instance_id: int | None = None,
    ) -> Mapping[str, Any]:
        self._ensure_open()
        selected_mode = self.config.connection_mode if mode is None else ConnectionMode.coerce(mode)
        selected_instance = self.config.instance_id if instance_id is None else instance_id
        if selected_instance < 0:
            raise SessionError("instance_id must be non-negative")
        with self._lock:
            current = self.snapshot
            if current.lifecycle is LifecycleState.CONNECTED:
                if current.mode is selected_mode and current.instance_id == selected_instance:
                    return self.status()
                raise SessionError("session is already connected with different parameters")
            self._state.transition(
                LifecycleState.CONNECTING,
                mode=selected_mode,
                instance_id=selected_instance,
            )
            try:
                metadata = self._executor.call(
                    self._connect_on_worker,
                    selected_mode,
                    selected_instance,
                )
            except Exception as exc:
                self._state.transition(
                    LifecycleState.FAULTED,
                    mode=selected_mode,
                    instance_id=selected_instance,
                    error=str(exc),
                )
                raise
            ownership = ApplicationOwnership(str(metadata.get("ownership", "none")))
            self._state.transition(
                LifecycleState.CONNECTED,
                mode=selected_mode,
                ownership=ownership,
                instance_id=selected_instance,
            )
            return metadata

    def _connect_on_worker(self, mode: ConnectionMode, instance_id: int) -> Mapping[str, Any]:
        return self._get_backend_on_worker().connect(mode, instance_id=instance_id)

    def dispatch(self, operation: str, /, **params: Any) -> Any:
        self._ensure_open()
        if operation.strip().lower() in {"connect", "disconnect", "close"}:
            raise SessionError(f"{operation!r} is a lifecycle operation, not a dispatch operation")
        if not self.connected:
            self.connect()
        return self._executor.call(self._dispatch_on_worker, operation, params)

    def _dispatch_on_worker(self, operation: str, params: dict[str, Any]) -> Any:
        return self._get_backend_on_worker().dispatch(operation, **params)

    def status(self) -> Mapping[str, Any]:
        snapshot = self.snapshot
        application_connected = snapshot.lifecycle is LifecycleState.CONNECTED
        result: dict[str, Any] = {
            "lifecycle": snapshot.lifecycle.value,
            "connected": application_connected,
            "application_connected": application_connected,
            "system_connected": application_connected,
            "mode": snapshot.mode.value if snapshot.mode else None,
            "ownership": snapshot.ownership.value,
            "instance_id": snapshot.instance_id,
            "error": snapshot.error,
            "worker_thread_id": self._executor.thread_id,
        }
        if snapshot.lifecycle is LifecycleState.CONNECTED:
            try:
                backend_status = self._executor.call(self._dispatch_on_worker, "status", {})
            except Exception as exc:
                result["backend_error"] = str(exc)
            else:
                if isinstance(backend_status, Mapping):
                    backend_data = dict(backend_status)
                    result["backend"] = backend_data
                    backend_connected = backend_data.get("connected", True)
                    result["application_connected"] = bool(
                        backend_data.get("application_connected", backend_connected)
                    )
                    result["system_connected"] = bool(
                        backend_data.get("system_connected", backend_connected)
                    )
                    result["connected"] = result["application_connected"]
        return result

    def disconnect(self, *, save: bool = False) -> Mapping[str, Any]:
        self._ensure_open()
        with self._lock:
            current = self.snapshot
            if current.lifecycle not in {
                LifecycleState.CONNECTED,
                LifecycleState.FAULTED,
                LifecycleState.CONNECTING,
            }:
                return {
                    "connected": False,
                    "application_connected": False,
                    "system_connected": False,
                    "saved": False,
                    "released": False,
                }
            self._state.transition(
                LifecycleState.DISCONNECTING,
                mode=current.mode,
                ownership=current.ownership,
                instance_id=current.instance_id,
            )
            try:
                result: Mapping[str, Any] = {
                    "connected": False,
                    "application_connected": False,
                    "system_connected": False,
                    "saved": False,
                    "released": False,
                }
                if self._backend is not None:
                    result = self._executor.call(self._backend.disconnect, save=save)
            except Exception as exc:
                self._state.transition(LifecycleState.FAULTED, error=str(exc))
                raise
            else:
                self._state.reset_connection()
                return result

    def restart(self) -> Mapping[str, Any]:
        self._ensure_open()
        current = self.snapshot
        mode = current.mode or self.config.connection_mode
        instance_id = (
            current.instance_id if current.instance_id is not None else self.config.instance_id
        )
        self.disconnect()
        return self.connect(mode, instance_id=instance_id)

    def close(self) -> None:
        with self._lock:
            if self.snapshot.lifecycle is LifecycleState.CLOSED:
                return
            try:
                self.disconnect()
            finally:
                if self._owns_executor:
                    self._executor.shutdown()
                self._state.reset_connection(LifecycleState.CLOSED)

    def __enter__(self) -> ZOSSession:
        self._ensure_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
