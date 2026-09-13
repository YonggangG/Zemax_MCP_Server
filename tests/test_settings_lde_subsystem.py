from __future__ import annotations

from enum import Enum
from types import SimpleNamespace
from typing import Any

import pytest

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.adapters.enums import enum_member
from zemax_mcp.zos.subsystems.settings_lde import build_operation_map


class Named(Enum):
    @property
    def Name(self) -> str:
        return self.name


class ApertureType(Named):
    EntrancePupilDiameter = 1
    ImageSpaceFNum = 2
    ObjectSpaceNA = 3
    FloatByStopSize = 4
    ParaxialWorkingFNum = 5
    ObjectConeAngle = 6


class ApodizationType(Named):
    Uniform = 0
    Gaussian = 1
    CosineCubed = 2


class FieldType(Named):
    Angle = 1
    ObjectHeight = 2
    ParaxialImageHeight = 3
    RealImageHeight = 4
    TheodoliteAngle = 5


class RayAimingMethod(Named):
    Off = 0
    Paraxial = 1
    Real = 2


class MTFUnits(Named):
    CyclesPerMillimeter = 1
    CyclesPerMilliradian = 2


class SystemUnits(Named):
    Millimeters = 0
    Centimeters = 1
    Inches = 2
    Meters = 3


class PolarizationMethod(Named):
    XAxisMethod = 0
    YAxisMethod = 1
    ZAxisMethod = 2


class MaterialCatalogs:
    def __init__(self) -> None:
        self.available = ["SCHOTT", "OHARA", "MISC"]
        self.in_use = ["SCHOTT"]
        self.add_result = True
        self.remove_result = True
        self.apply_add = True
        self.apply_remove = True

    def GetAvailableCatalogs(self) -> list[str]:
        return list(self.available)

    def GetCatalogsInUse(self) -> list[str]:
        return list(self.in_use)

    def IsCatalogInUse(self, name: str) -> bool:
        return name in self.in_use

    def AddCatalog(self, name: str) -> bool:
        if self.add_result and self.apply_add:
            self.in_use.append(name)
        return self.add_result

    def RemoveCatalog(self, name: str) -> bool:
        if self.remove_result and self.apply_remove:
            self.in_use.remove(name)
        return self.remove_result


class SolveType(Named):
    None_ = 0
    Fixed = 1
    Variable = 2
    SurfacePickup = 3
    MarginalRayHeight = 4


class SurfaceType(Named):
    Standard = 1
    EvenAspheric = 2
    CoordinateBreak = 3
    Data = 4


class SurfaceColumn(Named):
    Radius = 1
    Thickness = 2
    Material = 3
    SemiDiameter = 4
    Conic = 5
    Par1 = 11
    Par2 = 12
    Par3 = 13


class Cell:
    def __init__(self, value: Any = 0.0, data_type: str = "Double", header: str = "") -> None:
        self.Header = header
        self.DataType = data_type
        self.IsActive = True
        self.IsReadOnly = False
        self.Solve = SolveType.Fixed
        self.DoubleValue = float(value) if data_type == "Double" else 0.0
        self.IntegerValue = int(value) if data_type == "Integer" else 0
        self.Value = str(value)
        self.solve_data: Any = None

    def MakeSolveVariable(self) -> bool:
        self.Solve = SolveType.Variable
        return True

    def MakeSolveFixed(self) -> bool:
        self.Solve = SolveType.Fixed
        return True

    def CreateSolveType(self, solve_type: SolveType) -> Any:
        data = SimpleNamespace(Type=solve_type, _S_SurfacePickup=SimpleNamespace())
        data._S_MarginalRayHeight = SimpleNamespace()
        return data

    def SetSolveData(self, data: Any) -> None:
        self.solve_data = data
        self.Solve = data.Type


