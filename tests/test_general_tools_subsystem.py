from __future__ import annotations

from enum import Enum
from types import SimpleNamespace
from typing import Any

import pytest

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.protocol import ApplicationOwnership
from zemax_mcp.zos.subsystems.general_tools import build_operation_map


class Units(Enum):
    Millimeters = 0
    Centimeters = 1
    Inches = 2
    Meters = 3


class Tool:
    def __init__(self) -> None:
        self.NumberOfComponents = 3
        self.Succeeded = True
        self.ErrorMessage = ""
        self.Status = "Completed"
        self.IsRunning = False
        self.closed = False

    def RunAndWaitForCompletion(self) -> str:
        return "Completed"

    def RunAndWaitWithTimeout(self, _timeout: float) -> str:
        return "Completed"

    def Close(self) -> None:
        self.closed = True


class ScaleTool(Tool):
    ScaleByFactor = False
    ScaleByUnits = False
    ScaleFactor = 1.0
    FirstComponent = 1
    LastComponent = 3
    ScaleToUnit = Units.Millimeters


class LockdownTool(Tool):
    UsePrecisionRounding = False
    DecimalPrecision = 3
    ExcludePickups = False
    FixModelGlasses = False
    ConvertSDToMaxApertures = False


@pytest.fixture
def operations() -> tuple[dict[str, Any], ScaleTool, LockdownTool]:
    scale = ScaleTool()
    lockdown = LockdownTool()
    system = SimpleNamespace(
        Tools=SimpleNamespace(OpenScale=lambda: scale, OpenDesignLockdown=lambda: lockdown),
        SystemData=SimpleNamespace(Units=SimpleNamespace(LensUnits=Units.Millimeters)),
    )
    api = SimpleNamespace(Tools=SimpleNamespace(General=SimpleNamespace(ScaleToUnits=Units)))
    return (
        build_operation_map(lambda: system, lambda: api, lambda: ApplicationOwnership.OWNED),
        scale,
        lockdown,
    )


def test_scale_factor_and_units(operations: tuple[dict[str, Any], ScaleTool, LockdownTool]) -> None:
    ops, scale, _ = operations
    result = ops["scale_lens"](mode="factor", scale_factor=2.0)
    assert result["succeeded"] is True
    assert scale.ScaleByFactor is True
    assert scale.closed is True

    scale.closed = False
    result = ops["scale_lens"](mode="units", scale_to_unit="Centimeters")
    assert result["succeeded"] is True
    assert scale.ScaleToUnit is Units.Centimeters
    assert scale.closed is True


def test_scale_validation(operations: tuple[dict[str, Any], ScaleTool, LockdownTool]) -> None:
    ops, _, _ = operations
    with pytest.raises(BackendError):
        ops["scale_lens"](mode="factor", scale_factor=-1)
    with pytest.raises(BackendError):
        ops["scale_lens"](mode="units", scale_to_unit="Meters", first_component=1)


def test_lockdown_gates_and_settings(
    operations: tuple[dict[str, Any], ScaleTool, LockdownTool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops, _, lockdown = operations
    with pytest.raises(BackendError, match="confirm"):
        ops["design_lockdown"](confirm_destructive=False)
    monkeypatch.setenv("ZEMAX_MCP_ALLOW_DESTRUCTIVE", "1")
    result = ops["design_lockdown"](
        confirm_destructive=True,
        use_precision_rounding=True,
        decimal_precision=2,
        exclude_pickups=True,
    )
    assert result["succeeded"] is True
    assert lockdown.UsePrecisionRounding is True
    assert lockdown.DecimalPrecision == 2
    assert lockdown.ExcludePickups is True
    assert lockdown.closed is True
