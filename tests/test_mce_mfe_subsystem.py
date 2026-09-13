from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.subsystems.mce_mfe import build_operation_map, resolve_enum_member


class Cell:
    def __init__(self, value: float = 0.0) -> None:
        self.DoubleValue = value
        self.IsPickup = False
        self.PickupConfiguration: int | None = None
        self.PickupScaleFactor = 1.0
        self.PickupOffset = 0.0

    def MakePickupFrom(self, configuration: int, scale: float, offset: float) -> None:
        self.IsPickup = True
        self.PickupConfiguration = configuration
        self.PickupScaleFactor = scale
        self.PickupOffset = offset


class MCEOperand:
    def __init__(self, configurations: int) -> None:
        self.Type = "THIC"
        self.Param1 = 0
        self.Param2 = 0
        self.Param3 = 0
        self.cells = [Cell() for _ in range(configurations)]

    def ChangeType(self, operand_type: Any) -> None:
        self.Type = operand_type

    def GetOperandCell(self, configuration: int) -> Cell:
        return self.cells[configuration - 1]


class MCE:
    def __init__(self) -> None:
        self.CurrentConfiguration = 1
        self.operands = [MCEOperand(2)]

    @property
    def NumberOfConfigurations(self) -> int:
        return len(self.operands[0].cells) if self.operands else 2

    @property
    def NumberOfOperands(self) -> int:
        return len(self.operands)

    def GetOperandAt(self, row: int) -> MCEOperand:
        return self.operands[row - 1]

    def AddOperand(self) -> MCEOperand:
        operand = MCEOperand(self.NumberOfConfigurations)
        self.operands.append(operand)
        return operand

    def InsertNewOperandAt(self, row: int) -> MCEOperand:
        operand = MCEOperand(self.NumberOfConfigurations)
        self.operands.insert(row - 1, operand)
        return operand

    def RemoveOperandAt(self, row: int) -> None:
        del self.operands[row - 1]

    def AddConfiguration(self, with_pickups: bool = False) -> None:
        for operand in self.operands:
            cell = Cell()
            if with_pickups and operand.cells:
                cell.MakePickupFrom(len(operand.cells), 1.0, 0.0)
            operand.cells.append(cell)

    def DeleteConfiguration(self, configuration: int) -> None:
        for operand in self.operands:
            del operand.cells[configuration - 1]
        self.CurrentConfiguration = min(self.CurrentConfiguration, self.NumberOfConfigurations)


class MFEOperand:
    def __init__(self) -> None:
        self.Type = "BLNK"
        self.Target = 0.0
        self.Weight = 1.0
        self.Int1 = 0
        self.Int2 = 0
        self.Data1 = 0.0
        self.Data2 = 0.0
        self.Data3 = 0.0
        self.Data4 = 0.0
        self.Data5 = 0.0
        self.Data6 = 0.0
        self.Value = 7.5

    def ChangeType(self, operand_type: Any) -> None:
        self.Type = operand_type


class MFE:
    def __init__(self) -> None:
        self.operands = [MFEOperand()]
        self.loaded: list[str] = []
        self.saved: list[str] = []

    @property
    def NumberOfOperands(self) -> int:
        return len(self.operands)

    def GetOperandAt(self, row: int) -> MFEOperand:
        return self.operands[row - 1]

    def AddOperand(self) -> MFEOperand:
        operand = MFEOperand()
        self.operands.append(operand)
        return operand

    def InsertNewOperandAt(self, row: int) -> MFEOperand:
        operand = MFEOperand()
        self.operands.insert(row - 1, operand)
        return operand

    def RemoveOperandAt(self, row: int) -> None:
        del self.operands[row - 1]

    def CalculateMeritFunction(self) -> float:
        return 12.25

    def LoadMeritFunction(self, path: str) -> bool:
        self.loaded.append(path)
        return True

    def SaveMeritFunction(self, path: str) -> bool:
        self.saved.append(path)
        return True


@pytest.fixture
def subsystem() -> tuple[dict[str, Any], SimpleNamespace]:
    system = SimpleNamespace(MCE=MCE(), MFE=MFE())
    api = SimpleNamespace(
        Editors=SimpleNamespace(
            MCE=SimpleNamespace(MultiConfigOperandType=SimpleNamespace(THIC="THIC", CURV="CURV")),
            MFE=SimpleNamespace(
                MeritOperandType=SimpleNamespace(BLNK="BLNK", EFFL="EFFL", RSCE="RSCE")
            ),
        )
    )
    return build_operation_map(lambda: system, lambda: api), system


def test_operation_map_contains_modern_and_legacy_names(
    subsystem: tuple[dict[str, Any], Any],
) -> None:
    operations, _ = subsystem
    assert {
        "get_configuration",
        "set_number_of_configurations",
        "set_current_configuration",
        "get_configuration_operands",
        "add_configuration_operand",
        "delete_configuration_operand",
        "set_configuration_operand_value",
        "mce_summary",
        "mce_add_config",
        "mce_add_operand",
        "get_merit_function",
        "add_operand",
        "remove_operand",
        "merit_value",
        "load_merit_function_file",
        "save_merit_function_file",
    } <= operations.keys()


