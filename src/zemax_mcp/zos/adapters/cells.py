"""Reusable editor-cell access and serialization helpers."""

from __future__ import annotations

from typing import Any

from .enums import enum_member, enum_name

_CELL_PROPERTIES = {
    "comment": "CommentCell",
    "radius": "RadiusCell",
    "thickness": "ThicknessCell",
    "material": "MaterialCell",
    "coating": "CoatingCell",
    "semi_diameter": "SemiDiameterCell",
    "semidiameter": "SemiDiameterCell",
    "chip_zone": "ChipZoneCell",
    "mechanical_semi_diameter": "MechanicalSemiDiameterCell",
    "conic": "ConicCell",
    "tce": "TCECell",
}


def get_surface_cell(
    surface: Any, api: Any, property_name: str, parameter: int | None = None
) -> Any:
    """Resolve a named LDE cell or one-based surface parameter cell."""

    if parameter is not None:
        if parameter < 0:
            raise ValueError("parameter must be non-negative")
        column = enum_member(api.Editors.LDE.SurfaceColumn, f"Par{parameter}")
        return surface.GetSurfaceCell(column)
    key = property_name.strip().casefold().replace("-", "_").replace(" ", "_")
    attribute = _CELL_PROPERTIES.get(key)
    if attribute is None:
        column = enum_member(api.Editors.LDE.SurfaceColumn, property_name)
        return surface.GetSurfaceCell(column)
    return getattr(surface, attribute)


def set_cell_value(cell: Any, value: Any) -> None:
    """Assign through the ZOS editor cell's declared data type when possible."""

    data_type = enum_name(getattr(cell, "DataType", "")).casefold()
    if "integer" in data_type:
        cell.IntegerValue = int(value)
    elif "double" in data_type or "float" in data_type:
        cell.DoubleValue = float(value)
    else:
        cell.Value = str(value)


def cell_snapshot(cell: Any) -> dict[str, Any]:
    """Serialize the portable portion of an editor cell and its solve."""

    data_type = enum_name(getattr(cell, "DataType", ""))
    lowered = data_type.casefold()
    if "integer" in lowered:
        value: Any = int(getattr(cell, "IntegerValue", 0))
    elif "double" in lowered or "float" in lowered:
        value = float(getattr(cell, "DoubleValue", 0.0))
    else:
        value = str(getattr(cell, "Value", ""))
    return {
        "header": str(getattr(cell, "Header", "")),
        "active": bool(getattr(cell, "IsActive", True)),
        "read_only": bool(getattr(cell, "IsReadOnly", False)),
        "data_type": data_type,
        "value": value,
        "solve": enum_name(getattr(cell, "Solve", "None")),
    }
