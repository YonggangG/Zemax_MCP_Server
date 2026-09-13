from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.live_zemax


def _require_live_opt_in() -> None:
    if os.environ.get("ZEMAX_MCP_LIVE", "").casefold() not in {"1", "true", "yes"}:
        pytest.skip("set ZEMAX_MCP_LIVE=1 to run licensed OpticStudio integration tests")


def test_live_connect_status_disconnect_placeholder() -> None:
    """Opt-in smoke test; no license is consumed in ordinary test runs."""

    _require_live_opt_in()
    from zemax_mcp.zos.session import ZOSSession

    with ZOSSession() as session:
        metadata = session.connect()
        assert session.connected
        assert metadata
        status = session.status()
        assert status["connected"] is True


def test_live_read_only_system_snapshot_placeholder() -> None:
    """Opt-in read-only test intentionally avoids modifying user lens files."""

    _require_live_opt_in()
    from zemax_mcp.zos.session import ZOSSession

    with ZOSSession() as session:
        snapshot = session.dispatch("get_system")
        assert isinstance(snapshot, dict)


def test_live_plano_xdat_and_standard_spot_on_disposable_system() -> None:
    """Bounded regression checks on a fresh standalone sequential system."""

    _require_live_opt_in()
    from zemax_mcp.zos.session import ZOSSession

    with ZOSSession() as session:
        session.dispatch("new_system", sequential=True)
        session.dispatch("lde_insert_surface", position=1)

        session.dispatch("set_surface", surface_number=1, radius=1e20, thickness=1.0)
        plano = session.dispatch("get_surface", surface_number=1)
        assert plano["radius"] == 1e20
        assert isinstance(plano["radius"], float)

        session.dispatch("set_surface_type", surface_number=1, surface_type="Data")
        changed = session.dispatch(
            "set_extra_data",
            surface_number=1,
            values=[{"parameter": 1, "value": 2.5}, {"parameter": 2, "value": -1.0}],
        )
        assert changed["values"] == {"1": 2.5, "2": -1.0}
        assert session.dispatch(
            "get_extra_data", surface_number=1, start_parameter=1, end_parameter=2
        )["values"] == {"1": 2.5, "2": -1.0}

        spot = session.dispatch("spot_diagram", field=1, wavelength=1, rings=1)
        assert len(spot["spots"]) == 1
        assert isinstance(spot["spots"][0]["rms_radius"], float)
        assert isinstance(spot["spots"][0]["geometric_radius"], float)


def _disposable_double_gauss(tmp_path: Path) -> Path:
    zemax_root = Path.home() / "Documents" / "Zemax"
    source = (
        zemax_root / "Samples" / "Sequential" / "Objectives" / ("Double Gauss 28 degree field.zos")
    )
    if not source.is_file():
        pytest.skip(f"installed Double Gauss sample is unavailable: {source}")
    target = tmp_path / source.name
    shutil.copy2(source, target)
    return target


def test_live_nsc_operations_on_disposable_system() -> None:
    """Opt-in NSC smoke test using only a fresh, unsaved disposable system."""

    _require_live_opt_in()
    from zemax_mcp.zos.session import ZOSSession

    with ZOSSession() as session:
        created = session.dispatch("new_system", sequential=False)
        assert "NonSequential" in str(created["mode"])
        summary = session.dispatch("nsc_summary")
        assert summary["number_of_objects"] >= 1

        source = session.dispatch("nsc_set_object", object_number=1, object_type="SourcePoint")
        source_number = source["object_number"]
        session.dispatch(
            "nsc_set_object_parameter",
            object_number=source_number,
            parameter=2,
            value=10,
        )
        detector = session.dispatch(
            "nsc_add_object", object_type="DetectorRectangle", comment="live disposable detector"
        )
        detector_number = detector["object_number"]
        session.dispatch(
            "nsc_set_object",
            object_number=detector_number,
            z_position=10.0,
            material="ABSORB",
        )
        session.dispatch(
            "nsc_set_object_parameter",
            object_number=detector_number,
            parameter=3,
            value=4,
        )
        session.dispatch(
            "nsc_set_object_parameter",
            object_number=detector_number,
            parameter=4,
            value=4,
        )
        session.dispatch("nsc_clear_detectors", object_number=0)
        trace = session.dispatch(
            "nsc_ray_trace",
            split=False,
            scatter=False,
            clear_detectors=True,
            rays=10,
            use_polarization=False,
            ignore_errors=True,
        )
        assert trace["completed"] is True
        assert trace["ray_count_limit"] == 10
        pixel = session.dispatch(
            "nsc_detector_pixel", object_number=detector_number, pixel=0, data_type=1
        )
        assert isinstance(pixel["value"], float)
        data = session.dispatch(
            "nsc_detector_data",
            object_number=detector_number,
            data_type=1,
            max_values=16,
        )
        assert data["returned_values"] <= 16
        assert data["total_values"] >= data["returned_values"]

        inserted = session.dispatch("nsc_insert_object", object_number=2)
        assert inserted["object_number"] == 2
        assert session.dispatch("nsc_remove_object", object_number=2)["removed"] is True
        converted = session.dispatch("nsc_convert_to_sequential")
        assert "Sequential" in str(converted["mode"])
        back = session.dispatch("nsc_convert_to_nonsequential")
        assert "NonSequential" in str(back["mode"])


