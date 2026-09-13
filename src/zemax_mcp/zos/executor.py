"""Single-thread executor used to isolate all CLR/ZOS object access."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from queue import Queue
from threading import Event, Lock, Thread, get_ident
from typing import Any, Generic, TypeVar, cast

from zemax_mcp.errors import WorkerError
from zemax_mcp.logging_config import get_logger

T = TypeVar("T")
_STOP = object()


@dataclass(slots=True)
class _WorkItem(Generic[T]):
    function: Callable[..., T]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    future: Future[T]


class ZOSExecutor:
    """A deterministic executor with exactly one dedicated daemon thread."""

    def __init__(self, *, name: str = "zemax-zos-worker") -> None:
        self._name = name
        self._queue: Queue[_WorkItem[Any] | object] = Queue()
        self._thread: Thread | None = None
        self._start_lock = Lock()
        self._started = Event()
        self._closed = False
        self._thread_id: int | None = None
        self._logger = get_logger("zos.executor")

    @property
    def thread_id(self) -> int | None:
        return self._thread_id

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive() and not self._closed

    def start(self) -> None:
        with self._start_lock:
            if self._closed:
                raise WorkerError("cannot start a closed ZOS executor")
            if self._thread is not None:
                return
            self._thread = Thread(target=self._run, name=self._name, daemon=True)
            self._thread.start()
        if not self._started.wait(timeout=10):
            raise WorkerError("ZOS worker thread did not start")

    def submit(self, function: Callable[..., T], /, *args: Any, **kwargs: Any) -> Future[T]:
        if self._closed:
            raise WorkerError("ZOS executor is closed")
        self.start()
        if get_ident() == self._thread_id:
            future: Future[T] = Future()
            try:
                future.set_result(function(*args, **kwargs))
            except BaseException as exc:
                future.set_exception(exc)
            return future
        future = Future()
        self._queue.put(_WorkItem(function, args, kwargs, future))
        return future

    def call(self, function: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
        """Run a callable on the worker and synchronously return its result."""
        return self.submit(function, *args, **kwargs).result()

    def shutdown(self, *, wait: bool = True) -> None:
        with self._start_lock:
            if self._closed:
                return
            self._closed = True
            thread = self._thread
            if thread is not None:
                self._queue.put(_STOP)
        if wait and thread is not None and get_ident() != self._thread_id:
            thread.join()

    def _run(self) -> None:
        self._thread_id = get_ident()
        self._started.set()
        while True:
            item = self._queue.get()
            if item is _STOP:
                break
            work = cast(_WorkItem[Any], item)
            if not work.future.set_running_or_notify_cancel():
                continue
            try:
                result = work.function(*work.args, **work.kwargs)
            except BaseException as exc:
                work.future.set_exception(exc)
            else:
                work.future.set_result(result)
        self._logger.debug("ZOS worker stopped")

    def __enter__(self) -> ZOSExecutor:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.shutdown()
