# Testing

## Test tiers

### Unit tests

Pure-Python validation for configuration, discovery candidates, schemas, state transitions, handles, normalized errors, numerical helpers, and catalog metadata.

### Contract tests

Verify every manifest entry has a valid MCP schema, unique stable name, known category, provenance, backend operation, and one of the allowed implementation statuses.

### Fake-backend integration tests

Exercise service dispatch and lifecycle through the same backend protocol used by the real implementation, without pythonnet or OpticStudio.

### Stdio tests

Start the server as a subprocess, exchange MCP initialization/tool-list requests over stdio, and verify that stdout contains only protocol frames. These tests must use the fake/offline path and must not discover or launch OpticStudio.

### Live OpticStudio tests

Opt-in tests marked `live_zemax`. They are the only test tier that can contribute evidence toward `live-verified` status.

## Offline developer checks

```powershell
uv sync --all-extras --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest -m "not live_zemax" --cov=zemax_mcp --cov-report=term-missing --cov-report=xml
uv build
```

Twine 6.2 currently rejects Core Metadata 2.5 even when the distribution builds successfully, because that Twine release hard-codes metadata support through 2.4. Re-enable `twine check` when the pinned toolchain supports the emitted metadata version; meanwhile inspect archive contents as part of release review.

If optional dependencies are not relevant to a change, `uv sync --dev` can be used for a smaller environment. CI uses the locked dependencies and runs only offline checks.

## Live tests

Run live tests only on a licensed Windows workstation:

```powershell
$env:ZEMAX_MCP_LIVE = '1'
uv run pytest -m live_zemax
```

Before running:

1. Read the selected tests and understand their changes.
2. Close or save unrelated OpticStudio work.
3. Use disposable copies of optical systems.
4. Confirm a license seat is available.
5. Select standalone or extension mode deliberately.
6. Set explicit installation paths if auto-discovery could choose the wrong version.
7. Capture the environment metadata required by [tool-coverage.md](tool-coverage.md).

The `ZEMAX_MCP_LIVE=1` gate prevents accidental execution when a developer selects markers broadly. Live tests are excluded from public GitHub Actions. They must not be enabled by adding OpticStudio DLLs or license material to CI secrets/artifacts.

## Coverage policy

Python branch coverage is measured for `zemax_mcp`, with the project threshold configured in `pyproject.toml`. Coverage is a quality signal for offline code; it does not substitute for tool-level live verification.

## Adding a tool

A change that adds a tool should include:

- catalog metadata and upstream provenance;
- input contract tests;
- registration/manifest assertions;
- fake-backend success and failure behavior where implemented;
- status no higher than the evidence supports;
- an explicit unsupported reason if it cannot be implemented.

A live test may be added under the `live_zemax` marker, but it must remain skipped from ordinary and CI runs.

## CI platform matrix

Public CI is intentionally limited to:

- `windows-latest`;
- CPython 3.11 and 3.12;
- locked `uv` dependency installation;
- no OpticStudio discovery, no proprietary assemblies, no API license, and no live marker.

A test that tries to load ZOS-API in this environment is an architecture regression, not a reason to add licensed software to CI.
