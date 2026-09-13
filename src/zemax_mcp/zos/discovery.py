"""Windows ZOS-API installation discovery without importing pythonnet."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from zemax_mcp.config import ENV_INSTALL_DIR, ENV_ZOSAPI_PATH, RuntimeConfig
from zemax_mcp.errors import DiscoveryError

ZOSAPI_ASSEMBLY = "ZOSAPI.dll"
ZOSAPI_INTERFACES_ASSEMBLY = "ZOSAPI_Interfaces.dll"
NETHELPER_ASSEMBLY = "ZOSAPI_NetHelper.dll"


@dataclass(frozen=True, slots=True)
class ZOSInstallation:
    """Resolved paths needed by the worker-side loader."""

    install_dir: Path
    zosapi_dir: Path
    zosapi_dll: Path
    interfaces_dll: Path
    nethelper_dll: Path | None = None
    source: str = "unknown"

    def validate(self) -> ZOSInstallation:
        missing = [path for path in (self.zosapi_dll, self.interfaces_dll) if not path.is_file()]
        if missing:
            rendered = ", ".join(str(path) for path in missing)
            raise DiscoveryError(f"ZOS-API installation is incomplete; missing {rendered}")
        return self


RegistryReader = Callable[[], Iterable[Path]]


def _candidate_from_path(path: Path, source: str) -> ZOSInstallation | None:
    path = path.expanduser()
    if path.is_file():
        if path.name.lower() == ZOSAPI_ASSEMBLY.lower():
            zosapi_dir = path.parent
            install_dir = zosapi_dir.parent if zosapi_dir.name.lower() == "zos-api" else zosapi_dir
        elif path.name.lower() == NETHELPER_ASSEMBLY.lower():
            install_dir = path.parent
            zosapi_dir = install_dir / "ZOS-API"
        else:
            return None
    else:
        if (path / ZOSAPI_ASSEMBLY).is_file():
            zosapi_dir = path
            install_dir = path.parent if path.name.lower() == "zos-api" else path
        elif (path / "ZOS-API" / ZOSAPI_ASSEMBLY).is_file():
            install_dir = path
            zosapi_dir = path / "ZOS-API"
        else:
            return None
    nethelper = install_dir / NETHELPER_ASSEMBLY
    return ZOSInstallation(
        install_dir=install_dir.resolve(),
        zosapi_dir=zosapi_dir.resolve(),
        zosapi_dll=(zosapi_dir / ZOSAPI_ASSEMBLY).resolve(),
        interfaces_dll=(zosapi_dir / ZOSAPI_INTERFACES_ASSEMBLY).resolve(),
        nethelper_dll=nethelper.resolve() if nethelper.is_file() else None,
        source=source,
    )


def _registry_install_dirs() -> Iterable[Path]:
    """Read common Ansys/Zemax registry keys; unavailable off Windows."""
    if sys.platform != "win32":
        return ()
    try:
        import winreg
    except ImportError:
        return ()

    keys = (
        r"SOFTWARE\Zemax",
        r"SOFTWARE\Zemax\OpticStudio",
        r"SOFTWARE\Ansys, Inc.\Zemax OpticStudio",
        r"SOFTWARE\WOW6432Node\Zemax",
        r"SOFTWARE\WOW6432Node\Ansys, Inc.\Zemax OpticStudio",
    )
    values = (
        "InstallDir",
        "InstallPath",
        "ZemaxRoot",
        "RootDir",
        "Path",
    )
    result: list[Path] = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key_name in keys:
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    for value_name in values:
                        try:
                            value, _ = winreg.QueryValueEx(key, value_name)
                        except OSError:
                            continue
                        if isinstance(value, str) and value:
                            result.append(Path(os.path.expandvars(value)))
            except OSError:
                continue
    return result


def known_install_dirs(env: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    source = os.environ if env is None else env
    roots = [
        source.get("PROGRAMFILES"),
        source.get("PROGRAMW6432"),
        source.get("PROGRAMFILES(X86)"),
    ]
    suffixes = (
        Path("Ansys Zemax OpticStudio"),
        Path("Zemax OpticStudio"),
        Path("Zemax OpticStudio") / "OpticStudio",
    )
    candidates: list[Path] = []
    for root in roots:
        if root:
            candidates.extend(Path(root) / suffix for suffix in suffixes)
    return tuple(candidates)


def discover_installation(
    config: RuntimeConfig | None = None,
    *,
    env: Mapping[str, str] | None = None,
    registry_reader: RegistryReader = _registry_install_dirs,
    extra_paths: Iterable[Path] = (),
) -> ZOSInstallation:
    """Resolve an installation by explicit config, environment, registry, then known paths."""
    source_env = os.environ if env is None else env
    runtime = config or RuntimeConfig.from_env(source_env)
    candidates: list[tuple[Path, str]] = []
    if runtime.zosapi_path is not None:
        candidates.append((runtime.zosapi_path, "config:zosapi_path"))
    if runtime.install_dir is not None:
        candidates.append((runtime.install_dir, "config:install_dir"))
    if source_env.get(ENV_ZOSAPI_PATH):
        candidates.append((Path(source_env[ENV_ZOSAPI_PATH]), f"env:{ENV_ZOSAPI_PATH}"))
    if source_env.get(ENV_INSTALL_DIR):
        candidates.append((Path(source_env[ENV_INSTALL_DIR]), f"env:{ENV_INSTALL_DIR}"))
    candidates.extend((path, "registry") for path in registry_reader())
    candidates.extend((path, "known-path") for path in known_install_dirs(source_env))
    candidates.extend((path, "extra-path") for path in extra_paths)

    checked: list[str] = []
    seen: set[str] = set()
    for raw_path, source in candidates:
        path = Path(os.path.expandvars(str(raw_path))).expanduser()
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        checked.append(str(path))
        found = _candidate_from_path(path, source)
        if found is not None:
            try:
                return found.validate()
            except DiscoveryError:
                # A stale environment/registry entry should not prevent later
                # candidates from being considered.
                continue

    details = (
        f" Checked: {', '.join(checked)}" if checked else " No candidate paths were available."
    )
    raise DiscoveryError(
        "Could not locate ZOS-API. Set ZEMAX_MCP_INSTALL_DIR or ZEMAX_MCP_ZOSAPI_PATH." + details
    )
