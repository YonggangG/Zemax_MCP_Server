"""Reusable, bounded extraction for sequential ZOS-API analyses.

The adapter keeps live ZOS-API objects inside one call.  Analysis windows and any
other closeable objects acquired during the call are released in ``finally`` blocks.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable, Iterable
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from typing import Any

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.interop import get_member, to_python

ConfigureAnalysis = Callable[[Any], None]


class AnalysisRunner:
    """Open, run, extract, and close one ZOS-API analysis window."""

    MAX_SERIES = 64
    MAX_GRIDS = 16
    MAX_POINTS_PER_CURVE = 2_000
    MAX_GRID_CELLS = 20_000
    MAX_RUNTIME_SECONDS = 120.0

    def __init__(self, system: Any, zosapi: Any) -> None:
        self._system = system
        self._zosapi = zosapi

    def analysis_id(self, name: str) -> Any:
        """Resolve an exact ``AnalysisIDM`` member without evaluating user input."""

        analysis = get_member(self._zosapi, "Analysis")
        identifiers = get_member(analysis, "AnalysisIDM")
        return get_member(identifiers, name)

    def run(
        self,
        analysis_name: str,
        *,
        configure: ConfigureAnalysis | None = None,
        factory_name: str | None = None,
        max_points: int = MAX_POINTS_PER_CURVE,
        include_series: bool = True,
        include_grids: bool = True,
    ) -> dict[str, Any]:
        """Run an analysis and return only detached, transport-safe data."""

        point_limit = self._bounded_limit(
            max_points, minimum=1, maximum=self.MAX_POINTS_PER_CURVE, label="max_points"
        )
        analyses = get_member(self._system, "Analyses")
        window = None
        settings = None
        results = None
        try:
            factory = getattr(analyses, factory_name, None) if factory_name is not None else None
            if callable(factory):
                window = factory()
            else:
                window = get_member(analyses, "New_Analysis")(self.analysis_id(analysis_name))
            if window is None:
                raise BackendError("run_analysis", f"analysis {analysis_name!r} is unavailable")

            settings = get_member(window, "GetSettings")()
            if configure is not None:
                configure(settings)
            self._apply_with_timeout(window)
            results = get_member(window, "GetResults")()
            if results is None:
                raise BackendError(
                    "run_analysis", f"analysis {analysis_name!r} returned no results"
                )

            output: dict[str, Any] = {"analysis_type": analysis_name}
            header = getattr(getattr(results, "HeaderData", None), "Lines", None)
            if header is not None:
                output["header"] = [str(line)[:2_000] for line in self._vector(header)[:256]]
            metadata = getattr(results, "MetaData", None)
            if metadata is not None:
                output["metadata"] = {
                    key: to_python(value)
                    for source, key in (
                        ("FeatureDescription", "feature_description"),
                        ("LensFile", "lens_file"),
                        ("LensTitle", "lens_title"),
                        ("Date", "date"),
                    )
                    if (value := getattr(metadata, source, None)) is not None
                }
            if include_series:
                output["series"] = self.extract_series(results, max_points=point_limit)
            if include_grids:
                output["grids"] = self.extract_grids(results)
            if not output.get("series") and not output.get("grids") and not output.get("header"):
                text = self.extract_text(results)
                if text:
                    output["text"] = text
            return output
        finally:
            self.close_resources(results, settings, window)

    def run_to_file(
        self,
        analysis_name: str,
        file_path: str,
        *,
        configure: ConfigureAnalysis | None = None,
        factory_name: str | None = None,
    ) -> dict[str, Any]:
        """Run one allowlisted analysis and ask OpticStudio to export its text result."""

        destination = Path(file_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        analyses = get_member(self._system, "Analyses")
        window = settings = None
        try:
            factory = getattr(analyses, factory_name, None) if factory_name is not None else None
            window = (
                factory()
                if callable(factory)
                else get_member(analyses, "New_Analysis")(self.analysis_id(analysis_name))
            )
            if window is None:
                raise BackendError("export_analysis", f"analysis {analysis_name!r} is unavailable")
            settings = get_member(window, "GetSettings")()
            if configure is not None:
                configure(settings)
            self._apply_with_timeout(window)
            get_member(window, "ToFile")(str(destination), False, False)
            if not destination.is_file():
                raise BackendError("export_analysis", "OpticStudio did not create the export file")
            return {
                "analysis_type": analysis_name,
                "path": str(destination),
                "format": "text",
                "size_bytes": destination.stat().st_size,
            }
        finally:
            self.close_resources(settings, window)

    @staticmethod
    def write_detached(data: dict[str, Any], file_path: str, format_name: str) -> dict[str, Any]:
        """Write already-detached bounded analysis data as JSON or CSV."""

        destination = Path(file_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        normalized = format_name.strip().lower()
        if normalized == "json":
            destination.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        elif normalized == "csv":
            rows: list[dict[str, Any]] = []
            for series in data.get("series", []):
                x_values = series.get("x", [])
                for column, values in enumerate(series.get("y_columns", [])):
                    for point, value in enumerate(values):
                        rows.append(
                            {
                                "series": series.get("index"),
                                "column": column,
                                "point": point,
                                "x": x_values[point] if point < len(x_values) else None,
                                "y": value,
                            }
                        )
            if not rows:
                raise BackendError("export_analysis", "CSV export requires line-series results")
            with destination.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        else:
            raise BackendError("export_analysis", "format must be text, json, or csv")
        return {
            "path": str(destination),
            "format": normalized,
            "size_bytes": destination.stat().st_size,
        }

    def _apply_with_timeout(self, window: Any) -> None:
        """Prefer bounded asynchronous analysis execution; retain a synchronous fallback."""

        apply = getattr(window, "Apply", None)
        is_running = getattr(window, "IsRunning", None)
        if callable(apply) and callable(is_running):
            apply()
            deadline = monotonic() + self.MAX_RUNTIME_SECONDS
            while bool(is_running()):
                if monotonic() >= deadline:
                    terminate = getattr(window, "Terminate", None)
                    if callable(terminate):
                        with suppress(Exception):
                            terminate()
                    raise BackendError("run_analysis", "analysis exceeded 120 second limit")
                sleep(0.02)
            wait = getattr(window, "WaitForCompletion", None)
            if callable(wait):
                wait()
            return
        get_member(window, "ApplyAndWaitForCompletion")()

    @staticmethod
    def extract_text(results: Any, *, max_characters: int = 200_000) -> str:
        """Extract text-only analysis results through the stable ``GetTextFile`` API."""

        getter = getattr(results, "GetTextFile", None)
        if not callable(getter):
            return ""
        with TemporaryDirectory(prefix="zemax-analysis-") as directory:
            path = Path(directory) / "result.txt"
            if getter(str(path)) is False or not path.is_file():
                return ""
            return path.read_text(encoding="utf-8-sig", errors="replace")[:max_characters]

    def extract_series(self, results: Any, *, max_points: int) -> list[dict[str, Any]]:
        """Extract and decimate line-series data from an analysis result."""

        count = min(self._count(results, "NumberOfDataSeries"), self.MAX_SERIES)
        getter = getattr(results, "GetDataSeries", None)
        if not callable(getter):
            return []
        extracted: list[dict[str, Any]] = []
        for index in range(count):
            series = getter(index)
            x_data = getattr(getattr(series, "XData", None), "Data", [])
            y_data = getattr(getattr(series, "YData", None), "Data", [])
            x_values = self._vector(x_data)
            rows, shape = self._matrix(y_data)
            source_points = max(len(x_values), len(rows))
            indices = self._sample_indices(source_points, max_points)
            sampled_x = [x_values[i] for i in indices if i < len(x_values)]
            sampled_rows = [rows[i] for i in indices if i < len(rows)]
            y_columns = self._transpose(sampled_rows)
            item: dict[str, Any] = {
                "index": index,
                "x": sampled_x,
                "y_columns": y_columns,
                "source_shape": list(shape),
                "source_point_count": source_points,
                "point_count": len(indices),
                "decimated": len(indices) < source_points,
            }
            self._copy_labels(series, item)
            extracted.append(item)
        return extracted

    def extract_grids(self, results: Any) -> list[dict[str, Any]]:
        """Extract bounded two-dimensional data grids."""

        count = min(self._count(results, "NumberOfDataGrids"), self.MAX_GRIDS)
        getter = getattr(results, "GetDataGrid", None)
        if not callable(getter):
            return []
        extracted: list[dict[str, Any]] = []
        for index in range(count):
            grid = getter(index)
            raw = self._first_member(grid, "Values", "Data")
            rows, shape = self._matrix(raw)
            original_rows, original_columns = shape
            row_step = 1
            column_step = 1
            if original_rows * original_columns > self.MAX_GRID_CELLS:
                # Preserve both axes and keep the sampled product below the cap.
                scale = (original_rows * original_columns / self.MAX_GRID_CELLS) ** 0.5
                step = max(1, int(scale + 0.999999))
                row_step = column_step = step
            sampled = [row[::column_step] for row in rows[::row_step]]
            item: dict[str, Any] = {
                "index": index,
                "values": sampled,
                "source_shape": [original_rows, original_columns],
                "shape": [len(sampled), len(sampled[0]) if sampled else 0],
                "row_step": row_step,
                "column_step": column_step,
                "decimated": row_step > 1 or column_step > 1,
            }
            self._copy_grid_metadata(grid, item)
            extracted.append(item)
        return extracted

    @staticmethod
    def close_resources(*resources: Any) -> None:
        """Best-effort close/dispose, once per acquired object, in reverse order."""

        seen: set[int] = set()
        for resource in reversed(resources):
            if resource is None or id(resource) in seen:
                continue
            seen.add(id(resource))
            for name in ("Close", "Dispose"):
                close = getattr(resource, name, None)
                if callable(close):
                    # Cleanup must not hide the analysis failure or a completed result.
                    with suppress(Exception):
                        close()
                    break

    @staticmethod
    def _bounded_limit(value: int, *, minimum: int, maximum: int, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise BackendError("run_analysis", f"{label} must be {minimum}..{maximum}")
        return value

    @staticmethod
    def _count(value: Any, name: str) -> int:
        try:
            return max(0, int(getattr(value, name, 0)))
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _first_member(value: Any, *names: str) -> Any:
        for name in names:
            member = getattr(value, name, None)
            if member is not None:
                return member
        return []

    @staticmethod
    def _vector(value: Any) -> list[Any]:
        if value is None:
            return []
        try:
            converted = to_python(value)
        except BackendError:
            converted = list(value) if isinstance(value, Iterable) else []
        if not isinstance(converted, list):
            return [converted]
        return converted

    @classmethod
    def _matrix(cls, value: Any) -> tuple[list[list[Any]], tuple[int, int]]:
        if value is None:
            return [], (0, 0)
        get_length = getattr(value, "GetLength", None)
        if callable(get_length):
            try:
                row_count = int(get_length(0))
                column_count = int(get_length(1))
            except Exception:
                row_count = column_count = 0
            if row_count >= 0 and column_count >= 0:
                flat = cls._vector(value)
                rows = (
                    [
                        flat[offset : offset + column_count]
                        for offset in range(0, row_count * column_count, column_count)
                    ]
                    if column_count
                    else [[] for _ in range(row_count)]
                )
                return rows, (row_count, column_count)
        converted = cls._vector(value)
        if converted and all(isinstance(row, list) for row in converted):
            rows = [list(row) for row in converted]
        else:
            rows = [[item] for item in converted]
        return rows, (len(rows), max((len(row) for row in rows), default=0))

    @staticmethod
    def _transpose(rows: list[list[Any]]) -> list[list[Any]]:
        width = max((len(row) for row in rows), default=0)
        return [[row[column] for row in rows if column < len(row)] for column in range(width)]

    @staticmethod
    def _sample_indices(length: int, limit: int) -> list[int]:
        if length <= 0:
            return []
        if length <= limit:
            return list(range(length))
        if limit == 1:
            return [0]
        return [round(index * (length - 1) / (limit - 1)) for index in range(limit)]

    @staticmethod
    def _copy_labels(source: Any, target: dict[str, Any]) -> None:
        for source_name, target_name in (
            ("Description", "description"),
            ("SeriesLabel", "series_label"),
            ("XLabel", "x_label"),
            ("YLabel", "y_label"),
        ):
            value = getattr(source, source_name, None)
            if value not in (None, ""):
                target[target_name] = str(value)[:512]

    @staticmethod
    def _copy_grid_metadata(source: Any, target: dict[str, Any]) -> None:
        for source_name, target_name in (
            ("Description", "description"),
            ("MinX", "min_x"),
            ("MinY", "min_y"),
            ("Dx", "dx"),
            ("Dy", "dy"),
            ("XLabel", "x_label"),
            ("YLabel", "y_label"),
            ("ZLabel", "z_label"),
        ):
            value = getattr(source, source_name, None)
            if value is not None:
                target[target_name] = to_python(value)
