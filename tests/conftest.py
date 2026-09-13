from __future__ import annotations

import importlib
import inspect
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def import_optional(module_name: str) -> Any:
    """Import an evolving production module, skipping only when truly absent."""

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name or module_name.startswith(f"{exc.name}."):
            pytest.skip(f"intended production module is not available yet: {module_name}")
        raise


def first_attribute(module: Any, *names: str) -> Any:
    for name in names:
        if hasattr(module, name):
            return getattr(module, name)
    pytest.fail(f"{module.__name__} must expose one of: {', '.join(names)}")


def construct_with_supported_kwargs(factory: Any, **values: Any) -> Any:
    """Pass only named constructor arguments accepted by an evolving API."""

    signature = inspect.signature(factory)
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    kwargs = (
        values
        if accepts_kwargs
        else {key: value for key, value in values.items() if key in signature.parameters}
    )
    return factory(**kwargs)


@pytest.fixture(autouse=True)
def no_live_zemax_environment(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[None]:
    """Make every ordinary test explicitly offline and reproducible."""

    if request.node.get_closest_marker("live_zemax") is not None:
        yield
        return
    for name in (
        "ZEMAX_MCP_LIVE",
        "ZEMAX_OPTICSTUDIO_PATH",
        "ZOSAPI_PATH",
        "ANSYS_ZEMAX_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def live_zemax_enabled() -> bool:
    return os.environ.get("ZEMAX_MCP_LIVE", "").casefold() in {"1", "true", "yes"}
