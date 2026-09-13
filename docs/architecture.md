# Architecture

## Goals

The architecture keeps three concerns separate:

1. A deterministic MCP/JSON contract that clients and CI can inspect offline.
2. Stateful, serialized OpticStudio automation.
3. Proprietary runtime assets that remain on the user's licensed workstation.

This separation avoids importing or starting the .NET runtime during ordinary package discovery, manifest generation, schema tests, or documentation builds.

## Layers

### CLI and stdio transport

The `zemax-mcp` command owns process startup. `serve` starts a local MCP stdio transport. Stdin and stdout are protocol-only; human-readable logs and diagnostics must go to stderr so clients do not parse log lines as JSON-RPC.

Diagnostic and metadata subcommands do not require a live OpticStudio session:

- `doctor [--json]`
- `version`
- `manifest`

### Registry and union catalog

The registry presents the complete normalized union of the pinned upstream tool surfaces. It owns stable names, descriptions, categories, operation identifiers, input schemas, provenance, and implementation status. The runtime-generated manifest is the authoritative inventory and must be deterministic.

Overlapping upstream tools are represented once. Divergent behavior is reconciled behind one contract where safe; otherwise the distinction remains explicit in operation names or parameters. A tool's presence in the catalog does not imply live verification.

### Contracts and services

Pydantic models validate MCP input and serialize output. Service code translates stable contracts into backend operations. This layer must not leak pythonnet proxy objects, OpticStudio interfaces, or unmanaged handles into JSON.

Where an operation is not safely implemented, the service returns an explicit unsupported error rather than guessing at a ZOS-API member or silently reporting success.

### Executor and session lifecycle

OpticStudio automation is stateful and thread-sensitive. A process-wide executor serializes backend work on the dedicated ZOS worker instead of allowing arbitrary MCP request threads to call .NET objects directly.

The lifecycle tracks connection mode, ownership, instance ID, fault state, and cleanup:

- A standalone application is **owned** by the server and may be closed during disconnect.
- An extension application is **borrowed** and remains user-owned unless an explicit operation documents otherwise.
- Failed transitions leave a diagnostic state instead of an ambiguous partially connected state.

### Backend protocol

The pure-Python backend protocol defines connect, disconnect, state, and operation dispatch without importing pythonnet. Implementations include:

- A fake backend for deterministic offline tests.
- The real backend, which discovers the installation, loads the CLR and ZOS-API assemblies, connects to OpticStudio, and dispatches supported operations.

### Discovery and interop

Discovery order is:

1. Explicit `ZEMAX_MCP_ZOSAPI_PATH` or `ZEMAX_MCP_INSTALL_DIR` configuration.
2. Common machine and user registry locations.
3. Known Program Files installation paths.

The loader initializes pythonnet/.NET and loads assemblies only on the worker connection path. The public catalog and offline test suite therefore do not need OpticStudio installed.

### Handles

Long-lived OpticStudio/.NET objects are represented by opaque handles rather than serialized directly. Handle resolution is confined to the backend session, and invalid or expired handles produce explicit errors.

## Data flow

```text
MCP request
  -> tool registry and input contract
  -> service operation
  -> serialized executor request
  -> backend dispatch
  -> ZOS-API object model
  -> normalized JSON result
  -> MCP response
```

## Failure boundaries

Errors are normalized into package-specific categories for configuration, discovery, loading, connection, session state, invalid handles, backend failures, and unsupported operations. Raw .NET exception objects are not sent over MCP.

## Offline and live boundaries

Offline validation can prove:

- package imports do not require OpticStudio;
- schemas and manifests are deterministic;
- MCP tool registration and wrapper dispatch work;
- lifecycle and ownership rules work against fakes;
- errors serialize consistently.

It cannot prove:

- a specific OpticStudio release exposes the expected API member;
- a particular license permits a tool;
- a lens traces, optimizes, or analyzes correctly;
- extension attachment works in a user's UI session;
- performance and numerical output match a production environment.

Only recorded live tests on licensed systems can raise a tool to `live-verified`.
