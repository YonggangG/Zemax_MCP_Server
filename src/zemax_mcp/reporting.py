"""Generate and check derived capability reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .registry import catalog_manifest

REPORT_FILENAME = "tool-coverage.json"


def render_capability_report() -> str:
    """Render the authoritative source-derived manifest report."""
    return json.dumps(catalog_manifest(), indent=2, sort_keys=True, allow_nan=False) + "\n"


def write_capability_report(path: str | Path = REPORT_FILENAME) -> Path:
    """Write the current report and return its resolved path."""
    destination = Path(path)
    destination.write_text(render_capability_report(), encoding="utf-8")
    return destination.resolve()


def check_capability_report(path: str | Path = REPORT_FILENAME) -> tuple[bool, dict[str, Any]]:
    """Check a report against source without accepting stale hand-edited claims."""
    source = Path(path)
    if not source.exists():
        return False, {"path": str(source), "reason": "missing"}
    expected = render_capability_report()
    actual = source.read_text(encoding="utf-8")
    return actual == expected, {
        "path": str(source),
        "reason": "current" if actual == expected else "stale",
    }


__all__ = [
    "REPORT_FILENAME",
    "check_capability_report",
    "render_capability_report",
    "write_capability_report",
]
