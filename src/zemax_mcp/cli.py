"""Command-line interface for the Zemax MCP server."""

from __future__ import annotations

import argparse
import importlib.metadata as _importlib_metadata
import json
import platform
import sys
from collections.abc import Sequence

from .registry import TOOL_CATALOG, catalog_manifest
from .version import __version__


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zemax-mcp", description="Zemax OpticStudio MCP server")
    subcommands = parser.add_subparsers(dest="command")

    serve = subcommands.add_parser("serve", help="Run the MCP server")
    serve.add_argument("--transport", choices=("stdio", "sse", "streamable-http"), default="stdio")
    serve.add_argument("--host", default="127.0.0.1", help="HTTP transport bind host")
    serve.add_argument("--port", type=int, default=8000, help="HTTP transport bind port")

    doctor = subcommands.add_parser("doctor", help="Check package, SDK, and runtime readiness")
    doctor.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    subcommands.add_parser("version", help="Print package and MCP SDK versions")
    manifest = subcommands.add_parser("manifest", help="Print the union tool manifest as JSON")
    manifest.add_argument("--compact", action="store_true", help="Emit compact JSON")
    report = subcommands.add_parser("report", help="Generate or check the source-derived report")
    report.add_argument("--output", default="tool-coverage.json", help="Report destination")
    report.add_argument("--check", action="store_true", help="Fail if the report is stale")
    return parser


def _sdk_version() -> str:
    try:
        return _importlib_metadata.version("mcp")
    except _importlib_metadata.PackageNotFoundError:
        return "not-installed"


def _doctor(*, json_output: bool = False) -> int:
    checks: list[tuple[str, bool, str]] = []
    sdk = _sdk_version()
    checks.append(("Python", sys.version_info >= (3, 11), platform.python_version()))
    checks.append(("MCP SDK", sdk != "not-installed", sdk))
    try:
        from mcp.server import MCPServer

        checks.append(("MCPServer v2 API", True, f"{MCPServer.__module__}.{MCPServer.__name__}"))
    except Exception as exc:
        checks.append(("MCPServer v2 API", False, str(exc)))
    checks.append(("Union catalog", len(TOOL_CATALOG) > 0, f"{len(TOOL_CATALOG)} tools"))
    try:
        from .zos import ZOSSession

        ZOSSession()
        checks.append(("CLR-free ZOS runtime import", True, "ready"))
    except Exception as exc:
        checks.append(("CLR-free ZOS runtime import", False, str(exc)))
    is_windows = sys.platform == "win32"
    checks.append(("Windows live runtime", is_windows, sys.platform))

    if json_output:
        print(
            json.dumps(
                {
                    "ok": all(ok for _, ok, _ in checks[:-1]),
                    "checks": [
                        {"name": label, "ok": passed, "detail": detail}
                        for label, passed, detail in checks
                    ],
                    "liveVerified": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for label, passed, detail in checks:
            print(f"{'OK' if passed else 'WARN'}  {label}: {detail}")
        print("INFO  Live OpticStudio connectivity is not tested by doctor; call zemax_connect.")
    critical = {
        "Python",
        "MCP SDK",
        "MCPServer v2 API",
        "Union catalog",
        "CLR-free ZOS runtime import",
    }
    return 0 if all(ok for label, ok, _ in checks if label in critical) else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = args.command or "serve"
    if command == "version":
        print(f"zemax-mcp {__version__}")
        print(f"mcp {_sdk_version()}")
        return 0
    if command == "manifest":
        indent = None if args.compact else 2
        print(json.dumps(catalog_manifest(), indent=indent, sort_keys=True))
        return 0
    if command == "doctor":
        return _doctor(json_output=getattr(args, "json", False))
    if command == "report":
        from .reporting import check_capability_report, write_capability_report

        output = getattr(args, "output", "tool-coverage.json")
        if getattr(args, "check", False):
            current, detail = check_capability_report(output)
            print(json.dumps({"ok": current, **detail}, sort_keys=True))
            return 0 if current else 1
        path = write_capability_report(output)
        print(path)
        return 0
    if command == "serve":
        from .server import create_server

        transport = getattr(args, "transport", "stdio")
        host: str = getattr(args, "host", "127.0.0.1")
        port: int = getattr(args, "port", 8000)
        server = create_server()
        if transport == "stdio":
            server.run("stdio")
        elif transport == "sse":
            server.run("sse", host=host, port=port)
        else:
            server.run("streamable-http", host=host, port=port)
        return 0
    raise AssertionError(f"unhandled command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