class SurfaceData:
    def __init__(self) -> None:
        self.even = {index: 0.0 for index in range(1, 9)}
        self.even_cells = {index: Cell() for index in range(1, 9)}
        self.extra: dict[int, float] = {}

    def SetNthEvenOrderTerm(self, index: int, value: float) -> None:
        self.even[index] = value

    def GetNthEvenOrderTerm(self, index: int) -> float:
        return self.even[index]

    def NthEvenOrderTermCell(self, index: int) -> Cell:
        return self.even_cells[index]

    def SetNthExtraData(self, index: int, value: float) -> None:
        self.extra[index] = value

    def GetNthExtraData(self, index: int) -> float:
        return self.extra.get(index, 0.0)

    def NthExtraDataCell(self, index: int) -> Cell:
        return Cell(self.GetNthExtraData(index), header=f"XDAT {index}")


class Surface:
    def __init__(self, number: int, surface_type: SurfaceType = SurfaceType.Standard) -> None:
        self.SurfaceNumber = number
        self.Type = surface_type
        self.TypeName = surface_type.name
        self.Comment = f"S{number}"
        self.Radius = float(number)
        self.Thickness = 1.0
        self.Material = ""
        self.SemiDiameter = 5.0
        self.Conic = 0.0
        self.IsStop = number == 1
        self.RadiusCell = Cell(self.Radius, header="Radius")
        self.ThicknessCell = Cell(self.Thickness, header="Thickness")
        self.MaterialCell = Cell("", "String", "Material")
        self.SemiDiameterCell = Cell(self.SemiDiameter, header="Semi-Diameter")
        self.ConicCell = Cell(self.Conic, header="Conic")
        self.SurfaceData = SurfaceData()
        self.parameter_cells = {index: Cell(0.0, header=f"Par{index}") for index in range(1, 4)}

    def AvailableSurfaceTypes(self) -> list[SurfaceType]:
        return list(SurfaceType)

    def GetSurfaceTypeSettings(self, surface_type: SurfaceType) -> Any:
        return SimpleNamespace(IsValid=True, Type=surface_type)

    def ChangeType(self, settings: Any) -> bool:
        self.Type = settings.Type
        self.TypeName = settings.Type.name
        return True

    def GetSurfaceCell(self, column: SurfaceColumn) -> Cell:
        if column.name.startswith("Par"):
            return self.parameter_cells[int(column.name[3:])]
        value = getattr(self, f"{column.name}Cell")
        assert isinstance(value, Cell)
        return value


class LDE:
    def __init__(self) -> None:
        self.rows = [Surface(0), Surface(1), Surface(2), Surface(3)]
        self.StopSurface = 1

    @property
    def NumberOfSurfaces(self) -> int:
        return len(self.rows)

    def GetSurfaceAt(self, index: int) -> Surface:
        return self.rows[index]

    def InsertNewSurfaceAt(self, index: int) -> Surface:
        row = Surface(index)
        self.rows.insert(index, row)
        return row

    def RemoveSurfaceAt(self, index: int) -> bool:
        self.rows.pop(index)
        return True


class Fields:
    def __init__(self) -> None:
        self.rows = [SimpleNamespace(X=0.0, Y=0.0, Weight=1.0)]
        self.field_type = FieldType.Angle

    @property
    def NumberOfFields(self) -> int:
        return len(self.rows)

    def GetField(self, index: int) -> Any:
        return self.rows[index - 1]

    def AddField(self, x: float, y: float, weight: float) -> Any:
        row = SimpleNamespace(X=x, Y=y, Weight=weight)
        self.rows.append(row)
        return row

    def RemoveField(self, index: int) -> bool:
        self.rows.pop(index - 1)
        return True

    def SetFieldType(self, field_type: FieldType) -> None:
        self.field_type = field_type

    def GetFieldType(self) -> FieldType:
        return self.field_type


class Wavelength:
    def __init__(self, owner: Wavelengths, value: float, weight: float) -> None:
        self.owner = owner
        self.Wavelength = value
        self.Weight = weight
        self.IsPrimary = False

    def MakePrimary(self) -> None:
        for row in self.owner.rows:
            row.IsPrimary = False
        self.IsPrimary = True


