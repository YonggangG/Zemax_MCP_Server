# Roadmap

The roadmap is evidence-driven. Catalog parity, offline implementation, and live verification are tracked separately.

## Phase 1: offline foundation

- Maintain import safety without OpticStudio or eager CLR initialization.
- Stabilize environment configuration and Windows installation discovery.
- Serialize all ZOS-API work through the dedicated executor.
- Complete deterministic fake-backend lifecycle, error, and handle tests.
- Keep public CI Windows-only on Python 3.11 and 3.12 with no licensed dependencies.

## Phase 2: complete union catalog

- Preserve the full normalized union of the two pinned upstream commits.
- Deduplicate overlapping tools without discarding provenance.
- Expose deterministic manifest counts and category summaries.
- Require every tool to carry one status: `scaffolded`, `offline-implemented`, `live-verified`, or `unsupported`.
- Prevent documentation and release notes from claiming more than the manifest evidence.

## Phase 3: offline implementation breadth

- Implement connection/system lifecycle operations.
- Implement sequential lens data, system settings, fields, wavelengths, ray tracing, cardinal points, and surface solves.
- Implement multi-configuration and merit-function operations.
- Implement analysis families: spot, ray/OPD fans, MTF, encircled energy, aberrations, illumination, color, field curvature, and distortion.
- Implement glass catalog discovery, filtering, and export without redistributing catalogs.
- Implement optimization, constrained optimization, multistart, global search, and Hammer wrappers with cancellation and time bounds.
- Implement non-sequential-component operations represented by the union catalog.
- Keep advanced real operations explicit when unsupported rather than adding speculative ZOS-API calls.

## Phase 4: live verification

- Define a reusable, non-proprietary fixture set.
- Record OpticStudio build, Python/.NET versions, license assumptions, and connection mode for every live run.
- Verify a minimal smoke subset in standalone and extension modes.
- Expand verification by category and supported OpticStudio release.
- Record numerical tolerances and cleanup guarantees.
- Promote individual tools to `live-verified` only from recorded evidence.

Public CI will remain offline. Licensed live verification belongs on controlled private workstations or self-hosted runners that comply with Ansys licensing; it must not upload assemblies or test designs as artifacts.

## Phase 5: release readiness

- Audit source provenance and dependency notices.
- Inspect source distributions and wheels for proprietary assets.
- Freeze compatibility and deprecation policy for tool names/contracts.
- Add release notes generated from manifest status deltas.
- Add a manually dispatched release workflow based on a trusted version tag.
- Use `https://github.com/YonggangG/Zemax_MCP_Server` as the canonical GitHub repository and enable the required repository security settings before release publication.
- Consider PyPI publication only after package metadata, artifacts, installation docs, and release ownership are reviewed.

## Possible future work

- Additional client configuration examples and validation helpers.
- Structured live-verification reports without proprietary data.
- Compatibility aliases for upstream tool names where semantics are exact.
- Per-operation timeouts, cancellation, and resource budgeting.
- Better diagnostics for multiple installed OpticStudio versions.
- Optional private-runner workflows for licensed integration testing, kept separate from public CI.

## Non-goals

- Bundling or downloading OpticStudio, ZOS-API assemblies, catalogs, or licenses.
- Circumventing Ansys licensing or API entitlements.
- Claiming platform independence while the real backend requires Windows and OpticStudio.
- Marking tools live-verified based solely on mocks, schemas, upstream code, or documentation review.
