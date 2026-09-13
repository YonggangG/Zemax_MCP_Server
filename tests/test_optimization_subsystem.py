from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.subsystems.optimization import build_operation_map


class EnumValue:
    def __init__(self, name: str, value: int = 0) -> None:
        self.name = name
        self.value = value

    def __int__(self) -> int:
        return self.value


class EnumNamespace:
    def __init__(self, names: list[str]) -> None:
        for index, name in enumerate(names):
            setattr(self, name, EnumValue(name, index))

    def __call__(self, value: int) -> EnumValue:
        for candidate in vars(self).values():
            if isinstance(candidate, EnumValue) and candidate.value == value:
                return candidate
        raise ValueError(value)


class Cell:
    def __init__(self, header: str, solve: str = "Fixed", value: float = 0.0) -> None:
        self.Header = header
        self.Solve = EnumValue(solve)
        self.DataType = EnumValue("Double")
        self.DoubleValue = value
        self.IsActive = True


class Surface:
    def __init__(self, number: int) -> None:
        self.cells = {
            0: Cell("Radius", "Variable" if number == 1 else "Fixed", 10.0),
            1: Cell("Thickness", "Variable" if number == 2 else "Fixed", 2.0),
        }

    def GetSurfaceCell(self, column: EnumValue) -> Cell:
        return self.cells[column.value]


class LDE:
    NumberOfSurfaces = 3
    FirstColumn = 0
    LastColumn = 1

    def __init__(self) -> None:
        self.surfaces = [Surface(i) for i in range(3)]

    def GetSurfaceAt(self, index: int) -> Surface:
        return self.surfaces[index]


class Tool:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.Algorithm = EnumValue("DampedLeastSquares")
        self.Cycles = EnumValue("Automatic")
        self.Criterion = EnumValue("SpotSizeRadial")
        self.UseCentroid = True
        self.NumberOfCores = 0
        self.MaxCores = 4
        self.NumberToSave = EnumValue("Save_20")
        self.AutomaticOptimization = True
        self.TargetRunTimeM = 1.0
        self.InitialMeritFunction = 10.0
        self.CurrentMeritFunction = 2.0
        self.Variables = 2
        self.Targets = 3
        self.Systems = 7
        self.Cycles = EnumValue("Automatic")
        self.Succeeded = True
        self.Status = "Complete"
        self.ErrorMessage = ""
        self.IsRunning = False
        self.cancelled = False
        self.closed = False
        self.run_args: list[float | None] = []
        self.SetupMode = EnumValue("Sensitivity")
        self.CriterionSampling = 3
        self.CriterionComp = EnumValue("OptimizeAll_DLS")
        self.CriterionCycle = 1
        self.CriterionField = EnumValue("UserDefined")
        self.NumberOfRuns = 0
        self.ResultFilename = "result.txt"
        self.OpenDataViewer = True

    def RunAndWaitForCompletion(self) -> bool:
        self.run_args.append(None)
        return True

    def RunAndWaitWithTimeout(self, timeout: float) -> EnumValue:
        self.run_args.append(timeout)
        self.IsRunning = True
        return EnumValue("TimedOut")

    def Cancel(self) -> bool:
        self.cancelled = True
        self.IsRunning = False
        return True

    def WaitForCompletion(self) -> bool:
        return True

    def Close(self) -> bool:
        self.closed = True
        return True


class GlobalTool:
    def __init__(self) -> None:
        self.name = "global"
        self.Algorithm = EnumValue("DampedLeastSquares")
        self.NumberOfCores = 0
        self.NumberToSave: Any = 0
        self.Succeeded = True
        self.Status = "Complete"
        self.ErrorMessage = ""
        self.IsRunning = False
        self.cancelled = False
        self.closed = False
        self.run_args: list[float | None] = []

    def RunAndWaitWithTimeout(self, timeout: float) -> EnumValue:
        self.run_args.append(timeout)
        self.IsRunning = True
        return EnumValue("TimedOut")

    def Cancel(self) -> bool:
        self.cancelled = True
        self.IsRunning = False
        return True

    def WaitForCompletion(self) -> bool:
        return True

    def Close(self) -> bool:
        self.closed = True
        return True

    def CurrentMeritFunction(self, index: int) -> float:
        return float(index)


class Tools:
    def __init__(self) -> None:
        self.opened: list[Any] = []

    def _open(self, tool: Any) -> Any:
        self.opened.append(tool)
        return tool

    def OpenQuickFocus(self) -> Tool:
        tool = Tool("focus")
        self.opened.append(tool)
        return tool

    def OpenLocalOptimization(self) -> Tool:
        tool = Tool("local")
        self.opened.append(tool)
        return tool

    def OpenGlobalOptimization(self) -> GlobalTool:
        tool = GlobalTool()
        self.opened.append(tool)
        return tool

    def OpenHammerOptimization(self) -> Tool:
        tool = Tool("hammer")
        self.opened.append(tool)
        return tool

    def OpenTolerancing(self) -> Tool:
        tool = Tool("tolerancing")
        self.opened.append(tool)
        return tool


