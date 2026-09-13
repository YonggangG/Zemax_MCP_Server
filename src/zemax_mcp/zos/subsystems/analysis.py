"""Sequential analysis operation handlers.

This subsystem is intentionally constructed from callables so importing it never
loads pythonnet and a backend can merge its operation map without circular imports.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from zemax_mcp.errors import BackendError, UnsupportedOperationError
from zemax_mcp.zos.adapters.analysis_runner import AnalysisRunner
from zemax_mcp.zos.interop import get_member, to_python

SystemProvider = Callable[[], Any]
ApiProvider = Callable[[], Any]
Operation = Callable[..., Any]

# Generic execution is deliberately limited to analyses whose results use the
# standard data-series/data-grid interfaces. More specialized result interfaces
# need explicit handlers and offline/live verification before being added.
_ANALYSIS_FACTORIES = {
    "CardinalPoints": None,
    "DiffractionEncircledEnergy": "New_DiffractionEncircledEnergy",
    "FftMtf": "New_FftMtf",
    "FftMtfvsField": "New_FftMtfvsField",
    "FftPsf": "New_FftPsf",
    "FieldCurvatureAndDistortion": "New_FieldCurvatureAndDistortion",
    "FocalShiftDiagram": "New_Analysis",
    "GeometricEncircledEnergy": "New_GeometricEncircledEnergy",
    "GeometricImageAnalysis": "New_GeometricImageAnalysis",
    "GeometricMtf": "New_GeometricMtf",
    "GeometricMtfvsField": "New_GeometricMtfvsField",
    "HuygensPsf": "New_HuygensPsf",
    "LateralColor": "New_LateralColor",
    "LongitudinalAberration": "New_LongitudinalAberration",
    "OpticalPathFan": "New_OpticalPathFan",
    "PhysicalOpticsPropagation": None,
    "PupilAberrationFan": "New_PupilAberrationFan",
    "RayFan": "New_RayFan",
    "RelativeIllumination": "New_RelativeIllumination",
    "SeidelCoefficients": "New_SeidelCoefficients",
    "StandardSpot": None,
}
_ALLOWED_ANALYSES = frozenset(_ANALYSIS_FACTORIES)

_RAY_RESULT_NAMES = (
    "success",
    "ray_number",
    "error_code",
    "vignette_code",
    "x",
    "y",
    "z",
    "l",
    "m",
    "n",
    "l2",
    "m2",
    "n2",
    "opd",
    "intensity",
)


class AnalysisSubsystem:
    """Bound handlers for sequential ray tracing and native analyses."""

    MAX_BATCH_RAYS = 10_000
    MAX_SPOT_FIELDS = 256
    MAX_SPOT_WAVELENGTHS = 256
    MAX_IMAGE_RAYS_X1000 = 1_000
    MAX_DENSITY = 1_000

    def __init__(self, require_system: SystemProvider, api: ApiProvider) -> None:
        self._require_system = require_system
        self._api = api

    def operation_map(self) -> dict[str, Operation]:
        return {
            "analysis_series": self.analysis_series,
            "batch_ray_trace": self.batch_ray_trace,
            "cardinal_points": self.cardinal_points,
            "chromatic_focal_shift": self.chromatic_focal_shift,
            "diffraction_encircled_energy": self.diffraction_encircled_energy,
            "export_analysis": self.export_analysis,
            "fft_mtf": self.fft_mtf,
            "fft_mtf_vs_field": self.fft_mtf_vs_field,
            "fft_psf": self.fft_psf,
            "field_curvature_distortion": self.field_curvature_distortion,
            "geometric_encircled_energy": self.geometric_encircled_energy,
            "geometric_image_analysis": self.geometric_image_analysis,
            "geometric_mtf": self.geometric_mtf,
            "geometric_mtf_vs_field": self.geometric_mtf_vs_field,
            "huygens_mtf": self.huygens_mtf,
            "huygens_psf": self.huygens_psf,
            "lateral_color": self.lateral_color,
            "longitudinal_aberration": self.longitudinal_aberration,
            "opd_fan": self.opd_fan,
            "pop": self.pop,
            "pupil_aberration_fan": self.pupil_aberration_fan,
            "ray_fan": self.ray_fan,
            "relative_illumination": self.relative_illumination,
            "run_analysis": self.run_analysis,
            "seidel_coefficients": self.seidel_coefficients,
            "spot_diagram": self.spot_diagram,
            "spot_rms": self.spot_rms,
        }

    def batch_ray_trace(
        self,
        *,
        rays: Sequence[Sequence[float]],
        wavelength: int = 1,
        ray_type: str = "Real",
        to_surface: int = -1,
    ) -> dict[str, Any]:
        """Trace a bounded list of normalized ``[Hx, Hy, Px, Py]`` rays."""

        if not isinstance(rays, Sequence) or isinstance(rays, (str, bytes)):
            raise BackendError("batch_ray_trace", "rays must be a sequence")
        if not rays:
            return {"ray_count": 0, "results": []}
        if len(rays) > self.MAX_BATCH_RAYS:
            raise BackendError(
                "batch_ray_trace", f"at most {self.MAX_BATCH_RAYS} rays may be traced"
            )
        normalized: list[tuple[float, float, float, float]] = []
        for index, ray in enumerate(rays):
            if not isinstance(ray, Sequence) or isinstance(ray, (str, bytes)) or len(ray) != 4:
                raise BackendError(
                    "batch_ray_trace", f"ray {index} must contain exactly [Hx, Hy, Px, Py]"
                )
            coordinates = (
                float(ray[0]),
                float(ray[1]),
                float(ray[2]),
                float(ray[3]),
            )
            if any(value < -1.0 or value > 1.0 for value in coordinates):
                raise BackendError(
                    "batch_ray_trace", f"ray {index} has normalized coordinates outside [-1, 1]"
                )
            normalized.append(coordinates)
        if isinstance(wavelength, bool) or wavelength < 1:
            raise BackendError("batch_ray_trace", "wavelength must be one-based")

        system = self._require_system()
        surface_count = int(getattr(get_member(system, "LDE"), "NumberOfSurfaces", 0))
        target_surface = surface_count - 1 if to_surface == -1 else int(to_surface)
        if not 0 <= target_surface < surface_count:
            raise BackendError(
                "batch_ray_trace", f"to_surface must be -1 or 0..{max(surface_count - 1, 0)}"
            )
        api = self._api()
        ray_namespace = get_member(get_member(api, "Tools"), "RayTrace")
        ray_types = get_member(ray_namespace, "RaysType")
        ray_type_name = ray_type.strip().lower()
        if ray_type_name not in {"real", "paraxial"}:
            raise BackendError("batch_ray_trace", "ray_type must be 'Real' or 'Paraxial'")
        selected_ray_type = get_member(ray_types, ray_type_name.title())
        opd_none = get_member(get_member(ray_namespace, "OPDMode"), "None", "None_")

        tool = None
        data = None
        try:
            tool = get_member(get_member(system, "Tools"), "OpenBatchRayTrace")()
            if tool is None:
                raise BackendError("batch_ray_trace", "batch ray trace tool is unavailable")
            data = get_member(tool, "CreateNormUnpol")(
                len(normalized), selected_ray_type, target_surface
            )
            if data is None:
                raise BackendError("batch_ray_trace", "normalized ray data is unavailable")
            for hx, hy, px, py in normalized:
                get_member(data, "AddRay")(wavelength, hx, hy, px, py, opd_none)
            get_member(tool, "RunAndWaitForCompletion")()
            get_member(data, "StartReadingResults")()
            rows: list[dict[str, Any]] = []
            for _ in normalized:
                raw = get_member(data, "ReadNextResult")()
                result_values = list(raw)
                if not result_values or not bool(result_values[0]):
                    break
                row = dict(zip(_RAY_RESULT_NAMES, result_values, strict=False))
                serialized = to_python(row)
                if not isinstance(serialized, dict):
                    raise BackendError("batch_ray_trace", "ray result is not a mapping")
                rows.append(serialized)
            return {
                "ray_count": len(rows),
                "requested_ray_count": len(normalized),
                "wavelength": wavelength,
                "ray_type": ray_type_name.title(),
                "to_surface": target_surface,
                "results": rows,
            }
        finally:
            AnalysisRunner.close_resources(data, tool)

    def fft_mtf(
        self,
        *,
        frequency: float,
        wavelength: int = 0,
        sampling: int = 3,
    ) -> dict[str, Any]:
        if frequency <= 0:
            raise BackendError("fft_mtf", "frequency must be positive")
        sample_enum = self._sample_size(sampling)

        def configure(settings: Any) -> None:
            settings.MaximumFrequency = float(frequency)
            settings.SampleSize = sample_enum
            self._set_selector(getattr(settings, "Wavelength", None), wavelength, "wavelength")

        return self._runner().run(
            "FftMtf", configure=configure, factory_name="New_FftMtf", include_grids=False
        )

    def huygens_mtf(
        self,
        *,
        maximum_frequency: float,
        field: int = 1,
        wavelength: int = 0,
        pupil_sampling: int = 3,
        image_sampling: int = 3,
        image_delta: float = 0.0,
        use_polarization: bool = False,
        use_dashes: bool = False,
        configuration: int = 1,
    ) -> dict[str, Any]:
        if maximum_frequency <= 0 or maximum_frequency > 100_000:
            raise BackendError("huygens_mtf", "maximum_frequency must be in (0, 100000]")
        if image_delta < 0:
            raise BackendError("huygens_mtf", "image_delta must be non-negative")
        if configuration < 1:
            raise BackendError("huygens_mtf", "configuration must be one-based")
        pupil_size = self._sample_size(pupil_sampling)
        image_size = self._sample_size(image_sampling)

        def configure(settings: Any) -> None:
            settings.MaximumFrequency = float(maximum_frequency)
            settings.PupilSampleSize = pupil_size
            settings.ImageSampleSize = image_size
            settings.ImageDelta = float(image_delta)
            settings.UsePolarization = bool(use_polarization)
            settings.UseDashes = bool(use_dashes)
            settings.Configuration = int(configuration)
            mtf_types = self._api().Analysis.Settings.Mtf.HuygensMtfTypes
            settings.Type = self._enum_member(mtf_types, "Modulation")
            self._set_selector(getattr(settings, "Field", None), field, "field")
            self._set_selector(getattr(settings, "Wavelength", None), wavelength, "wavelength")

        result = self._runner().run(
            "HuygensMtf",
            configure=configure,
            factory_name="New_HuygensMtf",
            include_grids=False,
        )
        result["settings"] = {
            "maximum_frequency": maximum_frequency,
            "field": field,
            "wavelength": wavelength,
            "pupil_sampling": pupil_sampling,
            "image_sampling": image_sampling,
            "image_delta": image_delta,
            "use_polarization": use_polarization,
            "use_dashes": use_dashes,
            "configuration": configuration,
        }
        return result

    def ray_fan(self) -> dict[str, Any]:
        return self._all_fields_waves("RayFan", "New_RayFan")

    def opd_fan(self) -> dict[str, Any]:
        return self._all_fields_waves("OpticalPathFan", "New_OpticalPathFan")

    def pupil_aberration_fan(self) -> dict[str, Any]:
        return self._all_fields_waves("PupilAberrationFan", "New_PupilAberrationFan")

    def cardinal_points(self, *, wavelength: int = 1) -> dict[str, Any]:
        if isinstance(wavelength, bool) or wavelength < 1:
            raise BackendError("cardinal_points", "wavelength must be one-based")
        original = self._primary_wavelength()
        self._set_primary_wavelength(wavelength)
        try:
            output = self._runner().run("CardinalPoints", include_series=True, include_grids=False)
        finally:
            self._set_primary_wavelength(original)
        output["wavelength"] = wavelength
        return output

    def chromatic_focal_shift(self) -> dict[str, Any]:
        return self._runner().run("FocalShiftDiagram", include_series=True, include_grids=False)

    def lateral_color(self) -> dict[str, Any]:
        def configure(settings: Any) -> None:
            if hasattr(settings, "AllWavelengths"):
                settings.AllWavelengths = True

        return self._runner().run(
            "LateralColor",
            configure=configure,
            factory_name="New_LateralColor",
            include_grids=False,
        )

    def longitudinal_aberration(self) -> dict[str, Any]:
        return self._runner().run(
            "LongitudinalAberration", factory_name="New_LongitudinalAberration", include_grids=False
        )

    def seidel_coefficients(self, *, wavelength: int = 0) -> dict[str, Any]:
        def configure(settings: Any) -> None:
            self._set_selector(getattr(settings, "Wavelength", None), wavelength, "wavelength")

        return self._runner().run(
            "SeidelCoefficients", configure=configure, factory_name="New_SeidelCoefficients"
        )

    def field_curvature_distortion(self, *, distortion_type: str = "f_tan_theta") -> dict[str, Any]:
        names = {"f_tan_theta": "F_TanTheta", "f_theta": "F_Theta"}
        try:
            enum_name = names[distortion_type.strip().lower()]
        except (AttributeError, KeyError) as exc:
            raise BackendError(
                "field_curvature_distortion", "distortion_type must be f_tan_theta or f_theta"
            ) from exc

        def configure(settings: Any) -> None:
            aberrations = get_member(get_member(self._api(), "Analysis"), "Settings")
            distortion_enum = get_member(get_member(aberrations, "Aberrations"), "Distortions")
            settings.Distortion = get_member(distortion_enum, enum_name)
            self._set_selector(getattr(settings, "Wavelength", None), 0, "wavelength")

        return self._runner().run(
            "FieldCurvatureAndDistortion",
            configure=configure,
            factory_name="New_FieldCurvatureAndDistortion",
            include_grids=False,
        )

    def relative_illumination(self) -> dict[str, Any]:
        def configure(settings: Any) -> None:
            self._set_selector(getattr(settings, "Wavelength", None), 0, "wavelength")
            if hasattr(settings, "RayDensity"):
                settings.RayDensity = min(max(int(settings.RayDensity), 1), self.MAX_DENSITY)
            if hasattr(settings, "FieldDensity"):
                settings.FieldDensity = min(max(int(settings.FieldDensity), 1), self.MAX_DENSITY)

        return self._runner().run(
            "RelativeIllumination",
            configure=configure,
            factory_name="New_RelativeIllumination",
            include_grids=False,
        )

    def spot_diagram(
        self, *, field: int = 1, wavelength: int = 0, rings: int = 3
    ) -> dict[str, Any]:
        """Run Standard Spot and extract its specialized ``SpotData`` matrix."""

        if isinstance(rings, bool) or not 1 <= rings <= 20:
            raise BackendError("spot_diagram", "rings must be 1..20")
        if isinstance(field, bool) or field < 1:
            raise BackendError("spot_diagram", "field must be one-based")
        if isinstance(wavelength, bool) or wavelength < 0:
            raise BackendError("spot_diagram", "wavelength must be zero or one-based")

        runner = self._runner()
        system = self._require_system()
        window = settings = results = None
        try:
            analyses = get_member(system, "Analyses")
            factory = getattr(analyses, "New_StandardSpot", None)
            window = (
                factory()
                if callable(factory)
                else get_member(analyses, "New_Analysis")(runner.analysis_id("StandardSpot"))
            )
            if window is None:
                raise BackendError("spot_diagram", "standard spot analysis is unavailable")
            settings = get_member(window, "GetSettings")()
            spot_settings = self._spot_settings(settings)
            self._set_selector(getattr(spot_settings, "Field", None), field, "field")
            self._set_selector(getattr(spot_settings, "Wavelength", None), wavelength, "wavelength")
            for name in ("Rings", "NumberOfRings", "RayDensity"):
                if hasattr(spot_settings, name):
                    setattr(spot_settings, name, rings)
                    break
            get_member(window, "ApplyAndWaitForCompletion")()
            results = get_member(window, "GetResults")()
            spot_data = getattr(results, "SpotData", None)
            if spot_data is None:
                raise BackendError("spot_diagram", "SpotData is unavailable")
            rms = get_member(spot_data, "GetRMSSpotSizeFor")
            geo = get_member(spot_data, "GetGeoSpotSizeFor")
            result_wave = wavelength if wavelength > 0 else 1
            spots = [
                {
                    "field": field,
                    "wavelength": wavelength,
                    "rms_radius": float(rms(field, result_wave)),
                    "geometric_radius": float(geo(field, result_wave)),
                }
            ]
            return {
                "analysis_type": "StandardSpot",
                "field": field,
                "wavelength": wavelength,
                "rings": rings,
                "spots": spots,
            }
        finally:
            AnalysisRunner.close_resources(results, settings, window)

    def spot_rms(self) -> dict[str, Any]:
        """Return RMS and geometric spot radii for every bounded field/wavelength pair."""

        runner = self._runner()
        system = self._require_system()
        window = settings = results = None
        try:
            analyses = get_member(system, "Analyses")
            factory = getattr(analyses, "New_StandardSpot", None)
            window = (
                factory()
                if callable(factory)
                else get_member(analyses, "New_Analysis")(runner.analysis_id("StandardSpot"))
            )
            if window is None:
                raise BackendError("spot_rms", "standard spot analysis is unavailable")
            settings = get_member(window, "GetSettings")()
            spot_settings = self._spot_settings(settings)
            self._set_selector(getattr(spot_settings, "Field", None), 0, "field")
            self._set_selector(getattr(spot_settings, "Wavelength", None), 0, "wavelength")
            get_member(window, "ApplyAndWaitForCompletion")()
            results = get_member(window, "GetResults")()
            spot_data = getattr(results, "SpotData", None)
            if spot_data is None:
                raise BackendError("spot_rms", "SpotData is unavailable")
            field_count = min(
                self._system_count(system, "Fields", "NumberOfFields"),
                self.MAX_SPOT_FIELDS,
            )
            wave_count = min(
                self._system_count(system, "Wavelengths", "NumberOfWavelengths"),
                self.MAX_SPOT_WAVELENGTHS,
            )
            rms = get_member(spot_data, "GetRMSSpotSizeFor")
            geo = get_member(spot_data, "GetGeoSpotSizeFor")
            rows = [
                {
                    "field": field,
                    "wavelength": wavelength,
                    "rms_radius": float(rms(field, wavelength)),
                    "geometric_radius": float(geo(field, wavelength)),
                }
                for field in range(1, field_count + 1)
                for wavelength in range(1, wave_count + 1)
            ]
            return {"field_count": field_count, "wavelength_count": wave_count, "spots": rows}
        finally:
            AnalysisRunner.close_resources(results, settings, window)

    def fft_mtf_vs_field(self, *, sampling: int = 3, **frequencies: float) -> dict[str, Any]:
        return self._mtf_vs_field("FftMtfvsField", "New_FftMtfvsField", sampling, frequencies)

    def geometric_mtf(
        self,
        *,
        max_frequency: float = 100.0,
        wavelength: int = 0,
        multiply_by_diffraction_limit: bool = False,
    ) -> dict[str, Any]:
        if not 0 < max_frequency <= 100_000:
            raise BackendError("geometric_mtf", "max_frequency must be in (0, 100000]")

        def configure(settings: Any) -> None:
            settings.MaximumFrequency = float(max_frequency)
            settings.SampleSize = self._sample_size(3)
            settings.MultiplyByDiffractionLimit = bool(multiply_by_diffraction_limit)
            self._set_selector(getattr(settings, "Wavelength", None), wavelength, "wavelength")
            self._set_selector(getattr(settings, "Field", None), 0, "field")

        return self._runner().run(
            "GeometricMtf",
            configure=configure,
            factory_name="New_GeometricMtf",
            include_grids=False,
        )

    def geometric_mtf_vs_field(self, **frequencies: float) -> dict[str, Any]:
        return self._mtf_vs_field("GeometricMtfvsField", "New_GeometricMtfvsField", 3, frequencies)

    def diffraction_encircled_energy(
        self, *, sampling: int = 3, use_dashes: bool = False
    ) -> dict[str, Any]:
        def configure(settings: Any) -> None:
            settings.SampleSize = self._sample_size(sampling)
            settings.UseDashes = bool(use_dashes)
            self._set_selector(getattr(settings, "Field", None), 0, "field")
            self._set_selector(getattr(settings, "Wavelength", None), 0, "wavelength")

        return self._runner().run(
            "DiffractionEncircledEnergy",
            configure=configure,
            factory_name="New_DiffractionEncircledEnergy",
            include_grids=False,
        )

    def geometric_encircled_energy(
        self,
        *,
        sampling: int = 3,
        show_diffraction_limit: bool = True,
        scale_by_diffraction_limit: bool = False,
        scatter_rays: bool = False,
        use_dashes: bool = False,
    ) -> dict[str, Any]:
        def configure(settings: Any) -> None:
            settings.SampleSize = self._sample_size(sampling)
            settings.ShowDiffractionLimit = bool(show_diffraction_limit)
            settings.ScatterRays = bool(scatter_rays)
            settings.UseDashes = bool(use_dashes)
            self._set_selector(getattr(settings, "Field", None), 0, "field")
            self._set_selector(getattr(settings, "Wavelength", None), 0, "wavelength")

        output = self._runner().run(
            "GeometricEncircledEnergy",
            configure=configure,
            factory_name="New_GeometricEncircledEnergy",
            include_grids=False,
        )
        output["scale_by_diffraction_limit"] = bool(scale_by_diffraction_limit)
        return output

    def fft_psf(
        self,
        *,
        field: int = 1,
        wavelength: int = 0,
        sampling: int = 3,
        image_sampling: int = 3,
    ) -> dict[str, Any]:
        def configure(settings: Any) -> None:
            psf = get_member(get_member(get_member(self._api(), "Analysis"), "Settings"), "Psf")
            psf_sampling = get_member(psf, "PsfSampling")
            sample_dimension = self._sampling_dimension(sampling)
            output_dimension = self._sampling_dimension(image_sampling)
            settings.SampleSize = get_member(
                psf_sampling, f"PsfS_{sample_dimension}x{sample_dimension}"
            )
            settings.OutputSize = get_member(
                psf_sampling, f"PsfS_{output_dimension}x{output_dimension}"
            )
            self._set_selector(getattr(settings, "Field", None), field, "field")
            self._set_selector(getattr(settings, "Wavelength", None), wavelength, "wavelength")

        return self._runner().run(
            "FftPsf", configure=configure, factory_name="New_FftPsf", include_series=False
        )

    def huygens_psf(
        self,
        *,
        field: int = 1,
        wavelength: int = 0,
        pupil_sampling: int = 3,
        image_sampling: int = 3,
    ) -> dict[str, Any]:
        def configure(settings: Any) -> None:
            settings.PupilSampleSize = self._sample_size(pupil_sampling)
            settings.ImageSampleSize = self._sample_size(image_sampling)
            self._set_selector(getattr(settings, "Field", None), field, "field")
            self._set_selector(getattr(settings, "Wavelength", None), wavelength, "wavelength")

        return self._runner().run(
            "HuygensPsf", configure=configure, factory_name="New_HuygensPsf", include_series=False
        )

    def geometric_image_analysis(
        self,
        *,
        field: int = 1,
        wavelength: int = 0,
        rays_x1000: int = 100,
        show_as: str | None = None,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(rays_x1000, bool) or not 1 <= rays_x1000 <= self.MAX_IMAGE_RAYS_X1000:
            raise BackendError("geometric_image_analysis", "rays_x1000 must be 1..1000")

        def configure(settings: Any) -> None:
            settings.RaysX1000 = rays_x1000
            self._set_selector(getattr(settings, "Field", None), field, "field")
            self._set_selector(getattr(settings, "Wavelength", None), wavelength, "wavelength")
            if show_as:
                enum = get_member(get_member(self._api(), "Analysis"), "GiaShowAsTypes")
                settings.ShowAs = self._enum_member(enum, show_as)

        output = self._runner().run(
            "GeometricImageAnalysis",
            configure=configure,
            factory_name="New_GeometricImageAnalysis",
            include_series=False,
        )
        if file_path:
            output.update(AnalysisRunner.write_detached(output, file_path, "json"))
        return output

    def pop(
        self,
        *,
        start_surface: int,
        end_surface: int,
        field: int = 1,
        wavelength: int = 1,
        beam_type: str = "GaussianWaist",
        beam_parameter1: float | None = None,
        beam_parameter2: float | None = None,
        sampling_x: int = 128,
        sampling_y: int = 128,
        data_type: str = "Irradiance",
    ) -> dict[str, Any]:
        if start_surface < 0 or end_surface < start_surface:
            raise BackendError("pop", "surface range is invalid")
        x_level = self._sampling_level(sampling_x)
        y_level = self._sampling_level(sampling_y)

        def configure(raw_settings: Any) -> None:
            settings = self._cast_settings(
                raw_settings, "ZOSAPI.Analysis.PhysicalOptics.IAS_PhysicalOpticsPropagation"
            )
            self._set_surface_selector(settings.StartSurface, start_surface)
            self._set_surface_selector(settings.EndSurface, end_surface)
            self._set_selector(settings.Field, field, "field")
            self._set_selector(settings.Wavelength, wavelength, "wavelength")
            settings.XSampling = self._sample_size(x_level)
            settings.YSampling = self._sample_size(y_level)
            physical = get_member(get_member(self._api(), "Analysis"), "PhysicalOptics")
            settings.BeamType = self._enum_member(get_member(physical, "POPBeamTypes"), beam_type)
            settings.DataType = self._enum_member(get_member(physical, "POPDataTypes"), data_type)
            for index, value in enumerate((beam_parameter1, beam_parameter2)):
                if value is not None and index < int(getattr(settings, "NumberOfParameters", 0)):
                    get_member(settings, "SetParameterValue")(index, float(value))

        return self._runner().run(
            "PhysicalOpticsPropagation",
            configure=configure,
            include_series=False,
            include_grids=True,
        )

    def export_analysis(
        self, *, analysis_type: str, file_path: str, format: str = "text"
    ) -> dict[str, Any]:
        name = self._allowed_analysis(analysis_type)
        normalized = format.strip().lower()
        factory = _ANALYSIS_FACTORIES[name]
        if normalized == "text":
            actual_factory = factory if factory != "New_Analysis" else None
            return self._runner().run_to_file(name, file_path, factory_name=actual_factory)
        if normalized == "bmp":
            raise UnsupportedOperationError(
                "export_analysis", "bitmap export is not exposed by the stable analysis interface"
            )
        data = self._runner().run(name, factory_name=factory if factory != "New_Analysis" else None)
        exported = AnalysisRunner.write_detached(data, file_path, normalized)
        return {"analysis_type": name, **exported}

    def run_analysis(self, *, analysis_type: str) -> dict[str, Any]:
        name = self._allowed_analysis(analysis_type)
        factory = _ANALYSIS_FACTORIES[name]
        return self._runner().run(name, factory_name=factory if factory != "New_Analysis" else None)

    def analysis_series(self, *, analysis_type: str, max_points: int = 40) -> dict[str, Any]:
        name = self._allowed_analysis(analysis_type)
        factory = _ANALYSIS_FACTORIES[name]
        return self._runner().run(
            name,
            max_points=max_points,
            include_series=True,
            include_grids=False,
            factory_name=factory if factory != "New_Analysis" else None,
        )

    def _all_fields_waves(self, analysis_name: str, factory_name: str) -> dict[str, Any]:
        def configure(settings: Any) -> None:
            self._set_selector(getattr(settings, "Field", None), 0, "field")
            self._set_selector(getattr(settings, "Wavelength", None), 0, "wavelength")

        return self._runner().run(
            analysis_name, configure=configure, factory_name=factory_name, include_grids=False
        )

    def _mtf_vs_field(
        self,
        analysis_name: str,
        factory_name: str,
        sampling: int,
        frequency_values: dict[str, float],
    ) -> dict[str, Any]:
        sample_enum = self._sample_size(sampling)
        values = [float(frequency_values.get(f"frequency{index}", 0.0)) for index in range(1, 7)]
        if any(value < 0 or value > 100_000 for value in values):
            raise BackendError("mtf_vs_field", "frequencies must be 0..100000")
        if not any(values):
            raise BackendError("mtf_vs_field", "provide at least one positive frequency")

        def configure(settings: Any) -> None:
            settings.SampleSize = sample_enum
            self._set_selector(getattr(settings, "Wavelength", None), 0, "wavelength")
            for index, value in enumerate(values, 1):
                setattr(settings, f"Freq_{index}", value)
            if hasattr(settings, "FieldDensity"):
                settings.FieldDensity = min(max(int(settings.FieldDensity), 1), self.MAX_DENSITY)

        return self._runner().run(
            analysis_name, configure=configure, factory_name=factory_name, include_grids=False
        )

    def _primary_wavelength(self) -> int:
        wavelengths = getattr(
            getattr(self._require_system(), "SystemData", None), "Wavelengths", None
        )
        count = int(getattr(wavelengths, "NumberOfWavelengths", 0))
        getter = getattr(wavelengths, "GetWavelength", None)
        if callable(getter):
            for number in range(1, count + 1):
                if bool(getattr(getter(number), "IsPrimary", False)):
                    return number
        return 1

    def _set_primary_wavelength(self, number: int) -> None:
        wavelengths = getattr(
            getattr(self._require_system(), "SystemData", None), "Wavelengths", None
        )
        count = int(getattr(wavelengths, "NumberOfWavelengths", 0))
        if number < 1 or number > count:
            raise BackendError("cardinal_points", f"wavelength must be 1..{count}")
        if wavelengths is not None and hasattr(wavelengths, "PrimaryWavelength"):
            wavelengths.PrimaryWavelength = number
            return
        row = get_member(wavelengths, "GetWavelength")(number)
        make_primary = getattr(row, "MakePrimary", None)
        if callable(make_primary):
            make_primary()
            return
        raise UnsupportedOperationError(
            "cardinal_points", "installed ZOS-API cannot select a primary wavelength"
        )

    def _runner(self) -> AnalysisRunner:
        return AnalysisRunner(self._require_system(), self._api())

    def _spot_settings(self, settings: Any) -> Any:
        """Cast pythonnet's base settings proxy to Standard Spot settings."""

        if all(hasattr(settings, name) for name in ("Field", "Wavelength", "RayDensity")):
            return settings
        try:
            return self._api().Analysis.Settings.Spot.IAS_Spot(settings)
        except Exception as exc:
            raise UnsupportedOperationError(
                "spot_diagram", "installed pythonnet cannot cast Standard Spot settings"
            ) from exc

    def _cast_settings(self, settings: Any, interface_name: str) -> Any:
        """Cast pythonnet's base IAS_ proxy only for settings that require it."""

        if all(hasattr(settings, name) for name in ("StartSurface", "EndSurface")):
            return settings
        try:
            interface: Any = self._api()
            for part in interface_name.removeprefix("ZOSAPI.").split("."):
                interface = getattr(interface, part)
            return interface(settings)
        except Exception as exc:
            raise UnsupportedOperationError(
                "pop", "installed pythonnet cannot cast POP analysis settings"
            ) from exc

    def _allowed_analysis(self, analysis_type: str) -> str:
        if not isinstance(analysis_type, str) or not analysis_type.strip():
            raise BackendError("run_analysis", "analysis_type must be a non-empty name")
        normalized = analysis_type.strip()
        aliases = {name.lower(): name for name in _ALLOWED_ANALYSES}
        try:
            return aliases[normalized.lower()]
        except KeyError as exc:
            allowed = ", ".join(sorted(_ALLOWED_ANALYSES))
            raise UnsupportedOperationError(
                "run_analysis", f"analysis_type must be one of: {allowed}"
            ) from exc

    def _sample_size(self, sampling: int) -> Any:
        size = self._sampling_dimension(sampling)
        analysis = get_member(self._api(), "Analysis")
        sample_sizes = get_member(analysis, "SampleSizes")
        return get_member(sample_sizes, f"S_{size}x{size}")

    @staticmethod
    def _sampling_dimension(sampling: int) -> int:
        if isinstance(sampling, bool) or not 1 <= sampling <= 6:
            raise BackendError("analysis", "sampling must be 1..6")
        return (32, 64, 128, 256, 512, 1024)[sampling - 1]

    @staticmethod
    def _sampling_level(dimension: int) -> int:
        sizes = (32, 64, 128, 256, 512, 1024)
        if isinstance(dimension, bool) or dimension not in sizes:
            raise BackendError("pop", "sampling dimensions must be 32, 64, 128, 256, 512, or 1024")
        return sizes.index(dimension) + 1

    @staticmethod
    def _enum_member(enum: Any, requested: str) -> Any:
        normalized = requested.strip().lower().replace("_", "").replace("-", "")
        for name in dir(enum):
            if name.lower().replace("_", "") == normalized:
                return getattr(enum, name)
        raise BackendError("analysis", f"unknown enum value {requested!r}")

    @staticmethod
    def _set_surface_selector(selector: Any, number: int) -> None:
        if number < 0:
            raise BackendError("pop", "surface numbers must be non-negative")
        setter = getattr(selector, "SetSurfaceNumber", None)
        if callable(setter):
            setter(number)
            return
        raise BackendError("pop", "cannot set surface selector")

    @staticmethod
    def _set_selector(selector: Any, number: int, label: str) -> None:
        if selector is None:
            return
        if isinstance(number, bool) or number < 0:
            raise BackendError("analysis", f"{label} must be zero or one-based")
        if number == 0:
            for name in ("UseAllFields", "UseAllWavelengths"):
                use_all = getattr(selector, name, None)
                if callable(use_all):
                    use_all()
                    return
        for name in ("SetFieldNumber", "SetWavelengthNumber"):
            setter = getattr(selector, name, None)
            if callable(setter):
                setter(number)
                return
        raise BackendError("analysis", f"cannot set {label} selector")

    @staticmethod
    def _system_count(system: Any, collection_name: str, count_name: str) -> int:
        system_data = getattr(system, "SystemData", None)
        collection = getattr(system_data, collection_name, None)
        return max(0, int(getattr(collection, count_name, 0)))


def build_operation_map(require_system: SystemProvider, api: ApiProvider) -> dict[str, Operation]:
    """Build handlers bound to a backend's system and API providers."""

    return AnalysisSubsystem(require_system, api).operation_map()


__all__ = ["AnalysisSubsystem", "build_operation_map"]
