from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from zemax_mcp.errors import BackendError, UnsupportedOperationError
from zemax_mcp.zos.adapters.analysis_runner import AnalysisRunner
from zemax_mcp.zos.subsystems.analysis import build_operation_map


class Array2D:
    def __init__(self, rows: list[list[float]]) -> None:
        self.rows = rows

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter([value for row in self.rows for value in row])

    def GetLength(self, dimension: int) -> int:
        return len(self.rows) if dimension == 0 else len(self.rows[0])


class Closeable:
    def __init__(self) -> None:
        self.closed = 0

    def Close(self) -> None:
        self.closed += 1


class Selector:
    def __init__(self) -> None:
        self.number: int | None = None
        self.all = False

    def SetFieldNumber(self, number: int) -> None:
        self.number = number

    def SetWavelengthNumber(self, number: int) -> None:
        self.number = number

    def UseAllFields(self) -> None:
        self.all = True

    def UseAllWavelengths(self) -> None:
        self.all = True


class Settings(Closeable):
    def __init__(self) -> None:
        super().__init__()
        self.Field = Selector()
        self.Wavelength = Selector()
        self.MaximumFrequency = 0.0
        self.SampleSize: Any = None
        self.Rings = 0
        self.RayDensity = 0


class DataSeries:
    def __init__(self, count: int = 10) -> None:
        self.Description = "series"
        self.XData = SimpleNamespace(Data=list(range(count)))
        self.YData = SimpleNamespace(
            Data=Array2D([[float(index), float(index + 100)] for index in range(count)])
        )


class DataGrid:
    def __init__(self, rows: int = 4, columns: int = 5) -> None:
        self.Values = Array2D(
            [[float(row * columns + column) for column in range(columns)] for row in range(rows)]
        )
        self.MinX = -1.0
        self.MinY = -2.0
        self.Dx = 0.5
        self.Dy = 1.0


class SpotData:
    def GetRMSSpotSizeFor(self, field: int, wavelength: int) -> float:
        return float(field * 10 + wavelength)

    def GetGeoSpotSizeFor(self, field: int, wavelength: int) -> float:
        return float(field * 20 + wavelength)


class Results(Closeable):
    def __init__(self, *, series_count: int = 1, grid_count: int = 1) -> None:
        super().__init__()
        self.NumberOfDataSeries = series_count
        self.NumberOfDataGrids = grid_count
        self.SpotData = SpotData()

    def GetDataSeries(self, _index: int) -> DataSeries:
        return DataSeries()

    def GetDataGrid(self, _index: int) -> DataGrid:
        return DataGrid()


class AnalysisWindow(Closeable):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.settings = Settings()
        self.results = Results()
        self.fail = fail
        self.applied = False

    def GetSettings(self) -> Settings:
        return self.settings

    def ApplyAndWaitForCompletion(self) -> None:
        self.applied = True
        if self.fail:
            raise RuntimeError("analysis failed")

    def GetResults(self) -> Results:
        return self.results


class Analyses:
    def __init__(self) -> None:
        self.windows: list[AnalysisWindow] = []
        self.fail = False

    def _new(self) -> AnalysisWindow:
        window = AnalysisWindow(fail=self.fail)
        self.windows.append(window)
        return window

    def New_Analysis(self, _analysis_id: Any) -> AnalysisWindow:
        return self._new()

    def New_StandardSpot(self) -> AnalysisWindow:
        return self._new()

    def New_FftMtf(self) -> AnalysisWindow:
        return self._new()


class RayData(Closeable):
    def __init__(self, capacity: int) -> None:
        super().__init__()
        self.capacity = capacity
        self.rays: list[tuple[Any, ...]] = []
        self.index = 0

    def AddRay(self, *ray: Any) -> None:
        self.rays.append(ray)

    def StartReadingResults(self) -> None:
        self.index = 0

    def ReadNextResult(self) -> tuple[Any, ...]:
        if self.index >= len(self.rays):
            return (False,)
        number = self.index + 1
        ray = self.rays[self.index]
        self.index += 1
        return (
            True,
            number,
            0,
            0,
            ray[1] + ray[3],
            ray[2] + ray[4],
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            1.0,
            0.0,
            1.0,
        )


class RayTool(Closeable):
    def __init__(self) -> None:
        super().__init__()
        self.data: RayData | None = None
        self.ran = False

    def CreateNormUnpol(self, capacity: int, _ray_type: Any, _surface: int) -> RayData:
        self.data = RayData(capacity)
        return self.data

    def RunAndWaitForCompletion(self) -> None:
        self.ran = True


