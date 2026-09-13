"""Exception hierarchy for the Zemax runtime layer."""

from __future__ import annotations


class ZemaxError(Exception):
    """Base class for all package-specific errors."""


class ConfigurationError(ZemaxError):
    """Raised when runtime configuration is invalid."""


class DiscoveryError(ZemaxError):
    """Raised when a usable ZOS-API installation cannot be found."""


class LoaderError(ZemaxError):
    """Raised when pythonnet or the ZOS-API assemblies cannot be loaded."""


class WorkerError(ZemaxError):
    """Raised when the dedicated ZOS worker cannot execute a request."""


class SessionError(ZemaxError):
    """Base class for session lifecycle failures."""


class SessionClosedError(SessionError):
    """Raised when an operation is attempted on a closed session."""


class ConnectionError(SessionError):
    """Raised when OpticStudio cannot be connected or launched."""


class BackendError(ZemaxError):
    """Raised when a backend operation fails."""

    def __init__(self, operation: str, message: str) -> None:
        self.operation = operation
        self.message = message
        super().__init__(f"{operation}: {message}")


class UnsupportedOperationError(BackendError, NotImplementedError):
    """Raised for ZOS-API operations that are not implemented safely."""

    def __init__(self, operation: str, detail: str | None = None) -> None:
        message = detail or "operation is not implemented by this backend"
        super().__init__(operation, message)


class InvalidHandleError(BackendError, KeyError):
    """Raised when a runtime object handle is absent or has expired."""

    def __init__(self, handle: str) -> None:
        self.handle = handle
        BackendError.__init__(self, "resolve_handle", f"unknown handle {handle!r}")
