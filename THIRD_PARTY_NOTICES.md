# Third-party notices

This file records source provenance and runtime dependencies; it is not a substitute for each dependency's license text.

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
