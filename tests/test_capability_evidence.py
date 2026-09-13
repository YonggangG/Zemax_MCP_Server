from __future__ import annotations

import json
from pathlib import Path

from zemax_mcp.capabilities import (
    LIVE_BATCH1_EVIDENCE,
    LIVE_BATCH2_EVIDENCE,
    LIVE_BATCH3_EVIDENCE,
    LIVE_BATCH4_EVIDENCE,
    LIVE_CORE_EVIDENCE,
    PRODUCTION_BACKEND_OPERATIONS,
    PRODUCTION_HANDLER_OPERATIONS,
    PRODUCTION_LIFECYCLE_OPERATIONS,
)
from zemax_mcp.registry import TOOL_CATALOG, catalog_manifest, get_tool_spec
from zemax_mcp.reporting import check_capability_report, write_capability_report
from zemax_mcp.zos.real_backend import RealZOSBackend, production_operation_names

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_LIVE_BATCH1_TOOLS = {
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
EXPECTED_LIVE_BATCH2_TOOLS = set(LIVE_BATCH2_EVIDENCE.tools)
EXPECTED_LIVE_BATCH3_TOOLS = set(LIVE_BATCH3_EVIDENCE.tools)
EXPECTED_LIVE_BATCH4_TOOLS = set(LIVE_BATCH4_EVIDENCE.tools)
EXPECTED_LIVE_CORE_TOOLS = {
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


def test_capability_counts_are_derived_and_truthful() -> None:
    manifest = catalog_manifest()
    capabilities = manifest["capabilities"]
    evidence = manifest["evidence"]

    assert len(TOOL_CATALOG) == 143
    assert capabilities["productionHandlerCount"] == 131
    assert capabilities["scaffoldedRemainderCount"] == 11
    assert capabilities["unsupportedCount"] == 1
    all_live = (
        EXPECTED_LIVE_CORE_TOOLS
        | EXPECTED_LIVE_BATCH1_TOOLS
        | EXPECTED_LIVE_BATCH2_TOOLS
        | EXPECTED_LIVE_BATCH3_TOOLS
        | EXPECTED_LIVE_BATCH4_TOOLS
    )
    assert evidence["liveCoreRepresentativeCount"] == len(all_live)
    assert set(evidence["liveVerifiedTools"]) == all_live
    assert LIVE_CORE_EVIDENCE.tools == EXPECTED_LIVE_CORE_TOOLS
    assert LIVE_BATCH1_EVIDENCE.tools == EXPECTED_LIVE_BATCH1_TOOLS

    assert capabilities["productionHandlerCount"] == len(
        [spec for spec in TOOL_CATALOG if spec.capability_status == "production"]
    )
    assert capabilities["scaffoldedRemainderCount"] == len(
        [spec for spec in TOOL_CATALOG if spec.capability_status == "scaffolded"]
    )


def test_derived_handlers_match_real_backend_dispatch_composition() -> None:
    backend_operations = set(production_operation_names()) - {"status"}
    assert backend_operations == set(PRODUCTION_BACKEND_OPERATIONS)
    assert backend_operations | set(PRODUCTION_LIFECYCLE_OPERATIONS) == set(
        PRODUCTION_HANDLER_OPERATIONS
    )
    backend = RealZOSBackend()
    assert set(production_operation_names()) <= set(backend._operations)


def test_no_tool_claims_live_without_evidence_or_production_without_handler() -> None:
    all_live = (
        EXPECTED_LIVE_CORE_TOOLS
        | EXPECTED_LIVE_BATCH1_TOOLS
        | EXPECTED_LIVE_BATCH2_TOOLS
        | EXPECTED_LIVE_BATCH3_TOOLS
        | EXPECTED_LIVE_BATCH4_TOOLS
    )
    for spec in TOOL_CATALOG:
        if spec.evidence_status == "live-verified":
            assert spec.evidence
            assert spec.name in all_live
            assert spec.capability_status == "production"
        else:
            assert spec.name not in all_live
        if spec.capability_status == "production":
            assert spec.dispatch_operation in PRODUCTION_HANDLER_OPERATIONS
        if spec.capability_status == "scaffolded":
            assert spec.implementation_status == "scaffolded"
            assert spec.evidence_status == "none"


def test_eval_is_unsupported_and_never_advertised_live_or_offline_ready() -> None:
    spec = get_tool_spec("zemax_eval")
    assert spec.implementation_status == "unsupported"
    assert spec.capability_status == "unsupported"
    assert spec.evidence_status == "none"
    assert spec.unsupported_reason
    assert spec.dispatch_operation not in PRODUCTION_HANDLER_OPERATIONS


def test_checked_in_report_is_generated_from_source_and_checkable(tmp_path: Path) -> None:
    checked_in = ROOT / "tool-coverage.json"
    current, detail = check_capability_report(checked_in)
    assert current, detail

    generated = tmp_path / "coverage.json"
    write_capability_report(generated)
    assert json.loads(generated.read_text(encoding="utf-8")) == catalog_manifest()
    current, _ = check_capability_report(generated)
    assert current
    generated.write_text("{}\n", encoding="utf-8")
    current, detail = check_capability_report(generated)
    assert not current
    assert detail["reason"] == "stale"
