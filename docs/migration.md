# Migration and provenance

## Pinned sources

The Python package targets the union of two upstream commits rather than treating either repository's current branch as an unversioned dependency.

| Source | Pinned commit | Recorded contribution |
| --- | --- | --- |
| [jaruiz6363/OpticStudioMCPServer](https://github.com/jaruiz6363/OpticStudioMCPServer) | [`efc4d441796f5c1d5ae3e31759bbadfe3505b109`](https://github.com/jaruiz6363/OpticStudioMCPServer/commit/efc4d441796f5c1d5ae3e31759bbadfe3505b109) | Non-sequential-component merge, 2026-06-09 |
| [zym1998year/OpticStudioMCPServer](https://github.com/zym1998year/OpticStudioMCPServer) | [`8c9e3499f8d35db9a7383f7d2d0089ff92980a0a`](https://github.com/zym1998year/OpticStudioMCPServer/commit/8c9e3499f8d35db9a7383f7d2d0089ff92980a0a) | Divergent sequential operations, advanced analyses, and background startup, 2026-07-16 |

The manifest carries tool-level provenance. The table above documents the two reproducible primary source snapshots used to build the union. Supplemental compatibility comparison against `webworn/zemax-mcp-server` commit `3797d97492723f385988d47f8b183479bc172dd0` may also appear in per-tool provenance; it is not a replacement for either primary pin.

## Migration strategy

### Inventory before implementation

Every source tool is first recorded in the normalized catalog with its public name, description, input schema, category, backend operation, and provenance. This prevents a convenient subset from being mistaken for full parity.

### Deduplicate names, preserve capability

If both commits define the same capability, the Python registry exposes one stable contract. If their parameters differ, the union schema retains compatible optional parameters or documents the chosen normalization. A rename or merge must preserve provenance from both sources.

### Make divergence explicit

The two histories are not assumed to be interchangeable. Sequential operations, non-sequential operations, advanced analyses, optimizers, and startup behavior are reviewed independently. Incompatible semantics are not hidden behind a success response; they remain separate operations or are marked unsupported pending a safe design.

### Separate registration from verification

Migration has four states:

1. `scaffolded`: catalog and schema exist.
2. `offline-implemented`: wrapper/service behavior has deterministic offline coverage.
3. `live-verified`: the operation has passed a recorded licensed OpticStudio test.
4. `unsupported`: an explicit design, API, platform, or licensing reason prevents support.

No source implementation is promoted directly to `live-verified` merely because it existed upstream.

## Behavioral migration notes

### Process and startup

Upstream background-startup patterns are replaced by an explicit CLI plus a dedicated serialized ZOS executor. MCP server startup and OpticStudio connection are distinct lifecycle steps. This keeps `doctor`, `manifest`, imports, and CI usable without starting .NET or consuming a license.

### Connection modes

Upstream connection behavior is normalized into:

- `standalone`: server-owned application;
- `extension`: user-owned borrowed application selected by instance ID.

Cleanup honors ownership, avoiding accidental closure of a UI session attached through Interactive Extension.

### Configuration

Machine-specific paths are not embedded in source or client examples. Use `ZEMAX_MCP_INSTALL_DIR`, `ZEMAX_MCP_ZOSAPI_PATH`, `ZEMAX_MCP_CONNECTION_MODE`, and `ZEMAX_MCP_INSTANCE_ID`.

### Results and errors

Public results are JSON-compatible. Raw .NET objects and implicit global object references are replaced with normalized data or opaque session handles. Unsupported and unavailable operations report errors rather than returning a fabricated result.

### Numerics and advanced operations

Custom numerical optimization and image-producing analyses may require optional `numpy`, `scipy`, or Pillow dependencies. Their Python logic can be tested offline, but ZOS-API integration remains a separate verification gate.

## Guidance for users migrating client configuration

Replace an upstream direct script invocation with:

```powershell
uv --directory C:\path\to\zemax-mcp run zemax-mcp serve
```

Move local paths and connection selection into environment variables. Before using a tool name from an upstream README, query the union manifest:

```powershell
uv --directory C:\path\to\zemax-mcp run zemax-mcp manifest
```

Check the tool's `implementationStatus`; registration is not the same as live support. Test on disposable copies of optical systems before adopting the server in production workflows.

## Updating the pins later

A future upstream refresh should:

1. Record the new full commit hash and date.
2. Diff public tool names and schemas against the existing manifest.
3. Add new tools as `scaffolded` before implementation.
4. Preserve aliases only where their semantics are unambiguous.
5. Update provenance without deleting the historical pins.
6. Run the complete offline suite.
7. Perform live verification separately and record the exact environment.