class ToleranceRow:
    Type = EnumValue("TRAD")
    TypeName = "Radius"
    Min = -0.1
    Max = 0.1
    IsMinUsed = True
    IsMaxUsed = True
    Nominal = 20.0
    IsNominalUsed = True
    Param1 = 1
    Param2 = 0
    Param3 = 0
    Comment = "radius"
    IgnoreThisOperandDuringTolerancing = False


class Wizard:
    def __init__(self) -> None:
        self.CommonSettings = self
        self.applied = False
        for name in (
            "SurfaceRadius",
            "SurfaceThickness",
            "SurfaceDecenterX",
            "SurfaceDecenterY",
            "SurfaceTiltXDegrees",
            "SurfaceTiltYDegrees",
            "ElementDecenterX",
            "ElementDecenterY",
            "ElementTiltXDegrees",
            "ElementTiltYDegrees",
            "IsSurfaceSandAIrregularityUsed",
            "IsIndexUsed",
            "IsIndexAbbePercentageUsed",
        ):
            setattr(self, name, 0.0)

    def OK(self) -> None:
        self.applied = True


class TDE:
    NumberOfOperands = 1

    def __init__(self) -> None:
        self.SEQToleranceWizard = Wizard()

    def GetOperandAt(self, row: int) -> ToleranceRow:
        assert row == 1
        return ToleranceRow()


@pytest.fixture
def environment() -> tuple[dict[str, Any], Tools, TDE]:
    tools = Tools()
    tde = TDE()
    system = SimpleNamespace(LDE=LDE(), Tools=tools, TDE=tde)
    api = SimpleNamespace(
        Editors=SimpleNamespace(
            LDE=SimpleNamespace(SurfaceColumn=EnumNamespace(["Radius", "Thickness"]))
        ),
        Tools=SimpleNamespace(
            General=SimpleNamespace(
                QuickFocusCriterion=EnumNamespace(
                    ["SpotSizeRadial", "SpotSizeXOnly", "SpotSizeYOnly", "RMSWavefront"]
                )
            ),
            Optimization=SimpleNamespace(
                OptimizationAlgorithm=EnumNamespace(["DampedLeastSquares", "OrthogonalDescent"]),
                OptimizationCycles=EnumNamespace(
                    [
                        "Automatic",
                        "Fixed_1_Cycle",
                        "Fixed_5_Cycles",
                        "Fixed_10_Cycles",
                        "Fixed_50_Cycles",
                    ]
                ),
                OptimizationSaveCount=EnumNamespace([f"Save_{i}" for i in range(10, 101, 10)]),
            ),
            Tolerancing=SimpleNamespace(
                SetupModes=EnumNamespace(["Sensitivity"]),
                Criterions=EnumNamespace(["RMSSpotRadius"]),
                CriterionComps=EnumNamespace(["OptimizeAll_DLS"]),
                CriterionFields=EnumNamespace(["UserDefined"]),
            ),
        ),
    )
    return build_operation_map(lambda: system, lambda: api), tools, tde


def test_variable_scan_and_native_constraint_disclosure(
    environment: tuple[Any, Tools, TDE],
) -> None:
    operations, _, _ = environment
    result = operations["get_variables"]()
    assert result["number_of_variables"] == 2
    assert [(item["surface_number"], item["column"]) for item in result["variables"]] == [
        (1, "Radius"),
        (2, "Thickness"),
    ]
    assert result["native_hard_constraints_supported"] is False


def test_quick_focus_and_local_optimization_close_tools(
    environment: tuple[Any, Tools, TDE],
) -> None:
    operations, tools, _ = environment
    focus = operations["quick_focus"](criterion="RMSWavefront", use_centroid=False)
    assert focus["criterion"] == "RMSWavefront"
    result = operations["optimize"](algorithm="Orthogonal", cycles=5, cores=99)
    assert result["algorithm"] == "OrthogonalDescent"
    assert result["cores"] == 4
    assert all(tool.closed for tool in tools.opened)


def test_global_and_hammer_cancel_after_timeout(environment: tuple[Any, Tools, TDE]) -> None:
    operations, tools, _ = environment
    global_result = operations["global_search"](solutions_to_save=10, timeout_seconds=0.01)
    hammer_result = operations["hammer"](timeout_seconds=0.01, target_runtime_minutes=0.1)
    assert global_result["saved_merit_functions"] == [float(i) for i in range(1, 11)]
    assert hammer_result["run_status"] == "TimedOut"
    assert tools.opened[-2].cancelled and tools.opened[-2].closed
    assert tools.opened[-1].cancelled and tools.opened[-1].closed


def test_tde_wizard_and_bounded_tolerancing(environment: tuple[Any, Tools, TDE]) -> None:
    operations, tools, tde = environment
    assert operations["tde_summary"]()["operands"][0]["operand_type"] == "TRAD"
    wizard = operations["tolerance_wizard"]()
    assert wizard["wizard_applied"] is True
    assert tde.SEQToleranceWizard.applied is True
    result = operations["run_tolerancing"](monte_carlo_runs=2, timeout_seconds=0.01)
    assert result["monte_carlo_runs"] == 2
    assert tools.opened[-1].cancelled and tools.opened[-1].closed
    with pytest.raises(BackendError, match="between 1 and 100"):
        operations["run_tolerancing"](monte_carlo_runs=101)
    with pytest.raises(BackendError, match="timeout_seconds"):
        operations["hammer"](timeout_seconds=301)
