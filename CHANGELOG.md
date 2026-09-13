# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases are intended to follow semantic versioning.

## [Unreleased]

## [0.1.0] - 2026-09-13

### Added

- Windows Python package scaffold for an MCP stdio server over OpticStudio ZOS-API.
- Offline-safe runtime configuration, discovery, worker/executor, backend protocol, lifecycle state, and fake-test boundaries.
- Tool catalog and source-derived capability/evidence manifest with 143 cataloged tools across 13 categories, 131 production handlers, 34 live-verified tools, 97 offline-implemented tools, 11 scaffolded entries, one intentionally unsupported tool, 3 resources, and 3 prompts.
- CLI entry points for serving stdio, environment diagnostics, version reporting, and manifest inspection.
- GitHub-ready documentation for installation, client configuration, architecture, testing, troubleshooting, security, licensing, and roadmap.
- Windows-only offline CI matrix for CPython 3.11 and 3.12.

### Changed

- Implemented the project as a Python package with stable MCP contracts and explicit coverage statuses.
- Constrained the build backend to versions that emit metadata accepted by the release validation toolchain.

### Security

- Proprietary Ansys/Zemax assemblies and optical data are excluded from source, distributions, CI, and examples.
- Live OpticStudio tests are opt-in and excluded from public CI.

[Unreleased]: https://github.com/YonggangG/Zemax_MCP_Server/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YonggangG/Zemax_MCP_Server/releases/tag/v0.1.0
