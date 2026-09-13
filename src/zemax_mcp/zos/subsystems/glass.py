"""Read-only Glasscat access and safe AGF export.

The parser intentionally uses AGF text rather than ZOS-API material objects so catalog
inspection is deterministic, does not consume a license, and never mutates installed
catalogs.  Export writes preserved source records only to an explicit caller directory.
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zemax_mcp.errors import BackendError

Operation = Any
_CATALOG_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _default_glasscat_dirs() -> tuple[Path, ...]:
    """Return existing OpticStudio Glasscat roots, highest precedence first."""
    candidates: list[Path] = []
    explicit = os.environ.get("ZEMAX_MCP_GLASSCAT_DIR", "")
    if explicit.strip():
        candidates.extend(Path(item.strip()) for item in explicit.split(os.pathsep) if item.strip())
    zemax_root = os.environ.get("ZEMAX_MCP_ZEMAX_ROOT")
    if zemax_root:
        candidates.append(Path(zemax_root) / "Glasscat")
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Zemax") as key:
                root, _ = winreg.QueryValueEx(key, "ZemaxRoot")
                if root:
                    candidates.append(Path(root) / "Glasscat")
        except OSError:
            pass
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        candidates.append(Path(program_data) / "Zemax" / "Glasscat")
    else:
        candidates.append(Path(r"C:\ProgramData\Zemax\Glasscat"))
    documents = Path.home() / "Documents" / "Zemax" / "Glasscat"
    candidates.append(documents)

    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        path_key = os.path.normcase(str(resolved))
        if resolved.is_dir() and path_key not in seen:
            seen.add(path_key)
            result.append(resolved)
    return tuple(result)


def _number(token: str | None) -> float | None:
    if token is None or token in {"", "_", "-"}:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _integer(token: str | None) -> int | None:
    value = _number(token)
    return int(value) if value is not None and value.is_integer() else None


@dataclass(frozen=True, slots=True)
class GlassRecord:
    catalog: str
    source_path: Path
    name: str
    formula: int | None
    nd: float | None
    vd: float | None
    exclude_substitution: int | None
    status: int | None
    melt_frequency: int | None
    tce: float | None
    density: float | None
    dpgf: float | None
    relative_cost: float | None
    wavelength_min: float | None
    wavelength_max: float | None
    comment: str | None
    lines: tuple[str, ...]

    @property
    def preferred(self) -> bool:
        # The AGF NM status field uses 1 for preferred, 2 for inquiry and 3 for
        # obsolete/special glasses in current vendor catalogs.
        return self.status == 1

    def as_dict(self, *, distance: float | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "catalog": self.catalog,
            "name": self.name,
            "formula": self.formula,
            "nd": self.nd,
            "vd": self.vd,
            "dpgf": self.dpgf,
            "preferred": self.preferred,
            "status": self.status,
            "exclude_substitution": self.exclude_substitution,
            "relative_cost": self.relative_cost,
            "tce": self.tce,
            "density": self.density,
            "wavelength_min_um": self.wavelength_min,
            "wavelength_max_um": self.wavelength_max,
            "melt_frequency": self.melt_frequency,
            "comment": self.comment,
        }
        if distance is not None:
            result["distance"] = distance
        return result


def parse_agf(path: Path, *, catalog: str | None = None) -> list[GlassRecord]:
    """Parse stable material/filter properties while preserving complete AGF blocks."""
    try:
        text = path.read_text(encoding="latin-1")
    except OSError as exc:
        raise BackendError("get_glasses", f"cannot read catalog {path}: {exc}") from exc
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("NM "):
            if current:
                blocks.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
    if current:
        blocks.append(current)

    records: list[GlassRecord] = []
    catalog_name = catalog or path.stem
    for lines in blocks:
        nm = lines[0].split()
        if len(nm) < 2:
            continue
        fields: dict[str, list[str]] = {}
        comment: str | None = None
        for line in lines[1:]:
            code, _, remainder = line.partition(" ")
            if code == "GC" and comment is None:
                comment = remainder.strip() or None
            elif code in {"ED", "OD", "LD"} and code not in fields:
                fields[code] = remainder.split()
        ed, od, ld = fields.get("ED", []), fields.get("OD", []), fields.get("LD", [])
        records.append(
            GlassRecord(
                catalog=catalog_name,
                source_path=path,
                name=nm[1],
                formula=_integer(nm[2] if len(nm) > 2 else None),
                nd=_number(nm[4] if len(nm) > 4 else None),
                vd=_number(nm[5] if len(nm) > 5 else None),
                exclude_substitution=_integer(nm[6] if len(nm) > 6 else None),
                status=_integer(nm[7] if len(nm) > 7 else None),
                melt_frequency=_integer(nm[8] if len(nm) > 8 else None),
                tce=_number(ed[0] if ed else None),
                density=_number(ed[2] if len(ed) > 2 else None),
                dpgf=_number(ed[3] if len(ed) > 3 else None),
                relative_cost=_number(od[0] if od else None),
                wavelength_min=_number(ld[0] if ld else None),
                wavelength_max=_number(ld[1] if len(ld) > 1 else None),
                comment=comment,
                lines=tuple(lines),
            )
        )
    return records


class GlassOperations:
    def __init__(self, glasscat_dirs: Iterable[Path] | None = None) -> None:
        self._configured_dirs = tuple(glasscat_dirs) if glasscat_dirs is not None else None

    def _roots(self) -> tuple[Path, ...]:
        roots = (
            self._configured_dirs if self._configured_dirs is not None else _default_glasscat_dirs()
        )
        return tuple(Path(root).expanduser().resolve() for root in roots if Path(root).is_dir())

    def _catalogs(self) -> dict[str, Path]:
        catalogs: dict[str, Path] = {}
        # Roots are precedence ordered; retain the first catalog with a given name.
        for root in self._roots():
            for path in sorted(root.glob("*.[Aa][Gg][Ff]"), key=lambda item: item.name.casefold()):
                catalogs.setdefault(path.stem.casefold(), path.resolve())
        return catalogs

    def get_glass_catalogs(self) -> dict[str, Any]:
        catalogs = self._catalogs()
        entries = [
            {"name": path.stem, "file_name": path.name, "path": str(path)}
            for path in sorted(catalogs.values(), key=lambda item: item.stem.casefold())
        ]
        return {
            "count": len(entries),
            "catalogs": [entry["name"] for entry in entries],
            "details": entries,
            "search_paths": [str(p) for p in self._roots()],
        }

    @staticmethod
    def _names(catalogs: str) -> list[str]:
        names = [item.strip() for item in catalogs.split(",") if item.strip()]
        if not names:
            raise BackendError("get_glasses", "provide at least one catalog name")
        return names

    def _records(self, catalogs: str) -> list[GlassRecord]:
        available = self._catalogs()
        records: list[GlassRecord] = []
        missing: list[str] = []
        for requested in self._names(catalogs):
            path = available.get(Path(requested).stem.casefold())
            if path is None:
                missing.append(requested)
            else:
                records.extend(parse_agf(path, catalog=path.stem))
        if missing:
            raise BackendError("get_glasses", f"unknown glass catalog(s): {', '.join(missing)}")
        return records

    def get_glasses(self, catalogs: str) -> dict[str, Any]:
        records = self._records(catalogs)
        return {"count": len(records), "glasses": [record.as_dict() for record in records]}

    def filter_glasses(
        self,
        catalogs: str,
        preferred_only: bool = False,
        distance_radius: float | None = None,
        wn: float = 1.0,
        wa: float = 0.0001,
        wp: float = 100.0,
        nd_target: float = 1.5168,
        vd_target: float = 64.17,
        dpgf_target: float = 0.0,
        max_cost: float | None = None,
        nd_min: float | None = None,
        nd_max: float | None = None,
        vd_min: float | None = None,
        vd_max: float | None = None,
        dpgf_min: float | None = None,
        dpgf_max: float | None = None,
        tce_min: float | None = None,
        tce_max: float | None = None,
        min_wavelength_coverage: float | None = None,
        max_wavelength_coverage: float | None = None,
        max_melt_frequency: int | None = None,
    ) -> dict[str, Any]:
        if any(weight < 0 for weight in (wn, wa, wp)):
            raise BackendError("filter_glasses", "distance weights must be non-negative")
        if distance_radius is not None and distance_radius < 0:
            raise BackendError("filter_glasses", "distance_radius must be non-negative")
        if max_melt_frequency is not None and not 1 <= max_melt_frequency <= 5:
            raise BackendError("filter_glasses", "max_melt_frequency must be 1..5")

        selected: list[tuple[GlassRecord, float]] = []
        for record in self._records(catalogs):
            if preferred_only and not record.preferred:
                continue
            values = (
                (record.relative_cost, None, max_cost),
                (record.nd, nd_min, nd_max),
                (record.vd, vd_min, vd_max),
                (record.dpgf, dpgf_min, dpgf_max),
                (record.tce, tce_min, tce_max),
            )
            if any(
                (upper is not None and (value is None or value > upper))
                or (lower is not None and (value is None or value < lower))
                for value, lower, upper in values
            ):
                continue
            # Coverage inputs describe the requested spectral interval: a catalog
            # glass must reach at least as low/high as each supplied wavelength.
            if min_wavelength_coverage is not None and (
                record.wavelength_min is None or record.wavelength_min > min_wavelength_coverage
            ):
                continue
            if max_wavelength_coverage is not None and (
                record.wavelength_max is None or record.wavelength_max < max_wavelength_coverage
            ):
                continue
            if max_melt_frequency is not None and (
                record.melt_frequency is None or record.melt_frequency > max_melt_frequency
            ):
                continue
            if record.nd is None or record.vd is None or record.dpgf is None:
                distance = math.inf
            else:
                distance = math.sqrt(
                    wn * (record.nd - nd_target) ** 2
                    + wa * (record.vd - vd_target) ** 2
                    + wp * (record.dpgf - dpgf_target) ** 2
                )
            if distance_radius is not None and distance > distance_radius:
                continue
            selected.append((record, distance))
        selected.sort(
            key=lambda item: (item[1], item[0].catalog.casefold(), item[0].name.casefold())
        )
        return {
            "count": len(selected),
            "glasses": [record.as_dict(distance=distance) for record, distance in selected],
        }

    def export_glass_catalog(
        self,
        catalog_name: str,
        source_catalogs: str,
        output_directory: str,
        overwrite: bool = False,
        **filters: Any,
    ) -> dict[str, Any]:
        if not _CATALOG_NAME.fullmatch(catalog_name) or catalog_name.lower().endswith(".agf"):
            raise BackendError(
                "export_glass_catalog", "catalog_name must be a safe name without .agf"
            )
        output_dir = Path(output_directory).expanduser().resolve()
        for root in self._roots():
            try:
                output_dir.relative_to(root)
            except ValueError:
                pass
            else:
                raise BackendError(
                    "export_glass_catalog",
                    "output_directory must be outside installed Glasscat directories",
                )
        if output_dir.exists() and not output_dir.is_dir():
            raise BackendError("export_glass_catalog", "output_directory is not a directory")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{catalog_name}.AGF"
        if output_path.is_symlink():
            raise BackendError("export_glass_catalog", "output catalog may not be a symbolic link")
        if output_path.exists() and not overwrite:
            raise BackendError("export_glass_catalog", f"output already exists: {output_path}")

        filtered = self.filter_glasses(source_catalogs, **filters)
        wanted = {
            (item["catalog"].casefold(), item["name"].casefold()) for item in filtered["glasses"]
        }
        records = [
            record
            for record in self._records(source_catalogs)
            if (record.catalog.casefold(), record.name.casefold()) in wanted
        ]
        lines = [
            f"CC Generated from {source_catalogs}; installed source catalogs were not modified"
        ]
        for record in records:
            lines.extend(record.lines)
        try:
            output_path.write_text("\n".join(lines) + "\n", encoding="latin-1", newline="\n")
        except OSError as exc:
            raise BackendError(
                "export_glass_catalog", f"cannot write {output_path}: {exc}"
            ) from exc
        return {
            "path": str(output_path),
            "catalog_name": catalog_name,
            "count": len(records),
            "bytes": output_path.stat().st_size,
            "overwritten": bool(overwrite),
        }


def build_operation_map(glasscat_dirs: Iterable[Path] | None = None) -> dict[str, Operation]:
    ops = GlassOperations(glasscat_dirs)
    return {
        "get_glass_catalogs": ops.get_glass_catalogs,
        "get_glasses": ops.get_glasses,
        "filter_glasses": ops.filter_glasses,
        "export_glass_catalog": ops.export_glass_catalog,
    }


__all__ = ["GlassOperations", "GlassRecord", "build_operation_map", "parse_agf"]
