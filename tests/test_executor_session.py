from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from tests.conftest import construct_with_supported_kwargs, first_attribute, import_optional
from tests.fake_zemax import FakeBackend


def _executor_type() -> Any:
    module = import_optional("zemax_mcp.zos.executor")
    return first_attribute(
        module, "ZOSExecutor", "OneThreadExecutor", "SerializedExecutor", "ZosExecutor"
    )


def _close_executor(executor: Any) -> None:
    for name in ("shutdown", "close"):
        method = getattr(executor, name, None)
        if method is not None:
            method()
            return


def test_executor_serializes_concurrent_calls_on_one_stable_thread() -> None:
    executor = construct_with_supported_kwargs(_executor_type())
    active = 0
    maximum_active = 0
    activity_lock = threading.Lock()

    def work(value: int) -> tuple[int, int]:
        nonlocal active, maximum_active
        with activity_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            time.sleep(0.005)
            return value, threading.get_ident()
        finally:
            with activity_lock:
                active -= 1

    try:
        futures = [executor.submit(work, value) for value in range(12)]
        results = [future.result(timeout=5) for future in futures]
        assert [value for value, _thread_id in results] == list(range(12))
        thread_ids = {thread_id for _value, thread_id in results}
        assert len(thread_ids) == 1
        assert next(iter(thread_ids)) != threading.get_ident()
        assert maximum_active == 1
        exposed_thread_id = getattr(executor, "thread_id", None)
        if exposed_thread_id is not None:
            assert exposed_thread_id in thread_ids
    finally:
        _close_executor(executor)


def test_executor_propagates_errors_and_remains_usable() -> None:
    executor = construct_with_supported_kwargs(_executor_type())

    def fail() -> None:
        raise ValueError("sentinel")

    try:
        with pytest.raises(ValueError, match="sentinel"):
            executor.call(fail)
        assert executor.call(lambda: 42) == 42
    finally:
        _close_executor(executor)


def test_executor_reentrant_call_does_not_deadlock() -> None:
    executor = construct_with_supported_kwargs(_executor_type())
    try:
        result = executor.call(lambda: executor.call(lambda: threading.get_ident()))
        assert result == getattr(executor, "thread_id", result)
    finally:
        _close_executor(executor)


def test_executor_rejects_submissions_after_shutdown() -> None:
    module = import_optional("zemax_mcp.zos.executor")
    worker_error = import_optional("zemax_mcp.errors").WorkerError
    executor = construct_with_supported_kwargs(first_attribute(module, "ZOSExecutor"))
    executor.shutdown()
    with pytest.raises(worker_error, match="closed"):
        executor.submit(lambda: None)


def test_session_facade_delegates_to_injected_backend() -> None:
    session_module = import_optional("zemax_mcp.zos.session")
    session_type = first_attribute(session_module, "ZOSSession", "ZemaxSession", "Session")
    backend = FakeBackend()

    def backend_factory(*_args: Any, **_kwargs: Any) -> FakeBackend:
        return backend

    session = construct_with_supported_kwargs(session_type, backend_factory=backend_factory)
    try:
        result = session.connect(mode="standalone")
        assert result["connected"] is True
        assert session.connected is True

        status = session.status()
        assert status["application_connected"] is True
        assert status["system_connected"] is True

        result = session.dispatch("get_system")
        assert result["surfaces"][1]["is_stop"] is True
        assert backend.operations[-1][0] == "get_system"
        assert backend.operations[-1][2] != threading.get_ident()
    finally:
        session.close()
