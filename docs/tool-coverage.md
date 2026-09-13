# Tool coverage

## Source of truth

Tool coverage is generated at runtime from the normalized registry; there is no hand-maintained manifest file. Inspect the complete union with:

```powershell
uv run zemax-mcp manifest
```

The manifest is intended to include:

- package name and version;
- protocol/compatibility metadata;
- `toolCount`;
- category summaries;
- the complete `tools` array.

Each tool entry includes its name, description, category, backend operation, input schema, source provenance, and `implementationStatus`.

At the current development snapshot, the generated catalog reports **143 tools** in 13 categories: advanced (1), advanced-analysis (8), analysis (21), configuration (10), glass (6), lifecycle (9), merit (11), non-sequential (23), optimization (10), sequential (16), settings (23), tolerancing (3), and xdat (2). The production dispatcher exposes 131 public handlers, and the MCP server also advertises 3 resources and 3 prompts. Live stdio evidence against OpticStudio 2025 R1.01 verifies 34 tools; 97 other production handlers have offline-only evidence, 11 catalog entries remain scaffolded, and `zemax_eval` is intentionally unsupported. See `live-test-report.md` and the source-generated `tool-coverage.json` for exact lists and evidence. Run `uv run zemax-mcp report --check` to prevent report drift.

## Status model

| Status | Meaning | Evidence required |
| --- | --- | --- |
| `scaffolded` | The tool name, schema, category, and provenance are cataloged, but the implementation is incomplete. | Deterministic manifest generation. |
| `offline-implemented` | The MCP wrapper and service/backend behavior are implemented and tested with fakes or other offline facilities. | Offline contract/unit/stdio tests. |
| `live-verified` | The tool has succeeded against a recorded licensed OpticStudio environment. | An opt-in live test record with version, mode, license assumptions, input fixture, and expected result. |
| `unsupported` | The project intentionally cannot support the tool in its present design/environment. | A stable reason, such as unavailable ZOS-API capability, unsafe semantics, platform limitation, or missing legal redistribution right. |

Status is per tool, not per category or package version. A tool can be registered in MCP while still `scaffolded`, and an `offline-implemented` wrapper can still fail on a particular OpticStudio release or license.

## What offline implementation proves

Offline coverage can verify:

- MCP name and schema registration;
- argument validation and defaulting;
- operation dispatch and normalized JSON output;
- error mapping and unsupported behavior;
- lifecycle and ownership behavior using a fake backend;
- deterministic category and provenance metadata.

It does not verify ZOS-API member names, COM/.NET behavior, optical correctness, license availability, performance, or application UI state.

## Live-verification record

A future live-verification record should include at least:

- tool and package version;
- Windows version and architecture;
- Python version and pythonnet/.NET runtime;
- OpticStudio version/build;
- standalone or extension mode and extension instance ID when applicable;
- relevant license/API entitlement;
- non-proprietary or redistributable fixture description;
- expected assertions and observed result;
- cleanup behavior and whether files/application state were modified.

Do not include proprietary lens files, assemblies, activation data, or customer designs in the repository.

## Union policy

The catalog targets the complete public tool union of the two pinned upstream commits documented in [migration.md](migration.md). Overlaps are deduplicated without dropping provenance. Divergent operations remain visible. Newly discovered tools enter as `scaffolded`; they are never silently omitted because implementation work is incomplete.

## Release reporting

A release should report counts by status from the generated manifest, for example:

```text
scaffolded: <generated>
offline-implemented: <generated>
live-verified: <generated>
unsupported: <generated>
```

The current source-derived counts are `live-verified: 34`, `offline-implemented: 97`, `scaffolded: 11`, and `unsupported: 1`. Documentation must still avoid phrases such as “all tools work,” “fully validated,” or “production ready”; only the tools named in the recorded core and batch evidence have live verification.
