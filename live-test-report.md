# Live OpticStudio Test Report

Date: 2026-09-12

## Current rollup

The current source-generated catalog advertises **143 tools, 3 resources, and 3 prompts**. Its 143 tools comprise **131 production handlers**, including **34 live-verified** and **97 offline-implemented** tools, plus **11 scaffolded** tools and **1 intentionally unsupported** tool (`zemax_eval`). The 34 live-verified tools are backed by the accumulated core and Batch 1-4 records summarized below; historical advertised counts are retained where they describe the state of a specific run.

## Historical core-run environment

- Windows 11 Pro x64
- CPython 3.11.3 x64
- MCP Python SDK 2.2.0
- Ansys Zemax OpticStudio 2025 R1.01
- ZOS-API through Python.NET 3.1.0 and .NET Framework
- MCP transport: stdio
- Connection mode: standalone

## Historical core MCP surface

During the initial core run, the server advertised 122 tools, two resources, and three prompts. The following 13 tools completed successfully through a real MCP stdio subprocess and licensed OpticStudio instance:

- `zemax_status`
- `zemax_connect`
- `zemax_disconnect`
- `zemax_restart`
- `zemax_new_system`
- `zemax_open_file`
- `zemax_save_file`
- `zemax_get_system`
- `zemax_get_surface`
- `zemax_add_surface`
- `zemax_set_surface`
- `zemax_ray_trace`
- `zemax_rms_spot`

A disposable system was created and modified, saved to `live-output/mcp_live_test.zmx`, reopened, ray-traced, and evaluated for RMS spot. Standalone restart and ownership-aware disconnect succeeded. Detailed machine-readable results are in `live-output/mcp_stdio_core_results.json`.

## Defects found and fixed

1. `ZOSAPI_Initializer` was incorrectly instantiated; it is a static helper type.
2. `ZOSAPI_Interfaces.dll` does not always expose an importable Python namespace even though its assembly must be loaded.
3. Public MCP camelCase parameters were not translated to snake_case backend parameters.
4. Lifecycle tools were incorrectly sent through generic dispatch.
5. `CreateNewSystem` requires a `ZOSAPI.SystemType` argument.
6. RMS spot public inputs did not match the backend signature.
7. The resolved installation was not retained for status reporting.

Regression tests were added and the full offline suite passes.

## Historical core-run coverage

At the time of the initial core run, the source-derived capability model distinguished the 13 live-verified core tools from 52 additional production handlers with offline-only evidence, 56 scaffolded catalog entries, and the intentionally unsupported `zemax_eval`. That run did not validate the additional production handlers. Interactive Extension ownership had offline tests but was not live-tested in that pass. The current rollup above supersedes these historical counts.

## Runtime notice

OpticStudio emitted `FRU__delta_init(): Attempt to start when running!` on stderr during some repeated standalone starts. It did not corrupt MCP stdout or prevent operations, but it should be monitored during repeated restart/parallel-client testing.


## Interactive Extension verification

A user-prepared blank disposable GUI system was tested with a configured Interactive Extension instance and Auto Close on Disconnect disabled. The test verified:

- explicit attachment with `mode=extension` and an instance ID;
- borrowed ownership and matching GUI prescription;
- object, internal, and image surface reads;
- central batch ray trace;
- a full disposable surface write (radius, thickness, N-BK7, semi-diameter, comment);
- exact restoration to the pre-test surface state, including planar infinity;
- disconnect with no save and an explicitly released API connection;
- the original OpticStudio GUI process remained alive after disconnect;
- successful reconnection to the configured extension instance;
- extension restart preserving mode and the configured instance;
- final disconnect while the GUI remained alive.

Evidence: `live-output/extension_instance11_results.json`.


## Batch 1 certification

A standalone MCP stdio run on OpticStudio 2025 R1.01 advertised 131 tools and live-verified nine new Batch 1 tools: system units, title/notes/author, sequential polarization, current-system material catalog add/remove, and close-file. The disposable test restored changed settings, removed only its own added catalog, confirmed close-file left the application connected with no system, confirmed a system-dependent call failed without reconnecting, reopened via the application, verified the persisted title, created a new system without reconnecting, disconnected, and deleted temporary lens/auxiliary files. Evidence: `live-output/batch1/mcp_stdio_batch1_results.json`.


## Batch 2-4 certification

Batch 2 live stdio certification succeeded for `zemax_huygens_mtf`, `zemax_scale_lens`, and guarded `zemax_design_lockdown` on disposable sequential copies. Batch 3 succeeded for typed Black Body source spectrum get/set, Detector Polar full/pixel reads, detector DDP save/load, and scalar Detector Viewer after typed settings casting. Batch 4 succeeded for bounded streaming `zemax_zrd_summary` and `zemax_zrd_read` when the paired non-sequential lens was open; the small official ZRD produced one ray and ten segments. Evidence is retained under `live-output/batch2`, `live-output/batch3`, and `live-output/batch4`. The corrected NSC ZRD writer is production/offline implemented but was not promoted by the reader-only Batch 4 evidence.
