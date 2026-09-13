from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import zemax_mcp.zos.loader as loader
from zemax_mcp.zos.discovery import ZOSInstallation


class StaticInitializer:
    calls: ClassVar[list[str]] = []

    def __new__(cls) -> StaticInitializer:
        raise TypeError("cannot instantiate abstract class")

    @staticmethod
    def Initialize(path: str) -> bool:
        StaticInitializer.calls.append(path)
        return True


def test_nethelper_initializer_is_called_as_static_type(monkeypatch: Any, tmp_path: Path) -> None:
    install = tmp_path / "OpticStudio"
    install.mkdir()
    zosapi = install / "ZOSAPI.dll"
    interfaces = install / "ZOSAPI_Interfaces.dll"
    nethelper = install / "ZOSAPI_NetHelper.dll"
    for path in (zosapi, interfaces, nethelper):
        path.write_bytes(b"test")

    clr_module = ModuleType("clr")
    clr_module.AddReference = lambda _path: None  # type: ignore[attr-defined]
    helper_module = ModuleType("ZOSAPI_NetHelper")
    helper_module.ZOSAPI_Initializer = StaticInitializer  # type: ignore[attr-defined]
    zosapi_module = ModuleType("ZOSAPI")
    interfaces_module = ModuleType("ZOSAPI_Interfaces")
    modules = {
        "clr": clr_module,
        "ZOSAPI_NetHelper": helper_module,
        "ZOSAPI": zosapi_module,
        "ZOSAPI_Interfaces": interfaces_module,
    }

    monkeypatch.setattr(loader, "_loaded", None)
    monkeypatch.setattr(loader, "_load_pythonnet_netfx", lambda: None)
    monkeypatch.setattr(importlib, "import_module", lambda name: modules[name])
    StaticInitializer.calls.clear()

    result = loader.load_zosapi(
        ZOSInstallation(
            install_dir=install,
            zosapi_dir=install,
            zosapi_dll=zosapi,
            interfaces_dll=interfaces,
            nethelper_dll=nethelper,
            source="test",
        )
    )

    assert result.initializer is StaticInitializer
    assert StaticInitializer.calls == [str(install)]
