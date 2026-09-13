"""Stable, CLR-free public contracts for the Zemax MCP surface."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

ImplementationStatus = Literal["scaffolded", "offline-implemented", "live-verified", "unsupported"]
CapabilityStatus = Literal["production", "scaffolded", "unsupported"]
EvidenceStatus = Literal["live-verified", "offline-only", "none"]


@runtime_checkable
class OperationSession(Protocol):
    """Minimum backend contract consumed by tool wrappers."""

    def connect(self, mode: str | None = None, *, instance_id: int | None = None) -> Any: ...

    def disconnect(self, *, save: bool = False) -> Any: ...

    def restart(self) -> Any: ...

    def status(self) -> Any: ...

    def dispatch(self, operation: str, **params: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One tool in the compatibility catalog."""

    name: str
    description: str
    category: str
    input_schema: Mapping[str, Any]
    operation: str | None = None
    provenance: tuple[str, ...] = ()
    implementation_status: ImplementationStatus = "scaffolded"
    capability_status: CapabilityStatus = "scaffolded"
    evidence_status: EvidenceStatus = "none"
    evidence: tuple[str, ...] = ()
    unsupported_reason: str | None = None
    aliases: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.startswith("zemax_"):
            raise ValueError(f"tool name must start with 'zemax_': {self.name}")
        if self.input_schema.get("type") != "object":
            raise ValueError(f"tool input schema must be an object: {self.name}")

    @property
    def dispatch_operation(self) -> str:
        return self.operation or self.name.removeprefix("zemax_")

    def as_manifest_entry(self) -> dict[str, Any]:
        entry = {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "operation": self.dispatch_operation,
            "inputSchema": dict(self.input_schema),
            "provenance": list(self.provenance),
            "implementationStatus": self.implementation_status,
            "capabilityStatus": self.capability_status,
            "evidenceStatus": self.evidence_status,
            "evidence": list(self.evidence),
            "aliases": list(self.aliases),
            "metadata": dict(self.metadata),
        }
        if self.unsupported_reason is not None:
            entry["unsupportedReason"] = self.unsupported_reason
        return entry
