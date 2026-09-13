from __future__ import annotations

from enum import Enum
from types import SimpleNamespace
from typing import Any

import pytest

from zemax_mcp.errors import BackendError, UnsupportedOperationError
from zemax_mcp.zos.subsystems.nsc import NSCSubsystem, build_operation_map


class Named(Enum):
    @property
    def Name(self) -> str:
        return self.name


class SystemType(Named):
    Sequential = 1
    NonSequential = 2


class ObjectType(Named):
    NullObject = 1
    SourcePoint = 2
    DetectorRectangle = 3


class ObjectColumn(Named):
    Par1 = 11
    Par2 = 12
    Par3 = 13


class DetectorDataType(Named):
    Real = 0
    Imaginary = 1
    Amplitude = 2
    Power = 3


class Cell:
    def __init__(self, value: Any = 0.0, data_type: str = "Double") -> None:
        self.Header = "Parameter"
        self.DataType = data_type
        self.IsActive = True
        self.IsReadOnly = False
        self.DoubleValue = float(value) if data_type == "Double" else 0.0
        self.IntegerValue = int(value) if data_type == "Integer" else 0
        self.Value = str(value)
        self.Solve = "Fixed"


class Object:
    def __init__(self, number: int) -> None:
        self.ObjectNumber = number
        self.Type = ObjectType.NullObject
        self.TypeName = self.Type.name
        self.Comment = ""
        self.Material = ""
        self.RefObject = 0
        self.InsideOf = 0
        self.XPosition = self.YPosition = self.ZPosition = 0.0
        self.TiltAboutX = self.TiltAboutY = self.TiltAboutZ = 0.0
        self.ObjectData = SimpleNamespace(NumberOfAnalysisRays=10, NumberXPixels=2, NumberYPixels=2)
        self.cells = {
            ObjectColumn.Par1: Cell(),
            ObjectColumn.Par2: Cell(2, "Integer"),
            ObjectColumn.Par3: Cell("a", "String"),
        }

    def AvailableParameters(self) -> list[str]:
        return ["Width", "Count", "Label"]

    def GetObjectCell(self, column: ObjectColumn) -> Cell:
        return self.cells[column]

    def GetObjectTypeSettings(self, object_type: ObjectType) -> Any:
        return SimpleNamespace(Type=object_type, IsValid=True)

    def ChangeType(self, settings: Any) -> bool:
        self.Type = settings.Type
        self.TypeName = settings.Type.name
        return True


class NCE:
    def __init__(self) -> None:
        self.objects = [Object(1)]

    @property
    def NumberOfObjects(self) -> int:
        return len(self.objects)

    def _renumber(self) -> None:
        for index, obj in enumerate(self.objects, 1):
            obj.ObjectNumber = index

    def GetObjectAt(self, number: int) -> Object:
        return self.objects[number - 1]

    def AddObject(self) -> Object:
        obj = Object(len(self.objects) + 1)
        self.objects.append(obj)
        return obj

    def InsertNewObjectAt(self, number: int) -> Object:
        obj = Object(number)
        self.objects.insert(number - 1, obj)
        self._renumber()
        return obj

    def RemoveObjectAt(self, number: int) -> bool:
        self.objects.pop(number - 1)
        self._renumber()
        return True

    def GetDetectorData(
        self, _obj: int, pixel: int, _data: int, _placeholder: float
    ) -> tuple[bool, float]:
        return True, float(pixel + 10)

    def GetCoherentData(
        self, _obj: int, pixel: int, data: DetectorDataType, _placeholder: float
    ) -> tuple[bool, float]:
        return True, float(pixel + data.value)

    def GetAllDetectorDataSafe(self, _obj: int, _data: int) -> list[list[float]]:
        return [[1.0, 2.0], [3.0, 4.0]]

    def GetAllCoherentDataSafe(self, _obj: int, data: DetectorDataType) -> list[list[float]]:
        return [[float(data.value), 2.0], [3.0, 4.0]]


class RayTrace:
    def __init__(self) -> None:
        self.closed = False
        self.cleared: list[int] = []
        self.ran = False
        self.SaveRaysFile = ""

    def ClearDetectors(self, number: int) -> str:
        self.cleared.append(number)
        return "None"

    def ClearDetectorObject(self, number: int) -> str:
        self.cleared.append(number)
        return "None"

    def RunAndWaitForCompletion(self) -> None:
        self.ran = True

    def GetTotalRayEnergy(self) -> float:
        return 0.75

    def Close(self) -> None:
        self.closed = True


