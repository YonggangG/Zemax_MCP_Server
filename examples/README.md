# Examples

These examples configure local MCP clients to launch `zemax-mcp` over stdio. Two launch patterns are supported:

- From a source checkout with `uv`:

  ```text
  C:\absolute\path\to\uv.exe --directory C:\absolute\path\to\zemax-mcp run zemax-mcp serve
  ```

- From an installed package by invoking the executable directly:

  ```text
  C:\absolute\path\to\zemax-mcp.exe serve
  ```

  Use `where.exe zemax-mcp` after installation and copy the returned absolute executable path into the client configuration. Set the command to that path and the arguments to `serve`; no `--directory` or `uv run` arguments are needed.

1. For the checkout-based JSON examples, replace every `C:\\path\\to\\zemax-mcp` placeholder with the absolute checkout path.
2. If the client cannot resolve `uv`, replace `uv` with the absolute path from `where.exe uv`.
3. To use an installed executable instead, replace the command and arguments as described above.
4. Choose `standalone` or `extension` deliberately.
5. Never commit license material, proprietary DLLs, customer paths, or optical systems.
6. Run `uv run zemax-mcp doctor` from a checkout, or `<absolute-path-to-zemax-mcp.exe> doctor` for an installed executable, before starting the client.

Files:

- `cherry-studio.json`: JSON-shaped Cherry Studio local MCP server entry.
- `claude-desktop.json`: `mcpServers` fragment for Claude Desktop.
- `claude-code.mcp.json`: optional project-scoped Claude Code `.mcp.json` template.
- `extension-env.json`: environment fragment for Interactive Extension mode.

Client schemas and UI labels can change between client versions. The invariant is a local **stdio** process with command `uv` and arguments:

```text
--directory C:\path\to\zemax-mcp run zemax-mcp serve
```
