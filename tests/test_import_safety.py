from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from zemax_mcp import __version__

ROOT = Path(__file__).resolve().parents[1]


def _run_isolated(code: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )


def test_version_is_available_without_runtime_dependencies() -> None:
    assert __version__ == "0.1.0"


def test_package_import_does_not_import_pythonnet_or_zosapi() -> None:
    code = f"""
import importlib.abc, json, sys
sys.path.insert(0, {str(ROOT / "src")!r})
blocked = ('clr', 'pythonnet', 'System', 'ZOSAPI')
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == blocked or fullname.startswith(tuple(name + '.' for name in blocked)):
            raise RuntimeError('eager native import: ' + fullname)
sys.meta_path.insert(0, Deny())
import zemax_mcp
result = {{'version': zemax_mcp.__version__, 'native': sorted(set(sys.modules) & set(blocked))}}
print(json.dumps(result))
"""
    result = _run_isolated(code)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"version": "0.1.0", "native": []}


def test_import_emits_no_stdout_or_stderr() -> None:
    result = _run_isolated(
        f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); import zemax_mcp"
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