class Wavelengths:
    def __init__(self) -> None:
        self.rows = [Wavelength(self, 0.55, 1.0)]
        self.rows[0].IsPrimary = True

    @property
    def NumberOfWavelengths(self) -> int:
        return len(self.rows)

    def GetWavelength(self, index: int) -> Wavelength:
        return self.rows[index - 1]

    def AddWavelength(self, value: float, weight: float) -> Wavelength:
        row = Wavelength(self, value, weight)
        self.rows.append(row)
        return row

    def RemoveWavelength(self, index: int) -> bool:
        self.rows.pop(index - 1)
        return True


@pytest.fixture
def fixture() -> tuple[dict[str, Any], Any]:
    api = SimpleNamespace(
        SystemData=SimpleNamespace(
            ZemaxApertureType=ApertureType,
            ZemaxApodizationType=ApodizationType,
            FieldType=FieldType,
            RayAimingMethod=RayAimingMethod,
            ZemaxMTFUnits=MTFUnits,
            ZemaxSystemUnits=SystemUnits,
            PolarizationMethod=PolarizationMethod,
        ),
        Editors=SimpleNamespace(
            SolveType=SolveType,
            LDE=SimpleNamespace(
                SurfaceType=SurfaceType,
                SurfaceColumn=SurfaceColumn,
                ISurfaceData=lambda value: value,
            ),
        ),
    )
    data = SimpleNamespace(
        Aperture=SimpleNamespace(
            ApertureType=ApertureType.EntrancePupilDiameter,
            ApertureValue=10.0,
            ApodizationType=ApodizationType.Uniform,
            ApodizationFactor=0.0,
            ApodizationFactorIsUsed=False,
            SemiDiameterMargin=0.0,
            SemiDiameterMarginPct=0.0,
            AFocalImageSpace=False,
        ),
        RayAiming=SimpleNamespace(
            RayAiming=RayAimingMethod.Off,
            Method="Heuristic",
            UseRayAimingCache=False,
            UseRobustRayAiming=False,
            UseEnhancedRayAiming=False,
        ),
        Units=SimpleNamespace(
            MTFUnits=MTFUnits.CyclesPerMillimeter,
            LensUnits=SystemUnits.Millimeters,
        ),
        TitleNotes=SimpleNamespace(Title="Untitled", Notes="", Author=""),
        Polarization=SimpleNamespace(
            Method=PolarizationMethod.XAxisMethod,
            Unpolarized=False,
            Jx=1.0,
            Jy=0.0,
            XPhase=0.0,
            YPhase=0.0,
            ConvertThinFilmPhaseToRayEquivalent=False,
        ),
        MaterialCatalogs=MaterialCatalogs(),
        Fields=Fields(),
        Wavelengths=Wavelengths(),
    )
    system = SimpleNamespace(SystemData=data, LDE=LDE())
    return build_operation_map(lambda: system, lambda: api), system


def test_enum_helper_is_case_and_punctuation_tolerant() -> None:
    assert enum_member(ApertureType, "image-space f num") is ApertureType.ImageSpaceFNum
    assert (
        enum_member(ApertureType, "EPD", aliases={"epd": "EntrancePupilDiameter"})
        is ApertureType.EntrancePupilDiameter
    )
    with pytest.raises(ValueError, match="unknown enum value"):
        enum_member(ApertureType, "invalid")


def test_settings_operations_and_legacy_aliases(fixture: tuple[dict[str, Any], Any]) -> None:
    operations, _system = fixture
    operations["set_afocal_mode"](afocal_mode=True)
    assert operations["get_afocal_mode"]() == {"afocal_mode": True}
    assert operations["set_aperture"](value=4.0, aperture_type="f-number") == {
        "type": "ImageSpaceFNum",
        "value": 4.0,
    }
    assert operations["set_apodization"](apodization_type="gaussian", factor=1.0)["factor"] == 1.0
    assert operations["set_ray_aiming"](ray_aiming="real")["ray_aiming"] == "Real"
    assert operations["set_mtf_units"](mtf_units="cycles/mrad") == {
        "mtf_units": "CyclesPerMilliradian"
    }
    assert operations["set_clear_semi_diameter_margin"](margin=0.25)["margin"] == 0.25
    assert operations["settings_summary"] is operations["get_settings"]
    with pytest.raises(ValueError, match="positive"):
        operations["set_aperture"](value=0.0)


