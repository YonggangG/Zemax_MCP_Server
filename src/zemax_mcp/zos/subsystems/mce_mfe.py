"""Multi-configuration and merit-function operation handlers.

The handlers in this module deliberately use ZOS-like duck typing so they can
be tested without loading pythonnet.  ``build_operation_map`` binds the two
backend accessors and returns callables suitable for ``RealZOSBackend``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import Enum
from pathlib import Path
from typing import Any

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.interop import to_python

Operation = Callable[..., Any]


def _member(obj: Any, *names: str, default: Any = ...) -> Any:
    """Read a member while tolerating mappings, casing, and API-version names."""
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


def _enum_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return value.name
    for name in ("name", "Name"):
        candidate = _member(value, name, default=None)
        if candidate not in (None, ""):
            return str(candidate)
    to_string = _member(value, "ToString", default=None)
    if callable(to_string):
        return str(to_string())
    text = str(value)
    return text.rsplit(".", 1)[-1]


def _json_safe(value: Any) -> Any:
    """Serialize values without ever leaking a live CLR proxy."""
    try:
        return to_python(value)
    except BackendError:
        return _enum_name(value)


def resolve_enum_member(namespace: Any, requested: str, *, operation: str) -> Any:
    """Resolve an enum mnemonic from a ZOS enum namespace.

    Exact lookup is attempted first, then case-insensitive lookup over ordinary
    Python/fake namespaces.  Finally, pythonnet-style enum parsing is tried when
    the enum type exposes ``Parse``.  An unknown mnemonic is reported as a
    backend validation error rather than being passed deeper into ZOS-API.
    """
    name = requested.strip()
    if not name:
        raise BackendError(operation, "operand_type must not be empty")
    direct = _member(namespace, name, default=None)
    if direct is not None:
        return direct
    folded = name.casefold()
    for candidate in dir(namespace):
        if candidate.casefold() == folded:
            return getattr(namespace, candidate)
    parse = _member(namespace, "Parse", default=None)
    if callable(parse):
        try:
            return parse(namespace, name, True)
        except (TypeError, ValueError):
            try:
                return parse(name, True)
            except (TypeError, ValueError):
                pass
    raise BackendError(operation, f"unknown operand type {requested!r}")


def _enum_namespace(api_root: Any, editor: str, enum_name: str, operation: str) -> Any:
    try:
        editors = _member(api_root, "Editors")
        editor_namespace = _member(editors, editor, editor.upper(), editor.lower())
        return _member(editor_namespace, enum_name)
    except AttributeError as exc:
        detail = f"ZOS enum namespace Editors.{editor}.{enum_name} is unavailable"
        raise BackendError(operation, detail) from exc


def _count(editor: Any, *names: str) -> int:
    return int(_member(editor, *names, default=0))


def _validate_row(row: int, count: int, operation: str) -> None:
    if row < 1 or row > count:
        raise BackendError(operation, f"row {row} is out of range 1..{count}")


def _row_bounds(start_row: int, end_row: int, count: int, operation: str) -> range:
    if start_row < 1:
        raise BackendError(operation, "start_row must be at least 1")
    stop = count if end_row == 0 else end_row
    if stop < start_row - 1 or stop > count:
        raise BackendError(operation, f"row range {start_row}..{stop} is outside 1..{count}")
    return range(start_row, stop + 1)


def _change_type(operand: Any, operand_type: Any, operation: str) -> None:
    method = _member(operand, "ChangeType", "SetType", default=None)
    if callable(method):
        method(operand_type)
        return
    for attribute in ("Type", "OperandType"):
        if hasattr(operand, attribute):
            setattr(operand, attribute, operand_type)
            return
    raise BackendError(operation, "operand does not expose ChangeType or a writable type property")


def _operand_type(operand: Any) -> str:
    return _enum_name(_member(operand, "Type", "OperandType", default=None))


def _set_if_present(obj: Any, names: tuple[str, ...], value: Any, operation: str) -> None:
    if value is None:
        return
    for name in names:
        if hasattr(obj, name):
            setattr(obj, name, value)
            return
    raise BackendError(operation, f"operand does not expose writable {names[0]}")


def _mce_cell(operand: Any, configuration: int, operation: str) -> Any:
    try:
        return _call(operand, ("GetOperandCell", "GetCellAt", "GetCell"), configuration)
    except (AttributeError, TypeError) as exc:
        raise BackendError(operation, "MCE operand cell access is unavailable") from exc


def _cell_value(cell: Any) -> Any:
    data_type = _enum_name(_member(cell, "DataType", "CellType", default=""))
    candidates = (
        ("StringValue", "Value", "Text")
        if data_type.casefold() in {"string", "text"}
        else ("IntegerValue", "Value")
        if data_type.casefold() in {"integer", "int"}
        else ("DoubleValue", "Value")
    )
    for name in candidates:
        try:
            return _json_safe(getattr(cell, name))
        except (AttributeError, TypeError):
            continue
    return None


def _pickup_details(cell: Any) -> dict[str, Any] | None:
    is_pickup = bool(_member(cell, "IsPickup", "Pickup", default=False))
    source = _member(
        cell,
        "PickupConfiguration",
        "PickupConfig",
        "PickupConfigurationNumber",
        default=None,
    )
    if not is_pickup and source is None:
        return None
    return {
        "configuration": int(source) if source is not None else None,
        "scale_factor": float(
            _member(cell, "PickupScaleFactor", "ScaleFactor", "PickupScale", default=1.0)
        ),
        "offset": float(_member(cell, "PickupOffset", "Offset", default=0.0)),
    }


def _make_pickup(
    cell: Any,
    pickup_config: int,
    scale_factor: float,
    offset: float,
    operation: str,
) -> None:
    for name in ("MakePickupFrom", "SetPickup", "MakePickup"):
        method = _member(cell, name, default=None)
        if not callable(method):
            continue
        for args in (
            (pickup_config, scale_factor, offset),
            (pickup_config, scale_factor),
            (pickup_config,),
        ):
            try:
                method(*args)
                return
            except TypeError:
                continue
    # A few wrappers expose the solve as writable properties instead of a method.
    if hasattr(cell, "PickupConfiguration"):
        cell.PickupConfiguration = pickup_config
        if hasattr(cell, "PickupScaleFactor"):
            cell.PickupScaleFactor = scale_factor
        if hasattr(cell, "PickupOffset"):
            cell.PickupOffset = offset
        if hasattr(cell, "IsPickup"):
            cell.IsPickup = True
        return
    raise BackendError(operation, "MCE cell does not expose a pickup-solve API")


def _append_or_insert(editor: Any, insert_at: int, operation: str) -> tuple[Any, int]:
    count = _count(editor, "NumberOfOperands", "OperandCount")
    if insert_at == 0:
        method = _member(editor, "AddOperand", "AppendOperand", default=None)
        if callable(method):
            operand = method()
            return operand, count + 1
        insert_at = count + 1
    if insert_at < 1 or insert_at > count + 1:
        raise BackendError(operation, f"insert_at must be 1..{count + 1} or 0")
    try:
        operand = _call(editor, ("InsertNewOperandAt", "InsertOperandAt"), insert_at)
    except (AttributeError, TypeError) as exc:
        raise BackendError(operation, "operand insertion API is unavailable") from exc
    return operand, insert_at


def _remove_operand(editor: Any, row: int, operation: str) -> None:
    count = _count(editor, "NumberOfOperands", "OperandCount")
    _validate_row(row, count, operation)
    for name, args in (
        ("RemoveOperandAt", (row,)),
        ("DeleteOperandAt", (row,)),
        ("RemoveOperandsAt", (row, 1)),
    ):
        method = _member(editor, name, default=None)
        if callable(method):
            method(*args)
            return
    raise BackendError(operation, "operand removal API is unavailable")


def _mce_operand_snapshot(operand: Any, row: int, configurations: int) -> dict[str, Any]:
    cells = []
    for configuration in range(1, configurations + 1):
        cell = _mce_cell(operand, configuration, "get_configuration_operands")
        cells.append(
            {
                "configuration": configuration,
                "value": _cell_value(cell),
                "pickup": _pickup_details(cell),
            }
        )
    return {
        "row": row,
        "operand_type": _operand_type(operand),
        "param1": int(_member(operand, "Param1", "Parameter1", default=0)),
        "param2": int(_member(operand, "Param2", "Parameter2", default=0)),
        "param3": int(_member(operand, "Param3", "Parameter3", default=0)),
        "cells": cells,
    }


def _mfe_operand_snapshot(operand: Any, row: int, include_value: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "row": row,
        "operand_type": _operand_type(operand),
        "target": _json_safe(_member(operand, "Target", default=0.0)),
        "weight": _json_safe(_member(operand, "Weight", default=0.0)),
        "int1": int(_member(operand, "Int1", default=0)),
        "int2": int(_member(operand, "Int2", default=0)),
    }
    for index in range(1, 7):
        result[f"data{index}"] = _json_safe(_member(operand, f"Data{index}", default=0.0))
    if include_value:
        result["value"] = _json_safe(_member(operand, "Value", default=None))
    return result


def build_operation_map(
    require_system: Callable[[], Any],
    api: Callable[[], Any],
) -> dict[str, Operation]:
    """Build bound MCE/MFE handlers for the backend operation dispatcher."""

    def mce() -> Any:
        return _member(require_system(), "MCE")

    def mfe() -> Any:
        return _member(require_system(), "MFE")

    def get_configuration() -> dict[str, Any]:
        editor = mce()
        return {
            "number_of_configurations": _count(
                editor, "NumberOfConfigurations", "ConfigurationCount"
            ),
            "current_configuration": int(
                _member(editor, "CurrentConfiguration", "CurrentConfigurationNumber", default=1)
            ),
        }

    def set_number_of_configurations(number_of_configurations: int) -> dict[str, Any]:
        operation = "set_number_of_configurations"
        requested = int(number_of_configurations)
        if requested < 1:
            raise BackendError(operation, "number_of_configurations must be at least 1")
        editor = mce()
        setter = _member(editor, "SetNumberOfConfigurations", default=None)
        if callable(setter):
            setter(requested)
        else:
            current = _count(editor, "NumberOfConfigurations", "ConfigurationCount")
            add = _member(editor, "AddConfiguration", default=None)
            delete = _member(editor, "DeleteConfiguration", "RemoveConfiguration", default=None)
            if requested > current and not callable(add):
                raise BackendError(operation, "MCE configuration-add API is unavailable")
            if requested < current and not callable(delete):
                raise BackendError(operation, "MCE configuration-delete API is unavailable")
            while current < requested:
                try:
                    add(False)
                except TypeError:
                    add()
                current += 1
            while current > requested:
                delete(current)
                current -= 1
        return get_configuration()

    def set_current_configuration(configuration_number: int) -> dict[str, Any]:
        operation = "set_current_configuration"
        requested = int(configuration_number)
        editor = mce()
        count = _count(editor, "NumberOfConfigurations", "ConfigurationCount")
        if requested < 1 or requested > count:
            raise BackendError(operation, f"configuration {requested} is out of range 1..{count}")
        setter = _member(editor, "SetCurrentConfiguration", default=None)
        if callable(setter):
            setter(requested)
        elif hasattr(editor, "CurrentConfiguration"):
            editor.CurrentConfiguration = requested
        elif hasattr(editor, "CurrentConfigurationNumber"):
            editor.CurrentConfigurationNumber = requested
        else:
            raise BackendError(operation, "MCE current-configuration API is unavailable")
        return get_configuration()

    def get_configuration_operands(
        start_row: int = 1,
        end_row: int = 0,
    ) -> dict[str, Any]:
        operation = "get_configuration_operands"
        editor = mce()
        count = _count(editor, "NumberOfOperands", "OperandCount")
        configurations = _count(editor, "NumberOfConfigurations", "ConfigurationCount")
        operands = [
            _mce_operand_snapshot(
                _call(editor, ("GetOperandAt", "GetOperand"), row), row, configurations
            )
            for row in _row_bounds(int(start_row), int(end_row), count, operation)
        ]
        return {
            **get_configuration(),
            "number_of_operands": count,
            "operands": operands,
        }

    def add_configuration_operand(
        operand_type: str,
        insert_at: int = 0,
        param1: int | None = None,
        param2: int | None = None,
        param3: int | None = None,
    ) -> dict[str, Any]:
        operation = "add_configuration_operand"
        editor = mce()
        operand, row = _append_or_insert(editor, int(insert_at), operation)
        enum_namespace = _enum_namespace(api(), "MCE", "MultiConfigOperandType", operation)
        _change_type(
            operand,
            resolve_enum_member(enum_namespace, operand_type, operation=operation),
            operation,
        )
        _set_if_present(operand, ("Param1", "Parameter1"), param1, operation)
        _set_if_present(operand, ("Param2", "Parameter2"), param2, operation)
        _set_if_present(operand, ("Param3", "Parameter3"), param3, operation)
        configurations = _count(editor, "NumberOfConfigurations", "ConfigurationCount")
        return _mce_operand_snapshot(operand, row, configurations)

    def delete_configuration_operand(row: int) -> dict[str, Any]:
        editor = mce()
        _remove_operand(editor, int(row), "delete_configuration_operand")
        return {
            "deleted": True,
            "row": int(row),
            "number_of_operands": _count(editor, "NumberOfOperands", "OperandCount"),
        }

    def set_configuration_operand_value(
        operand_row: int,
        configuration_number: int,
        value: float | None = None,
        pickup_config: int | None = None,
        scale_factor: float = 1.0,
        offset: float = 0.0,
    ) -> dict[str, Any]:
        operation = "set_configuration_operand_value"
        if (value is None) == (pickup_config is None):
            raise BackendError(operation, "provide exactly one of value or pickup_config")
        editor = mce()
        operand_count = _count(editor, "NumberOfOperands", "OperandCount")
        configurations = _count(editor, "NumberOfConfigurations", "ConfigurationCount")
        _validate_row(int(operand_row), operand_count, operation)
        configuration = int(configuration_number)
        if configuration < 1 or configuration > configurations:
            raise BackendError(
                operation, f"configuration {configuration} is out of range 1..{configurations}"
            )
        operand = _call(editor, ("GetOperandAt", "GetOperand"), int(operand_row))
        cell = _mce_cell(operand, configuration, operation)
        if pickup_config is not None:
            source = int(pickup_config)
            if source < 1 or source > configurations:
                raise BackendError(
                    operation, f"pickup configuration {source} is out of range 1..{configurations}"
                )
            if source == configuration:
                raise BackendError(operation, "a configuration cell cannot pick up from itself")
            _make_pickup(cell, source, float(scale_factor), float(offset), operation)
        else:
            assert value is not None
            if hasattr(cell, "DoubleValue"):
                cell.DoubleValue = float(value)
            elif hasattr(cell, "Value"):
                cell.Value = float(value)
            else:
                raise BackendError(operation, "MCE cell does not expose a writable value")
        return {
            "operand_row": int(operand_row),
            "configuration_number": configuration,
            "value": _cell_value(cell),
            "pickup": _pickup_details(cell),
        }

    def mce_add_config(with_pickups: bool = False) -> dict[str, Any]:
        editor = mce()
        add = _member(editor, "AddConfiguration", default=None)
        if not callable(add):
            return set_number_of_configurations(
                _count(editor, "NumberOfConfigurations", "ConfigurationCount") + 1
            )
        try:
            add(bool(with_pickups))
        except TypeError:
            add()
        return get_configuration()

    def mce_add_operand(
        operand_type: str,
        param1: int = 0,
        values: list[float] | None = None,
    ) -> dict[str, Any]:
        result = add_configuration_operand(operand_type, param1=param1)
        if values is not None:
            configurations = get_configuration()["number_of_configurations"]
            if len(values) > configurations:
                raise BackendError(
                    "mce_add_operand",
                    f"received {len(values)} values for {configurations} configurations",
                )
            for configuration, cell_value in enumerate(values, start=1):
                set_configuration_operand_value(
                    result["row"], configuration, value=float(cell_value)
                )
            result = _mce_operand_snapshot(
                _call(mce(), ("GetOperandAt", "GetOperand"), result["row"]),
                result["row"],
                configurations,
            )
        return result

    def get_merit_function(
        include_values: bool = True,
        start_row: int = 1,
        end_row: int = 0,
    ) -> dict[str, Any]:
        operation = "get_merit_function"
        editor = mfe()
        count = _count(editor, "NumberOfOperands", "OperandCount")
        operands = [
            _mfe_operand_snapshot(
                _call(editor, ("GetOperandAt", "GetOperand"), row),
                row,
                bool(include_values),
            )
            for row in _row_bounds(int(start_row), int(end_row), count, operation)
        ]
        return {"number_of_operands": count, "operands": operands}

    def add_operand(
        operand_type: str,
        target: float = 0.0,
        weight: float = 1.0,
        insert_at: int = 0,
        int1: int | None = None,
        int2: int | None = None,
        data1: float | None = None,
        data2: float | None = None,
        data3: float | None = None,
        data4: float | None = None,
        data5: float | None = None,
        data6: float | None = None,
    ) -> dict[str, Any]:
        operation = "add_operand"
        editor = mfe()
        operand, row = _append_or_insert(editor, int(insert_at), operation)
        enum_namespace = _enum_namespace(api(), "MFE", "MeritOperandType", operation)
        _change_type(
            operand,
            resolve_enum_member(enum_namespace, operand_type, operation=operation),
            operation,
        )
        _set_if_present(operand, ("Target",), float(target), operation)
        _set_if_present(operand, ("Weight",), float(weight), operation)
        _set_if_present(operand, ("Int1",), int1, operation)
        _set_if_present(operand, ("Int2",), int2, operation)
        for index, data in enumerate((data1, data2, data3, data4, data5, data6), start=1):
            _set_if_present(operand, (f"Data{index}",), data, operation)
        return _mfe_operand_snapshot(operand, row, True)

    def remove_operand(row: int) -> dict[str, Any]:
        editor = mfe()
        _remove_operand(editor, int(row), "remove_operand")
        return {
            "removed": True,
            "row": int(row),
            "number_of_operands": _count(editor, "NumberOfOperands", "OperandCount"),
        }

    def merit_value() -> dict[str, Any]:
        operation = "merit_value"
        editor = mfe()
        calculate = _member(
            editor,
            "CalculateMeritFunction",
            "CalculateMeritFunctionValue",
            "GetMeritFunctionValue",
            default=None,
        )
        if not callable(calculate):
            value = _member(editor, "MeritFunctionValue", "CurrentMeritFunction", default=None)
            if value is None:
                raise BackendError(operation, "merit-function calculation API is unavailable")
        else:
            value = calculate()
            if value is None:
                value = _member(editor, "MeritFunctionValue", "CurrentMeritFunction", default=None)
        return {"merit_value": _json_safe(value)}

    def load_merit_function_file(file_path: str) -> dict[str, Any]:
        operation = "load_merit_function_file"
        path = str(Path(file_path).expanduser().resolve())
        try:
            result = _call(
                mfe(),
                ("LoadMeritFunction", "LoadMeritFunctionFile", "LoadFile"),
                path,
            )
        except (AttributeError, TypeError) as exc:
            raise BackendError(operation, "merit-function load API is unavailable") from exc
        if result is False:
            raise BackendError(operation, f"OpticStudio did not load {path}")
        return {"path": path, "loaded": True}

    def save_merit_function_file(file_path: str) -> dict[str, Any]:
        operation = "save_merit_function_file"
        path = str(Path(file_path).expanduser().resolve())
        try:
            result = _call(
                mfe(),
                ("SaveMeritFunction", "SaveMeritFunctionFile", "SaveFile"),
                path,
            )
        except (AttributeError, TypeError) as exc:
            raise BackendError(operation, "merit-function save API is unavailable") from exc
        if result is False:
            raise BackendError(operation, f"OpticStudio did not save {path}")
        return {"path": path, "saved": True}

    operations: dict[str, Operation] = {
        "get_configuration": get_configuration,
        "set_number_of_configurations": set_number_of_configurations,
        "set_current_configuration": set_current_configuration,
        "get_configuration_operands": get_configuration_operands,
        "add_configuration_operand": add_configuration_operand,
        "delete_configuration_operand": delete_configuration_operand,
        "set_configuration_operand_value": set_configuration_operand_value,
        "get_merit_function": get_merit_function,
        "add_operand": add_operand,
        "remove_operand": remove_operand,
        "load_merit_function_file": load_merit_function_file,
        "save_merit_function_file": save_merit_function_file,
        # Legacy catalog operations retained as bound aliases/wrappers.
        "mce_summary": get_configuration_operands,
        "mce_add_config": mce_add_config,
        "mce_add_operand": mce_add_operand,
        "merit_value": merit_value,
    }
    return operations


__all__ = ["build_operation_map", "resolve_enum_member"]
