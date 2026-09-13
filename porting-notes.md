# Porting Notes

This project combines the public MCP surfaces researched at:

- `jaruiz6363/OpticStudioMCPServer` commit `efc4d441796f5c1d5ae3e31759bbadfe3505b109`
- `zym1998year/OpticStudioMCPServer` commit `8c9e3499f8d35db9a7383f7d2d0089ff92980a0a`
- supplemental Python naming/coverage reference `webworn/zemax-mcp-server` commit `3797d97492723f385988d47f8b183479bc172dd0`

The MCP catalog is complete at the contract/delegation layer. The direct Python.NET backend is implemented and offline-tested for connection lifecycle, file operations, basic system/surface operations, single-ray tracing, and RMS spot evaluation. Advanced calls retain explicit schemas and delegate through the session, but most require live per-version ZOS-API implementation/verification before production use. Unsupported real-backend calls fail explicitly; they do not fabricate optical results.

Important corrections relative to the C# implementations include a dedicated ZOS owner thread, extension sessions that do not close the user's GUI instance, rollback of partial connection failures, CLR-free server imports, and strict stdout protection for MCP stdio.
