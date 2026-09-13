# Third-party notices

This file records source provenance and runtime dependencies; it is not a substitute for each dependency's license text.

## Upstream implementation references

This project is a clean Python-package integration informed by two pinned upstream histories:

1. **jaruiz6363/OpticStudioMCPServer**
   - Repository: https://github.com/jaruiz6363/OpticStudioMCPServer
   - Pin: [`efc4d441796f5c1d5ae3e31759bbadfe3505b109`](https://github.com/jaruiz6363/OpticStudioMCPServer/commit/efc4d441796f5c1d5ae3e31759bbadfe3505b109)
   Recorded scope: non-sequential-component merge, 2026-06-09.

2. **zym1998year/OpticStudioMCPServer**
   - Repository: https://github.com/zym1998year/OpticStudioMCPServer
   - Pin: [`8c9e3499f8d35db9a7383f7d2d0089ff92980a0a`](https://github.com/zym1998year/OpticStudioMCPServer/commit/8c9e3499f8d35db9a7383f7d2d0089ff92980a0a)
   Recorded scope: divergent sequential operations, advanced analyses, and background startup, 2026-07-16.

Individual tools retain provenance metadata in the generated catalog manifest where applicable. The compatibility inventory also records supplemental comparison provenance from `webworn/zemax-mcp-server` at commit `3797d97492723f385988d47f8b183479bc172dd0`; that reference supplements schema/name reconciliation and is not one of the two primary migration pins above. Consult every corresponding upstream repository for its license and notices before copying code beyond what is included and licensed in this repository.

## Python dependencies

The package uses open-source dependencies declared in `pyproject.toml`, including:

- Model Context Protocol Python SDK (`mcp`)
- Pydantic
- pythonnet
- optional NumPy, SciPy, and Pillow packages
- development tools such as Hatchling, pytest, coverage, Ruff, mypy, build, and Twine

Their authors retain their copyrights, trademarks, and license terms. Dependency versions and transitive packages are recorded in `uv.lock`.

## Ansys Zemax OpticStudio and ZOS-API

Ansys Zemax OpticStudio, ZOS-API, its .NET assemblies, examples, catalogs, optical systems, documentation, and license technology are proprietary Ansys/Zemax products. They are **not included** in this repository or its distributions.

The package dynamically locates files from a user's separately installed and licensed OpticStudio environment. In particular, releases must not bundle:

- `ZOSAPI.dll`
- `ZOSAPI_Interfaces.dll`
- `ZOSAPI_NetHelper.dll`
- OpticStudio executables
- proprietary glass catalogs, sample lenses, analysis output, or license data

Users are responsible for complying with their Ansys license and ZOS-API terms. The MIT license for this repository grants no rights to Ansys software, trademarks, or proprietary data.

## Trademarks

Ansys, Zemax, OpticStudio, and ZOS-API are trademarks or product names of Ansys, Inc. Claude is a product of Anthropic. Cherry Studio is a product of its respective maintainers. All marks remain the property of their owners. Use in this repository is descriptive and does not imply endorsement or affiliation.
