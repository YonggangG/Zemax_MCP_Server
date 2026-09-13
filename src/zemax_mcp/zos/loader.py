"""Worker-only pythonnet and ZOS-API assembly loading."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import get_ident
from types import ModuleType
from typing import Any

from zemax_mcp.errors import LoaderError

from .discovery import ZOSInstallation


@dataclass(frozen=True, slots=True)
class LoadedZOSAPI:
    """Python modules and initializer exposed after a successful load."""

    zosapi: ModuleType
    zosapi_interfaces: ModuleType
    nethelper: ModuleType | None
    initializer: Any | None
    worker_thread_id: int


_loaded: LoadedZOSAPI | None = None


def _load_pythonnet_netfx() -> None:
    try:
        pythonnet = importlib.import_module("pythonnet")
    except ImportError as exc:
        raise LoaderError(
            "pythonnet is not installed; install zemax-mcp on Windows with its dependencies"
        ) from exc
    load = getattr(pythonnet, "load", None)
    if load is None:
        raise LoaderError("pythonnet.load is unavailable; pythonnet 3.1 or newer is required")
    try:
        load("netfx")
    except RuntimeError as exc:
        # pythonnet raises after a runtime was already loaded. Accept only netfx.
        get_runtime_info = getattr(pythonnet, "get_runtime_info", None)
        info = get_runtime_info() if callable(get_runtime_info) else None
        if info is None or "netfx" not in str(info).lower():
            raise LoaderError(f"failed to initialize the .NET Framework runtime: {exc}") from exc


def _add_reference(clr: ModuleType, path: Path, label: str) -> None:
    try:
        clr.AddReference(str(path))
    except Exception as exc:
        raise LoaderError(f"failed to load {label} from {path}: {exc}") from exc


def load_zosapi(installation: ZOSInstallation) -> LoadedZOSAPI:
    """Explicitly load netfx and ZOS assemblies on the calling worker thread.

    This is the only module that imports ``pythonnet`` or ``clr``, and it does so
    inside this function rather than at package import time.
    """
    global _loaded
    if _loaded is not None:
        return _loaded
    if sys.platform != "win32":
        raise LoaderError("ZOS-API is supported only on Windows")
    installation.validate()
    _load_pythonnet_netfx()
    try:
        clr = importlib.import_module("clr")
    except ImportError as exc:
        raise LoaderError("pythonnet initialized but the clr module could not be imported") from exc

    initializer: Any | None = None
    nethelper_module: ModuleType | None = None
    if installation.nethelper_dll is not None:
        _add_reference(clr, installation.nethelper_dll, "ZOSAPI_NetHelper")
        try:
            nethelper_module = importlib.import_module("ZOSAPI_NetHelper")
            initializer_type = getattr(nethelper_module, "ZOSAPI_Initializer", None)
            if initializer_type is not None:
                # ZOSAPI_Initializer is a static .NET helper type. Instantiating it
                # through pythonnet raises "cannot instantiate abstract class" on
                # current OpticStudio releases.
                initializer = initializer_type
                initialize = getattr(initializer_type, "Initialize", None)
                if callable(initialize):
                    initialized = initialize(str(installation.install_dir))
                    if initialized is False:
                        raise LoaderError(f"ZOSAPI_Initializer rejected {installation.install_dir}")
        except LoaderError:
            raise
        except Exception as exc:
            raise LoaderError(f"ZOSAPI_NetHelper initialization failed: {exc}") from exc

    _add_reference(clr, installation.interfaces_dll, "ZOSAPI_Interfaces")
    _add_reference(clr, installation.zosapi_dll, "ZOSAPI")
    try:
        zosapi = importlib.import_module("ZOSAPI")
        # ZOSAPI_Interfaces.dll contains interface metadata but does not expose a
        # Python-importable namespace on all OpticStudio releases. Loading its
        # assembly reference is required; importing it is optional.
        try:
            interfaces = importlib.import_module("ZOSAPI_Interfaces")
        except ImportError:
            interfaces = zosapi
    except ImportError as exc:
        raise LoaderError(
            f"ZOS-API assemblies loaded but the ZOSAPI namespace is unavailable: {exc}"
        ) from exc
    _loaded = LoadedZOSAPI(
        zosapi=zosapi,
        zosapi_interfaces=interfaces,
        nethelper=nethelper_module,
        initializer=initializer,
        worker_thread_id=get_ident(),
    )
    return _loaded
