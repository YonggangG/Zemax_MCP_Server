from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path

import pytest

from zemax_mcp.errors import BackendError
from zemax_mcp.zos.interop import PLANO_RADIUS_COMPAT, compatible_radius, get_member, to_python


class Color(Enum):
    RED = "red"


@dataclass
class Sample:
    name: str
    values: tuple[int, int]


class FakeClrType:
    FullName = "System.Guid"


class FakeClrValue:
    def GetType(self) -> FakeClrType:
        return FakeClrType()

    def __str__(self) -> str:
        return "00000000-0000-0000-0000-000000000000"


def test_to_python_converts_transport_safe_value_families() -> None:
    value = {
        "enum": Color.RED,
        "path": Path("a") / "b",
        "date": date(2025, 1, 2),
        "datetime": datetime(2025, 1, 2, 3, 4, 5),
        "bytes": b"\x00\xff",
        "record": Sample("x", (1, 2)),
        "set": {3},
    }
    converted = to_python(value)
    assert converted == {
        "enum": "red",
        "path": str(Path("a") / "b"),
        "date": "2025-01-02",
        "datetime": "2025-01-02 03:04:05",
        "bytes": "00ff",
        "record": {"name": "x", "values": [1, 2]},
        "set": [3],
    }


def test_to_python_normalizes_non_finite_floats_and_clr_scalars() -> None:
    assert to_python(float("inf")) == "inf"
    assert to_python(float("-inf")) == "-inf"
    assert to_python(float("nan")) == "nan"
    assert to_python(FakeClrValue()) == "00000000-0000-0000-0000-000000000000"


def test_compatible_radius_uses_numeric_plano_sentinel() -> None:
    assert compatible_radius(float("inf")) == PLANO_RADIUS_COMPAT
    assert compatible_radius(float("-inf")) == -PLANO_RADIUS_COMPAT
    assert compatible_radius(25.0) == 25.0
    assert isinstance(compatible_radius(float("inf")), float)


def test_to_python_rejects_live_opaque_objects_and_excessive_depth() -> None:
    with pytest.raises(BackendError, match="store it as a handle"):
        to_python(object())
    with pytest.raises(BackendError, match="maximum conversion depth"):
        to_python([[[1]]], max_depth=1)


def test_get_member_supports_api_version_and_casing_fallbacks() -> None:
    class API:
        PrimarySystem = "system"

    assert get_member(API(), "primary_system", "PrimarySystem") == "system"
    with pytest.raises(AttributeError, match="none of"):
        get_member(API(), "Missing", "AlsoMissing")
