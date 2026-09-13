from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
from typing import Any

import pytest

from zemax_mcp import cli


def test_cli_version_manifest_and_doctor_outputs(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["version"]) == 0
    output = capsys.readouterr().out
    assert "zemax-mcp 0.1.0" in output
    assert "mcp " in output

    assert cli.main(["manifest", "--compact"]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["toolCount"] >= 50
    assert len(manifest["tools"]) == manifest["toolCount"]

    assert cli.main(["doctor", "--json"]) in {0, 1}
    doctor = json.loads(capsys.readouterr().out)
    assert "checks" in doctor
    assert doctor["liveVerified"] is False

    assert cli.main(["doctor"]) in {0, 1}
    text = capsys.readouterr().out
    assert "Live OpticStudio connectivity is not tested" in text


def test_cli_report_generates_and_detects_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "tool-coverage.json"
    assert cli.main(["report", "--output", str(report)]) == 0
    capsys.readouterr()
    assert cli.main(["report", "--output", str(report), "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    report.write_text("{}\n", encoding="utf-8")
    assert cli.main(["report", "--output", str(report), "--check"]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "stale"


def test_sdk_version_handles_missing_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert cli._sdk_version() == "not-installed"


def test_cli_serve_routes_transport_options_without_starting_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class Server:
        def run(self, transport: str, **kwargs: Any) -> None:
            calls.append((transport, kwargs))

    monkeypatch.setattr("zemax_mcp.server.create_server", lambda: Server())
    assert cli.main(["serve", "--transport", "stdio"]) == 0
    assert (
        cli.main(["serve", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9001"])
        == 0
    )
    assert calls == [
        ("stdio", {}),
        ("streamable-http", {"host": "0.0.0.0", "port": 9001}),
    ]