def test_mce_configuration_lifecycle(subsystem: tuple[dict[str, Any], Any]) -> None:
    operations, _ = subsystem
    assert operations["get_configuration"]() == {
        "number_of_configurations": 2,
        "current_configuration": 1,
    }
    assert operations["mce_add_config"](with_pickups=True)["number_of_configurations"] == 3
    assert operations["set_current_configuration"](configuration_number=3) == {
        "number_of_configurations": 3,
        "current_configuration": 3,
    }
    result = operations["set_number_of_configurations"](number_of_configurations=2)
    assert result == {"number_of_configurations": 2, "current_configuration": 2}

    with pytest.raises(BackendError, match="at least 1"):
        operations["set_number_of_configurations"](number_of_configurations=0)
    with pytest.raises(BackendError, match="out of range"):
        operations["set_current_configuration"](configuration_number=9)


def test_mce_operands_values_and_pickups_are_json_safe(
    subsystem: tuple[dict[str, Any], Any],
) -> None:
    operations, _ = subsystem
    added = operations["add_configuration_operand"](
        operand_type="curv", insert_at=1, param1=4, param2=5, param3=6
    )
    assert added["row"] == 1
    assert added["operand_type"] == "CURV"
    assert (added["param1"], added["param2"], added["param3"]) == (4, 5, 6)

    direct = operations["set_configuration_operand_value"](
        operand_row=1, configuration_number=1, value=2.5
    )
    assert direct == {
        "operand_row": 1,
        "configuration_number": 1,
        "value": 2.5,
        "pickup": None,
    }
    pickup = operations["set_configuration_operand_value"](
        operand_row=1,
        configuration_number=2,
        pickup_config=1,
        scale_factor=2.0,
        offset=-0.25,
    )
    assert pickup["pickup"] == {
        "configuration": 1,
        "scale_factor": 2.0,
        "offset": -0.25,
    }

    summary = operations["mce_summary"]()
    assert summary["number_of_operands"] == 2
    assert summary["operands"][0]["cells"][1]["pickup"]["configuration"] == 1
    json.dumps(summary)

    deleted = operations["delete_configuration_operand"](row=1)
    assert deleted == {"deleted": True, "row": 1, "number_of_operands": 1}


def test_legacy_mce_add_operand_sets_values(subsystem: tuple[dict[str, Any], Any]) -> None:
    operations, _ = subsystem
    result = operations["mce_add_operand"](operand_type="THIC", param1=7, values=[1.25, 2.5])
    assert result["param1"] == 7
    assert [cell["value"] for cell in result["cells"]] == [1.25, 2.5]


def test_mce_validation_rejects_ambiguous_cells_and_bad_ranges(
    subsystem: tuple[dict[str, Any], Any],
) -> None:
    operations, _ = subsystem
    with pytest.raises(BackendError, match="exactly one"):
        operations["set_configuration_operand_value"](
            operand_row=1, configuration_number=1, value=1.0, pickup_config=2
        )
    with pytest.raises(BackendError, match="cannot pick up from itself"):
        operations["set_configuration_operand_value"](
            operand_row=1, configuration_number=1, pickup_config=1
        )
    with pytest.raises(BackendError, match="outside"):
        operations["get_configuration_operands"](start_row=1, end_row=99)


def test_mfe_list_add_remove_and_value(subsystem: tuple[dict[str, Any], Any]) -> None:
    operations, _ = subsystem
    initial = operations["get_merit_function"](include_values=False)
    assert "value" not in initial["operands"][0]

    added = operations["add_operand"](
        operand_type="effl",
        target=50.0,
        weight=2.0,
        int1=3,
        int2=4,
        data1=0.55,
        data6=6.0,
    )
    assert added["operand_type"] == "EFFL"
    assert added["target"] == 50.0
    assert added["weight"] == 2.0
    assert added["int1"] == 3
    assert added["int2"] == 4
    assert added["data1"] == 0.55
    assert added["data6"] == 6.0
    json.dumps(added)

    assert operations["merit_value"]() == {"merit_value": 12.25}
    assert operations["remove_operand"](row=2) == {
        "removed": True,
        "row": 2,
        "number_of_operands": 1,
    }


def test_mfe_load_and_save_paths(subsystem: tuple[dict[str, Any], Any], tmp_path: Path) -> None:
    operations, system = subsystem
    path = tmp_path / "optimization.MF"
    loaded = operations["load_merit_function_file"](file_path=str(path))
    saved = operations["save_merit_function_file"](file_path=str(path))
    assert loaded == {"path": str(path.resolve()), "loaded": True}
    assert saved == {"path": str(path.resolve()), "saved": True}
    assert system.MFE.loaded == [str(path.resolve())]
    assert system.MFE.saved == [str(path.resolve())]


def test_enum_resolver_is_case_insensitive_and_reports_unknown_values() -> None:
    namespace = SimpleNamespace(THIC="resolved")
    assert resolve_enum_member(namespace, "thic", operation="test") == "resolved"
    with pytest.raises(BackendError, match="unknown operand type"):
        resolve_enum_member(namespace, "NOPE", operation="test")
