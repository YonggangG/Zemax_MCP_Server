"""Bounded native general-system tools."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.adapters.enums import enum_member, enum_name

Accessor = Callable[[], Any]
Operation = Callable[..., Any]


def _run_and_close(tool: Any, operation: str, timeout_seconds: float) -> dict[str, Any]:
    if tool is None:
        raise BackendError(operation, "OpticStudio did not open the requested tool")
    try:
        if timeout_seconds:
            if not 0 < timeout_seconds <= 300:
                raise BackendError(operation, "timeout_seconds must be in (0, 300]")
            status = tool.RunAndWaitWithTimeout(float(timeout_seconds))
        else:
            status = tool.RunAndWaitForCompletion()
        succeeded = bool(getattr(tool, "Succeeded", True))
        error = str(getattr(tool, "ErrorMessage", ""))
        if not succeeded:
            raise BackendError(operation, error or "OpticStudio tool failed")
        return {"succeeded": True, "run_status": enum_name(status), "error_message": error}
    finally:
        if bool(getattr(tool, "IsRunning", False)):
            cancel = getattr(tool, "Cancel", None)
            if callable(cancel):
                with suppress(Exception):
                    cancel()
        close = getattr(tool, "Close", None)
        if callable(close):
            with suppress(Exception):
                close()


class GeneralToolOperations:
    def __init__(self, require_system: Accessor, api: Accessor, ownership: Accessor) -> None:
        self._require_system = require_system
        self._api = api
        self._ownership = ownership

    def scale_lens(
        self,
        *,
        mode: str,
        scale_factor: float | None = None,
        scale_to_unit: str | None = None,
        first_component: int | None = None,
        last_component: int | None = None,
        timeout_seconds: float = 0.0,
    ) -> dict[str, Any]:
        operation = "scale_lens"
        selected = mode.strip().lower()
        if selected not in {"factor", "units"}:
            raise BackendError(operation, "mode must be 'factor' or 'units'")
        if (first_component is None) != (last_component is None):
            raise BackendError(operation, "provide both component bounds or neither")
        system = self._require_system()
        tool = system.Tools.OpenScale()
        if tool is None:
            raise BackendError(operation, "Scale Lens tool is unavailable")
        before_units = enum_name(system.SystemData.Units.LensUnits)
        count = int(tool.NumberOfComponents)
        if first_component is not None and last_component is not None:
            if not 1 <= first_component <= last_component <= count:
                tool.Close()
                raise BackendError(operation, f"component range must be within 1..{count}")
            tool.FirstComponent = first_component
            tool.LastComponent = last_component
        if selected == "factor":
            if scale_factor is None or scale_to_unit is not None:
                tool.Close()
                raise BackendError(operation, "factor mode requires only scale_factor")
            if not math.isfinite(scale_factor) or not 1e-6 <= scale_factor <= 1e6:
                tool.Close()
                raise BackendError(operation, "scale_factor must be finite and within 1e-6..1e6")
            tool.ScaleByFactor = True
            tool.ScaleByUnits = False
            tool.ScaleFactor = float(scale_factor)
        else:
            if scale_to_unit is None or scale_factor is not None:
                tool.Close()
                raise BackendError(operation, "units mode requires only scale_to_unit")
            tool.ScaleByFactor = False
            tool.ScaleByUnits = True
            tool.ScaleToUnit = enum_member(self._api().Tools.General.ScaleToUnits, scale_to_unit)
        result = _run_and_close(tool, operation, timeout_seconds)
        result.update(
            {
                "mode": selected,
                "scale_factor": scale_factor,
                "scale_to_unit": scale_to_unit,
                "first_component": first_component,
                "last_component": last_component,
                "component_count": count,
                "before_lens_units": before_units,
                "after_lens_units": enum_name(system.SystemData.Units.LensUnits),
                "modified_system": True,
            }
        )
        return result

    def design_lockdown(
        self,
        *,
        confirm_destructive: bool,
        use_precision_rounding: bool = False,
        decimal_precision: int = 3,
        exclude_pickups: bool = False,
        fix_model_glasses: bool = False,
        convert_sd_to_max_apertures: bool = False,
        convert_s_d_to_max_apertures: bool | None = None,
        timeout_seconds: float = 0.0,
    ) -> dict[str, Any]:
        operation = "design_lockdown"
        if not confirm_destructive:
            raise BackendError(operation, "confirm_destructive=true is required")
        if os.environ.get("ZEMAX_MCP_ALLOW_DESTRUCTIVE") != "1":
            raise BackendError(operation, "set ZEMAX_MCP_ALLOW_DESTRUCTIVE=1 to enable lockdown")
        if str(self._ownership()).lower() not in {"owned", "applicationownership.owned"}:
            raise BackendError(
                operation, "design lockdown requires an owned standalone application"
            )
        if not 0 <= decimal_precision <= 15:
            raise BackendError(operation, "decimal_precision must be 0..15")
        system = self._require_system()
        tool = system.Tools.OpenDesignLockdown()
        if tool is None:
            raise BackendError(operation, "Design Lockdown tool is unavailable")
        if convert_s_d_to_max_apertures is not None:
            convert_sd_to_max_apertures = convert_s_d_to_max_apertures
        tool.UsePrecisionRounding = bool(use_precision_rounding)
        tool.DecimalPrecision = int(decimal_precision)
        tool.ExcludePickups = bool(exclude_pickups)
        tool.FixModelGlasses = bool(fix_model_glasses)
        tool.ConvertSDToMaxApertures = bool(convert_sd_to_max_apertures)
        result = _run_and_close(tool, operation, timeout_seconds)
        result.update(
            {
                "use_precision_rounding": use_precision_rounding,
                "decimal_precision": decimal_precision,
                "exclude_pickups": exclude_pickups,
                "fix_model_glasses": fix_model_glasses,
                "convert_sd_to_max_apertures": convert_sd_to_max_apertures,
                "modified_system": True,
            }
        )
        return result


def build_operation_map(
    require_system: Accessor, api: Accessor, ownership: Accessor
) -> dict[str, Operation]:
    operations = GeneralToolOperations(require_system, api, ownership)
    return {
        "scale_lens": operations.scale_lens,
        "design_lockdown": operations.design_lockdown,
    }
