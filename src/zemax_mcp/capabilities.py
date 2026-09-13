"""Derived production capability and live-evidence declarations.

This module is the single source for claims about what the real backend can execute
and what has actually been exercised against OpticStudio. Catalog registration alone
is deliberately not treated as implementation evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .zos.real_backend import production_operation_names

CapabilityStatus = Literal["production", "scaffolded", "unsupported"]
EvidenceStatus = Literal["live-verified", "offline-only", "none"]

# Operations with explicit production paths. Lifecycle operations are implemented by
# the wrapper/session; the remaining operations are explicit RealZOSBackend handlers.
PRODUCTION_LIFECYCLE_OPERATIONS = frozenset({"connect", "disconnect", "restart", "status"})
# Importing the backend and subsystem operation maps is CLR-free. This derives the
# production handler inventory from the actual dispatcher composition rather than a
# second hand-maintained list.
PRODUCTION_BACKEND_OPERATIONS = production_operation_names() - {"status"}
PRODUCTION_HANDLER_OPERATIONS = PRODUCTION_LIFECYCLE_OPERATIONS | PRODUCTION_BACKEND_OPERATIONS

UNSUPPORTED_TOOLS: dict[str, str] = {
    "zemax_eval": (
        "Arbitrary backend evaluation is intentionally unsupported; the production backend "
        "only exposes explicit, reviewed ZOS-API operations."
    )
}

SCAFFOLDED_REASONS: dict[str, str] = {
    "zemax_set_variable_constraints": (
        "OpticStudio 2025 R1.01 exposes variable solves but no public ZOS-API method for "
        "per-variable hard bounds. Native optimization must use merit-function boundary "
        "operands instead, so this mutating compatibility tool is not emulated."
    ),
    "zemax_constrained_optimize": (
        "No existing pure bound-constrained optimizer service is present in this codebase, "
        "and the installed ZOS-API exposes only native local/global/Hammer tools. A numerical "
        "optimizer was not invented without a verified variable-vector and rollback contract."
    ),
    "zemax_multistart_optimize": (
        "No existing pure multistart service is present; safely implementing it requires the "
        "same verified variable-vector, hard-bound, cancellation, and rollback contracts as "
        "the constrained optimizer."
    ),
    "zemax_multistart_status": (
        "Multistart execution is intentionally not started, so there is no truthful background "
        "job state to report."
    ),
    "zemax_multistart_stop": (
        "Multistart execution is intentionally not started, so there is no background job to stop."
    ),
}


@dataclass(frozen=True, slots=True)
class LiveEvidenceRecord:
    """A checked-in record supporting per-tool live-verification claims."""

    identifier: str
    tested_on: str
    tools: frozenset[str]
    environment: dict[str, str]
    report_path: str
    artifact_path: str

    def as_manifest_entry(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "testedOn": self.tested_on,
            "tools": sorted(self.tools),
            "environment": dict(sorted(self.environment.items())),
            "reportPath": self.report_path,
            "artifactPath": self.artifact_path,
        }


LIVE_CORE_EVIDENCE = LiveEvidenceRecord(
    identifier="opticstudio-2025-r1.01-stdio-core-2026-09-12",
    tested_on="2026-09-12",
    tools=frozenset(
        {
            "zemax_add_surface",
            "zemax_connect",
            "zemax_disconnect",
            "zemax_get_surface",
            "zemax_get_system",
            "zemax_new_system",
            "zemax_open_file",
            "zemax_ray_trace",
            "zemax_restart",
            "zemax_rms_spot",
            "zemax_save_file",
            "zemax_set_surface",
            "zemax_status",
        }
    ),
    environment={
        "client": "MCP Python high-level Client and Cherry Studio-exposed server",
        "connectionMode": "standalone",
        "mcpSdk": "2.2.0",
        "opticStudio": "Ansys Zemax OpticStudio 2025 R1.01",
        "os": "Windows 11 Pro x64",
        "python": "3.11.3 x64",
        "transport": "stdio",
    },
    report_path="live-test-report.md",
    artifact_path="live-output/mcp_stdio_core_results.json",
)

LIVE_BATCH1_EVIDENCE = LiveEvidenceRecord(
    identifier="opticstudio-2025-r1.01-stdio-batch1-2026-09-12",
    tested_on="2026-09-12",
    tools=frozenset(
        {
            "zemax_add_material_catalog",
            "zemax_close_file",
            "zemax_get_polarization",
            "zemax_get_system_units",
            "zemax_get_title_notes",
            "zemax_remove_material_catalog",
            "zemax_set_polarization",
            "zemax_set_system_units",
            "zemax_set_title_notes",
        }
    ),
    environment={
        "client": "MCP Python high-level Client",
        "connectionMode": "standalone",
        "mcpSdk": "2.2.0",
        "opticStudio": "Ansys Zemax OpticStudio 2025 R1.01",
        "os": "Windows 11 Pro x64",
        "python": "3.11.3 x64",
        "transport": "stdio",
    },
    report_path="live-test-report.md",
    artifact_path="live-output/batch1/mcp_stdio_batch1_results.json",
)

LIVE_BATCH2_EVIDENCE = LiveEvidenceRecord(
    identifier="opticstudio-2025-r1.01-stdio-batch2-2026-09-12",
    tested_on="2026-09-12",
    tools=frozenset({"zemax_scale_lens", "zemax_design_lockdown", "zemax_huygens_mtf"}),
    environment={
        "connectionMode": "standalone",
        "opticStudio": "Ansys Zemax OpticStudio 2025 R1.01",
        "transport": "stdio",
    },
    report_path="live-test-report.md",
    artifact_path="live-output/batch2/mcp_stdio_batch2_results.json",
)

LIVE_BATCH3_EVIDENCE = LiveEvidenceRecord(
    identifier="opticstudio-2025-r1.01-stdio-batch3-2026-09-12",
    tested_on="2026-09-12",
    tools=frozenset(
        {
            "zemax_nsc_get_source_spectrum",
            "zemax_nsc_set_source_spectrum",
            "zemax_nsc_save_detector",
            "zemax_nsc_load_detector",
            "zemax_nsc_polar_detector_data",
            "zemax_nsc_polar_detector_pixel",
            "zemax_nsc_detector_viewer",
        }
    ),
    environment={
        "connectionMode": "standalone",
        "opticStudio": "Ansys Zemax OpticStudio 2025 R1.01",
        "transport": "stdio",
    },
    report_path="live-test-report.md",
    artifact_path="live-output/batch3/mcp_stdio_batch3_results.json",
)

LIVE_BATCH4_EVIDENCE = LiveEvidenceRecord(
    identifier="opticstudio-2025-r1.01-stdio-batch4-2026-09-12",
    tested_on="2026-09-12",
    tools=frozenset({"zemax_zrd_summary", "zemax_zrd_read"}),
    environment={
        "connectionMode": "standalone",
        "opticStudio": "Ansys Zemax OpticStudio 2025 R1.01",
        "transport": "stdio",
    },
    report_path="live-test-report.md",
    artifact_path="live-output/batch4/mcp_stdio_batch4_results.json",
)

LIVE_EVIDENCE_RECORDS = (
    LIVE_CORE_EVIDENCE,
    LIVE_BATCH1_EVIDENCE,
    LIVE_BATCH2_EVIDENCE,
    LIVE_BATCH3_EVIDENCE,
    LIVE_BATCH4_EVIDENCE,
)


@dataclass(frozen=True, slots=True)
class ToolCapability:
    """Capability and evidence derived for one public tool."""

    capability_status: CapabilityStatus
    evidence_status: EvidenceStatus
    evidence: tuple[str, ...] = ()
    unsupported_reason: str | None = None


def evidence_ids_for_tool(name: str) -> tuple[str, ...]:
    """Return deterministic live-evidence identifiers for a public tool."""
    return tuple(record.identifier for record in LIVE_EVIDENCE_RECORDS if name in record.tools)


def derive_tool_capability(name: str, operation: str) -> ToolCapability:
    """Derive capability from production handlers and evidence from checked-in records."""
    unsupported_reason = UNSUPPORTED_TOOLS.get(name)
    if unsupported_reason is not None:
        return ToolCapability("unsupported", "none", unsupported_reason=unsupported_reason)
    evidence = evidence_ids_for_tool(name)
    scaffolded_reason = SCAFFOLDED_REASONS.get(name)
    if operation in PRODUCTION_HANDLER_OPERATIONS:
        return ToolCapability(
            "production",
            "live-verified" if evidence else "offline-only",
            evidence=evidence,
        )
    return ToolCapability(
        "scaffolded", "none", evidence=evidence, unsupported_reason=scaffolded_reason
    )


__all__ = [
    "LIVE_BATCH1_EVIDENCE",
    "LIVE_BATCH2_EVIDENCE",
    "LIVE_BATCH3_EVIDENCE",
    "LIVE_BATCH4_EVIDENCE",
    "LIVE_CORE_EVIDENCE",
    "LIVE_EVIDENCE_RECORDS",
    "PRODUCTION_BACKEND_OPERATIONS",
    "PRODUCTION_HANDLER_OPERATIONS",
    "PRODUCTION_LIFECYCLE_OPERATIONS",
    "SCAFFOLDED_REASONS",
    "UNSUPPORTED_TOOLS",
    "CapabilityStatus",
    "EvidenceStatus",
    "ToolCapability",
    "derive_tool_capability",
    "evidence_ids_for_tool",
]
