# Troubleshooting

Start every investigation with:

```powershell
uv run zemax-mcp doctor
uv run zemax-mcp doctor --json
```

The diagnostic output describes detected prerequisites; it is not a live validation report for every tool.

## `uv` or `zemax-mcp` is not found

Check:

```powershell
where.exe uv
uv --version
uv --directory C:\path\to\zemax-mcp run zemax-mcp version
```

GUI MCP clients often inherit a different PATH from an interactive terminal. Put the absolute `uv.exe` path in the client configuration if needed. Use an absolute project directory and restart the client after configuration changes.

## ZOS-API cannot be located

Set either the installation root or assembly location:

```powershell
$env:ZEMAX_MCP_INSTALL_DIR = 'C:\Program Files\Ansys Zemax OpticStudio'
# or
$env:ZEMAX_MCP_ZOSAPI_PATH = 'C:\Program Files\Ansys Zemax OpticStudio\ZOS-API'
uv run zemax-mcp doctor
```

`ZEMAX_MCP_ZOSAPI_PATH` may identify the `ZOS-API` directory or `ZOSAPI.dll`. The installation must also contain the matching `ZOSAPI_Interfaces.dll`; some loading paths use `ZOSAPI_NetHelper.dll` from the installation root.

Do not solve discovery by copying the DLLs into this repository or virtual environment.

## pythonnet or CLR load failure

Verify:

- 64-bit CPython 3.11 or 3.12 is being used;
- OpticStudio and Python architectures match;
- the required Windows/.NET Framework runtime is installed;
- another library has not initialized an incompatible CLR first;
- assemblies all come from the same OpticStudio installation.

The server delays CLR loading until the ZOS worker connects. If `manifest` or package import triggers a CLR error, report it as a bug.

## No license or no application

Standalone mode may fail when no API-capable license seat is available, the license service is unreachable, or the installed version does not permit the requested automation mode. Check OpticStudio licensing directly, then retry `doctor` and a basic connection.

Do not retry rapidly in a loop; repeated launches can leave processes or license seats in use.

## Extension mode cannot connect

1. Start OpticStudio normally.
2. Enable/start **Programming → Interactive Extension** in the UI.
3. Note the instance ID displayed by OpticStudio.
4. Configure:

```powershell
$env:ZEMAX_MCP_CONNECTION_MODE = 'extension'
$env:ZEMAX_MCP_INSTANCE_ID = '0'
```

5. Start a fresh MCP server process.

Extension mode borrows the UI application. Confirm that the selected system is the one you intend to modify. If several instances exist, set the correct ID rather than relying on `0`.

## Standalone mode opens unexpected processes

Stop the MCP client so its stdio child can clean up, then inspect Task Manager for stale OpticStudio/server processes. Standalone applications are server-owned; extension applications are not. Abruptly killing the server can prevent normal standalone cleanup.

## MCP client reports invalid JSON or disconnects immediately

The usual cause is text written to stdout. Stdio stdout must contain MCP protocol messages only. Send diagnostics to stderr and remove `Write-Host`, shell banners, activation scripts, or wrapper commands that print before the server starts.

Run the direct command from a terminal and inspect behavior:

```powershell
uv --directory C:\path\to\zemax-mcp run zemax-mcp serve
```

Also verify that `serve` remains running rather than returning after printing help.

## Client shows an old tool list

MCP clients commonly keep the server process alive and cache tool metadata. Fully stop the client or remove/re-add the server, then confirm:

```powershell
uv --directory C:\path\to\zemax-mcp run zemax-mcp manifest
```

If the manifest is current but the client is not, the client is likely launching a different checkout or executable. Replace relative paths with absolute ones.

## A listed tool reports unsupported

Tool registration, offline implementation, and live verification are different states. Inspect `implementationStatus` and provenance in the manifest. An advanced operation may be cataloged for union completeness while its real backend remains intentionally unsupported.

Do not interpret a cataloged name as a promise that a particular OpticStudio version/license supports it.

## Analysis, optimization, or ray trace fails for one system

Check the optical system's mode, surfaces/objects, fields, wavelengths, aperture, merit function, operands, and analysis prerequisites. A successful connection does not make every tool valid for every model. Reproduce with a minimal disposable system and include normalized inputs and errors in a bug report, not the proprietary system file.

## Optional numerical or image functionality is unavailable

Install all extras:

```powershell
uv sync --all-extras --dev
```

NumPy/SciPy-backed custom optimization and Pillow-backed image handling are optional. Missing optional packages should produce an explicit dependency error, not a false tool success.

## Reporting a bug safely

Include:

- package, Python, Windows, and OpticStudio versions;
- connection mode and non-secret configuration names;
- tool name, normalized parameters, status, and error;
- whether the issue reproduces with a minimal non-proprietary system;
- `doctor --json` output after removing local paths or sensitive values.

Never attach proprietary assemblies, licenses, customer lens designs, private catalogs, credentials, or full logs without reviewing them.
