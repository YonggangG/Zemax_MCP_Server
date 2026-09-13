"""System Explorer settings and sequential Lens Data Editor operations.

The implementation stays CLR-free at import time.  Callers inject accessors for the
current optical system and loaded ``ZOSAPI`` module, which also makes the operations
unit-testable without launching OpticStudio.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.adapters.cells import cell_snapshot, get_surface_cell, set_cell_value
from zemax_mcp.zos.adapters.enums import enum_member, enum_name, enum_names
from zemax_mcp.zos.interop import compatible_radius

Accessor = Callable[[], Any]
Operation = Callable[..., Any]

_APERTURE_ALIASES = {
    "epd": "EntrancePupilDiameter",
    "entrance pupil diameter": "EntrancePupilDiameter",
    "fnumber": "ImageSpaceFNum",
    "f-number": "ImageSpaceFNum",
    "image space f number": "ImageSpaceFNum",
    "objectna": "ObjectSpaceNA",
    "object na": "ObjectSpaceNA",
    "floatbystop": "FloatByStopSize",
    "float by stop": "FloatByStopSize",
    "paraxialworkingfnumber": "ParaxialWorkingFNum",
}
_SOLVE_ALIASES = {
    "pickup": "SurfacePickup",
    "surface pickup": "SurfacePickup",
    "ray height": "MarginalRayHeight",
    "ray angle": "MarginalRayAngle",
    "edge thickness": "EdgeThickness",
    "f number": "FNumber",
    "material substitute": "MaterialSubstitute",
    "material offset": "MaterialOffset",
}
_MTF_ALIASES = {
    "cycles/mm": "CyclesPerMillimeter",
    "cycles per mm": "CyclesPerMillimeter",
    "cycles/mrad": "CyclesPerMilliradian",
    "cycles per milliradian": "CyclesPerMilliradian",
}


class SettingsLDEOperations:
    """Bound operation collection for one ``RealZOSBackend``-like owner."""

    def __init__(self, require_system: Accessor, api: Accessor) -> None:
        self._require_system = require_system
        self._get_api = api

    def _system(self) -> Any:
        return self._require_system()

    def _api(self) -> Any:
        return self._get_api()

    def _data(self) -> Any:
        return self._system().SystemData

    def _lde(self) -> Any:
        return self._system().LDE

    def _surface(self, surface_number: int) -> Any:
        lde = self._lde()
        count = int(lde.NumberOfSurfaces)
        index = count - 1 if surface_number == -1 else int(surface_number)
        if index < 0 or index >= count:
            raise ValueError(f"surface {surface_number} is out of range 0..{count - 1}")
        return lde.GetSurfaceAt(index)

    # System Explorer settings -------------------------------------------------

    def get_afocal_mode(self) -> dict[str, bool]:
        return {"afocal_mode": bool(self._data().Aperture.AFocalImageSpace)}

    def set_afocal_mode(self, afocal_mode: bool) -> dict[str, bool]:
        self._data().Aperture.AFocalImageSpace = bool(afocal_mode)
        return self.get_afocal_mode()

    def set_aperture(self, value: float, aperture_type: str = "EPD") -> dict[str, Any]:
        if value <= 0:
            raise ValueError("aperture value must be positive")
        aperture = self._data().Aperture
        aperture.ApertureType = enum_member(
            self._api().SystemData.ZemaxApertureType,
            aperture_type,
            aliases=_APERTURE_ALIASES,
        )
        aperture.ApertureValue = float(value)
        return {
            "type": enum_name(aperture.ApertureType),
            "value": float(aperture.ApertureValue),
        }

    def get_apodization(self) -> dict[str, Any]:
        aperture = self._data().Aperture
        return {
            "type": enum_name(aperture.ApodizationType),
            "factor": float(aperture.ApodizationFactor),
            "factor_is_used": bool(getattr(aperture, "ApodizationFactorIsUsed", False)),
        }

    def set_apodization(self, apodization_type: str, factor: float = 0.0) -> dict[str, Any]:
        aperture = self._data().Aperture
        aperture.ApodizationType = enum_member(
            self._api().SystemData.ZemaxApodizationType, apodization_type
        )
        aperture.ApodizationFactor = float(factor)
        return self.get_apodization()

    def get_clear_semi_diameter_margin(self) -> dict[str, float]:
        aperture = self._data().Aperture
        return {
            "margin": float(aperture.SemiDiameterMargin),
            "margin_percent": float(getattr(aperture, "SemiDiameterMarginPct", 0.0)),
        }

    def set_clear_semi_diameter_margin(self, margin: float) -> dict[str, float]:
        if margin < 0:
            raise ValueError("clear semi-diameter margin cannot be negative")
        self._data().Aperture.SemiDiameterMargin = float(margin)
        return self.get_clear_semi_diameter_margin()

    def get_ray_aiming(self) -> dict[str, Any]:
        aiming = self._data().RayAiming
        return {
            "ray_aiming": enum_name(aiming.RayAiming),
            "method": enum_name(getattr(aiming, "Method", "")),
            "use_cache": bool(getattr(aiming, "UseRayAimingCache", False)),
            "robust": bool(getattr(aiming, "UseRobustRayAiming", False)),
            "enhanced": bool(getattr(aiming, "UseEnhancedRayAiming", False)),
        }

    def set_ray_aiming(self, ray_aiming: str) -> dict[str, Any]:
        aiming = self._data().RayAiming
        aiming.RayAiming = enum_member(self._api().SystemData.RayAimingMethod, ray_aiming)
        return self.get_ray_aiming()

    def get_mtf_units(self) -> dict[str, str]:
        return {"mtf_units": enum_name(self._data().Units.MTFUnits)}

    def set_mtf_units(self, mtf_units: str) -> dict[str, str]:
        self._data().Units.MTFUnits = enum_member(
            self._api().SystemData.ZemaxMTFUnits, mtf_units, aliases=_MTF_ALIASES
        )
        return self.get_mtf_units()

    def get_system_units(self) -> dict[str, str]:
        return {"lens_units": enum_name(self._data().Units.LensUnits)}

    def set_system_units(self, lens_units: str) -> dict[str, str]:
        self._data().Units.LensUnits = enum_member(
            self._api().SystemData.ZemaxSystemUnits, lens_units
        )
        return self.get_system_units()

    def get_title_notes(self) -> dict[str, str]:
        title_notes = self._data().TitleNotes
        return {
            "title": str(title_notes.Title),
            "notes": str(title_notes.Notes),
            "author": str(title_notes.Author),
        }

    def set_title_notes(
        self,
        *,
        title: str | None = None,
        notes: str | None = None,
        author: str | None = None,
    ) -> dict[str, str]:
        changes = {"Title": title, "Notes": notes, "Author": author}
        if all(value is None for value in changes.values()):
            raise ValueError("provide at least one of title, notes, or author")
        title_notes = self._data().TitleNotes
        for name, value in changes.items():
            if value is not None:
                setattr(title_notes, name, value)
        return self.get_title_notes()

    def get_polarization(self) -> dict[str, Any]:
        polarization = self._data().Polarization
        return {
            "method": enum_name(polarization.Method),
            "unpolarized": bool(polarization.Unpolarized),
            "jx": float(polarization.Jx),
            "jy": float(polarization.Jy),
            "x_phase": float(polarization.XPhase),
            "y_phase": float(polarization.YPhase),
            "convert_thin_film_phase_to_ray_equivalent": bool(
                polarization.ConvertThinFilmPhaseToRayEquivalent
            ),
        }

    def set_polarization(
        self,
        *,
        method: str | None = None,
        unpolarized: bool | None = None,
        jx: float | None = None,
        jy: float | None = None,
        x_phase: float | None = None,
        y_phase: float | None = None,
        convert_thin_film_phase_to_ray_equivalent: bool | None = None,
    ) -> dict[str, Any]:
        changes = {
            "Unpolarized": unpolarized,
            "Jx": jx,
            "Jy": jy,
            "XPhase": x_phase,
            "YPhase": y_phase,
            "ConvertThinFilmPhaseToRayEquivalent": convert_thin_film_phase_to_ray_equivalent,
        }
        if method is None and all(value is None for value in changes.values()):
            raise ValueError("provide at least one polarization setting")
        polarization = self._data().Polarization
        if method is not None:
            polarization.Method = enum_member(self._api().SystemData.PolarizationMethod, method)
        for name, value in changes.items():
            if value is not None:
                setattr(polarization, name, value)
        return self.get_polarization()

    def _material_catalogs(self) -> Any:
        return self._data().MaterialCatalogs

    @staticmethod
    def _catalog_names(values: Any) -> list[str]:
        return [str(value) for value in values]

    def _catalog_name(self, catalog_name: str, *, require_available: bool) -> str:
        requested = catalog_name.strip()
        if not requested:
            raise ValueError("catalog_name cannot be empty")
        catalogs = self._material_catalogs()
        available = self._catalog_names(catalogs.GetAvailableCatalogs())
        canonical = next(
            (name for name in available if name.casefold() == requested.casefold()), None
        )
        if canonical is not None:
            return canonical
        in_use = self._catalog_names(catalogs.GetCatalogsInUse())
        canonical = next((name for name in in_use if name.casefold() == requested.casefold()), None)
        if canonical is not None:
            return canonical
        if require_available:
            raise BackendError(
                "add_material_catalog", f"material catalog {requested!r} is not available"
            )
        return requested

    def add_material_catalog(self, catalog_name: str) -> dict[str, Any]:
        catalogs = self._material_catalogs()
        canonical = self._catalog_name(catalog_name, require_available=True)
        before = self._catalog_names(catalogs.GetCatalogsInUse())
        already_in_use = bool(catalogs.IsCatalogInUse(canonical)) or any(
            name.casefold() == canonical.casefold() for name in before
        )
        if not already_in_use and catalogs.AddCatalog(canonical) is False:
            raise BackendError(
                "add_material_catalog", f"OpticStudio did not add material catalog {canonical!r}"
            )
        after = self._catalog_names(catalogs.GetCatalogsInUse())
        if not any(name.casefold() == canonical.casefold() for name in after):
            raise BackendError(
                "add_material_catalog",
                f"material catalog {canonical!r} is not in use after add",
            )
        return {
            "catalog_name": canonical,
            "added": not already_in_use,
            "already_in_use": already_in_use,
            "catalogs_in_use": after,
        }

    def remove_material_catalog(self, catalog_name: str) -> dict[str, Any]:
        catalogs = self._material_catalogs()
        canonical = self._catalog_name(catalog_name, require_available=False)
        before = self._catalog_names(catalogs.GetCatalogsInUse())
        active_name = next(
            (name for name in before if name.casefold() == canonical.casefold()), None
        )
        was_in_use = active_name is not None
        if active_name is not None:
            canonical = active_name
            if catalogs.RemoveCatalog(canonical) is False:
                raise BackendError(
                    "remove_material_catalog",
                    f"OpticStudio did not remove material catalog {canonical!r}",
                )
        after = self._catalog_names(catalogs.GetCatalogsInUse())
        if was_in_use and any(name.casefold() == canonical.casefold() for name in after):
            raise BackendError(
                "remove_material_catalog",
                f"material catalog {canonical!r} is still in use after remove",
            )
        return {
            "catalog_name": canonical,
            "removed": was_in_use,
            "was_in_use": was_in_use,
            "catalogs_in_use": after,
        }

    def set_fields(
        self,
        fields: Sequence[Mapping[str, Any]] | None = None,
        *,
        field_type: str = "Angle",
        points: Sequence[Sequence[float]] | None = None,
    ) -> dict[str, Any]:
        rows = list(fields or ())
        if points is not None:
            if rows:
                raise ValueError("provide fields or points, not both")
            rows = [{"x": point[0], "y": point[1]} for point in points]
        if not rows:
            raise ValueError("at least one field is required")
        collection = self._data().Fields
        collection.SetFieldType(enum_member(self._api().SystemData.FieldType, field_type))
        while int(collection.NumberOfFields) > len(rows):
            collection.RemoveField(int(collection.NumberOfFields))
        while int(collection.NumberOfFields) < len(rows):
            collection.AddField(0.0, 0.0, 1.0)
        for index, raw in enumerate(rows, 1):
            row = collection.GetField(index)
            row.X = float(raw.get("x", 0.0))
            row.Y = float(raw.get("y", 0.0))
            row.Weight = float(raw.get("weight", 1.0))
        return self._fields_snapshot()

    def set_number_of_fields(self, number_of_fields: int) -> dict[str, Any]:
        count = int(number_of_fields)
        if count < 1:
            raise ValueError("number_of_fields must be at least 1")
        collection = self._data().Fields
        while int(collection.NumberOfFields) > count:
            collection.RemoveField(int(collection.NumberOfFields))
        while int(collection.NumberOfFields) < count:
            collection.AddField(0.0, 0.0, 1.0)
        return self._fields_snapshot()

    def _fields_snapshot(self) -> dict[str, Any]:
        collection = self._data().Fields
        return {
            "field_type": enum_name(collection.GetFieldType()),
            "fields": [
                {
                    "x": float(collection.GetField(index).X),
                    "y": float(collection.GetField(index).Y),
                    "weight": float(collection.GetField(index).Weight),
                }
                for index in range(1, int(collection.NumberOfFields) + 1)
            ],
        }

    def set_wavelengths(
        self,
        wavelengths: Sequence[Mapping[str, Any]] | None = None,
        *,
        wavelengths_um: Sequence[float] | None = None,
        primary_wavelength: int = 1,
        primary: int | None = None,
    ) -> dict[str, Any]:
        rows = list(wavelengths or ())
        if wavelengths_um is not None:
            if rows:
                raise ValueError("provide wavelengths or wavelengths_um, not both")
            rows = [{"wavelength": value} for value in wavelengths_um]
        if not rows:
            raise ValueError("at least one wavelength is required")
        selected_primary = int(primary if primary is not None else primary_wavelength)
        if selected_primary < 1 or selected_primary > len(rows):
            raise ValueError("primary wavelength is out of range")
        collection = self._data().Wavelengths
        while int(collection.NumberOfWavelengths) > len(rows):
            collection.RemoveWavelength(int(collection.NumberOfWavelengths))
        while int(collection.NumberOfWavelengths) < len(rows):
            collection.AddWavelength(0.55, 1.0)
        for index, raw in enumerate(rows, 1):
            row = collection.GetWavelength(index)
            row.Wavelength = float(raw["wavelength"])
            row.Weight = float(raw.get("weight", 1.0))
        collection.GetWavelength(selected_primary).MakePrimary()
        return self._wavelengths_snapshot()

    def set_number_of_wavelengths(self, number_of_wavelengths: int) -> dict[str, Any]:
        count = int(number_of_wavelengths)
        if count < 1:
            raise ValueError("number_of_wavelengths must be at least 1")
        collection = self._data().Wavelengths
        while int(collection.NumberOfWavelengths) > count:
            collection.RemoveWavelength(int(collection.NumberOfWavelengths))
        while int(collection.NumberOfWavelengths) < count:
            collection.AddWavelength(0.55, 1.0)
        return self._wavelengths_snapshot()

    def _wavelengths_snapshot(self) -> dict[str, Any]:
        collection = self._data().Wavelengths
        rows = []
        primary = 1
        for index in range(1, int(collection.NumberOfWavelengths) + 1):
            row = collection.GetWavelength(index)
            if bool(row.IsPrimary):
                primary = index
            rows.append({"wavelength": float(row.Wavelength), "weight": float(row.Weight)})
        return {"primary_wavelength": primary, "wavelengths": rows}

    def get_settings(self) -> dict[str, Any]:
        aperture = self._data().Aperture
        return {
            "afocal_mode": bool(aperture.AFocalImageSpace),
            "aperture": {
                "type": enum_name(aperture.ApertureType),
                "value": float(aperture.ApertureValue),
            },
            "apodization": self.get_apodization(),
            "ray_aiming": self.get_ray_aiming(),
            "mtf_units": self.get_mtf_units()["mtf_units"],
            "lens_units": self.get_system_units()["lens_units"],
            "title_notes": self.get_title_notes(),
            "polarization": self.get_polarization(),
            "clear_semi_diameter": self.get_clear_semi_diameter_margin(),
            **self._fields_snapshot(),
            **self._wavelengths_snapshot(),
        }

    # Lens Data Editor ---------------------------------------------------------

    def lde_summary(self) -> dict[str, Any]:
        lde = self._lde()
        return {
            "number_of_surfaces": int(lde.NumberOfSurfaces),
            "stop_surface": int(getattr(lde, "StopSurface", -1)),
            "surfaces": [self._surface_snapshot(i) for i in range(int(lde.NumberOfSurfaces))],
        }

    def _surface_snapshot(self, surface_number: int) -> dict[str, Any]:
        row = self._surface(surface_number)
        return {
            "surface_number": surface_number,
            "type": enum_name(getattr(row, "Type", getattr(row, "TypeName", ""))),
            "comment": str(row.Comment),
            "radius": compatible_radius(row.Radius),
            "thickness": float(row.Thickness),
            "material": str(row.Material),
            "semi_diameter": float(row.SemiDiameter),
            "conic": float(row.Conic),
            "is_stop": bool(row.IsStop),
        }

    def insert_surface(self, position: int) -> dict[str, Any]:
        lde = self._lde()
        index = int(position)
        count = int(lde.NumberOfSurfaces)
        if index <= 0 or index >= count:
            raise ValueError(f"position must be 1..{max(count - 1, 1)}")
        lde.InsertNewSurfaceAt(index)
        return self._surface_snapshot(index)

    def remove_surface(self, surface_number: int) -> dict[str, Any]:
        lde = self._lde()
        count = int(lde.NumberOfSurfaces)
        if surface_number <= 0 or surface_number >= count - 1:
            raise ValueError("only non-object, non-image surfaces may be removed")
        removed = bool(lde.RemoveSurfaceAt(int(surface_number)))
        return {"removed": removed, "surface_number": int(surface_number)}

    def list_surface_types(self, surface_number: int = 1) -> dict[str, Any]:
        row = self._surface(surface_number)
        available = getattr(row, "AvailableSurfaceTypes", None)
        values = available() if callable(available) else ()
        names = [enum_name(value) for value in values]
        if not names:
            names = list(enum_names(self._api().Editors.LDE.SurfaceType))
        return {"surface_types": names}

    def set_surface_common(
        self,
        surface: int,
        *,
        radius: float | None = None,
        thickness: float | None = None,
        material: str | None = None,
        comment: str | None = None,
        semi_diameter: float | None = None,
    ) -> dict[str, Any]:
        row = self._surface(surface)
        changes = {
            "Radius": radius,
            "Thickness": thickness,
            "Material": material,
            "Comment": comment,
            "SemiDiameter": semi_diameter,
        }
        for name, value in changes.items():
            if value is not None:
                setattr(row, name, value)
        return self._surface_snapshot(surface)

    def set_surface_variable(self, surface: int, cell: str = "thickness") -> dict[str, Any]:
        row = self._surface(surface)
        editor_cell = get_surface_cell(row, self._api(), cell)
        editor_cell.MakeSolveVariable()
        return {"surface_number": surface, "property": cell, **cell_snapshot(editor_cell)}

    def set_surface_type(self, surface_number: int, surface_type: str) -> dict[str, Any]:
        row = self._surface(surface_number)
        selected = enum_member(self._api().Editors.LDE.SurfaceType, surface_type)
        settings = row.GetSurfaceTypeSettings(selected)
        if not bool(getattr(settings, "IsValid", True)):
            raise ValueError(
                f"surface type {surface_type!r} is not valid for surface {surface_number}"
            )
        if row.ChangeType(settings) is False:
            raise RuntimeError(f"OpticStudio did not change surface {surface_number} type")
        return self._surface_snapshot(surface_number)

    def set_surface_parameter(
        self, surface_number: int, parameter: int, value: Any
    ) -> dict[str, Any]:
        row = self._surface(surface_number)
        cell = get_surface_cell(row, self._api(), "", int(parameter))
        set_cell_value(cell, value)
        return {"surface_number": surface_number, "parameter": parameter, **cell_snapshot(cell)}

    def get_surface_solves(
        self, surface_number: int, *, include_parameters: int = 0
    ) -> dict[str, Any]:
        row = self._surface(surface_number)
        properties = ["radius", "thickness", "material", "semi_diameter", "conic"]
        solves = {
            name: cell_snapshot(get_surface_cell(row, self._api(), name)) for name in properties
        }
        parameters = {
            str(index): cell_snapshot(get_surface_cell(row, self._api(), "", index))
            for index in range(1, max(0, int(include_parameters)) + 1)
        }
        return {"surface_number": surface_number, "solves": solves, "parameters": parameters}

    def set_surface_solve(
        self,
        surface_number: int,
        property: str,
        solve_type: str,
        *,
        parameter: int | None = None,
        pickup_surface: int | None = None,
        pickup_column: str | None = None,
        scale_factor: float = 1.0,
        offset: float = 0.0,
        height: float | None = None,
        pupil_zone: float | None = None,
        thickness: float | None = None,
        radial_height: float | None = None,
        position: float | None = None,
        reference_surface: int | None = None,
        f_number: float | None = None,
        catalog: str | None = None,
        index_offset: float | None = None,
    ) -> dict[str, Any]:
        row = self._surface(surface_number)
        cell = get_surface_cell(row, self._api(), property, parameter)
        selected = enum_member(self._api().Editors.SolveType, solve_type, aliases=_SOLVE_ALIASES)
        selected_name = enum_name(selected).casefold()
        if selected_name == "variable":
            cell.MakeSolveVariable()
        elif selected_name in {"fixed", "none"}:
            cell.MakeSolveFixed()
        else:
            data = cell.CreateSolveType(selected)
            if selected_name == "surfacepickup":
                if pickup_surface is None:
                    raise ValueError("pickup_surface is required for a surface pickup solve")
                target = data._S_SurfacePickup
                target.Surface = int(pickup_surface)
                target.ScaleFactor = float(scale_factor)
                target.Offset = float(offset)
                if pickup_column is not None:
                    target.Column = enum_member(
                        self._api().Editors.LDE.SurfaceColumn, pickup_column
                    )
            else:
                target = getattr(data, f"_S_{enum_name(selected)}")
                assignments = {
                    "Height": height,
                    "PupilZone": pupil_zone,
                    "Thickness": thickness,
                    "RadialHeight": radial_height,
                    "Length": position,
                    "FromSurface": reference_surface,
                    "FNumber": f_number,
                    "Catalog": catalog,
                    "NdOffset": index_offset,
                }
                for name, value in assignments.items():
                    if value is not None and hasattr(target, name):
                        setattr(target, name, value)
            cell.SetSolveData(data)
        return {"surface_number": surface_number, "property": property, **cell_snapshot(cell)}

    def set_aspheric_surface(
        self,
        surface_number: int,
        *,
        conic: float | None = None,
        conic_variable: bool = False,
        **values: Any,
    ) -> dict[str, Any]:
        row = self._surface(surface_number)
        if enum_name(row.Type) != "EvenAspheric":
            self.set_surface_type(surface_number, "EvenAspheric")
            row = self._surface(surface_number)
        if conic is not None:
            row.Conic = float(conic)
        if conic_variable:
            row.ConicCell.MakeSolveVariable()
        surface_data = row.SurfaceData
        for index in range(1, 9):
            key = f"alpha{index}"
            if values.get(key) is not None:
                surface_data.SetNthEvenOrderTerm(index, float(values[key]))
            if bool(values.get(f"{key}_variable", False)):
                surface_data.NthEvenOrderTermCell(index).MakeSolveVariable()
        return self.get_aspheric_surface(surface_number)

    def get_aspheric_surface(self, surface_number: int) -> dict[str, Any]:
        row = self._surface(surface_number)
        if enum_name(row.Type) != "EvenAspheric":
            raise ValueError(f"surface {surface_number} is not an EvenAspheric surface")
        data = row.SurfaceData
        return {
            "surface_number": surface_number,
            "type": "EvenAspheric",
            "conic": float(row.Conic),
            "conic_solve": enum_name(row.ConicCell.Solve),
            "coefficients": {
                f"alpha{index}": float(data.GetNthEvenOrderTerm(index)) for index in range(1, 9)
            },
            "coefficient_solves": {
                f"alpha{index}": enum_name(data.NthEvenOrderTermCell(index).Solve)
                for index in range(1, 9)
            },
        }

    def _extra_data_surface(self, surface_number: int) -> Any:
        """Return the type-specific Data-surface interface used by XDAT cells."""

        row = self._surface(surface_number)
        if enum_name(row.Type) != "Data":
            raise ValueError(f"surface {surface_number} is not a Data surface")
        surface_data = row.SurfaceData
        data_interface = getattr(self._api().Editors.LDE, "ISurfaceData", None)
        if data_interface is not None:
            surface_data = data_interface(surface_data)
        if not all(
            callable(getattr(surface_data, name, None))
            for name in ("NthExtraDataCell", "GetNthExtraData", "SetNthExtraData")
        ):
            raise RuntimeError("Data-surface XDAT interface is unavailable")
        return surface_data

    def get_extra_data(
        self, surface_number: int, start_parameter: int = 1, end_parameter: int = 0
    ) -> dict[str, Any]:
        if start_parameter < 1:
            raise ValueError("start_parameter must be at least 1")
        if end_parameter and end_parameter < start_parameter:
            raise ValueError("end_parameter must not precede start_parameter")
        data = self._extra_data_surface(surface_number)
        last = int(end_parameter) if end_parameter else 250
        values: dict[str, float] = {}
        for index in range(int(start_parameter), last + 1):
            cell = data.NthExtraDataCell(index)
            if not bool(getattr(cell, "IsActive", True)):
                if end_parameter == 0:
                    break
                continue
            values[str(index)] = float(data.GetNthExtraData(index))
        return {"surface_number": surface_number, "values": values}

    def set_extra_data(
        self, surface_number: int, values: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        data = self._extra_data_surface(surface_number)
        changed: dict[str, float] = {}
        for item in values:
            parameter = int(item["parameter"])
            if parameter < 1:
                raise ValueError("extra-data parameter must be at least 1")
            cell = data.NthExtraDataCell(parameter)
            if not bool(getattr(cell, "IsActive", True)):
                raise ValueError(
                    f"extra-data parameter {parameter} is inactive for surface {surface_number}"
                )
            if bool(getattr(cell, "IsReadOnly", False)):
                raise ValueError(
                    f"extra-data parameter {parameter} is read-only for surface {surface_number}"
                )
            value = float(item["value"])
            data.SetNthExtraData(parameter, value)
            changed[str(parameter)] = float(data.GetNthExtraData(parameter))
        return {"surface_number": surface_number, "values": changed}


def build_operation_map(require_system: Accessor, api: Accessor) -> dict[str, Operation]:
    """Build the settings/LDE dispatch map for later backend composition.

    Aliases intentionally point to the same bound callable so integration can reject
    only true collisions, not subtly divergent legacy implementations.
    """

    ops = SettingsLDEOperations(require_system, api)
    mapping: dict[str, Operation] = {
        "get_settings": ops.get_settings,
        "get_afocal_mode": ops.get_afocal_mode,
        "set_afocal_mode": ops.set_afocal_mode,
        "set_aperture": ops.set_aperture,
        "get_apodization": ops.get_apodization,
        "set_apodization": ops.set_apodization,
        "get_clear_semi_diameter_margin": ops.get_clear_semi_diameter_margin,
        "set_clear_semi_diameter_margin": ops.set_clear_semi_diameter_margin,
        "get_ray_aiming": ops.get_ray_aiming,
        "set_ray_aiming": ops.set_ray_aiming,
        "get_mtf_units": ops.get_mtf_units,
        "set_mtf_units": ops.set_mtf_units,
        "get_system_units": ops.get_system_units,
        "set_system_units": ops.set_system_units,
        "get_title_notes": ops.get_title_notes,
        "set_title_notes": ops.set_title_notes,
        "get_polarization": ops.get_polarization,
        "set_polarization": ops.set_polarization,
        "add_material_catalog": ops.add_material_catalog,
        "remove_material_catalog": ops.remove_material_catalog,
        "set_fields": ops.set_fields,
        "set_number_of_fields": ops.set_number_of_fields,
        "set_wavelengths": ops.set_wavelengths,
        "set_number_of_wavelengths": ops.set_number_of_wavelengths,
        "lde_summary": ops.lde_summary,
        "lde_insert_surface": ops.insert_surface,
        "lde_set_surface": ops.set_surface_common,
        "set_variable": ops.set_surface_variable,
        "remove_surface": ops.remove_surface,
        "list_surface_types": ops.list_surface_types,
        "set_surface_type": ops.set_surface_type,
        "set_surface_parameter": ops.set_surface_parameter,
        "get_surface_solves": ops.get_surface_solves,
        "set_surface_solve": ops.set_surface_solve,
        "set_aspheric_surface": ops.set_aspheric_surface,
        "get_aspheric_surface": ops.get_aspheric_surface,
        "get_extra_data": ops.get_extra_data,
        "set_extra_data": ops.set_extra_data,
    }
    aliases = {
        "settings_summary": "get_settings",
        "get_system_settings": "get_settings",
        "get_lde_summary": "lde_summary",
        "lde_remove_surface": "remove_surface",
        "get_surface_extra_data": "get_extra_data",
        "set_surface_extra_data": "set_extra_data",
    }
    mapping.update({alias: mapping[target] for alias, target in aliases.items()})
    return mapping
