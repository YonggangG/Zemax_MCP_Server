from __future__ import annotations

from pathlib import Path

import pytest

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.subsystems.glass import GlassOperations, parse_agf

AGF = """CC small test catalog
NM N-BK7 2 517642.251 1.5168 64.17 0 1 1
GC preferred crown
ED 7.100000 8.300000 2.510000 -0.000900 0
CD 1 2 3 4 5 6
OD 1.0 1.0 0.0 1.0 2.3 2.3
LD 0.300 2.500
NM F2 2 620364.360 1.62004 36.37 0 2 4
GC inquiry flint
ED 8.200000 9.200000 3.599000 0.000200 0
CD 6 5 4 3 2 1
OD 1.2 1.0 0.0 1.0 2.3 1.3
LD 0.320 2.500
"""


def catalog(tmp_path: Path) -> Path:
    root = tmp_path / "Glasscat"
    root.mkdir()
    path = root / "SCHOTT.AGF"
    path.write_text(AGF, encoding="latin-1")
    return path


def test_parse_agf_extracts_stable_properties_and_preserves_records(tmp_path: Path) -> None:
    path = catalog(tmp_path)
    records = parse_agf(path)
    assert [record.name for record in records] == ["N-BK7", "F2"]
    assert records[0].nd == pytest.approx(1.5168)
    assert records[0].vd == pytest.approx(64.17)
    assert records[0].dpgf == pytest.approx(-0.0009)
    assert records[0].relative_cost == pytest.approx(1.0)
    assert records[0].preferred is True
    assert records[0].wavelength_min == pytest.approx(0.3)
    assert records[0].lines[0].startswith("NM N-BK7 ")


def test_catalog_listing_get_and_filters_are_bounded(tmp_path: Path) -> None:
    path = catalog(tmp_path)
    ops = GlassOperations([path.parent])
    listing = ops.get_glass_catalogs()
    assert listing["count"] == 1
    assert listing["catalogs"] == ["SCHOTT"]
    assert listing["details"][0]["name"] == "SCHOTT"

    glasses = ops.get_glasses("schott")
    assert glasses["count"] == 2
    preferred = ops.filter_glasses("SCHOTT", preferred_only=True)
    assert [item["name"] for item in preferred["glasses"]] == ["N-BK7"]
    nearby = ops.filter_glasses("SCHOTT", distance_radius=0.02)
    assert [item["name"] for item in nearby["glasses"]] == ["N-BK7"]
    covered = ops.filter_glasses(
        "SCHOTT", min_wavelength_coverage=0.31, max_wavelength_coverage=2.4
    )
    assert [item["name"] for item in covered["glasses"]] == ["N-BK7"]
    low_melt = ops.filter_glasses("SCHOTT", max_melt_frequency=2)
    assert [item["name"] for item in low_melt["glasses"]] == ["N-BK7"]


def test_export_preserves_selected_agf_block_outside_source(tmp_path: Path) -> None:
    path = catalog(tmp_path)
    ops = GlassOperations([path.parent])
    output = tmp_path / "live-output"
    result = ops.export_glass_catalog("CROWNS", "SCHOTT", str(output), preferred_only=True)
    exported = Path(result["path"])
    text = exported.read_text(encoding="latin-1")
    assert result["count"] == 1
    assert "NM N-BK7 " in text
    assert "CD 1 2 3 4 5 6" in text
    assert "NM F2 " not in text
    assert path.read_text(encoding="latin-1") == AGF
    with pytest.raises(BackendError, match="already exists"):
        ops.export_glass_catalog("CROWNS", "SCHOTT", str(output))


def test_export_rejects_installed_catalog_tree_and_unsafe_names(tmp_path: Path) -> None:
    path = catalog(tmp_path)
    ops = GlassOperations([path.parent])
    with pytest.raises(BackendError, match="outside installed Glasscat"):
        ops.export_glass_catalog("NEW", "SCHOTT", str(path.parent / "child"))
    with pytest.raises(BackendError, match="safe name"):
        ops.export_glass_catalog("../NEW", "SCHOTT", str(tmp_path / "output"))


def test_glass_operation_map_is_backend_compatible(tmp_path: Path) -> None:
    path = catalog(tmp_path)
    from zemax_mcp.zos.subsystems.glass import build_operation_map

    operations = build_operation_map([path.parent])
    assert set(operations) == {
        "get_glass_catalogs",
        "get_glasses",
        "filter_glasses",
        "export_glass_catalog",
    }
    assert operations["get_glasses"](catalogs="SCHOTT")["count"] == 2