def test_system_units_title_notes_and_polarization(
    fixture: tuple[dict[str, Any], Any],
) -> None:
    operations, system = fixture
    for unit in SystemUnits:
        assert operations["set_system_units"](lens_units=unit.name) == {"lens_units": unit.name}
    with pytest.raises(ValueError, match="unknown enum value"):
        operations["set_system_units"](lens_units="microns")

    assert operations["get_title_notes"]() == {
        "title": "Untitled",
        "notes": "",
        "author": "",
    }
    assert operations["set_title_notes"](notes="line 1\nline 2") == {
        "title": "Untitled",
        "notes": "line 1\nline 2",
        "author": "",
    }
    assert operations["set_title_notes"](title="", author="Engineering")["title"] == ""
    with pytest.raises(ValueError, match="at least one"):
        operations["set_title_notes"]()

    updated = operations["set_polarization"](
        method="y-axis method",
        unpolarized=False,
        jx=0.6,
        jy=0.8,
        x_phase=10.0,
        y_phase=90.0,
        convert_thin_film_phase_to_ray_equivalent=True,
    )
    assert updated == {
        "method": "YAxisMethod",
        "unpolarized": False,
        "jx": 0.6,
        "jy": 0.8,
        "x_phase": 10.0,
        "y_phase": 90.0,
        "convert_thin_film_phase_to_ray_equivalent": True,
    }
    assert operations["set_polarization"](unpolarized=True)["method"] == "YAxisMethod"
    assert system.SystemData.Polarization.Jx == 0.6
    for method in PolarizationMethod:
        assert operations["set_polarization"](method=method.name)["method"] == method.name
    with pytest.raises(ValueError, match="at least one"):
        operations["set_polarization"]()


def test_material_catalog_membership_is_safe_and_idempotent(
    fixture: tuple[dict[str, Any], Any],
) -> None:
    operations, system = fixture
    catalogs = system.SystemData.MaterialCatalogs

    assert operations["add_material_catalog"](catalog_name=" schott ") == {
        "catalog_name": "SCHOTT",
        "added": False,
        "already_in_use": True,
        "catalogs_in_use": ["SCHOTT"],
    }
    catalogs.available.remove("SCHOTT")
    assert operations["add_material_catalog"](catalog_name="schott")["already_in_use"] is True
    assert operations["add_material_catalog"](catalog_name="ohara") == {
        "catalog_name": "OHARA",
        "added": True,
        "already_in_use": False,
        "catalogs_in_use": ["SCHOTT", "OHARA"],
    }
    assert operations["remove_material_catalog"](catalog_name="oHaRa") == {
        "catalog_name": "OHARA",
        "removed": True,
        "was_in_use": True,
        "catalogs_in_use": ["SCHOTT"],
    }
    assert operations["remove_material_catalog"](catalog_name="misc") == {
        "catalog_name": "MISC",
        "removed": False,
        "was_in_use": False,
        "catalogs_in_use": ["SCHOTT"],
    }
    with pytest.raises(ValueError, match="cannot be empty"):
        operations["add_material_catalog"](catalog_name="  ")
    with pytest.raises(BackendError, match="not available"):
        operations["add_material_catalog"](catalog_name="UNKNOWN")

    catalogs.add_result = False
    with pytest.raises(BackendError, match="did not add"):
        operations["add_material_catalog"](catalog_name="MISC")
    catalogs.add_result = True
    catalogs.apply_add = False
    with pytest.raises(BackendError, match="not in use after add"):
        operations["add_material_catalog"](catalog_name="MISC")
    catalogs.apply_add = True
    catalogs.in_use.append("MISC")
    catalogs.remove_result = False
    with pytest.raises(BackendError, match="did not remove"):
        operations["remove_material_catalog"](catalog_name="MISC")
    catalogs.remove_result = True
    catalogs.apply_remove = False
    with pytest.raises(BackendError, match="still in use after remove"):
        operations["remove_material_catalog"](catalog_name="MISC")


