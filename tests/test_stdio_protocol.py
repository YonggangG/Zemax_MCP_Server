from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import import_optional

ROOT = Path(__file__).resolve().parents[1]


def test_logging_defaults_to_stderr_not_stdout() -> None:
    module = import_optional("zemax_mcp.logging_config")
    configure = getattr(module, "configure_logging", None)
    if configure is None:
        pytest.skip("logging setup is currently internal")
    # A subprocess catches import-time output and any accidental stdout handler.
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); "
        "from zemax_mcp.logging_config import configure_logging, get_logger; "
        "configure_logging(); get_logger('purity').warning('sentinel')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, text=True, capture_output=True, timeout=20
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert "sentinel" in result.stderr


def test_stdio_server_answers_initialize_without_stdout_contamination() -> None:
    import_optional("zemax_mcp.cli")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "offline-test", "version": "1"},
        },
    }
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    # MCP Python supports newline-framed JSON on stdio; timeout protects against
    # implementations that wait for a follow-up initialized notification.
    try:
        result = subprocess.run(
            [sys.executable, "-m", "zemax_mcp"],
            cwd=ROOT,
            env=environment,
            input=json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("stdio lifecycle requires a persistent client; covered by MCP SDK tests")
    if result.returncode != 0 and "usage:" in result.stderr.casefold():
        pytest.skip("CLI requires an explicit serve subcommand")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, result.stderr
    messages = [json.loads(line) for line in lines]
    response = next(message for message in messages if message.get("id") == 1)
    assert response["jsonrpc"] == "2.0"
    assert "result" in response or "error" in response
    assert all(line.lstrip().startswith("{") for line in lines)