class Tools:
    def __init__(self) -> None:
        self.opened: list[RayTool] = []

    def OpenBatchRayTrace(self) -> RayTool:
        tool = RayTool()
        self.opened.append(tool)
        return tool


class System:
    def __init__(self) -> None:
        self.Analyses = Analyses()
        self.Tools = Tools()
        self.LDE = SimpleNamespace(NumberOfSurfaces=5)
        self.SystemData = SimpleNamespace(
            Fields=SimpleNamespace(NumberOfFields=2),
            Wavelengths=SimpleNamespace(NumberOfWavelengths=2),
        )


@pytest.fixture
def environment() -> tuple[System, Any, dict[str, Any]]:
    system = System()
    api = SimpleNamespace(
        Analysis=SimpleNamespace(
            AnalysisIDM=SimpleNamespace(
                CardinalPoints="CARDINAL",
                DiffractionEncircledEnergy="DEE",
                FftMtf="FFT",
                FftMtfvsField="FFTFIELD",
                FftPsf="FFTPSF",
                FieldCurvatureAndDistortion="FCD",
                FocalShiftDiagram="FOCAL",
                GeometricEncircledEnergy="GEE",
                GeometricImageAnalysis="GIA",
                GeometricMtf="GMTF",
                GeometricMtfvsField="GMTFFIELD",
                HuygensPsf="HPSF",
                LateralColor="LAT",
                LongitudinalAberration="LONG",
                OpticalPathFan="OPD",
                PhysicalOpticsPropagation="POP",
                PupilAberrationFan="PUPIL",
                RayFan="RAY",
                RelativeIllumination="RI",
                SeidelCoefficients="SEIDEL",
                StandardSpot="SPOT",
            ),
            SampleSizes=SimpleNamespace(
                S_32x32="32",
                S_64x64="64",
                S_128x128="128",
                S_256x256="256",
                S_512x512="512",
                S_1024x1024="1024",
            ),
        ),
        Tools=SimpleNamespace(
            RayTrace=SimpleNamespace(
                RaysType=SimpleNamespace(Real="REAL", Paraxial="PARAXIAL"),
                OPDMode=SimpleNamespace(None_="NONE"),
            )
        ),
    )
    operations = build_operation_map(lambda: system, lambda: api)
    return system, api, operations


def test_operation_map_exposes_analysis_handlers(
    environment: tuple[System, Any, dict[str, Any]],
) -> None:
    _system, _api, operations = environment
    assert set(operations) == {
        "analysis_series",
        "batch_ray_trace",
        "cardinal_points",
        "chromatic_focal_shift",
        "diffraction_encircled_energy",
        "export_analysis",
        "fft_mtf",
        "fft_mtf_vs_field",
        "fft_psf",
        "field_curvature_distortion",
        "geometric_encircled_energy",
        "geometric_image_analysis",
        "geometric_mtf",
        "geometric_mtf_vs_field",
        "huygens_mtf",
        "huygens_psf",
        "lateral_color",
        "longitudinal_aberration",
        "opd_fan",
        "pop",
        "pupil_aberration_fan",
        "ray_fan",
        "relative_illumination",
        "run_analysis",
        "seidel_coefficients",
        "spot_diagram",
        "spot_rms",
    }


def test_runner_extracts_decimated_series_and_grid_and_closes_resources(
    environment: tuple[System, Any, dict[str, Any]],
) -> None:
    system, api, _operations = environment
    result = AnalysisRunner(system, api).run("RayFan", max_points=4)
    window = system.Analyses.windows[-1]

    assert result["series"][0]["x"] == [0, 3, 6, 9]
    assert result["series"][0]["y_columns"] == [
        [0.0, 3.0, 6.0, 9.0],
        [100.0, 103.0, 106.0, 109.0],
    ]
    assert result["series"][0]["decimated"] is True
    assert result["grids"][0]["shape"] == [4, 5]
    assert window.closed == window.settings.closed == window.results.closed == 1


def test_runner_closes_window_and_settings_when_analysis_fails(
    environment: tuple[System, Any, dict[str, Any]],
) -> None:
    system, api, _operations = environment
    system.Analyses.fail = True
    with pytest.raises(RuntimeError, match="analysis failed"):
        AnalysisRunner(system, api).run("RayFan")
    window = system.Analyses.windows[-1]
    assert window.closed == 1
    assert window.settings.closed == 1


