from __future__ import annotations

from pathlib import Path

import pytest

from zemax_mcp.zos.subsystems.glass import GlassOperations, parse_agf

pytestmark = pytest.mark.live_zemax


def _installed_ops() -> GlassOperations:
    ops = GlassOperations()
    if not ops.get_glass_catalogs()["catalogs"]:
        pytest.skip("no installed OpticStudio Glasscat AGF files were found")
    return ops


def test_live_glasscat_bounded_read() -> None:
    """Read one installed catalog and a bounded record subset without ZOS-API writes."""
    ops = _installed_ops()
    listing = ops.get_glass_catalogs()
    preferred = next(
        (name for name in listing["catalogs"] if name.casefold() == "schott"),
        listing["catalogs"][0],
    )
    detail = next(item for item in listing["details"] if item["name"] == preferred)
    records = parse_agf(Path(detail["path"]), catalog=preferred)[:25]
    assert records
    assert all(record.name and record.catalog == preferred for record in records)
    assert any(record.nd is not None and record.vd is not None for record in records)


def test_live_glass_filter_bounded_result() -> None:
    ops = _installed_ops()
    listing = ops.get_glass_catalogs()
    catalog = next(
        (name for name in listing["catalogs"] if name.casefold() == "schott"),
        listing["catalogs"][0],
    )
    result = ops.filter_glasses(catalog, distance_radius=0.05, preferred_only=True)
    assert result["count"] <= len(ops.get_glasses(catalog)["glasses"])
    assert all(item["preferred"] and item["distance"] <= 0.05 for item in result["glasses"])