def test_batch_one_operation_registration(fixture: tuple[dict[str, Any], Any]) -> None:
    operations, _system = fixture
    baseline = build_operation_map(lambda: None, lambda: None).keys()
    expected = {
        "get_system_units",
        "set_system_units",
        "get_title_notes",
        "set_title_notes",
        "get_polarization",
        "set_polarization",
        "add_material_catalog",
        "remove_material_catalog",
    }
    assert expected <= operations.keys()
    assert expected == set(baseline) & expected


def test_fields_and_wavelengths_replace_collections(fixture: tuple[dict[str, Any], Any]) -> None:
    operations, _system = fixture
    fields = operations["set_fields"](
        field_type="object height",
        fields=[{"x": 0, "y": 0}, {"x": 1, "y": 2, "weight": 0.5}],
    )
    assert fields == {
        "field_type": "ObjectHeight",
        "fields": [
            {"x": 0.0, "y": 0.0, "weight": 1.0},
            {"x": 1.0, "y": 2.0, "weight": 0.5},
        ],
    }
    wavelengths = operations["set_wavelengths"](wavelengths_um=[0.486, 0.588, 0.656], primary=2)
    assert wavelengths["primary_wavelength"] == 2
    assert [row["wavelength"] for row in wavelengths["wavelengths"]] == [0.486, 0.588, 0.656]


def test_lde_summary_remove_types_parameters_and_solves(
    fixture: tuple[dict[str, Any], Any],
) -> None:
    operations, system = fixture
    assert operations["lde_summary"]()["number_of_surfaces"] == 4
    assert "EvenAspheric" in operations["list_surface_types"]()["surface_types"]
    assert operations["set_surface_type"](1, "coordinate break")["type"] == "CoordinateBreak"
    result = operations["set_surface_parameter"](1, 2, 3.5)
    assert result["value"] == 3.5
    assert operations["set_surface_solve"](1, "radius", "variable")["solve"] == "Variable"
    pickup = operations["set_surface_solve"](
        1, "thickness", "pickup", pickup_surface=2, scale_factor=-1.0
    )
    assert pickup["solve"] == "SurfacePickup"
    assert system.LDE.rows[1].ThicknessCell.solve_data._S_SurfacePickup.Surface == 2
    assert operations["remove_surface"](2) == {"removed": True, "surface_number": 2}
    with pytest.raises(ValueError, match="non-object"):
        operations["remove_surface"](0)


def test_even_asphere_and_extra_data(fixture: tuple[dict[str, Any], Any]) -> None:
    operations, _system = fixture
    result = operations["set_aspheric_surface"](
        1,
        conic=-1.0,
        conic_variable=True,
        alpha1=1e-4,
        alpha2=2e-6,
        alpha2_variable=True,
    )
    assert result["type"] == "EvenAspheric"
    assert result["conic"] == -1.0
    assert result["coefficients"]["alpha1"] == 1e-4
    assert result["coefficient_solves"]["alpha2"] == "Variable"
    with pytest.raises(ValueError, match="not a Data surface"):
        operations["get_extra_data"](1)
    operations["set_surface_type"](1, "Data")
    assert operations["set_extra_data"](
        1, [{"parameter": 1, "value": 2.5}, {"parameter": 2, "value": -1.0}]
    )["values"] == {"1": 2.5, "2": -1.0}
    assert operations["get_extra_data"](1, 1, 2)["values"] == {"1": 2.5, "2": -1.0}
    all_values = operations["get_extra_data"](1, 1, 0)["values"]
    assert len(all_values) == 250
    assert all_values["1"] == 2.5
    assert all_values["250"] == 0.0
