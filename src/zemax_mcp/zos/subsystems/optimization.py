"""Native sequential optimization and tolerancing operation handlers.

The implementation follows the installed ZOS-API Python examples 01, 03, 14,
and 15.  Every opened system tool is cancelled when still running and closed in
``finally``; long-running global, Hammer, and tolerancing calls support hard
timeouts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import suppress
from typing import Any

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.adapters.enums import enum_member, enum_name

Accessor = Callable[[], Any]
Operation = Callable[..., Any]

_OPTIMIZATION_ALIASES = {
    "dls": "DampedLeastSquares",
    "damped least squares": "DampedLeastSquares",
    "orthogonal": "OrthogonalDescent",
    "od": "OrthogonalDescent",
}
_CYCLE_NAMES = {
    0: "Automatic",
    1: "Fixed_1_Cycle",
    5: "Fixed_5_Cycles",
    10: "Fixed_10_Cycles",
    50: "Fixed_50_Cycles",
}
_SAVE_COUNTS = {10, 20, 30, 40, 50, 60, 70, 80, 90, 100}
_MAX_TIMEOUT_SECONDS = 300.0
_MAX_TOLERANCE_RUNS = 100


def _member(obj: Any, *names: str, default: Any = ...) -> Any:
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        try:
            return getattr(obj, name)
        except (AttributeError, TypeError):
            pass
    if default is not ...:
        return default
    raise AttributeError(f"none of {names!r} exist on {type(obj).__name__}")


def _call(obj: Any, names: tuple[str, ...], *args: Any) -> Any:
    method = _member(obj, *names)
    if not callable(method):
        raise TypeError(f"{names[0]} on {type(obj).__name__} is not callable")
    return method(*args)


def _bounded_timeout(value: float, operation: str, *, allow_zero: bool = True) -> float:
    timeout = float(value)
    minimum = 0.0 if allow_zero else 0.001
    if timeout < minimum or timeout > _MAX_TIMEOUT_SECONDS:
        detail = f"timeout_seconds must be between {minimum:g} and {_MAX_TIMEOUT_SECONDS:g}"
        raise BackendError(operation, detail)
    return timeout


def _set_cores(tool: Any, cores: int, operation: str) -> int:
    requested = int(cores)
    if requested < 0:
        raise BackendError(operation, "cores cannot be negative")
    maximum = int(_member(tool, "MaxCores", default=0))
    selected = maximum if requested == 0 and maximum > 0 else requested
    if maximum > 0:
        selected = min(selected, maximum)
    if selected > 0 and hasattr(tool, "NumberOfCores"):
        tool.NumberOfCores = selected
    return selected


def _tool_result(tool: Any, **extra: Any) -> dict[str, Any]:
    result = {
        "succeeded": bool(_member(tool, "Succeeded", default=True)),
        "status": str(_member(tool, "Status", default="")),
        "error_message": str(_member(tool, "ErrorMessage", default="")),
    }
    result.update(extra)
    return result


def _finish_tool(tool: Any, *, cancel: bool) -> None:
    if tool is None:
        return
    if cancel and bool(_member(tool, "IsRunning", default=False)):
        method = _member(tool, "Cancel", default=None)
        if callable(method):
            with suppress(Exception):
                method()
        wait = _member(tool, "WaitForCompletion", default=None)
        if callable(wait):
            with suppress(Exception):
                wait()
    close = _member(tool, "Close", default=None)
    if callable(close):
        with suppress(Exception):
            close()


def _run_tool(tool: Any, operation: str, timeout_seconds: float = 0.0) -> Any:
    timeout = _bounded_timeout(timeout_seconds, operation)
    if timeout > 0:
        return _call(tool, ("RunAndWaitWithTimeout",), timeout)
    return _call(tool, ("RunAndWaitForCompletion",))


def _cell_value(cell: Any) -> Any:
    data_type = enum_name(_member(cell, "DataType", default="")).casefold()
    if "integer" in data_type:
        return int(_member(cell, "IntegerValue", default=0))
    if "double" in data_type or "float" in data_type:
        return float(_member(cell, "DoubleValue", default=0.0))
    return str(_member(cell, "Value", default=""))


class OptimizationTolerancingOperations:
    """Bound native tool operations for one sequential optical system."""

    def __init__(self, require_system: Accessor, api: Accessor) -> None:
        self._require_system = require_system
        self._get_api = api

    def _system(self) -> Any:
        return self._require_system()

    def _api(self) -> Any:
        return self._get_api()

    def _tools(self) -> Any:
        return self._system().Tools

    def get_variables(self) -> dict[str, Any]:
        lde = self._system().LDE
        columns = self._api().Editors.LDE.SurfaceColumn
        first = int(_member(lde, "FirstColumn", default=1))
        last = int(_member(lde, "LastColumn", default=first + 9))
        variables: list[dict[str, Any]] = []
        number = 0
        for surface_number in range(int(lde.NumberOfSurfaces)):
            surface = lde.GetSurfaceAt(surface_number)
            for raw_column in range(first, last + 1):
                column = enum_member(columns, raw_column)
                try:
                    cell = surface.GetSurfaceCell(column)
                except Exception:
                    continue
                if not bool(_member(cell, "IsActive", default=True)):
                    continue
                if enum_name(_member(cell, "Solve", default="")).casefold() != "variable":
                    continue
                number += 1
                variables.append(
                    {
                        "variable_number": number,
                        "surface_number": surface_number,
                        "column": enum_name(column),
                        "header": str(_member(cell, "Header", default="")),
                        "value": _cell_value(cell),
                        "constraint": "Unconstrained",
                        "minimum": None,
                        "maximum": None,
                    }
                )
        return {
            "number_of_variables": len(variables),
            "variables": variables,
            "native_hard_constraints_supported": False,
            "constraint_note": (
                "ZOS-API 2025 R1.01 exposes variable solves but no public per-variable "
                "hard-bound API; use merit-function boundary operands for native optimization."
            ),
        }

    def quick_focus(
        self, criterion: str = "SpotSizeRadial", use_centroid: bool = True
    ) -> dict[str, Any]:
        operation = "quick_focus"
        tool = self._tools().OpenQuickFocus()
        if tool is None:
            raise BackendError(operation, "OpenQuickFocus returned no tool")
        try:
            general = self._api().Tools.General
            criterion_enum = _member(general, "QuickFocusCriterion", "QuickAdjustCriterion")
            tool.Criterion = enum_member(criterion_enum, criterion)
            tool.UseCentroid = bool(use_centroid)
            _run_tool(tool, operation)
            return _tool_result(
                tool,
                criterion=enum_name(tool.Criterion),
                use_centroid=bool(tool.UseCentroid),
            )
        finally:
            _finish_tool(tool, cancel=True)

    def optimize(
        self,
        algorithm: str = "DLS",
        cycles: int = 0,
        method: str | None = None,
        cores: int = 0,
    ) -> dict[str, Any]:
        if method and method.strip().casefold() not in {"local", "dls", "orthogonal"}:
            raise BackendError(
                "optimize", "zemax_optimize runs local optimization; use global_search or hammer"
            )
        requested_cycles = int(cycles)
        if requested_cycles not in _CYCLE_NAMES:
            raise BackendError("optimize", "cycles must be one of 0, 1, 5, 10, or 50")
        tool = self._tools().OpenLocalOptimization()
        if tool is None:
            raise BackendError("optimize", "OpenLocalOptimization returned no tool")
        try:
            namespace = self._api().Tools.Optimization
            tool.Algorithm = enum_member(
                namespace.OptimizationAlgorithm, algorithm, aliases=_OPTIMIZATION_ALIASES
            )
            tool.Cycles = enum_member(namespace.OptimizationCycles, _CYCLE_NAMES[requested_cycles])
            selected_cores = _set_cores(tool, int(cores), "optimize")
            initial = float(_member(tool, "InitialMeritFunction", default=0.0))
            _run_tool(tool, "optimize")
            return _tool_result(
                tool,
                algorithm=enum_name(tool.Algorithm),
                cycles=enum_name(tool.Cycles),
                cores=selected_cores,
                variables=int(_member(tool, "Variables", default=0)),
                targets=int(_member(tool, "Targets", default=0)),
                initial_merit_function=initial,
                final_merit_function=float(_member(tool, "CurrentMeritFunction", default=initial)),
            )
        finally:
            _finish_tool(tool, cancel=True)

    def global_search(
        self,
        algorithm: str = "DLS",
        cores: int = 0,
        solutions_to_save: int = 20,
        timeout_seconds: float = 0.0,
    ) -> dict[str, Any]:
        operation = "global_search"
        save_count = int(solutions_to_save)
        if save_count not in _SAVE_COUNTS:
            raise BackendError(operation, "solutions_to_save must be 10, 20, ..., or 100")
        tool = self._tools().OpenGlobalOptimization()
        if tool is None:
            raise BackendError(operation, "OpenGlobalOptimization returned no tool")
        try:
            namespace = self._api().Tools.Optimization
            tool.Algorithm = enum_member(
                namespace.OptimizationAlgorithm, algorithm, aliases=_OPTIMIZATION_ALIASES
            )
            tool.NumberToSave = enum_member(namespace.OptimizationSaveCount, f"Save_{save_count}")
            selected_cores = _set_cores(tool, int(cores), operation)
            initial = float(_member(tool, "InitialMeritFunction", default=0.0))
            run_status = _run_tool(tool, operation, float(timeout_seconds))
            merits = []
            current = _member(tool, "CurrentMeritFunction", default=None)
            if callable(current):
                for index in range(1, save_count + 1):
                    with suppress(Exception):
                        merits.append(float(current(index)))
            return _tool_result(
                tool,
                algorithm=enum_name(tool.Algorithm),
                cores=selected_cores,
                solutions_to_save=save_count,
                timeout_seconds=float(timeout_seconds),
                run_status=enum_name(run_status),
                initial_merit_function=initial,
                saved_merit_functions=merits,
                systems=int(_member(tool, "Systems", default=0)),
                cycles=int(_member(tool, "Cycles", default=0)),
            )
        finally:
            _finish_tool(tool, cancel=True)

    def hammer(
        self,
        algorithm: str = "DLS",
        cores: int = 0,
        target_runtime_minutes: float = 1.0,
        timeout_seconds: float = 120.0,
        automatic: bool = True,
    ) -> dict[str, Any]:
        operation = "hammer"
        timeout = _bounded_timeout(float(timeout_seconds), operation, allow_zero=False)
        target = float(target_runtime_minutes)
        if target <= 0 or target > 60:
            raise BackendError(operation, "target_runtime_minutes must be between 0 and 60")
        tool = self._tools().OpenHammerOptimization()
        if tool is None:
            raise BackendError(operation, "OpenHammerOptimization returned no tool")
        try:
            namespace = self._api().Tools.Optimization
            tool.Algorithm = enum_member(
                namespace.OptimizationAlgorithm, algorithm, aliases=_OPTIMIZATION_ALIASES
            )
            selected_cores = _set_cores(tool, int(cores), operation)
            if hasattr(tool, "AutomaticOptimization"):
                tool.AutomaticOptimization = bool(automatic)
            if hasattr(tool, "TargetRunTimeM"):
                tool.TargetRunTimeM = target
            initial = float(_member(tool, "InitialMeritFunction", default=0.0))
            run_status = _run_tool(tool, operation, timeout)
            return _tool_result(
                tool,
                algorithm=enum_name(tool.Algorithm),
                cores=selected_cores,
                automatic=bool(_member(tool, "AutomaticOptimization", default=automatic)),
                target_runtime_minutes=target,
                timeout_seconds=timeout,
                run_status=enum_name(run_status),
                initial_merit_function=initial,
                final_merit_function=float(_member(tool, "CurrentMeritFunction", default=initial)),
                systems=int(_member(tool, "Systems", default=0)),
            )
        finally:
            _finish_tool(tool, cancel=True)

    def tde_summary(self) -> dict[str, Any]:
        tde = self._system().TDE
        operands = []
        for row in range(1, int(tde.NumberOfOperands) + 1):
            operand = tde.GetOperandAt(row)
            operands.append(
                {
                    "row": row,
                    "operand_type": enum_name(_member(operand, "Type", default="")),
                    "type_name": str(_member(operand, "TypeName", default="")),
                    "minimum": float(_member(operand, "Min", default=0.0)),
                    "maximum": float(_member(operand, "Max", default=0.0)),
                    "minimum_used": bool(_member(operand, "IsMinUsed", default=False)),
                    "maximum_used": bool(_member(operand, "IsMaxUsed", default=False)),
                    "nominal": float(_member(operand, "Nominal", default=0.0)),
                    "nominal_used": bool(_member(operand, "IsNominalUsed", default=False)),
                    "param1": int(_member(operand, "Param1", default=0)),
                    "param2": int(_member(operand, "Param2", default=0)),
                    "param3": int(_member(operand, "Param3", default=0)),
                    "comment": str(_member(operand, "Comment", default="")),
                    "ignore": bool(
                        _member(operand, "IgnoreThisOperandDuringTolerancing", default=False)
                    ),
                }
            )
        return {"number_of_operands": int(tde.NumberOfOperands), "operands": operands}

    def tolerance_wizard(self) -> dict[str, Any]:
        wizard = self._system().TDE.SEQToleranceWizard
        settings = {
            "SurfaceRadius": 0.1,
            "SurfaceThickness": 0.1,
            "SurfaceDecenterX": 0.1,
            "SurfaceDecenterY": 0.1,
            "SurfaceTiltXDegrees": 0.2,
            "SurfaceTiltYDegrees": 0.2,
            "ElementDecenterX": 0.1,
            "ElementDecenterY": 0.1,
            "ElementTiltXDegrees": 0.2,
            "ElementTiltYDegrees": 0.2,
            "IsSurfaceSandAIrregularityUsed": False,
            "IsIndexUsed": False,
            "IsIndexAbbePercentageUsed": False,
        }
        for name, value in settings.items():
            if hasattr(wizard, name):
                setattr(wizard, name, value)
        common = _member(wizard, "CommonSettings", default=wizard)
        _call(common, ("OK", "Apply"))
        result = self.tde_summary()
        result["wizard_applied"] = True
        result["defaults"] = {
            name: value for name, value in settings.items() if hasattr(wizard, name)
        }
        return result

    def run_tolerancing(
        self, monte_carlo_runs: int = 20, timeout_seconds: float = 30.0
    ) -> dict[str, Any]:
        operation = "run_tolerancing"
        runs = int(monte_carlo_runs)
        if runs < 1 or runs > _MAX_TOLERANCE_RUNS:
            raise BackendError(
                operation, f"monte_carlo_runs must be between 1 and {_MAX_TOLERANCE_RUNS}"
            )
        timeout = _bounded_timeout(float(timeout_seconds), operation, allow_zero=False)
        tool = self._tools().OpenTolerancing()
        if tool is None:
            raise BackendError(operation, "OpenTolerancing returned no tool")
        try:
            namespace = self._api().Tools.Tolerancing
            tool.SetupMode = enum_member(namespace.SetupModes, "Sensitivity")
            tool.Criterion = enum_member(namespace.Criterions, "RMSSpotRadius")
            tool.CriterionSampling = 3
            tool.CriterionComp = enum_member(namespace.CriterionComps, "OptimizeAll_DLS")
            tool.CriterionCycle = 1
            tool.CriterionField = enum_member(namespace.CriterionFields, "UserDefined")
            tool.NumberOfRuns = runs
            tool.NumberToSave = 0
            if hasattr(tool, "OpenDataViewer"):
                tool.OpenDataViewer = False
            run_status = _run_tool(tool, operation, timeout)
            return _tool_result(
                tool,
                run_status=enum_name(run_status),
                monte_carlo_runs=runs,
                timeout_seconds=timeout,
                setup_mode=enum_name(tool.SetupMode),
                criterion=enum_name(tool.Criterion),
                result_filename=str(_member(tool, "ResultFilename", default="")),
            )
        finally:
            _finish_tool(tool, cancel=True)


def build_operation_map(require_system: Accessor, api: Accessor) -> dict[str, Operation]:
    ops = OptimizationTolerancingOperations(require_system, api)
    return {
        "get_variables": ops.get_variables,
        "quick_focus": ops.quick_focus,
        "optimize": ops.optimize,
        "global_search": ops.global_search,
        "hammer": ops.hammer,
        "tde_summary": ops.tde_summary,
        "tolerance_wizard": ops.tolerance_wizard,
        "run_tolerancing": ops.run_tolerancing,
    }


__all__ = ["OptimizationTolerancingOperations", "build_operation_map"]
