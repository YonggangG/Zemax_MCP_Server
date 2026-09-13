"""Bounded streaming reader for OpticStudio ZRD ray databases."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.adapters.enums import enum_name

Accessor = Callable[[], Any]
Operation = Callable[..., Any]


def _validate_path(file_path: str) -> Path:
    path = Path(file_path).expanduser().resolve()
    if path.suffix.casefold() != ".zrd" or not path.is_file():
        raise BackendError("zrd", "file_path must identify an existing .ZRD file")
    return path


def _validate_filter(value: str | None) -> str:
    if value is None:
        return ""
    if len(value) > 4096 or "\x00" in value or "\r" in value or "\n" in value:
        raise BackendError("zrd", "filter contains invalid characters or is too long")
    return value


def _tuple(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


class ZRDOperations:
    def __init__(self, require_system: Accessor, _api: Accessor) -> None:
        self._require_system = require_system

    def _read(
        self,
        *,
        file_path: str,
        filter: str | None,
        max_rays: int,
        max_segments: int,
        return_segments: bool,
    ) -> dict[str, Any]:
        if not 0 <= max_rays <= 1_000_000:
            raise BackendError("zrd", "max_rays must be in 0..1000000")
        if not 0 <= max_segments <= 10_000_000:
            raise BackendError("zrd", "max_segments must be in 0..10000000")
        path = _validate_path(file_path)
        expression = _validate_filter(filter)
        reader = self._require_system().Tools.OpenRayDatabaseReader()
        if reader is None:
            raise BackendError("zrd", "ZRD reader is unavailable")
        try:
            reader.ZRDFile = str(path)
            if expression:
                reader.Filter = expression
            reader.RunAndWaitForCompletion()
            if not bool(getattr(reader, "Succeeded", True)):
                raise BackendError("zrd", str(getattr(reader, "ErrorMessage", "reader failed")))
            results = reader.GetResults()
            if results is None or not bool(getattr(results, "IsValid", True)):
                raise BackendError("zrd", "ZRD reader returned invalid results")
            rays: list[dict[str, Any]] = []
            ray_count = segment_count = 0
            hit_counts: Counter[str] = Counter()
            status_counts: Counter[str] = Counter()
            wavelengths: set[float] = set()
            truncated = False
            while ray_count < max_rays:
                header = _tuple(results.ReadNextResult())
                if not header or not bool(header[0]):
                    break
                if len(header) < 5:
                    raise BackendError("zrd", "unexpected ray-header tuple")
                _, ray_number, wave_index, wavelength_um, declared_segments = header[:5]
                wavelengths.add(float(wavelength_um))
                segment_rows: list[dict[str, Any]] = []
                record: dict[str, Any] = {
                    "ray_number": int(ray_number),
                    "wave_index": int(wave_index),
                    "wavelength_um": float(wavelength_um),
                    "declared_segments": int(declared_segments),
                    "segments": segment_rows,
                }
                for _ in range(int(declared_segments)):
                    if segment_count >= max_segments:
                        truncated = True
                        break
                    segment = _tuple(results.ReadNextSegmentFull())
                    if not segment or not bool(segment[0]):
                        break
                    if len(segment) < 30:
                        raise BackendError("zrd", "unexpected full-segment tuple")
                    values = segment[1:30]
                    status = values[5]
                    hit_counts[str(int(values[2]))] += 1
                    status_counts[enum_name(status)] += 1
                    segment_count += 1
                    if return_segments:
                        segment_rows.append(
                            {
                                "segment_level": int(values[0]),
                                "segment_parent": int(values[1]),
                                "hit_object": int(values[2]),
                                "hit_face": int(values[3]),
                                "inside_of": int(values[4]),
                                "status": enum_name(status),
                                "x": float(values[6]),
                                "y": float(values[7]),
                                "z": float(values[8]),
                                "l": float(values[9]),
                                "m": float(values[10]),
                                "n": float(values[11]),
                                "intensity": float(values[18]),
                                "path_length": float(values[19]),
                                "xy_bin": int(values[20]),
                                "lm_bin": int(values[21]),
                                "refractive_index": float(values[25]),
                                "starting_phase": float(values[26]),
                                "phase_of": float(values[27]),
                                "phase_at": float(values[28]),
                            }
                        )
                record["segments_returned"] = len(segment_rows)
                record["segments_truncated"] = truncated
                ray_count += 1
                if return_segments:
                    rays.append(record)
                if truncated:
                    break
            if ray_count >= max_rays:
                truncated = True
            return {
                "file_path": str(path),
                "filter": expression or None,
                "rays_scanned": ray_count,
                "segments_scanned": segment_count,
                "wavelengths_um": sorted(wavelengths),
                "hit_object_counts": dict(hit_counts),
                "status_counts": dict(status_counts),
                "truncated": truncated,
                "rays": rays,
            }
        finally:
            close = getattr(reader, "Close", None)
            if callable(close):
                close()

    def summary(
        self,
        *,
        file_path: str,
        filter: str | None = None,
        max_rays_to_scan: int = 100_000,
        max_segments_to_scan: int = 1_000_000,
    ) -> dict[str, Any]:
        return self._read(
            file_path=file_path,
            filter=filter,
            max_rays=max_rays_to_scan,
            max_segments=max_segments_to_scan,
            return_segments=False,
        )

    def read(
        self,
        *,
        file_path: str,
        filter: str | None = None,
        max_rays: int = 100,
        max_segments: int = 4096,
    ) -> dict[str, Any]:
        return self._read(
            file_path=file_path,
            filter=filter,
            max_rays=max_rays,
            max_segments=max_segments,
            return_segments=True,
        )


def build_operation_map(require_system: Accessor, api: Accessor) -> dict[str, Operation]:
    operations = ZRDOperations(require_system, api)
    return {"zrd_summary": operations.summary, "zrd_read": operations.read}
