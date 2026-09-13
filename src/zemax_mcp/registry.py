"""Union catalog for all supported Zemax MCP compatibility surfaces.

The catalog is deliberately data-driven: every public name and JSON schema is stable,
while execution is delegated to the selected ZOS session/backend.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from .capabilities import LIVE_EVIDENCE_RECORDS, derive_tool_capability
from .contracts import ToolSpec, compatibility_manifest
from .version import __version__

JSON = dict[str, Any]
ZYM = "zym@8c9e3499f8d35db9a7383f7d2d0089ff92980a0a"
WEBWORN = "webworn@3797d97492723f385988d47f8b183479bc172dd0"
JARUIZ = "jaruiz-nsc@efc4d441796f5c1d5ae3e31759bbadfe3505b109"
UNION = "compatibility-union"


def _object(properties: JSON | None = None, required: Iterable[str] = ()) -> JSON:
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
        "additionalProperties": False,
    }


def _string(description: str, *, enum: list[str] | None = None, default: str | None = None) -> JSON:
    out: JSON = {"type": "string", "description": description}
    if enum is not None:
        out["enum"] = enum
    if default is not None:
        out["default"] = default
    return out


def _number(description: str, default: float | None = None) -> JSON:
    out: JSON = {"type": "number", "description": description}
    if default is not None:
        out["default"] = default
    return out


def _integer(description: str, default: int | None = None) -> JSON:
    out: JSON = {"type": "integer", "description": description}
    if default is not None:
        out["default"] = default
    return out


def _boolean(description: str, default: bool | None = None) -> JSON:
    out: JSON = {"type": "boolean", "description": description}
    if default is not None:
        out["default"] = default
    return out


def _array(description: str, items: JSON) -> JSON:
    return {"type": "array", "description": description, "items": items}


def _spec(
    name: str,
    description: str,
    category: str,
    properties: JSON | None = None,
    required: Iterable[str] = (),
    provenance: tuple[str, ...] = (UNION,),
    *,
    operation: str | None = None,
) -> ToolSpec:
    dispatch_operation = operation or name.removeprefix("zemax_")
    capability = derive_tool_capability(name, dispatch_operation)
    implementation_status = (
        "live-verified"
        if capability.evidence_status == "live-verified"
        else "offline-implemented"
        if capability.capability_status == "production"
        else capability.capability_status
    )
    return ToolSpec(
        name=name,
        description=description,
        category=category,
        input_schema=_object(properties, required),
        provenance=provenance,
        operation=operation,
        implementation_status=implementation_status,
        capability_status=capability.capability_status,
        evidence_status=capability.evidence_status,
        evidence=capability.evidence,
        unsupported_reason=capability.unsupported_reason,
    )


_FIELD = _object(
    {
        "x": _number("Field X coordinate"),
        "y": _number("Field Y coordinate"),
        "weight": _number("Relative weight", 1.0),
    },
    ("x", "y"),
)
_WAVE = _object(
    {"wavelength": _number("Wavelength in micrometers"), "weight": _number("Relative weight", 1.0)},
    ("wavelength",),
)

_SPECS: list[ToolSpec] = [
    # Lifecycle and files
    _spec(
        "zemax_connect",
        "Connect to OpticStudio in standalone or interactive-extension mode.",
        "lifecycle",
        {
            "mode": _string(
                "Connection mode", enum=["standalone", "extension"], default="standalone"
            ),
            "instanceId": _integer("Interactive Extension instance ID", 0),
        },
        provenance=(ZYM, WEBWORN),
    ),
    _spec(
        "zemax_status",
        "Return connection, ownership, license, and current-system status.",
        "lifecycle",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_disconnect",
        "Disconnect cleanly and close an owned OpticStudio application.",
        "lifecycle",
        {"save": _boolean("Save before disconnecting", False)},
        provenance=(ZYM, WEBWORN),
    ),
    _spec(
        "zemax_restart",
        "Restart the OpticStudio connection when the current session is unhealthy.",
        "lifecycle",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_info",
        "Report the current session and optical-system information.",
        "lifecycle",
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_new_system",
        "Create a blank sequential or non-sequential optical system.",
        "lifecycle",
        {"sequential": _boolean("Create a sequential system", True)},
        provenance=(ZYM, WEBWORN),
    ),
    _spec(
        "zemax_open_file",
        "Open a Zemax .zmx or .zos lens file.",
        "lifecycle",
        {
            "filePath": _string("Absolute Windows lens-file path"),
            "path": _string("Legacy absolute lens-file path"),
        },
        provenance=(ZYM, WEBWORN),
    ),
    _spec(
        "zemax_save_file",
        "Save the current lens, optionally using Save As.",
        "lifecycle",
        {
            "filePath": _string("Optional destination path"),
            "path": _string("Legacy optional destination path"),
        },
        provenance=(ZYM, WEBWORN),
    ),
    _spec(
        "zemax_close_file",
        "Close the current optical system while retaining the application connection.",
        "lifecycle",
        {"save": _boolean("Save the current system if needed before closing")},
        ("save",),
        provenance=(UNION,),
    ),
    # System data and settings
    _spec(
        "zemax_get_system",
        "Get optical-system data, optionally including surfaces, fields, and wavelengths.",
        "sequential",
        {
            "includeSurfaces": _boolean("Include surface details", True),
            "includeFields": _boolean("Include field definitions", True),
            "includeWavelengths": _boolean("Include wavelength definitions", True),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_aperture",
        "Set the system aperture type and value.",
        "settings",
        {
            "value": _number("Aperture value"),
            "apertureType": _string(
                "EPD, FNumber, ObjectNA, FloatByStop, or Zemax enum name", default="EPD"
            ),
        },
        ("value",),
        provenance=(ZYM, WEBWORN),
    ),
    _spec(
        "zemax_set_wavelengths",
        "Replace wavelength definitions and select the primary wavelength.",
        "settings",
        {
            "wavelengths": _array("Wavelength definitions", _WAVE),
            "primaryWavelength": _integer("One-based primary wavelength", 1),
            "wavelengthsUm": _array(
                "Legacy list of wavelengths in micrometers", {"type": "number"}
            ),
            "primary": _integer("Legacy one-based primary wavelength", 1),
        },
        provenance=(ZYM, WEBWORN),
    ),
    _spec(
        "zemax_set_number_of_wavelengths",
        "Set the number of wavelength rows.",
        "settings",
        {"numberOfWavelengths": _integer("Desired wavelength count")},
        ("numberOfWavelengths",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_fields",
        "Set all field points and the field coordinate type.",
        "settings",
        {
            "fields": _array("Field definitions", _FIELD),
            "fieldType": _string(
                "Angle, ObjectHeight, ParaxialImageHeight, or RealImageHeight", default="Angle"
            ),
            "points": _array(
                "Legacy [x,y] coordinate pairs", _array("Coordinate pair", {"type": "number"})
            ),
        },
        provenance=(ZYM, WEBWORN),
    ),
    _spec(
        "zemax_set_number_of_fields",
        "Set the number of field rows.",
        "settings",
        {"numberOfFields": _integer("Desired field count")},
        ("numberOfFields",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_get_afocal_mode",
        "Get the sequential afocal-mode setting.",
        "settings",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_afocal_mode",
        "Enable or disable sequential afocal mode.",
        "settings",
        {"afocalMode": _boolean("Whether afocal mode is enabled")},
        ("afocalMode",),
        provenance=(ZYM,),
    ),
    _spec("zemax_get_ray_aiming", "Get the ray-aiming setting.", "settings", provenance=(ZYM,)),
    _spec(
        "zemax_set_ray_aiming",
        "Set ray aiming to Off, Paraxial, or Real.",
        "settings",
        {"rayAiming": _string("Ray-aiming mode", enum=["Off", "Paraxial", "Real"])},
        ("rayAiming",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_get_apodization", "Get aperture apodization settings.", "settings", provenance=(ZYM,)
    ),
    _spec(
        "zemax_set_apodization",
        "Set aperture apodization type and factor.",
        "settings",
        {"apodizationType": _string("Apodization type"), "factor": _number("Apodization factor")},
        ("apodizationType", "factor"),
        provenance=(ZYM,),
    ),
    _spec("zemax_get_mtf_units", "Get MTF spatial-frequency units.", "settings", provenance=(ZYM,)),
    _spec(
        "zemax_set_mtf_units",
        "Set MTF spatial-frequency units.",
        "settings",
        {"mtfUnits": _string("MTF units")},
        ("mtfUnits",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_get_system_units",
        "Get the current optical system's lens units.",
        "settings",
    ),
    _spec(
        "zemax_set_system_units",
        "Set the current optical system's lens units.",
        "settings",
        {
            "lensUnits": _string(
                "Lens coordinate and prescription units",
                enum=["Millimeters", "Centimeters", "Inches", "Meters"],
            )
        },
        ("lensUnits",),
    ),
    _spec(
        "zemax_get_title_notes",
        "Get the current optical system's title, notes, and author.",
        "settings",
    ),
    _spec(
        "zemax_set_title_notes",
        "Update the current optical system's title, notes, and author.",
        "settings",
        {
            "title": _string("Optical-system title; an empty string clears it"),
            "notes": _string("Optical-system notes; an empty string clears them"),
            "author": _string("Optical-system author; an empty string clears it"),
        },
    ),
    _spec(
        "zemax_get_polarization",
        "Get the current optical system's default input polarization settings.",
        "settings",
    ),
    _spec(
        "zemax_set_polarization",
        "Update the current optical system's default input polarization settings.",
        "settings",
        {
            "method": _string(
                "Polarization-axis reference method",
                enum=["XAxisMethod", "YAxisMethod", "ZAxisMethod"],
            ),
            "unpolarized": _boolean("Treat rays as unpolarized"),
            "jx": _number("X-component Jones amplitude"),
            "jy": _number("Y-component Jones amplitude"),
            "xPhase": _number("X-component phase"),
            "yPhase": _number("Y-component phase"),
            "convertThinFilmPhaseToRayEquivalent": _boolean(
                "Convert thin-film phase to its ray-equivalent value"
            ),
        },
    ),
    _spec(
        "zemax_get_clear_semi_diameter_margin",
        "Get the clear semi-diameter margin.",
        "settings",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_clear_semi_diameter_margin",
        "Set the clear semi-diameter margin.",
        "settings",
        {"margin": _number("Margin value")},
        ("margin",),
        provenance=(ZYM,),
    ),
    # Sequential surfaces and XDAT
    _spec(
        "zemax_lde_summary",
        "Return a compact sequential Lens Data Editor prescription.",
        "sequential",
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_get_surface",
        "Get detailed data for a sequential surface.",
        "sequential",
        {"surfaceNumber": _integer("Surface number; 0 is object and -1 is image")},
        ("surfaceNumber",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_add_surface",
        "Insert a new sequential surface.",
        "sequential",
        {
            "insertAt": _integer("Position; 0 appends before image", 0),
            "radius": _number("Radius; 0 is planar", 0),
            "thickness": _number("Thickness to the next surface", 0),
            "material": _string("Glass name; empty means air", default=""),
            "comment": _string("Surface comment", default=""),
        },
        provenance=(ZYM, WEBWORN),
    ),
    _spec(
        "zemax_lde_insert_surface",
        "Insert a surface at a zero-based LDE position.",
        "sequential",
        {"position": _integer("Zero-based insertion position")},
        ("position",),
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_remove_surface",
        "Remove a sequential surface.",
        "sequential",
        {"surfaceNumber": _integer("Surface number to remove")},
        ("surfaceNumber",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_surface",
        "Modify common properties and variable states of a sequential surface.",
        "sequential",
        {
            "surfaceNumber": _integer("Surface to modify"),
            "radius": _number("Radius of curvature"),
            "thickness": _number("Thickness to next surface"),
            "material": _string("Glass name"),
            "semiDiameter": _number("Semi-diameter"),
            "conic": _number("Conic constant"),
            "comment": _string("Comment"),
            "isStop": _boolean("Set as stop"),
            "radiusVariable": _boolean("Make radius variable"),
            "thicknessVariable": _boolean("Make thickness variable"),
            "conicVariable": _boolean("Make conic variable"),
            "thicknessMin": _number("Hard lower thickness bound"),
            "thicknessMax": _number("Hard upper thickness bound"),
        },
        ("surfaceNumber",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_lde_set_surface",
        "Legacy wrapper for editing common surface properties.",
        "sequential",
        {
            "surface": _integer("Zero-based surface"),
            "radius": _number("Radius"),
            "thickness": _number("Thickness"),
            "material": _string("Material"),
            "comment": _string("Comment"),
            "semiDiameter": _number("Semi-diameter"),
        },
        ("surface",),
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_set_surface_type",
        "Change a surface to a named Zemax surface type.",
        "sequential",
        {"surfaceNumber": _integer("Surface number"), "surfaceType": _string("Zemax surface type")},
        ("surfaceNumber", "surfaceType"),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_list_surface_types",
        "List surface types supported by the installed OpticStudio build.",
        "sequential",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_surface_parameter",
        "Set a type-specific surface parameter.",
        "sequential",
        {
            "surfaceNumber": _integer("Surface number"),
            "parameter": _integer("One-based parameter number"),
            "value": _number("Parameter value"),
        },
        ("surfaceNumber", "parameter", "value"),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_get_surface_solves",
        "Get solve, pickup, and variable states for all surface properties.",
        "sequential",
        {"surfaceNumber": _integer("Surface number")},
        ("surfaceNumber",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_surface_solve",
        "Set the solve type for a surface property.",
        "sequential",
        {
            "surfaceNumber": _integer("Surface number"),
            "property": _string(
                "radius, thickness, conic, semiDiameter, material, or param1-param8"
            ),
            "solveType": _string(
                "Fixed, Variable, Pickup, ray-height/angle, edge-thickness, position, "
                "FNumber, or material solve"
            ),
            "pickupSurface": _integer("Pickup source surface"),
            "pickupColumn": _integer("Pickup source column"),
            "scaleFactor": _number("Pickup scale", 1),
            "offset": _number("Pickup offset", 0),
            "height": _number("Ray height or angle"),
            "pupilZone": _number("Pupil zone"),
            "thickness": _number("Edge thickness"),
            "radialHeight": _number("Edge radial height"),
            "position": _number("Position solve distance"),
            "fNumber": _number("F-number solve value"),
            "referenceSurface": _integer("Reference surface"),
            "catalog": _string("Glass substitution catalog"),
            "materialName": _string("Material name"),
            "indexOffset": _number("Material index offset"),
        },
        ("surfaceNumber", "property", "solveType"),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_variable",
        "Legacy wrapper to make a surface cell variable.",
        "sequential",
        {
            "surface": _integer("Surface number"),
            "cell": _string("Cell", enum=["radius", "thickness", "conic"], default="thickness"),
        },
        ("surface",),
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_get_aspheric_surface",
        "Get Even Asphere conic and alpha1-alpha8 coefficients.",
        "sequential",
        {"surfaceNumber": _integer("Surface number")},
        ("surfaceNumber",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_aspheric_surface",
        "Convert to Even Asphere and set conic and alpha coefficients.",
        "sequential",
        {
            "surfaceNumber": _integer("Surface number"),
            **{f"alpha{i}": _number(f"Even-asphere alpha{i} coefficient") for i in range(1, 9)},
            **{f"alpha{i}Variable": _boolean(f"Make alpha{i} variable") for i in range(1, 9)},
            "conic": _number("Conic constant"),
            "conicVariable": _boolean("Make conic variable"),
        },
        ("surfaceNumber",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_get_extra_data",
        "Read surface Extra Data (XDAT) values.",
        "xdat",
        {
            "surfaceNumber": _integer("Surface number"),
            "startParameter": _integer("First XDAT parameter", 1),
            "endParameter": _integer("Last XDAT parameter; 0 means all", 0),
        },
        ("surfaceNumber",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_extra_data",
        "Set one or more surface Extra Data (XDAT) values.",
        "xdat",
        {
            "surfaceNumber": _integer("Surface number"),
            "values": _array(
                "XDAT entries",
                _object(
                    {"parameter": _integer("Parameter number"), "value": _number("Value")},
                    ("parameter", "value"),
                ),
            ),
        },
        ("surfaceNumber", "values"),
        provenance=(ZYM,),
    ),
    # Multi-configuration
    _spec(
        "zemax_get_configuration",
        "Get number of configurations and current configuration.",
        "configuration",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_number_of_configurations",
        "Set the number of configurations.",
        "configuration",
        {"numberOfConfigurations": _integer("Desired count")},
        ("numberOfConfigurations",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_current_configuration",
        "Set the active configuration.",
        "configuration",
        {"configurationNumber": _integer("One-based configuration")},
        ("configurationNumber",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_get_configuration_operands",
        "Get MCE operands and values across configurations.",
        "configuration",
        {"startRow": _integer("First row", 1), "endRow": _integer("Last row; 0 means all", 0)},
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_add_configuration_operand",
        "Add an MCE operand.",
        "configuration",
        {
            "operandType": _string("THIC, CURV, CONI, PRAM, MOFF, and so on"),
            "insertAt": _integer("Row; 0 appends", 0),
            "param1": _integer("Parameter 1"),
            "param2": _integer("Parameter 2"),
            "param3": _integer("Parameter 3"),
        },
        ("operandType",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_delete_configuration_operand",
        "Delete an MCE operand row.",
        "configuration",
        {"row": _integer("One-based row")},
        ("row",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_configuration_operand_value",
        "Set a value or pickup solve for one configuration operand cell.",
        "configuration",
        {
            "operandRow": _integer("One-based operand row"),
            "configurationNumber": _integer("One-based configuration"),
            "value": _number("Direct value"),
            "pickupConfig": _integer("Pickup configuration"),
            "scaleFactor": _number("Pickup scale", 1),
            "offset": _number("Pickup offset", 0),
        },
        ("operandRow", "configurationNumber"),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_mce_summary", "Legacy compact MCE summary.", "configuration", provenance=(WEBWORN,)
    ),
    _spec(
        "zemax_mce_add_config",
        "Legacy wrapper to append a configuration.",
        "configuration",
        {"withPickups": _boolean("Link new cells with pickups", False)},
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_mce_add_operand",
        "Legacy wrapper to append an MCE operand.",
        "configuration",
        {
            "operandType": _string("MCE operand type"),
            "param1": _integer("Primary parameter", 0),
            "values": _array("Per-configuration values", {"type": "number"}),
        },
        ("operandType",),
        provenance=(WEBWORN,),
    ),
    # Merit function and optimization
    _spec(
        "zemax_get_merit_function",
        "Retrieve merit-function operands and optional calculated values.",
        "merit",
        {
            "includeValues": _boolean("Calculate operand values", True),
            "startRow": _integer("First row", 1),
            "endRow": _integer("Last row; 0 means all", 0),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_add_operand",
        "Add an optimization operand to the merit function.",
        "merit",
        {
            "operandType": _string("Operand mnemonic such as EFFL, MTFT, or RSCE"),
            "target": _number("Target value", 0),
            "weight": _number("Weight", 1),
            "insertAt": _integer("Row; 0 appends", 0),
            "int1": _integer("Integer parameter 1"),
            "int2": _integer("Integer parameter 2"),
            **{f"data{i}": _number(f"Data parameter {i}") for i in range(1, 7)},
        },
        ("operandType",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_remove_operand",
        "Remove a merit-function operand.",
        "merit",
        {"row": _integer("One-based row")},
        ("row",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_optimization_wizard",
        "Construct a merit function using Optimization Wizard criteria.",
        "merit",
        {
            "criterion": _string(
                "RMSSpotRadius, RMSWavefront, PeakToValley, etc.", default="RMSSpotRadius"
            ),
            "reference": _string("Centroid or ChiefRay", default="Centroid"),
            "pupilIntegration": _string(
                "GaussianQuadrature or RectangularArray", default="GaussianQuadrature"
            ),
            "rings": _integer("Gaussian rings", 3),
            "gridSize": _integer("Rectangular grid size", 5),
            "arms": _integer("Gaussian arms", 6),
            "includeAllFields": _boolean("Include every field", True),
            "wavelength": _integer("0 for polychromatic", 0),
            "addBoundaryConstraints": _boolean("Add thickness constraints", True),
            "minCenterThickness": _number("Minimum glass center thickness"),
            "maxCenterThickness": _number("Maximum glass center thickness"),
            "minEdgeThickness": _number("Minimum air edge thickness"),
            "clearExisting": _boolean("Clear existing operands", True),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_forbes_merit_function",
        "Build explicit OPD operands using Forbes 1988 Gaussian quadrature sampling.",
        "merit",
        {
            "operandType": _string("OPDX, OPDC, or OPDM", default="OPDX"),
            "rings": _integer("Radial rings", 3),
            "arms": _integer("Angular arms", 6),
            "includeAllWavelengths": _boolean("Include all wavelengths", True),
            "wavelength": _integer("Specific wavelength; 0 polychromatic", 0),
            "includeAllConfigurations": _boolean("Include all configurations", True),
            "clearExisting": _boolean("Clear existing operands", True),
            "addComments": _boolean("Add BLNK comments", True),
            "useRadauForAxial": _boolean("Use Radau sampling for axial fields", True),
            "assumeSymmetry": _boolean("Use Y symmetry", True),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_merit_wizard",
        "Legacy merit-function wizard wrapper.",
        "merit",
        {"optimizationGoal": _string("Informational goal", default="RMS_Spot")},
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_merit_value",
        "Calculate the current merit-function value.",
        "merit",
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_operand_help",
        "Get detailed documentation for an optimization operand.",
        "merit",
        {"operandType": _string("Operand mnemonic")},
        ("operandType",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_search_operands",
        "Search operand names and descriptions.",
        "merit",
        {
            "query": _string("Search query"),
            "maxResults": _integer("Maximum results", 20),
            "category": _string("Optional category filter"),
        },
        ("query",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_load_merit_function_file",
        "Load a .MF merit-function file.",
        "merit",
        {"filePath": _string("Absolute .MF file path")},
        ("filePath",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_save_merit_function_file",
        "Save the merit function to a .MF file.",
        "merit",
        {"filePath": _string("Absolute .MF file path")},
        ("filePath",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_get_variables",
        "Scan the system for optimization variables and constraint states.",
        "optimization",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_set_variable_constraints",
        "Set hard min/max constraints on optimization variables.",
        "optimization",
        {
            "constraints": _array(
                "Variable constraints",
                _object(
                    {
                        "variableNumber": _integer("Variable number"),
                        "constraint": _string("Unconstrained, MinAndMax, MinOnly, or MaxOnly"),
                        "min": _number("Minimum"),
                        "max": _number("Maximum"),
                    },
                    ("variableNumber", "constraint"),
                ),
            )
        },
        ("constraints",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_optimize",
        "Run native local optimization.",
        "optimization",
        {
            "algorithm": _string("DLS or Orthogonal", default="DLS"),
            "cycles": _integer("0 for automatic", 0),
            "method": _string("Legacy local, hammer, or global"),
            "cores": _integer("Legacy CPU core count", 0),
        },
        provenance=(ZYM, WEBWORN),
    ),
    _spec(
        "zemax_constrained_optimize",
        "Run the custom bound-constrained Levenberg-Marquardt optimizer.",
        "optimization",
        {
            "maxIterations": _integer("Maximum iterations", 200),
            "initialMu": _number("Initial damping", 0.001),
            "delta": _number("Finite-difference step", 1e-7),
            "useBroydenUpdate": _boolean("Use rank-1 Jacobian updates", True),
            "maxRestarts": _integer("Fresh-Jacobian restarts", 2),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_global_search",
        "Run native global optimization with optional glass substitution.",
        "optimization",
        {
            "algorithm": _string("DLS or Orthogonal", default="DLS"),
            "cores": _integer("0 uses all cores", 0),
            "solutionsToSave": _integer("10, 20, 50, or 100", 20),
            "timeoutSeconds": _number("0 means no time limit", 0),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_hammer",
        "Run native Hammer optimization.",
        "optimization",
        {
            "algorithm": _string("DLS or Orthogonal", default="DLS"),
            "cores": _integer("0 uses all cores", 0),
            "targetRuntimeMinutes": _number("Automatic target runtime", 1),
            "timeoutSeconds": _number("Hard timeout", 120),
            "automatic": _boolean("Use automatic mode", True),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_multistart_optimize",
        "Start non-blocking randomized multistart constrained optimization.",
        "optimization",
        {
            "maxTrials": _integer("Random trials", 100),
            "lmIterationsPerTrial": _integer("LM iterations per trial", 50),
            "initialLmIterations": _integer("Initial LM iterations", 200),
            "randomizationPercent": _number("Percent of variable bound range", 5),
            "initialMu": _number("Initial damping", 0.001),
            "delta": _number("Finite-difference step", 1e-7),
            "useBroydenUpdate": _boolean("Use Broyden updates", True),
            "maxRestarts": _integer("Initial LM restarts", 0),
            "constrainedOnly": _boolean("Randomize only constrained variables", False),
            "glassSubstitutionProbability": _number("Per-trial probability", 0.5),
            "progressInterval": _integer("Log every N trials", 0),
            "resume": _boolean("Resume prior run", False),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_multistart_status",
        "Poll multistart progress without blocking.",
        "optimization",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_multistart_stop",
        "Request graceful stop of multistart optimization.",
        "optimization",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_quick_focus",
        "Run Quick Focus to adjust back focal distance.",
        "optimization",
        {
            "criterion": _string(
                "SpotSizeRadial, SpotSizeXOnly, SpotSizeYOnly, or RMSWavefront",
                default="SpotSizeRadial",
            ),
            "useCentroid": _boolean("Reference spot size to the centroid", True),
        },
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_scale_lens",
        "Scale a disposable lens by factor or convert it to another lens unit.",
        "settings",
        {
            "mode": _string("Scaling mode", enum=["factor", "units"]),
            "scaleFactor": _number("Finite positive scale factor"),
            "scaleToUnit": _string(
                "Target lens unit",
                enum=["Millimeters", "Centimeters", "Inches", "Meters"],
            ),
            "firstComponent": _integer("First component to scale"),
            "lastComponent": _integer("Last component to scale"),
            "timeoutSeconds": _number("Bounded timeout in seconds", 0),
        },
        ("mode",),
        provenance=(UNION,),
    ),
    _spec(
        "zemax_design_lockdown",
        "Apply destructive Design Lockdown to an owned disposable sequential system.",
        "settings",
        {
            "confirmDestructive": _boolean("Explicitly confirm destructive changes"),
            "usePrecisionRounding": _boolean("Round prescription values", False),
            "decimalPrecision": _integer("Decimal precision 0-15", 3),
            "excludePickups": _boolean("Preserve eligible pickups", False),
            "fixModelGlasses": _boolean("Replace model glasses", False),
            "convertSDToMaxApertures": _boolean(
                "Convert semi-diameters to maximum apertures", False
            ),
            "timeoutSeconds": _number("Bounded timeout in seconds", 0),
        },
        ("confirmDestructive",),
        provenance=(UNION,),
    ),
    # Analyses from zym and compatibility list
    _spec(
        "zemax_cardinal_points",
        "Calculate focal lengths, principal planes, and other cardinal points.",
        "analysis",
        {"wavelength": _integer("Wavelength number", 1)},
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_chromatic_focal_shift",
        "Calculate longitudinal chromatic focal shift versus wavelength.",
        "analysis",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_lateral_color",
        "Calculate lateral color versus field.",
        "analysis",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_longitudinal_aberration",
        "Calculate longitudinal aberration versus pupil position.",
        "analysis",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_seidel_coefficients",
        "Calculate third-order Seidel and chromatic aberration coefficients.",
        "analysis",
        {"wavelength": _integer("0 for primary", 0)},
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_field_curvature_distortion",
        "Calculate tangential/sagittal field curvature and distortion.",
        "analysis",
        {"distortionType": _string("f_tan_theta or f_theta", default="f_tan_theta")},
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_relative_illumination",
        "Calculate relative illumination and effective F-number versus field.",
        "analysis",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_ray_fan",
        "Calculate transverse ray aberration fans for all fields and wavelengths.",
        "analysis",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_opd_fan",
        "Calculate optical-path-difference fans for all fields and wavelengths.",
        "analysis",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_pupil_aberration_fan",
        "Calculate entrance-pupil aberration fans.",
        "analysis",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_ray_trace",
        "Trace one normalized sequential ray.",
        "analysis",
        {
            "hx": _number("Normalized field X", 0),
            "hy": _number("Normalized field Y", 0),
            "px": _number("Normalized pupil X", 0),
            "py": _number("Normalized pupil Y", 0),
            "wavelength": _integer("Wavelength number", 1),
            "surface": _integer("0 traces to image", 0),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_batch_ray_trace",
        "Trace a batch of normalized sequential rays.",
        "analysis",
        {
            "rays": _array("[Hx,Hy,Px,Py] rays", _array("Normalized ray", {"type": "number"})),
            "wavelength": _integer("Wavelength number", 1),
            "rayType": _string("Real or Paraxial", default="Real"),
            "toSurface": _integer("-1 means image", -1),
        },
        ("rays",),
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_rms_spot",
        "Calculate an RMS spot radius for a normalized field point.",
        "analysis",
        {
            "hx": _number("Normalized field X", 0),
            "hy": _number("Normalized field Y", 0),
            "wavelength": _integer("0 for polychromatic", 0),
            "reference": _string("centroid or chief", default="centroid"),
            "sampling": _integer("Rings or grid size", 3),
            "useGrid": _boolean("Use rectangular sampling", False),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_spot_diagram",
        "Calculate spot-size analysis for one field.",
        "analysis",
        {
            "field": _integer("One-based field", 1),
            "wavelength": _integer("0 for polychromatic", 0),
            "rings": _integer("Gaussian rings", 3),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_spot_rms",
        "Legacy RMS spot radius analysis for every field.",
        "analysis",
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_fft_mtf",
        "Calculate diffraction FFT MTF curves for all fields.",
        "analysis",
        {
            "frequency": _number("Maximum cycles/mm"),
            "wavelength": _integer("0 for polychromatic", 0),
            "sampling": _integer("Sampling level 1-6", 3),
        },
        ("frequency",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_fft_mtf_vs_field",
        "Calculate polychromatic FFT MTF versus Y field for up to six frequencies.",
        "analysis",
        {
            **{f"frequency{i}": _number(f"Spatial frequency {i}; 0 skips", 0) for i in range(1, 7)},
            "sampling": _integer("Sampling level 1-6", 3),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_geometric_mtf",
        "Calculate geometric MTF curves for all fields.",
        "analysis",
        {
            "maxFrequency": _number("Maximum cycles/mm", 100),
            "wavelength": _integer("0 for polychromatic", 0),
            "multiplyByDiffractionLimit": _boolean("Multiply by diffraction limit", False),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_geometric_mtf_vs_field",
        "Calculate geometric MTF versus field for up to six frequencies.",
        "analysis",
        {**{f"frequency{i}": _number(f"Spatial frequency {i}; 0 skips", 0) for i in range(1, 7)}},
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_diffraction_encircled_energy",
        "Calculate FFT diffraction encircled energy versus radius.",
        "analysis",
        {
            "sampling": _integer("Sampling level 1-6", 3),
            "useDashes": _boolean("Use dashes reference", False),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_geometric_encircled_energy",
        "Calculate ray-based geometric encircled energy versus radius.",
        "analysis",
        {
            "sampling": _integer("Sampling level 1-6", 3),
            "showDiffractionLimit": _boolean("Include diffraction limit", True),
            "scaleByDiffractionLimit": _boolean("Scale by diffraction limit", False),
            "scatterRays": _boolean("Use scatter rays", False),
            "useDashes": _boolean("Use dashes reference", False),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_fft_psf",
        "Calculate a diffraction FFT point-spread function.",
        "advanced-analysis",
        {
            "field": _integer("One-based field", 1),
            "wavelength": _integer("0 for polychromatic", 0),
            "sampling": _integer("Sampling level", 3),
            "imageSampling": _integer("Image sampling level", 3),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_huygens_mtf",
        "Calculate Huygens MTF by direct pupil integration.",
        "advanced-analysis",
        {
            "maximumFrequency": _number("Maximum spatial frequency"),
            "field": _integer("Zero for all or one-based field", 1),
            "wavelength": _integer("Zero for polychromatic or one-based wavelength", 0),
            "pupilSampling": _integer("Pupil sampling level 1-6", 3),
            "imageSampling": _integer("Image sampling level 1-6", 3),
            "imageDelta": _number("Image spacing in micrometers; zero uses default", 0),
            "usePolarization": _boolean("Use polarization", False),
            "useDashes": _boolean("Use dashed reference", False),
            "configuration": _integer("One-based configuration", 1),
        },
        ("maximumFrequency",),
        provenance=(UNION,),
    ),
    _spec(
        "zemax_huygens_psf",
        "Calculate a Huygens point-spread function.",
        "advanced-analysis",
        {
            "field": _integer("One-based field", 1),
            "wavelength": _integer("0 for polychromatic", 0),
            "pupilSampling": _integer("Pupil sampling", 3),
            "imageSampling": _integer("Image sampling", 3),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_geometric_image_analysis",
        "Run geometric image analysis and return/export the image grid.",
        "advanced-analysis",
        {
            "field": _integer("One-based field", 1),
            "wavelength": _integer("0 for polychromatic", 0),
            "raysX1000": _integer("Ray count in thousands", 100),
            "showAs": _string("Display mode"),
            "filePath": _string("Optional export path"),
        },
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_pop",
        "Run Physical Optics Propagation (POP).",
        "advanced-analysis",
        {
            "startSurface": _integer("Start surface"),
            "endSurface": _integer("End surface"),
            "field": _integer("One-based field", 1),
            "wavelength": _integer("One-based wavelength", 1),
            "beamType": _string("Beam type", default="GaussianWaist"),
            "beamParameter1": _number("Beam parameter 1"),
            "beamParameter2": _number("Beam parameter 2"),
            "samplingX": _integer("X sampling", 128),
            "samplingY": _integer("Y sampling", 128),
            "dataType": _string("Irradiance, phase, etc.", default="Irradiance"),
        },
        ("startSurface", "endSurface"),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_export_analysis",
        "Export an analysis result as text, bitmap, or structured data.",
        "advanced-analysis",
        {
            "analysisType": _string("Analysis identifier"),
            "filePath": _string("Destination path"),
            "format": _string("text, bmp, json, or csv", default="text"),
        },
        ("analysisType", "filePath"),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_run_analysis",
        "Run an arbitrary AnalysisIDM by name and extract sample results.",
        "advanced-analysis",
        {"analysisType": _string("ZOSAPI AnalysisIDM member")},
        ("analysisType",),
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_analysis_series",
        "Run an arbitrary series analysis and return decimated curves.",
        "advanced-analysis",
        {
            "analysisType": _string("ZOSAPI AnalysisIDM member"),
            "maxPoints": _integer("Approximate max points per curve", 40),
        },
        ("analysisType",),
        provenance=(WEBWORN,),
    ),
    # Glass catalogs
    _spec(
        "zemax_add_material_catalog",
        "Add a material catalog to the current optical system.",
        "glass",
        {"catalogName": _string("Material catalog name without the .agf extension")},
        ("catalogName",),
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_remove_material_catalog",
        "Remove a material catalog from the current optical system.",
        "glass",
        {"catalogName": _string("Material catalog name without the .agf extension")},
        ("catalogName",),
    ),
    _spec(
        "zemax_get_glass_catalogs",
        "List glass catalog names installed in Glasscat.",
        "glass",
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_get_glasses",
        "List glasses and optical/manufacturing properties from catalogs.",
        "glass",
        {"catalogs": _string("Comma-separated catalog names")},
        ("catalogs",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_filter_glasses",
        "Filter glasses by preferred state, optical coordinates, cost, TCE, coverage, "
        "and melt frequency.",
        "glass",
        {
            "catalogs": _string("Comma-separated catalog names"),
            "preferredOnly": _boolean("Only preferred glasses"),
            "distanceRadius": _number("Max weighted optical distance"),
            "wn": _number("Nd weight", 1),
            "wa": _number("Vd weight", 0.0001),
            "wp": _number("dPgF weight", 100),
            "ndTarget": _number("Target Nd", 1.5168),
            "vdTarget": _number("Target Vd", 64.17),
            "dpgfTarget": _number("Target dPgF", 0),
            "maxCost": _number("Max BK7-relative cost"),
            "ndMin": _number("Minimum Nd"),
            "ndMax": _number("Maximum Nd"),
            "vdMin": _number("Minimum Vd"),
            "vdMax": _number("Maximum Vd"),
            "dpgfMin": _number("Minimum dPgF"),
            "dpgfMax": _number("Maximum dPgF"),
            "tceMin": _number("Minimum TCE"),
            "tceMax": _number("Maximum TCE"),
            "minWavelengthCoverage": _number("Minimum wavelength coverage in um"),
            "maxWavelengthCoverage": _number("Maximum wavelength coverage in um"),
            "maxMeltFrequency": _integer("Maximum melt frequency 1-5"),
        },
        ("catalogs",),
        provenance=(ZYM,),
    ),
    _spec(
        "zemax_export_glass_catalog",
        "Export filtered glasses to a new AGF catalog.",
        "glass",
        {
            "catalogName": _string("New catalog name without .agf"),
            "sourceCatalogs": _string("Comma-separated source catalogs"),
            "outputDirectory": _string(
                "Explicit caller-owned output directory outside installed Glasscat directories"
            ),
            "overwrite": _boolean("Overwrite existing", False),
            "preferredOnly": _boolean("Only preferred glasses"),
            "distanceRadius": _number("Maximum distance"),
            "wn": _number("Nd weight"),
            "wa": _number("Vd weight"),
            "wp": _number("dPgF weight"),
            "ndTarget": _number("Target Nd"),
            "vdTarget": _number("Target Vd"),
            "dpgfTarget": _number("Target dPgF"),
            "maxCost": _number("Maximum cost"),
            "ndMin": _number("Minimum Nd"),
            "ndMax": _number("Maximum Nd"),
            "vdMin": _number("Minimum Vd"),
            "vdMax": _number("Maximum Vd"),
            "dpgfMin": _number("Minimum dPgF"),
            "dpgfMax": _number("Maximum dPgF"),
            "tceMin": _number("Minimum TCE"),
            "tceMax": _number("Maximum TCE"),
            "minWavelengthCoverage": _number("Minimum wavelength coverage"),
            "maxWavelengthCoverage": _number("Maximum wavelength coverage"),
            "maxMeltFrequency": _integer("Maximum melt frequency"),
        },
        ("catalogName", "sourceCatalogs", "outputDirectory"),
        provenance=(ZYM,),
    ),
    # Tolerancing compatibility
    _spec(
        "zemax_tde_summary",
        "Return tolerance operands and bounds.",
        "tolerancing",
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_tolerance_wizard",
        "Populate default sequential tolerances.",
        "tolerancing",
        provenance=(WEBWORN,),
    ),
    _spec(
        "zemax_run_tolerancing",
        "Run bounded Monte Carlo tolerancing.",
        "tolerancing",
        {
            "monteCarloRuns": _integer("Number of Monte Carlo runs (1-100)", 20),
            "timeoutSeconds": _number("Hard timeout in seconds (maximum 300)", 30),
        },
        provenance=(WEBWORN,),
    ),
    # Non-sequential / jaruiz compatibility surface
    _spec(
        "zemax_nsc_summary",
        "List non-sequential objects and common properties.",
        "non-sequential",
        provenance=(WEBWORN, JARUIZ),
    ),
    _spec(
        "zemax_nsc_get_object",
        "Get a non-sequential object and its common/type-specific data.",
        "non-sequential",
        {"objectNumber": _integer("One-based object number")},
        ("objectNumber",),
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_nsc_add_object",
        "Append a non-sequential object.",
        "non-sequential",
        {"objectType": _string("Optional Zemax object type"), "comment": _string("Object comment")},
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_nsc_insert_object",
        "Insert a non-sequential object.",
        "non-sequential",
        {
            "objectNumber": _integer("One-based insertion row"),
            "objectType": _string("Optional Zemax object type"),
        },
        ("objectNumber",),
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_nsc_remove_object",
        "Remove a non-sequential object.",
        "non-sequential",
        {"objectNumber": _integer("One-based object number")},
        ("objectNumber",),
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_nsc_set_object",
        "Set common placement, material, comment, and reference properties of an NSC object.",
        "non-sequential",
        {
            "objectNumber": _integer("One-based object number"),
            "objectType": _string("Object type"),
            "comment": _string("Comment"),
            "material": _string("Material"),
            "xPosition": _number("X position"),
            "yPosition": _number("Y position"),
            "zPosition": _number("Z position"),
            "tiltAboutX": _number("Tilt X"),
            "tiltAboutY": _number("Tilt Y"),
            "tiltAboutZ": _number("Tilt Z"),
            "refObject": _integer("Reference object"),
        },
        ("objectNumber",),
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_nsc_set_object_parameter",
        "Set a type-specific NSC object parameter.",
        "non-sequential",
        {
            "objectNumber": _integer("One-based object number"),
            "parameter": _integer("One-based parameter column"),
            "value": {"description": "Numeric or string value"},
        },
        ("objectNumber", "parameter", "value"),
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_nsc_get_object_parameter",
        "Get a type-specific NSC object parameter.",
        "non-sequential",
        {
            "objectNumber": _integer("One-based object number"),
            "parameter": _integer("One-based parameter column"),
        },
        ("objectNumber", "parameter"),
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_nsc_ray_trace",
        "Run a non-sequential ray trace.",
        "non-sequential",
        {
            "split": _boolean("Split rays", True),
            "scatter": _boolean("Scatter rays", False),
            "clearDetectors": _boolean("Clear all detectors first", True),
            "rays": _integer("Compatibility ray count hint", 100000),
            "usePolarization": _boolean("Trace polarization", False),
            "ignoreErrors": _boolean("Ignore ray errors", True),
            "saveZrd": _boolean("Save ray database", False),
            "zrdFile": _string("Optional lens-directory ZRD filename"),
            "zrdFormat": _string(
                "ZRD format",
                enum=[
                    "UncompressedFullData",
                    "CompressedBasicData",
                    "CompressedFullData",
                ],
                default="CompressedFullData",
            ),
        },
        provenance=(WEBWORN, JARUIZ),
    ),
    _spec(
        "zemax_nsc_clear_detectors",
        "Clear all or one non-sequential detector.",
        "non-sequential",
        {"objectNumber": _integer("0 clears all", 0)},
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_nsc_detector_data",
        "Read full detector data and aggregate statistics.",
        "non-sequential",
        {
            "objectNumber": _integer("Detector object number"),
            "dataType": _integer("1 incoherent flux, 2 coherent power, 3 coherent phase", 1),
            "maxValues": _integer(
                "Maximum detector values returned; 0 returns statistics only", 4096
            ),
            "quantity": _string(
                "Optional exact detector quantity",
                enum=[
                    "incoherentFlux",
                    "coherentReal",
                    "coherentImaginary",
                    "coherentAmplitude",
                    "coherentPower",
                    "coherentPhaseDegrees",
                ],
            ),
        },
        ("objectNumber",),
        provenance=(WEBWORN, JARUIZ),
    ),
    _spec(
        "zemax_nsc_detector_pixel",
        "Read one detector pixel or aggregate index.",
        "non-sequential",
        {
            "objectNumber": _integer("Detector object number"),
            "pixel": _integer("Pixel index; negative values may select totals"),
            "dataType": _integer("1 incoherent flux, 2 coherent power, 3 coherent phase", 1),
            "quantity": _string(
                "Optional exact detector quantity",
                enum=[
                    "incoherentFlux",
                    "coherentReal",
                    "coherentImaginary",
                    "coherentAmplitude",
                    "coherentPower",
                    "coherentPhaseDegrees",
                ],
            ),
        },
        ("objectNumber", "pixel"),
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_nsc_get_source_spectrum",
        "Get typed spectrum settings for an NSC source object.",
        "non-sequential",
        {"objectNumber": _integer("One-based source object number")},
        ("objectNumber",),
        provenance=(UNION,),
    ),
    _spec(
        "zemax_nsc_set_source_spectrum",
        "Set typed spectrum settings for an NSC source object.",
        "non-sequential",
        {
            "objectNumber": _integer("One-based source object number"),
            "mode": _string("Source color mode"),
            "settings": _object({}, ()),
        },
        ("objectNumber", "mode", "settings"),
        provenance=(UNION,),
    ),
    _spec(
        "zemax_nsc_save_detector",
        "Save detector data to a type-compatible detector data file.",
        "non-sequential",
        {
            "objectNumber": _integer("Detector object number"),
            "filePath": _string("Destination detector data file"),
            "overwrite": _boolean("Overwrite existing file", False),
        },
        ("objectNumber", "filePath"),
        provenance=(UNION,),
    ),
    _spec(
        "zemax_nsc_load_detector",
        "Load detector data from a type-compatible detector data file.",
        "non-sequential",
        {
            "objectNumber": _integer("Detector object number"),
            "filePath": _string("Existing detector data file"),
            "appendData": _boolean("Append rather than replace", False),
        },
        ("objectNumber", "filePath"),
        provenance=(UNION,),
    ),
    _spec(
        "zemax_nsc_polar_detector_data",
        "Read bounded full Detector Polar data.",
        "non-sequential",
        {
            "objectNumber": _integer("Detector Polar object number"),
            "quantity": _string("Polar detector quantity"),
            "maxValues": _integer("Maximum values returned", 4096),
        },
        ("objectNumber", "quantity"),
        provenance=(UNION,),
    ),
    _spec(
        "zemax_nsc_polar_detector_pixel",
        "Read one Detector Polar pixel or aggregate value.",
        "non-sequential",
        {
            "objectNumber": _integer("Detector Polar object number"),
            "pixel": _integer("Pixel or documented aggregate index"),
            "quantity": _string("Polar detector quantity"),
        },
        ("objectNumber", "pixel", "quantity"),
        provenance=(UNION,),
    ),
    _spec(
        "zemax_nsc_detector_viewer",
        "Run bounded Detector Viewer extraction for scalar or RGB data.",
        "non-sequential",
        {
            "objectNumber": _integer("Detector object number"),
            "showAs": _string("Detector Viewer display mode", default="FalseColor"),
            "dataType": _string("Detector Viewer data type", default="IncoherentIrradiance"),
            "scale": _string("Detector Viewer scale", default="Linear"),
            "smoothing": _integer("Smoothing level", 0),
            "filter": _string("Optional NSC filter expression"),
            "maxCells": _integer("Maximum returned cells", 4096),
        },
        ("objectNumber",),
        provenance=(UNION,),
    ),
    _spec(
        "zemax_nsc_convert_to_sequential",
        "Convert an eligible NSC group to sequential mode.",
        "non-sequential",
        {"firstObject": _integer("First object"), "lastObject": _integer("Last object")},
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_nsc_convert_to_nonsequential",
        "Convert or make the current optical system non-sequential.",
        "non-sequential",
        provenance=(JARUIZ,),
    ),
    _spec(
        "zemax_zrd_summary",
        "Stream an existing ZRD and return bounded aggregate metadata.",
        "non-sequential",
        {
            "filePath": _string("Existing absolute .ZRD file path"),
            "filter": _string("Optional OpticStudio NSC filter expression"),
            "maxRaysToScan": _integer("Maximum rays to scan", 100000),
            "maxSegmentsToScan": _integer("Maximum segments to scan", 1000000),
        },
        ("filePath",),
        provenance=(UNION,),
    ),
    _spec(
        "zemax_zrd_read",
        "Read a bounded nested ray and segment sample from a ZRD.",
        "non-sequential",
        {
            "filePath": _string("Existing absolute .ZRD file path"),
            "filter": _string("Optional OpticStudio NSC filter expression"),
            "maxRays": _integer("Maximum returned rays", 100),
            "maxSegments": _integer("Maximum total returned segments", 4096),
        },
        ("filePath",),
        provenance=(UNION,),
    ),
    # Deliberately gated generic escape hatch
    _spec(
        "zemax_eval",
        "Advanced backend-defined diagnostic/evaluation escape hatch; disabled unless "
        "explicitly allowed.",
        "advanced",
        {"code": _string("Backend-specific expression or statement")},
        ("code",),
        provenance=(WEBWORN,),
    ),
]

# Guard compatibility guarantees at import time.
_by_name: dict[str, ToolSpec] = {}
for _item in _SPECS:
    if _item.name in _by_name:
        raise RuntimeError(f"duplicate Zemax MCP tool name: {_item.name}")
    _by_name[_item.name] = _item

TOOL_CATALOG: tuple[ToolSpec, ...] = tuple(sorted(_SPECS, key=lambda item: item.name))


def iter_tool_specs(category: str | None = None) -> Iterable[ToolSpec]:
    """Iterate deterministically, optionally filtering by category."""
    if category is None:
        return iter(TOOL_CATALOG)
    return (item for item in TOOL_CATALOG if item.category == category)


def get_tool_spec(name: str) -> ToolSpec:
    """Return one tool specification or raise a useful KeyError."""
    try:
        return _by_name[name]
    except KeyError as exc:
        raise KeyError(f"unknown Zemax MCP tool: {name}") from exc


def catalog_manifest() -> JSON:
    """Return a deterministic JSON-serializable union and capability manifest."""
    categories = Counter(item.category for item in TOOL_CATALOG)
    statuses = Counter(item.implementation_status for item in TOOL_CATALOG)
    capabilities = Counter(item.capability_status for item in TOOL_CATALOG)
    evidence = Counter(item.evidence_status for item in TOOL_CATALOG)
    production_tools = [
        item.name for item in TOOL_CATALOG if item.capability_status == "production"
    ]
    scaffolded_tools = [
        item.name for item in TOOL_CATALOG if item.capability_status == "scaffolded"
    ]
    unsupported_tools = [
        item.name for item in TOOL_CATALOG if item.capability_status == "unsupported"
    ]
    live_tools = [item.name for item in TOOL_CATALOG if item.evidence_status == "live-verified"]
    return {
        "name": "zemax-mcp",
        "version": __version__,
        "compatibility": compatibility_manifest(),
        "toolCount": len(TOOL_CATALOG),
        "categories": dict(sorted(categories.items())),
        "implementationStatuses": dict(sorted(statuses.items())),
        "capabilities": {
            "productionHandlerCount": len(production_tools),
            "scaffoldedRemainderCount": len(scaffolded_tools),
            "unsupportedCount": len(unsupported_tools),
            "statuses": dict(sorted(capabilities.items())),
            "productionTools": production_tools,
            "scaffoldedTools": scaffolded_tools,
            "unsupportedTools": unsupported_tools,
        },
        "evidence": {
            "liveCoreRepresentativeCount": len(live_tools),
            "statuses": dict(sorted(evidence.items())),
            "liveVerifiedTools": live_tools,
            "records": [record.as_manifest_entry() for record in LIVE_EVIDENCE_RECORDS],
        },
        "tools": [item.as_manifest_entry() for item in TOOL_CATALOG],
    }


__all__ = ["TOOL_CATALOG", "ToolSpec", "catalog_manifest", "get_tool_spec", "iter_tool_specs"]
