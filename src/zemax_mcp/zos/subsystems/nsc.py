"""Non-sequential editor, ray-trace, and detector operation handlers."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from typing import Any

from zemax_mcp.errors import BackendError, UnsupportedOperationError
from zemax_mcp.zos.adapters.cells import cell_snapshot, set_cell_value
from zemax_mcp.zos.adapters.enums import enum_member, enum_name
from zemax_mcp.zos.interop import get_member, to_python

SystemProvider = Callable[[], Any]
ApiProvider = Callable[[], Any]
Operation = Callable[..., Any]


def _result_values(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


class NSCSubsystem:
    """Bound operations for a pure non-sequential optical system."""

    MAX_OBJECTS_RETURNED = 1_000
    MAX_PARAMETER_SNAPSHOT = 32
    MAX_DETECTOR_VALUES = 16_384
    MAX_RAY_HINT = 1_000_000

    def __init__(self, require_system: SystemProvider, api: ApiProvider) -> None:
        self._require_system = require_system
        self._api = api

    def operation_map(self) -> dict[str, Operation]:
        return {
            "nsc_summary": self.summary,
            "nsc_get_object": self.get_object,
            "nsc_add_object": self.add_object,
            "nsc_insert_object": self.insert_object,
            "nsc_remove_object": self.remove_object,
            "nsc_set_object": self.set_object,
            "nsc_set_object_parameter": self.set_object_parameter,
            "nsc_get_object_parameter": self.get_object_parameter,
            "nsc_ray_trace": self.ray_trace,
            "nsc_clear_detectors": self.clear_detectors,
            "nsc_detector_data": self.detector_data,
            "nsc_detector_pixel": self.detector_pixel,
            "nsc_get_source_spectrum": self.get_source_spectrum,
            "nsc_set_source_spectrum": self.set_source_spectrum,
            "nsc_save_detector": self.save_detector,
            "nsc_load_detector": self.load_detector,
            "nsc_polar_detector_data": self.polar_detector_data,
            "nsc_polar_detector_pixel": self.polar_detector_pixel,
            "nsc_detector_viewer": self.detector_viewer,
            "nsc_convert_to_sequential": self.convert_to_sequential,
            "nsc_convert_to_nonsequential": self.convert_to_nonsequential,
        }

    def _system(self) -> Any:
        system = self._require_system()
        if "nonsequential" not in enum_name(getattr(system, "Mode", "")).casefold():
            raise BackendError("nsc", "current system is not in pure non-sequential mode")
        return system

    def _nce(self) -> Any:
        return get_member(self._system(), "NCE")

    def _object(self, object_number: int) -> Any:
        nce = self._nce()
        count = int(getattr(nce, "NumberOfObjects", 0))
        if object_number < 1 or object_number > count:
            raise BackendError(
                "nsc_get_object", f"object {object_number} is out of range 1..{count}"
            )
        return get_member(nce, "GetObjectAt")(object_number)

    def _object_type(self, value: str) -> Any:
        return enum_member(self._api().Editors.NCE.ObjectType, value)

    @staticmethod
    def _simple_properties(value: Any, *, limit: int = 64) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in sorted(name for name in dir(value) if not name.startswith("_")):
            if len(result) >= limit:
                break
            try:
                item = getattr(value, name)
            except Exception:
                continue
            if callable(item) or not isinstance(item, (str, int, float, bool, type(None))):
                continue
            if isinstance(item, float) and not math.isfinite(item):
                item = str(item)
            result[name] = item
        return result

    def _snapshot(self, object_number: int, obj: Any | None = None) -> dict[str, Any]:
        obj = obj or self._object(object_number)
        available = getattr(obj, "AvailableParameters", None)
        parameter_names = list(available()) if callable(available) else []
        parameters: list[dict[str, Any]] = []
        for parameter in range(1, min(len(parameter_names), self.MAX_PARAMETER_SNAPSHOT) + 1):
            try:
                cell = self._parameter_cell(obj, parameter)
                snapshot = cell_snapshot(cell)
            except Exception:
                continue
            snapshot["parameter"] = parameter
            snapshot["name"] = str(parameter_names[parameter - 1])
            parameters.append(snapshot)
        data = getattr(obj, "ObjectData", None)
        return {
            "object_number": object_number,
            "type": enum_name(getattr(obj, "Type", getattr(obj, "TypeName", ""))),
            "type_name": str(getattr(obj, "TypeName", "")),
            "comment": str(getattr(obj, "Comment", "")),
            "material": str(getattr(obj, "Material", "")),
            "ref_object": int(getattr(obj, "RefObject", 0)),
            "inside_of": int(getattr(obj, "InsideOf", 0)),
            "position": {
                "x": float(getattr(obj, "XPosition", 0.0)),
                "y": float(getattr(obj, "YPosition", 0.0)),
                "z": float(getattr(obj, "ZPosition", 0.0)),
            },
            "tilt": {
                "x": float(getattr(obj, "TiltAboutX", 0.0)),
                "y": float(getattr(obj, "TiltAboutY", 0.0)),
                "z": float(getattr(obj, "TiltAboutZ", 0.0)),
            },
            "object_data": self._simple_properties(data) if data is not None else {},
            "parameters": parameters,
            "parameters_truncated": len(parameter_names) > self.MAX_PARAMETER_SNAPSHOT,
        }

    def summary(self) -> dict[str, Any]:
        nce = self._nce()
        count = int(getattr(nce, "NumberOfObjects", 0))
        if count > self.MAX_OBJECTS_RETURNED:
            raise BackendError("nsc_summary", f"object count {count} exceeds response limit")
        return {
            "number_of_objects": count,
            "objects": [self._snapshot(i) for i in range(1, count + 1)],
        }

    def get_object(self, object_number: int) -> dict[str, Any]:
        return self._snapshot(object_number)

    def _change_type(self, obj: Any, object_type: str | None) -> None:
        if not object_type:
            return
        settings = get_member(obj, "GetObjectTypeSettings")(self._object_type(object_type))
        if getattr(settings, "IsValid", True) is False:
            raise BackendError("nsc_set_object", f"object type {object_type!r} is not valid")
        if get_member(obj, "ChangeType")(settings) is False:
            raise BackendError("nsc_set_object", f"could not change object type to {object_type!r}")

    def add_object(
        self, *, object_type: str | None = None, comment: str | None = None
    ) -> dict[str, Any]:
        nce = self._nce()
        obj = get_member(nce, "AddObject")()
        number = int(getattr(obj, "ObjectNumber", getattr(nce, "NumberOfObjects", 0)))
        self._change_type(obj, object_type)
        if comment is not None:
            obj.Comment = comment
        return self._snapshot(number, obj)

    def insert_object(
        self, object_number: int, *, object_type: str | None = None
    ) -> dict[str, Any]:
        nce = self._nce()
        count = int(getattr(nce, "NumberOfObjects", 0))
        if object_number < 1 or object_number > count + 1:
            raise BackendError("nsc_insert_object", f"object_number must be 1..{count + 1}")
        obj = get_member(nce, "InsertNewObjectAt")(object_number)
        self._change_type(obj, object_type)
        return self._snapshot(object_number, obj)

    def remove_object(self, object_number: int) -> dict[str, Any]:
        self._object(object_number)
        removed = get_member(self._nce(), "RemoveObjectAt")(object_number)
        if removed is False:
            raise BackendError("nsc_remove_object", f"could not remove object {object_number}")
        return {"removed": True, "object_number": object_number}

    def set_object(
        self,
        object_number: int,
        *,
        object_type: str | None = None,
        comment: str | None = None,
        material: str | None = None,
        x_position: float | None = None,
        y_position: float | None = None,
        z_position: float | None = None,
        tilt_about_x: float | None = None,
        tilt_about_y: float | None = None,
        tilt_about_z: float | None = None,
        ref_object: int | None = None,
    ) -> dict[str, Any]:
        obj = self._object(object_number)
        self._change_type(obj, object_type)
        changes = {
            "Comment": comment,
            "Material": material,
            "XPosition": x_position,
            "YPosition": y_position,
            "ZPosition": z_position,
            "TiltAboutX": tilt_about_x,
            "TiltAboutY": tilt_about_y,
            "TiltAboutZ": tilt_about_z,
            "RefObject": ref_object,
        }
        for name, value in changes.items():
            if value is not None:
                setattr(obj, name, value)
        return self._snapshot(object_number, obj)

    def _parameter_cell(self, obj: Any, parameter: int) -> Any:
        if parameter < 1 or parameter > 250:
            raise BackendError("nsc_object_parameter", "parameter must be in 1..250")
        column = enum_member(self._api().Editors.NCE.ObjectColumn, f"Par{parameter}")
        getter = getattr(obj, "GetObjectCell", None) or getattr(obj, "GetCellAt", None)
        if not callable(getter):
            raise UnsupportedOperationError(
                "nsc_object_parameter", "object parameter cells unavailable"
            )
        try:
            return getter(column)
        except (TypeError, ValueError):
            # GetCellAt is a physical editor-column accessor; Par1 begins at column 11.
            return getter(parameter + 10)

    def get_object_parameter(self, object_number: int, parameter: int) -> dict[str, Any]:
        cell = self._parameter_cell(self._object(object_number), parameter)
        result = cell_snapshot(cell)
        result.update({"object_number": object_number, "parameter": parameter})
        return result

    def set_object_parameter(
        self, object_number: int, parameter: int, value: Any
    ) -> dict[str, Any]:
        cell = self._parameter_cell(self._object(object_number), parameter)
        if bool(getattr(cell, "IsReadOnly", False)):
            raise BackendError("nsc_set_object_parameter", f"parameter {parameter} is read-only")
        set_cell_value(cell, value)
        return self.get_object_parameter(object_number, parameter)

    @staticmethod
    def _close(resource: Any) -> None:
        close = getattr(resource, "Close", None)
        if callable(close):
            close()

    def _bound_source_rays(self, total_limit: int) -> list[tuple[Any, Any]]:
        """Temporarily divide a total analysis-ray limit across enabled NSC sources."""
        nce = self._nce()
        candidates: list[Any] = []
        for number in range(1, int(getattr(nce, "NumberOfObjects", 0)) + 1):
            obj = get_member(nce, "GetObjectAt")(number)
            if not str(getattr(obj, "TypeName", "")).casefold().startswith("source"):
                continue
            data = getattr(obj, "ObjectData", None)
            if data is not None and hasattr(data, "NumberOfAnalysisRays"):
                candidates.append(data)
        if not candidates:
            return []
        per_source = max(1, total_limit // len(candidates))
        originals: list[tuple[Any, Any]] = []
        for data in candidates:
            original = data.NumberOfAnalysisRays
            originals.append((data, original))
            data.NumberOfAnalysisRays = min(int(original), per_source)
        return originals

    def clear_detectors(self, *, object_number: int = 0) -> dict[str, Any]:
        if object_number < 0:
            raise BackendError("nsc_clear_detectors", "object_number must be zero or positive")
        if object_number:
            self._object(object_number)
        tool = get_member(get_member(self._system(), "Tools"), "OpenNSCRayTrace")()
        if tool is None:
            raise BackendError("nsc_clear_detectors", "NSC ray trace tool is unavailable")
        try:
            if object_number == 0:
                result = get_member(tool, "ClearDetectors")(0)
            else:
                clear_one = getattr(tool, "ClearDetectorObject", None)
                result = (
                    clear_one(object_number)
                    if callable(clear_one)
                    else tool.ClearDetectors(object_number)
                )
            return {"cleared": True, "object_number": object_number, "result": enum_name(result)}
        finally:
            self._close(tool)

    def ray_trace(
        self,
        *,
        split: bool = True,
        scatter: bool = False,
        clear_detectors: bool = True,
        rays: int = 100_000,
        use_polarization: bool = False,
        ignore_errors: bool = True,
        save_zrd: bool = False,
        zrd_file: str | None = None,
        zrd_format: str = "CompressedFullData",
    ) -> dict[str, Any]:
        if rays < 1 or rays > self.MAX_RAY_HINT:
            raise BackendError("nsc_ray_trace", f"rays must be in 1..{self.MAX_RAY_HINT}")
        if save_zrd and not zrd_file:
            raise BackendError("nsc_ray_trace", "zrd_file is required when save_zrd is true")
        system = self._system()
        resolved_zrd = None
        if save_zrd:
            from pathlib import Path

            if (
                Path(zrd_file or "").name != zrd_file
                or Path(zrd_file or "").suffix.casefold() != ".zrd"
            ):
                raise BackendError("nsc_ray_trace", "zrd_file must be a .ZRD basename")
            system_file = str(getattr(system, "SystemFile", ""))
            if not system_file:
                raise BackendError("nsc_ray_trace", "save the lens before writing a ZRD")
            resolved_zrd = Path(system_file).resolve().parent / str(zrd_file)
        elif zrd_file is not None:
            raise BackendError("nsc_ray_trace", "zrd_file requires save_zrd=true")
        tool = get_member(get_member(system, "Tools"), "OpenNSCRayTrace")()
        if tool is None:
            raise BackendError("nsc_ray_trace", "NSC ray trace tool is unavailable")
        source_rays: list[tuple[Any, Any]] = []
        try:
            source_rays = self._bound_source_rays(rays)
            tool.SplitNSCRays = split
            tool.ScatterNSCRays = scatter
            tool.UsePolarization = use_polarization
            tool.IgnoreErrors = ignore_errors
            tool.SaveRays = save_zrd
            if zrd_file is not None:
                tool.SaveRaysFile = zrd_file
                tool.ZRDFormat = enum_member(self._api().Tools.RayTrace.ZRDFormatType, zrd_format)
            if clear_detectors:
                tool.ClearDetectors(0)
            get_member(tool, "RunAndWaitForCompletion")()
            if not bool(getattr(tool, "Succeeded", True)):
                raise BackendError(
                    "nsc_ray_trace", str(getattr(tool, "ErrorMessage", "ray trace failed"))
                )
            if resolved_zrd is not None and not resolved_zrd.is_file():
                raise BackendError("nsc_ray_trace", f"expected ZRD was not created: {resolved_zrd}")
            return {
                "completed": True,
                "split": split,
                "scatter": scatter,
                "use_polarization": use_polarization,
                "ignore_errors": ignore_errors,
                "detectors_cleared": clear_detectors,
                "ray_count_limit": rays,
                "bounded_sources": len(source_rays),
                "saved_zrd": save_zrd,
                "zrd_file": zrd_file,
                "zrd_path": str(resolved_zrd) if resolved_zrd is not None else None,
                "zrd_format": zrd_format if save_zrd else None,
                "total_ray_energy": float(tool.GetTotalRayEnergy())
                if callable(getattr(tool, "GetTotalRayEnergy", None))
                else None,
            }
        finally:
            for data, original in source_rays:
                data.NumberOfAnalysisRays = original
            self._close(tool)

    @staticmethod
    def _flatten(data: Any) -> tuple[list[Any], list[int]]:
        get_length = getattr(data, "GetLength", None)
        if callable(get_length):
            rows, columns = int(get_length(0)), int(get_length(1))
            values = [data[row, column] for row in range(rows) for column in range(columns)]
            return values, [rows, columns]
        converted = to_python(data)
        if isinstance(converted, list) and converted and isinstance(converted[0], list):
            rows = len(converted)
            columns = max((len(row) for row in converted), default=0)
            return [value for row in converted for value in row], [rows, columns]
        values = list(converted) if isinstance(converted, list) else [converted]
        return values, [len(values)]

    @staticmethod
    def _stats(values: Iterable[Any]) -> dict[str, Any]:
        numeric = [float(value) for value in values if isinstance(value, (int, float))]
        if not numeric:
            return {"count": 0, "sum": 0.0, "min": None, "max": None}
        return {
            "count": len(numeric),
            "sum": sum(numeric),
            "min": min(numeric),
            "max": max(numeric),
        }

    def detector_data(
        self,
        object_number: int,
        *,
        data_type: int = 1,
        max_values: int = 4096,
        quantity: str | None = None,
    ) -> dict[str, Any]:
        self._object(object_number)
        if data_type not in {1, 2, 3}:
            raise BackendError("nsc_detector_data", "data_type must be 1, 2, or 3")
        if max_values < 0 or max_values > self.MAX_DETECTOR_VALUES:
            raise BackendError(
                "nsc_detector_data", f"max_values must be in 0..{self.MAX_DETECTOR_VALUES}"
            )
        nce = self._nce()
        quantity_key = quantity.casefold() if quantity else None
        coherent_names = {
            "coherentreal": "Real",
            "coherentimaginary": "Imaginary",
            "coherentamplitude": "Amplitude",
            "coherentpower": "Power",
        }
        if quantity_key in coherent_names:
            detector_type = enum_member(
                self._api().Editors.NCE.DetectorDataType, coherent_names[quantity_key]
            )
            data = get_member(nce, "GetAllCoherentDataSafe")(object_number, detector_type)
            kind = quantity_key
        elif quantity_key == "coherentphasedegrees":
            data_type = 3
            data = None
            kind = quantity_key
        elif quantity_key in {None, "incoherentflux"} and data_type == 1:
            data = get_member(nce, "GetAllDetectorDataSafe")(object_number, 0)
            kind = "incoherent_flux"
        elif data_type == 2:
            detector_type = enum_member(self._api().Editors.NCE.DetectorDataType, "Power")
            data = get_member(nce, "GetAllCoherentDataSafe")(object_number, detector_type)
            kind = "coherent_power"
        else:
            real_type = enum_member(self._api().Editors.NCE.DetectorDataType, "Real")
            imaginary_type = enum_member(self._api().Editors.NCE.DetectorDataType, "Imaginary")
            real, shape = self._flatten(
                get_member(nce, "GetAllCoherentDataSafe")(object_number, real_type)
            )
            imaginary, imaginary_shape = self._flatten(
                get_member(nce, "GetAllCoherentDataSafe")(object_number, imaginary_type)
            )
            if shape != imaginary_shape or len(real) != len(imaginary):
                raise BackendError("nsc_detector_data", "coherent detector arrays do not match")
            data = [
                math.degrees(math.atan2(float(y), float(x)))
                for x, y in zip(real, imaginary, strict=True)
            ]
            kind = "coherent_phase_degrees"
        values, shape = self._flatten(data)
        total = len(values)
        return {
            "object_number": object_number,
            "data_type": data_type,
            "kind": kind,
            "shape": shape,
            "statistics": self._stats(values),
            "values": values[:max_values],
            "returned_values": min(total, max_values),
            "total_values": total,
            "truncated": total > max_values,
        }

    def detector_pixel(
        self, object_number: int, pixel: int, *, data_type: int = 1
    ) -> dict[str, Any]:
        self._object(object_number)
        nce = self._nce()
        if data_type == 1:
            result = get_member(nce, "GetDetectorData")(object_number, pixel, 0, 0.0)
            kind = "incoherent_flux"
        elif data_type == 2:
            detector_type = enum_member(self._api().Editors.NCE.DetectorDataType, "Power")
            result = get_member(nce, "GetCoherentData")(object_number, pixel, detector_type, 0.0)
            kind = "coherent_power"
        elif data_type == 3:
            real_type = enum_member(self._api().Editors.NCE.DetectorDataType, "Real")
            imaginary_type = enum_member(self._api().Editors.NCE.DetectorDataType, "Imaginary")
            real_result = get_member(nce, "GetCoherentData")(object_number, pixel, real_type, 0.0)
            imaginary_result = get_member(nce, "GetCoherentData")(
                object_number, pixel, imaginary_type, 0.0
            )
            real_values = (
                list(real_result) if isinstance(real_result, (list, tuple)) else [real_result]
            )
            imaginary_values = (
                list(imaginary_result)
                if isinstance(imaginary_result, (list, tuple))
                else [imaginary_result]
            )
            if not bool(real_values[0]) or not bool(imaginary_values[0]):
                raise BackendError("nsc_detector_pixel", "OpticStudio could not read phase data")
            result = (
                True,
                math.degrees(math.atan2(float(imaginary_values[-1]), float(real_values[-1]))),
            )
            kind = "coherent_phase_degrees"
        else:
            raise BackendError("nsc_detector_pixel", "data_type must be 1, 2, or 3")
        values = list(result) if isinstance(result, (list, tuple)) else [result]
        success = bool(values[0]) if len(values) > 1 else True
        value = values[-1]
        if not success:
            raise BackendError("nsc_detector_pixel", "OpticStudio could not read detector data")
        return {
            "object_number": object_number,
            "pixel": pixel,
            "data_type": data_type,
            "kind": kind,
            "value": float(value),
        }

    def get_source_spectrum(self, object_number: int) -> dict[str, Any]:
        obj = self._object(object_number)
        sources = getattr(obj, "SourcesData", None)
        if sources is None or not bool(getattr(sources, "IsSourcesAvailable", True)):
            raise BackendError("nsc_get_source_spectrum", "object has no source-spectrum data")
        mode = enum_name(sources.SourceColor)
        settings = sources.SourceColorSettings
        branch = getattr(settings, f"_S_{mode}", settings)
        values = self._simple_properties(branch, limit=32)
        return {"object_number": object_number, "mode": mode, "settings": values}

    def set_source_spectrum(
        self, object_number: int, mode: str, settings: dict[str, Any]
    ) -> dict[str, Any]:
        obj = self._object(object_number)
        sources = getattr(obj, "SourcesData", None)
        if sources is None or not bool(getattr(sources, "IsSourcesAvailable", True)):
            raise BackendError("nsc_set_source_spectrum", "object has no source-spectrum data")
        selected = enum_member(self._api().Editors.NCE.SourceColorMode, mode)
        sources.SourceColor = selected
        canonical = enum_name(selected)
        branch = getattr(sources.SourceColorSettings, f"_S_{canonical}", None)
        if branch is None:
            raise BackendError("nsc_set_source_spectrum", "typed source settings are unavailable")
        aliases = {
            "spectrumCount": "SpectrumCount",
            "wavelengthFrom": "WavelengthFrom",
            "wavelengthTo": "WavelengthTo",
            "temperatureK": "TemperatureK",
            "spectrumFile": "SpectrumFile",
            "chromaticityX": "cx",
            "chromaticityY": "cy",
            "red": "R",
            "green": "G",
            "blue": "B",
            "uPrime": "u",
            "vPrime": "v",
        }
        for key, value in settings.items():
            name = aliases.get(key, key)
            if not hasattr(branch, name):
                raise BackendError(
                    "nsc_set_source_spectrum", f"field {key!r} is invalid for {canonical}"
                )
            setattr(branch, name, value)
        return self.get_source_spectrum(object_number)

    def _detector_suffix(self, object_number: int) -> str:
        name = str(getattr(self._object(object_number), "TypeName", "")).casefold()
        for marker, suffix in (
            ("polar", ".ddp"),
            ("rectangle", ".ddr"),
            ("color", ".ddc"),
            ("volume", ".ddv"),
        ):
            if marker in name:
                return suffix
        raise BackendError("nsc_detector_file", "unsupported detector object type")

    def save_detector(
        self, object_number: int, file_path: str, *, overwrite: bool = False
    ) -> dict[str, Any]:
        from pathlib import Path

        path = Path(file_path).expanduser().resolve()
        suffix = self._detector_suffix(object_number)
        if path.suffix.casefold() != suffix:
            raise BackendError("nsc_save_detector", f"detector requires {suffix} file")
        if path.exists() and not overwrite:
            raise BackendError("nsc_save_detector", "destination exists; set overwrite=true")
        if not path.parent.is_dir():
            raise BackendError("nsc_save_detector", "destination parent does not exist")
        if get_member(self._nce(), "SaveDetector")(object_number, str(path)) is False:
            raise BackendError("nsc_save_detector", "OpticStudio did not save detector")
        return {"object_number": object_number, "file_path": str(path), "saved": True}

    def load_detector(
        self, object_number: int, file_path: str, *, append_data: bool = False
    ) -> dict[str, Any]:
        from pathlib import Path

        path = Path(file_path).expanduser().resolve()
        suffix = self._detector_suffix(object_number)
        if not path.is_file() or path.suffix.casefold() != suffix:
            raise BackendError("nsc_load_detector", f"existing {suffix} file is required")
        if get_member(self._nce(), "LoadDetector")(object_number, str(path), append_data) is False:
            raise BackendError("nsc_load_detector", "OpticStudio did not load detector")
        return {
            "object_number": object_number,
            "file_path": str(path),
            "loaded": True,
            "append_data": append_data,
        }

    def polar_detector_data(
        self, object_number: int, quantity: str, *, max_values: int = 4096
    ) -> dict[str, Any]:
        self._detector_suffix(object_number)
        if max_values < 0 or max_values > self.MAX_DETECTOR_VALUES:
            raise BackendError("nsc_polar_detector_data", "max_values exceeds limit")
        enum = enum_member(self._api().Editors.NCE.PolarDetectorDataType, quantity)
        values, shape = self._flatten(self._nce().GetAllPolarDetectorDataSafe(object_number, enum))
        return {
            "object_number": object_number,
            "quantity": quantity,
            "shape": shape,
            "statistics": self._stats(values),
            "values": values[:max_values],
            "total_values": len(values),
            "truncated": len(values) > max_values,
        }

    def polar_detector_pixel(self, object_number: int, pixel: int, quantity: str) -> dict[str, Any]:
        self._detector_suffix(object_number)
        enum = enum_member(self._api().Editors.NCE.PolarDetectorDataType, quantity)
        result = _result_values(self._nce().GetPolarDetectorData(object_number, pixel, enum, 0.0))
        if len(result) > 1 and not bool(result[0]):
            raise BackendError("nsc_polar_detector_pixel", "OpticStudio could not read polar data")
        return {
            "object_number": object_number,
            "pixel": pixel,
            "quantity": quantity,
            "value": float(result[-1]),
        }

    def detector_viewer(
        self,
        object_number: int,
        *,
        show_as: str = "FalseColor",
        data_type: str = "IncoherentIrradiance",
        scale: str = "Linear",
        smoothing: int = 0,
        filter: str | None = None,
        max_cells: int = 4096,
    ) -> dict[str, Any]:
        if max_cells < 1 or max_cells > 20_000:
            raise BackendError("nsc_detector_viewer", "max_cells must be in 1..20000")
        analysis = self._system().Analyses.New_DetectorViewer()
        if analysis is None:
            raise BackendError("nsc_detector_viewer", "Detector Viewer is unavailable")
        try:
            settings = analysis.GetSettings()
            if not hasattr(settings, "Detector"):
                try:
                    settings = self._api().Analysis.Settings.RayTracing.IAS_DetectorViewer(settings)
                except Exception as exc:
                    raise UnsupportedOperationError(
                        "nsc_detector_viewer",
                        "installed pythonnet cannot cast Detector Viewer settings",
                    ) from exc
            settings.Detector.SetDetectorNumber(object_number)
            settings.ShowAs = enum_member(type(settings.ShowAs), show_as)
            settings.DataType = enum_member(type(settings.DataType), data_type)
            settings.Scale = enum_member(type(settings.Scale), scale)
            settings.Smoothing = smoothing
            if filter is not None:
                settings.Filter = filter
            analysis.ApplyAndWaitForCompletion()
            results = analysis.GetResults()
            grids = []
            if int(getattr(results, "NumberOfDataGridsRgb", 0)):
                grid = results.GetDataGridRgb(0)
                nx, ny = int(grid.Nx), int(grid.Ny)
                if nx * ny > max_cells:
                    raise BackendError("nsc_detector_viewer", "RGB detector grid exceeds max_cells")
                values = [to_python(grid.GetValue(x, y)) for y in range(ny) for x in range(nx)]
                grids.append({"shape": [ny, nx], "values": values, "rgb": True})
            else:
                grid = results.GetDataGrid(0)
                values, shape = self._flatten(grid.Values)
                grids.append(
                    {
                        "shape": shape,
                        "values": values[:max_cells],
                        "rgb": False,
                        "truncated": len(values) > max_cells,
                    }
                )
            return {
                "object_number": object_number,
                "show_as": show_as,
                "data_type": data_type,
                "scale": scale,
                "grids": grids,
            }
        finally:
            self._close(analysis)

    def convert_to_nonsequential(self) -> dict[str, Any]:
        system = self._require_system()
        if "nonsequential" in enum_name(getattr(system, "Mode", "")).casefold():
            return {"converted": False, "mode": "NonSequential", "already_in_mode": True}
        if get_member(system, "MakeNonSequential")() is False:
            raise BackendError("nsc_convert_to_nonsequential", "OpticStudio refused conversion")
        return {"converted": True, "mode": enum_name(getattr(system, "Mode", "NonSequential"))}

    def convert_to_sequential(
        self, *, first_object: int | None = None, last_object: int | None = None
    ) -> dict[str, Any]:
        system = self._system()
        count = int(getattr(get_member(system, "NCE"), "NumberOfObjects", 0))
        first = 1 if first_object is None else first_object
        last = count if last_object is None else last_object
        if count == 0:
            raise BackendError("nsc_convert_to_sequential", "cannot convert an empty NSC system")
        if first != 1 or last != count:
            raise UnsupportedOperationError(
                "nsc_convert_to_sequential",
                f"partial object-range conversion is unsafe; select the complete range 1..{count}",
            )
        if get_member(system, "MakeSequential")() is False:
            raise BackendError(
                "nsc_convert_to_sequential",
                "OpticStudio refused conversion; the NSC objects are not sequentially eligible",
            )
        return {
            "converted": True,
            "mode": enum_name(getattr(system, "Mode", "Sequential")),
            "first_object": first,
            "last_object": last,
        }


def build_operation_map(require_system: SystemProvider, api: ApiProvider) -> dict[str, Operation]:
    return NSCSubsystem(require_system, api).operation_map()


__all__ = ["NSCSubsystem", "build_operation_map"]
