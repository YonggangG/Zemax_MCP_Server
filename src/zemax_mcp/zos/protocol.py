"""Pure-Python interfaces shared by real and test ZOS backends."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class ConnectionMode(StrEnum):
    """How a session obtains an OpticStudio application."""

    STANDALONE = "standalone"
    EXTENSION = "extension"

    @classmethod
    def coerce(cls, value: ConnectionMode | str) -> ConnectionMode:
        if isinstance(value, cls):
            return value
        return cls(value.strip().lower())


class ApplicationOwnership(StrEnum):
    """Whether this process is responsible for closing OpticStudio."""

    NONE = "none"
    OWNED = "owned"
    BORROWED = "borrowed"


JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


@runtime_checkable
class ZOSBackend(Protocol):
    """Backend contract; it deliberately contains no pythonnet types."""

    @property
    def connected(self) -> bool:
        """Whether an OpticStudio application connection is available."""
        ...

    @property
    def application_connected(self) -> bool:
        """Whether an OpticStudio application connection is available."""
        ...

    @property
    def system_connected(self) -> bool:
        """Whether a current optical system is available."""
        ...

    @property
    def ownership(self) -> ApplicationOwnership:
        """Current application ownership."""
        ...

    def connect(
        self,
        mode: ConnectionMode | str = ConnectionMode.STANDALONE,
        *,
        instance_id: int = 0,
    ) -> Mapping[str, Any]:
        """Connect to OpticStudio and return connection metadata."""
        ...

    def disconnect(
        self,
        *,
        close_application: bool | None = None,
        save: bool = False,
    ) -> Mapping[str, Any]:
        """Release the API connection and optionally save the current system."""
        ...

    def dispatch(self, operation: str, /, **params: Any) -> Any:
        """Execute a named backend operation."""
        ...