class Tools:
    def __init__(self) -> None:
        self.opened: list[RayTrace] = []

    def OpenNSCRayTrace(self) -> RayTrace:
        ray_trace = RayTrace()
        self.opened.append(ray_trace)
        return ray_trace


class System:
    def __init__(self) -> None:
        self.Mode = SystemType.NonSequential
        self.NCE = NCE()
        self.Tools = Tools()

    def MakeNonSequential(self) -> bool:
        self.Mode = SystemType.NonSequential
        return True

    def MakeSequential(self) -> bool:
        self.Mode = SystemType.Sequential
        return True


@pytest.fixture
def fixture() -> tuple[dict[str, Any], System]:
    system = System()
    api = SimpleNamespace(
        Editors=SimpleNamespace(
            NCE=SimpleNamespace(
                ObjectType=ObjectType,
                ObjectColumn=ObjectColumn,
                DetectorDataType=DetectorDataType,
            )
        )
    )
    return build_operation_map(lambda: system, lambda: api), system


def test_nsc_crud_and_typed_parameters(fixture: tuple[dict[str, Any], System]) -> None:
    operations, system = fixture
    assert operations["nsc_summary"]()["number_of_objects"] == 1
    added = operations["nsc_add_object"](object_type="source point", comment="source")
    assert added["type"] == "SourcePoint"
    inserted = operations["nsc_insert_object"](2, object_type="detector rectangle")
    assert inserted["object_number"] == 2
    updated = operations["nsc_set_object"](2, z_position=25.0, material="ABSORB", ref_object=1)
    assert updated["position"]["z"] == 25.0
    assert updated["material"] == "ABSORB"
    integer = operations["nsc_set_object_parameter"](2, 2, 7)
    assert integer["data_type"] == "Integer"
    assert integer["value"] == 7
    text = operations["nsc_set_object_parameter"](2, 3, "label")
    assert text["value"] == "label"
    assert operations["nsc_remove_object"](3) == {"removed": True, "object_number": 3}
    assert system.NCE.NumberOfObjects == 2


def test_nsc_detector_results_are_bounded(fixture: tuple[dict[str, Any], System]) -> None:
    operations, _system = fixture
    data = operations["nsc_detector_data"](1, data_type=1, max_values=3)
    assert data["statistics"] == {"count": 4, "sum": 10.0, "min": 1.0, "max": 4.0}
    assert data["values"] == [1.0, 2.0, 3.0]
    assert data["truncated"] is True
    stats_only = operations["nsc_detector_data"](1, data_type=3, max_values=0)
    assert stats_only["values"] == []
    assert stats_only["total_values"] == 4
    assert operations["nsc_detector_pixel"](1, -1, data_type=1)["value"] == 9.0
    with pytest.raises(BackendError, match="max_values"):
        operations["nsc_detector_data"](1, max_values=NSCSubsystem.MAX_DETECTOR_VALUES + 1)


def test_nsc_ray_trace_and_clear_are_bounded_and_close_tools(
    fixture: tuple[dict[str, Any], System],
) -> None:
    operations, system = fixture
    source = system.NCE.GetObjectAt(1)
    source.Type = ObjectType.SourcePoint
    source.TypeName = "SourcePoint"
    original_rays = source.ObjectData.NumberOfAnalysisRays
    result = operations["nsc_ray_trace"](rays=5, scatter=True, clear_detectors=True)
    assert result["completed"] is True
    assert result["ray_count_limit"] == 5
    assert result["bounded_sources"] == 1
    assert source.ObjectData.NumberOfAnalysisRays == original_rays
    assert result["total_ray_energy"] == 0.75
    assert system.Tools.opened[-1].cleared == [0]
    assert system.Tools.opened[-1].closed is True
    assert operations["nsc_clear_detectors"](object_number=1)["cleared"] is True
    assert system.Tools.opened[-1].closed is True
    with pytest.raises(BackendError, match="rays"):
        operations["nsc_ray_trace"](rays=NSCSubsystem.MAX_RAY_HINT + 1)
    with pytest.raises(BackendError, match="zrd_file"):
        operations["nsc_ray_trace"](rays=1, save_zrd=True)


def test_nsc_safe_mode_conversion(fixture: tuple[dict[str, Any], System]) -> None:
    operations, system = fixture
    with pytest.raises(UnsupportedOperationError, match="complete range"):
        operations["nsc_convert_to_sequential"](first_object=1, last_object=0)
    converted = operations["nsc_convert_to_sequential"]()
    assert converted["mode"] == "Sequential"
    assert system.Mode is SystemType.Sequential
    assert operations["nsc_convert_to_nonsequential"]()["mode"] == "NonSequential"
    assert operations["nsc_convert_to_nonsequential"]()["already_in_mode"] is True
