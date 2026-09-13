from __future__ import annotations

from pathlib import Path

import pytest

from zemax_mcp.config import RuntimeConfig
from zemax_mcp.errors import DiscoveryError
from zemax_mcp.zos.discovery import discover_installation


def _installation(tmp_path: Path, name: str = "OpticStudio") -> Path:
    install = tmp_path / name
    api = install / "ZOS-API"
    api.mkdir(parents=True)
    (api / "ZOSAPI.dll").write_bytes(b"fake")
    (api / "ZOSAPI_Interfaces.dll").write_bytes(b"fake")
    (install / "ZOSAPI_NetHelper.dll").write_bytes(b"fake")
    return install


def test_discovery_accepts_explicit_install_directory(tmp_path: Path) -> None:
    install = _installation(tmp_path)
    found = discover_installation(
        RuntimeConfig(install_dir=install), env={}, registry_reader=lambda: ()
    )
    assert found.install_dir == install.resolve()
    assert found.zosapi_dir == (install / "ZOS-API").resolve()
    assert found.source == "config:install_dir"


def test_discovery_accepts_direct_zosapi_dll_path(tmp_path: Path) -> None:
    install = _installation(tmp_path)
    dll = install / "ZOS-API" / "ZOSAPI.dll"
    found = discover_installation(
        RuntimeConfig(zosapi_path=dll), env={}, registry_reader=lambda: ()
    )
    assert found.zosapi_dll == dll.resolve()


def test_discovery_precedence_is_explicit_then_registry_then_extra(tmp_path: Path) -> None:
    explicit = _installation(tmp_path, "Explicit")
    registry = _installation(tmp_path, "Registry")
    extra = _installation(tmp_path, "Extra")
    found = discover_installation(
        RuntimeConfig(install_dir=explicit),
        env={},
        registry_reader=lambda: (registry,),
        extra_paths=(extra,),
    )
    assert found.install_dir == explicit.resolve()


def test_discovery_skips_incomplete_candidate_and_uses_next(tmp_path: Path) -> None:
    incomplete = tmp_path / "Incomplete" / "ZOS-API"
    incomplete.mkdir(parents=True)
    (incomplete / "ZOSAPI.dll").write_bytes(b"fake")
    complete = _installation(tmp_path, "Complete")
    found = discover_installation(
        RuntimeConfig(), env={}, registry_reader=lambda: (), extra_paths=(incomplete, complete)
    )
    assert found.install_dir == complete.resolve()


def test_discovery_failure_is_actionable_and_lists_checked_paths(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(DiscoveryError) as captured:
        discover_installation(
            RuntimeConfig(install_dir=missing), env={}, registry_reader=lambda: ()
        )
    message = str(captured.value)
    assert "ZEMAX_MCP_INSTALL_DIR" in message
    assert str(missing) in message