def test_live_native_optimization_tools_on_disposable_copy(tmp_path: Path) -> None:
    """Opt-in native-tool smoke test with millisecond time limits."""

    _require_live_opt_in()
    from zemax_mcp.zos.session import ZOSSession

    lens = _disposable_double_gauss(tmp_path)
    with ZOSSession() as session:
        session.dispatch("open_file", file_path=str(lens))
        variables = session.dispatch("get_variables")
        assert isinstance(variables["variables"], list)
        focus = session.dispatch("quick_focus")
        assert focus["succeeded"] is True
        local = session.dispatch("optimize", cycles=1, cores=1)
        assert local["cycles"] == "Fixed_1_Cycle"
        global_result = session.dispatch(
            "global_search", solutions_to_save=10, timeout_seconds=0.01, cores=1
        )
        assert global_result["timeout_seconds"] == 0.01
        hammer_result = session.dispatch(
            "hammer", timeout_seconds=0.01, target_runtime_minutes=0.01, cores=1
        )
        assert hammer_result["timeout_seconds"] == 0.01


def test_live_advanced_analyses_on_disposable_copy(tmp_path: Path) -> None:
    """Opt-in bounded read-only analyses against a copied sequential sample."""

    _require_live_opt_in()
    from zemax_mcp.zos.session import ZOSSession

    lens = _disposable_double_gauss(tmp_path)
    with ZOSSession() as session:
        session.dispatch("open_file", file_path=str(lens))
        for operation in (
            "cardinal_points",
            "chromatic_focal_shift",
            "lateral_color",
            "longitudinal_aberration",
            "seidel_coefficients",
            "field_curvature_distortion",
            "relative_illumination",
            "opd_fan",
            "pupil_aberration_fan",
        ):
            result = session.dispatch(operation)
            assert result["analysis_type"]
            assert result.get("series") or result.get("header") or result.get("text")
        for operation, parameters in (
            ("fft_mtf_vs_field", {"frequency1": 10.0, "sampling": 1}),
            ("geometric_mtf", {"max_frequency": 10.0}),
            ("geometric_mtf_vs_field", {"frequency1": 10.0}),
            ("diffraction_encircled_energy", {"sampling": 1}),
            ("geometric_encircled_energy", {"sampling": 1}),
        ):
            result = session.dispatch(operation, **parameters)
            assert result["series"]
        for operation, parameters in (
            ("fft_psf", {"sampling": 1, "image_sampling": 1}),
            ("huygens_psf", {"pupil_sampling": 1, "image_sampling": 1}),
            ("geometric_image_analysis", {"rays_x1000": 1}),
            ("pop", {"start_surface": 1, "end_surface": 10, "sampling_x": 32, "sampling_y": 32}),
        ):
            result = session.dispatch(operation, **parameters)
            assert result.get("grids") or result.get("text")
        exported = session.dispatch(
            "export_analysis",
            analysis_type="RayFan",
            file_path=str(tmp_path / "ray_fan.json"),
            format="json",
        )
        assert Path(exported["path"]).is_file()


def test_live_tolerancing_on_disposable_copy(tmp_path: Path) -> None:
    """Opt-in tolerance wizard and one-run bounded tolerancing smoke test."""

    _require_live_opt_in()
    from zemax_mcp.zos.session import ZOSSession

    lens = _disposable_double_gauss(tmp_path)
    with ZOSSession() as session:
        session.dispatch("open_file", file_path=str(lens))
        wizard = session.dispatch("tolerance_wizard")
        assert wizard["wizard_applied"] is True
        summary = session.dispatch("tde_summary")
        assert summary["number_of_operands"] > 0
        run = session.dispatch("run_tolerancing", monte_carlo_runs=1, timeout_seconds=0.05)
        assert run["monte_carlo_runs"] == 1