def test_batch_ray_trace_validates_returns_rows_and_closes(
    environment: tuple[System, Any, dict[str, Any]],
) -> None:
    system, _api, operations = environment
    result = operations["batch_ray_trace"](
        rays=[[0.0, 0.2, 0.3, 0.4], [0.1, 0.5, -0.2, 0.1]],
        wavelength=1,
        ray_type="Paraxial",
        to_surface=-1,
    )
    tool = system.Tools.opened[-1]
    assert result["ray_count"] == 2
    assert result["to_surface"] == 4
    assert result["results"][0]["x"] == 0.3
    assert tool.closed == 1
    assert tool.data is not None and tool.data.closed == 1

    with pytest.raises(BackendError, match="exactly"):
        operations["batch_ray_trace"](rays=[[0.0, 0.0, 0.0]])
    with pytest.raises(BackendError, match=r"outside \[-1, 1\]"):
        operations["batch_ray_trace"](rays=[[0.0, 0.0, 2.0, 0.0]])


def test_fft_mtf_and_spot_diagram_configure_native_settings(
    environment: tuple[System, Any, dict[str, Any]],
) -> None:
    system, _api, operations = environment
    fft = operations["fft_mtf"](frequency=50.0, wavelength=0, sampling=4)
    fft_window = system.Analyses.windows[-1]
    assert fft["analysis_type"] == "FftMtf"
    assert fft_window.settings.MaximumFrequency == 50.0
    assert fft_window.settings.SampleSize == "256"
    assert fft_window.settings.Wavelength.all is True

    spot = operations["spot_diagram"](field=2, wavelength=1, rings=5)
    spot_window = system.Analyses.windows[-1]
    assert spot == {
        "analysis_type": "StandardSpot",
        "field": 2,
        "wavelength": 1,
        "rings": 5,
        "spots": [{"field": 2, "wavelength": 1, "rms_radius": 21.0, "geometric_radius": 41.0}],
    }
    assert spot_window.settings.Field.number == 2
    assert spot_window.settings.Wavelength.number == 1
    assert spot_window.settings.Rings == 5
    assert spot_window.closed == spot_window.settings.closed == spot_window.results.closed == 1


def test_spot_rms_returns_all_pairs_and_closes(
    environment: tuple[System, Any, dict[str, Any]],
) -> None:
    system, _api, operations = environment
    result = operations["spot_rms"]()
    window = system.Analyses.windows[-1]
    assert result == {
        "field_count": 2,
        "wavelength_count": 2,
        "spots": [
            {"field": 1, "wavelength": 1, "rms_radius": 11.0, "geometric_radius": 21.0},
            {"field": 1, "wavelength": 2, "rms_radius": 12.0, "geometric_radius": 22.0},
            {"field": 2, "wavelength": 1, "rms_radius": 21.0, "geometric_radius": 41.0},
            {"field": 2, "wavelength": 2, "rms_radius": 22.0, "geometric_radius": 42.0},
        ],
    }
    assert window.closed == window.settings.closed == window.results.closed == 1


def test_generic_analysis_is_allowlisted_and_series_output_is_bounded(
    environment: tuple[System, Any, dict[str, Any]],
) -> None:
    _system, _api, operations = environment
    result = operations["analysis_series"](analysis_type="rayfan", max_points=3)
    assert result["analysis_type"] == "RayFan"
    assert result["series"][0]["point_count"] == 3

    with pytest.raises(UnsupportedOperationError, match="must be one of"):
        operations["run_analysis"](analysis_type="ShadedModel")
    with pytest.raises(BackendError, match="max_points"):
        operations["analysis_series"](analysis_type="RayFan", max_points=10_000)


def test_advanced_series_handlers_are_explicit_and_close(
    environment: tuple[System, Any, dict[str, Any]],
) -> None:
    system, _api, operations = environment
    for operation, expected in (
        ("chromatic_focal_shift", "FocalShiftDiagram"),
        ("lateral_color", "LateralColor"),
        ("longitudinal_aberration", "LongitudinalAberration"),
        ("opd_fan", "OpticalPathFan"),
        ("pupil_aberration_fan", "PupilAberrationFan"),
        ("relative_illumination", "RelativeIllumination"),
    ):
        result = operations[operation]()
        window = system.Analyses.windows[-1]
        assert result["analysis_type"] == expected
        assert window.closed == window.settings.closed == window.results.closed == 1


def test_mtf_frequency_validation_and_export_json(
    environment: tuple[System, Any, dict[str, Any]], tmp_path: Any
) -> None:
    _system, _api, operations = environment
    with pytest.raises(BackendError, match="positive frequency"):
        operations["fft_mtf_vs_field"]()
    with pytest.raises(BackendError, match=r"1\.\.1000"):
        operations["geometric_image_analysis"](rays_x1000=1001)

    path = tmp_path / "analysis.json"
    result = operations["export_analysis"](
        analysis_type="RayFan", file_path=str(path), format="json"
    )
    assert result["format"] == "json"
    assert path.is_file()
