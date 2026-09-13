"""Conservative production backend for sequential ZOS-API systems."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from threading import get_ident
from typing import Any

from zemax_mcp.config import RuntimeConfig
from zemax_mcp.errors import BackendError, ConnectionError, UnsupportedOperationError

from .discovery import ZOSInstallation, discover_installation
from .handles import HandleStore
from .interop import compatible_radius, get_member, to_python
from .loader import LoadedZOSAPI, load_zosapi
from .protocol import ApplicationOwnership, ConnectionMode

Loader = Callable[[ZOSInstallation], LoadedZOSAPI]
Discoverer = Callable[[RuntimeConfig | None], ZOSInstallation]

PRODUCTION_OPERATION_METHODS: dict[str, str] = {
    "add_surface": "add_surface",
    "close_file": "close_file",
    "get_surface": "get_surface",
    "get_system": "get_system",
    "new_system": "new_system",
    "open_file": "open_file",
    "ray_trace": "ray_trace",
    "rms_spot": "rms_spot",
    "save_file": "save_file",
    "set_surface": "set_surface",
    "status": "status",
}


def production_operation_names() -> frozenset[str]:
    """Return every explicit production dispatch name without opening OpticStudio."""
    from .subsystems.analysis import build_operation_map as build_analysis_operations
    from .subsystems.general_tools import build_operation_map as build_general_operations
    from .subsystems.glass import build_operation_map as build_glass_operations
    from .subsystems.mce_mfe import build_operation_map as build_mce_mfe_operations
    from .subsystems.nsc import build_operation_map as build_nsc_operations
    from .subsystems.optimization import build_operation_map as build_optimization_operations
    from .subsystems.settings_lde import build_operation_map as build_settings_operations
    from .subsystems.zrd import build_operation_map as build_zrd_operations

    def unavailable() -> None:
        return None

    operations = set(PRODUCTION_OPERATION_METHODS)
    operations.update(build_glass_operations())
    operations.update(build_general_operations(unavailable, unavailable, unavailable))
    for builder in (
        build_settings_operations,
        build_mce_mfe_operations,
        build_nsc_operations,
        build_optimization_operations,
        build_analysis_operations,
        build_zrd_operations,
    ):
        operations.update(builder(unavailable, unavailable))
    return frozenset(operations)


class RealZOSBackend:
    """ZOS-API backend whose methods must all run on one worker thread.

    The class intentionally implements only operations for which stable ZOS-API
    entry points are known. Advanced tools should be added as explicit methods;
    unknown dispatch names fail rather than returning synthetic results.
    """

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        *,
        installation: ZOSInstallation | None = None,
        loader: Loader = load_zosapi,
        discoverer: Discoverer = discover_installation,
    ) -> None:
        self._config = config or RuntimeConfig.from_env()
        self._installation = installation
        self._loader = loader
        self._discoverer = discoverer
        self._loaded: LoadedZOSAPI | None = None
        self._connection: Any | None = None
        self._application: Any | None = None
        self._system: Any | None = None
        self._ownership = ApplicationOwnership.NONE
        self._mode: ConnectionMode | None = None
        self._thread_id: int | None = None
        self._handles = HandleStore()
        self._operations: dict[str, Callable[..., Any]] = {
            operation: getattr(self, method_name)
            for operation, method_name in PRODUCTION_OPERATION_METHODS.items()
        }
        self._operations["release_handle"] = self.release_handle
        self._register_subsystems()

    def _register_subsystems(self) -> None:
        from .subsystems.analysis import build_operation_map as build_analysis_operations
        from .subsystems.general_tools import build_operation_map as build_general_operations
        from .subsystems.glass import build_operation_map as build_glass_operations
        from .subsystems.mce_mfe import build_operation_map as build_mce_mfe_operations
        from .subsystems.nsc import build_operation_map as build_nsc_operations
        from .subsystems.optimization import build_operation_map as build_optimization_operations
        from .subsystems.settings_lde import build_operation_map as build_settings_operations
        from .subsystems.zrd import build_operation_map as build_zrd_operations

        self._operations.update(build_glass_operations())
        self._operations.update(
            build_general_operations(self._require_system, self._api, lambda: self._ownership)
        )
        for builder in (
            build_settings_operations,
            build_mce_mfe_operations,
            build_nsc_operations,
            build_optimization_operations,
            build_analysis_operations,
            build_zrd_operations,
        ):
            for operation, handler in builder(self._require_system, self._api).items():
                if operation in self._operations:
                    continue
                self._operations[operation] = handler

    @property
    def connected(self) -> bool:
        return self.application_connected

    @property
    def application_connected(self) -> bool:
        return self._application is not None

    @property
    def system_connected(self) -> bool:
        return self._system is not None

    @property
    def ownership(self) -> ApplicationOwnership:
        return self._ownership

    def _bind_thread(self) -> None:
        current = get_ident()
        if self._thread_id is None:
            self._thread_id = current
        elif self._thread_id != current:
            raise BackendError(
                "thread_affinity",
                "RealZOSBackend may only be accessed from its dedicated worker thread",
            )

    def _require_system(self) -> Any:
        self._bind_thread()
        if self._system is None:
            raise ConnectionError("no OpticStudio system is connected")
        return self._system

    def _api(self) -> Any:
        if self._loaded is None:
            raise ConnectionError("ZOS-API has not been loaded")
        return self._loaded.zosapi

    def connect(
        self,
        mode: ConnectionMode | str = ConnectionMode.STANDALONE,
        *,
        instance_id: int = 0,
    ) -> Mapping[str, Any]:
        self._bind_thread()
        selected_mode = ConnectionMode.coerce(mode)
        if self.application_connected:
            if selected_mode == self._mode:
                return self.status()
            raise ConnectionError("already connected in a different mode")
        installation = self._installation or self._discoverer(self._config)
        self._installation = installation
        loaded = self._loader(installation)
        self._loaded = loaded
        connection: Any | None = None
        application: Any | None = None
        ownership = ApplicationOwnership.NONE
        try:
            connection_type = get_member(loaded.zosapi, "ZOSAPI_Connection")
            connection = connection_type()
            if selected_mode is ConnectionMode.STANDALONE:
                application = get_member(connection, "CreateNewApplication")()
                ownership = ApplicationOwnership.OWNED
            else:
                application = get_member(connection, "ConnectAsExtension")(instance_id)
                ownership = ApplicationOwnership.BORROWED
            if application is None:
                raise ConnectionError(
                    f"OpticStudio returned no application for {selected_mode.value} mode"
                )
            valid_license = getattr(application, "IsValidLicenseForAPI", True)
            if not bool(valid_license):
                raise ConnectionError("OpticStudio license is not valid for ZOS-API")
            system = getattr(application, "PrimarySystem", None)
            if system is None:
                raise ConnectionError("connected application has no PrimarySystem")
        except Exception as exc:
            close = getattr(application, "CloseApplication", None)
            if callable(close):
                with suppress(Exception):
                    close()
            self._connection = None
            self._application = None
            self._system = None
            self._ownership = ApplicationOwnership.NONE
            self._mode = None
            if isinstance(exc, ConnectionError):
                raise
            raise ConnectionError(
                f"failed to connect to OpticStudio in {selected_mode.value} mode: {exc}"
            ) from exc
        self._connection = connection
        self._application = application
        self._system = system
        self._ownership = ownership
        self._mode = selected_mode
        return self.status()

    def disconnect(
        self,
        *,
        close_application: bool | None = None,
        save: bool = False,
    ) -> Mapping[str, Any]:
        self._bind_thread()
        application = self._application
        ownership = self._ownership
        saved = False
        released = False
        if close_application is False and ownership is ApplicationOwnership.OWNED:
            raise BackendError(
                "disconnect",
                "an owned standalone application must be closed when disconnecting",
            )
        try:
            if save and self._system is not None:
                self.save_file()
                saved = True
            if application is not None:
                # For standalone this closes the owned application. For Interactive
                # Extension, OpticStudio documents this as releasing the external
                # API connection without closing the user-owned GUI process.
                close = getattr(application, "CloseApplication", None)
                if not callable(close):
                    raise BackendError("disconnect", "CloseApplication is unavailable")
                close()
                released = True
            return {
                "connected": False,
                "application_connected": False,
                "system_connected": False,
                "saved": saved,
                "released": released,
            }
        finally:
            self._handles.clear()
            self._system = None
            self._application = None
            self._connection = None
            self._ownership = ApplicationOwnership.NONE
            self._mode = None

    def dispatch(self, operation: str, /, **params: Any) -> Any:
        self._bind_thread()
        normalized = operation.strip().lower().replace("-", "_").replace(".", "_")
        handler = self._operations.get(normalized)
        if handler is None:
            raise UnsupportedOperationError(
                operation,
                "operation is not verified for the installed ZOS-API version",
            )
        try:
            return to_python(handler(**params))
        except (BackendError, ConnectionError, UnsupportedOperationError):
            raise
        except Exception as exc:
            raise BackendError(operation, str(exc)) from exc

    def status(self) -> dict[str, Any]:
        self._bind_thread()
        return {
            "connected": self.connected,
            "application_connected": self.application_connected,
            "system_connected": self.system_connected,
            "mode": self._mode.value if self._mode else None,
            "ownership": self._ownership.value,
            "worker_thread_id": self._thread_id,
            "install_dir": str(self._installation.install_dir)
            if self._installation is not None
            else None,
        }

    def close_file(self, *, save: bool = False) -> dict[str, Any]:
        system = self._require_system()
        close = getattr(system, "Close", None)
        if not callable(close):
            raise BackendError("close_file", "Close is unavailable")
        try:
            result = close(save)
            if result is False:
                raise BackendError("close_file", "OpticStudio did not close the current system")
        finally:
            self._handles.clear()
            self._system = None
        return {
            "connected": self.connected,
            "application_connected": self.application_connected,
            "system_connected": False,
            "saved": save,
            "closed": True,
        }

    def open_file(
        self,
        file_path: str | None = None,
        *,
        path: str | None = None,
        save_if_needed: bool = False,
    ) -> dict[str, Any]:
        application = self._application
        if application is None:
            raise ConnectionError("no OpticStudio application is connected")
        selected_path = file_path or path
        if not selected_path:
            raise BackendError("open_file", "provide file_path or path")
        path = str(Path(selected_path).expanduser().resolve())
        if self._system is None:
            # The installed R1.01 application API exposes LoadNewSystem(path)
            # without the save-if-needed argument because no current system exists.
            system = get_member(application, "LoadNewSystem")(path)
            if system is None:
                raise BackendError("open_file", f"OpticStudio did not load {path}")
            self._system = system
        else:
            result = get_member(self._system, "LoadFile")(path, save_if_needed)
            if result is False:
                raise BackendError("open_file", f"OpticStudio did not load {path}")
        return {
            "path": path,
            "loaded": True,
            "application_connected": True,
            "system_connected": True,
        }

    def save_file(
        self,
        file_path: str | None = None,
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        system = self._require_system()
        selected_path = file_path or path
        if selected_path:
            output_path = str(Path(selected_path).expanduser().resolve())
            result = get_member(system, "SaveAs")(output_path)
        else:
            output_path = str(getattr(system, "SystemFile", ""))
            if not output_path:
                raise BackendError("save_file", "system has no current file; provide file_path")
            result = get_member(system, "Save")()
        if result is False:
            raise BackendError("save_file", f"OpticStudio did not save {output_path}")
        return {"path": output_path, "saved": True}

    def new_system(self, *, sequential: bool = True) -> dict[str, Any]:
        application = self._application
        if application is None:
            raise ConnectionError("no OpticStudio application is connected")
        create = getattr(application, "CreateNewSystem", None)
        if callable(create):
            api = self._api()
            system_type = get_member(api, "SystemType")
            requested_type = get_member(
                system_type,
                "Sequential" if sequential else "NonSequential",
            )
            system = create(requested_type)
            if system is not None:
                self._system = system
                return self.get_system(include_surfaces=False)
        if self._system is None:
            raise UnsupportedOperationError(
                "new_system", "CreateNewSystem is unavailable after closing the current system"
            )
        # A fresh standalone application already supplies its PrimarySystem. Clear
        # the current sequential system when the stable New method is available.
        system = self._require_system()
        new = getattr(system, "New", None)
        if callable(new):
            new(False)
            return self.get_system(include_surfaces=False)
        raise UnsupportedOperationError("new_system", "no stable system creation method is exposed")

    def get_system(
        self,
        *,
        include_surfaces: bool = True,
        include_fields: bool = True,
        include_wavelengths: bool = True,
    ) -> dict[str, Any]:
        system = self._require_system()
        lde = getattr(system, "LDE", None)
        data: dict[str, Any] = {
            "file": str(getattr(system, "SystemFile", "")) or None,
            "mode": str(getattr(system, "Mode", "")) or None,
            "number_of_surfaces": int(getattr(lde, "NumberOfSurfaces", 0)) if lde else 0,
        }
        system_data = getattr(system, "SystemData", None)
        if include_fields and system_data is not None:
            fields = getattr(system_data, "Fields", None)
            count = int(getattr(fields, "NumberOfFields", 0)) if fields else 0
            get_field = getattr(fields, "GetField", None)
            data["fields"] = (
                [self._read_field(get_field(index)) for index in range(1, count + 1)]
                if callable(get_field)
                else []
            )
        if include_wavelengths and system_data is not None:
            wavelengths = getattr(system_data, "Wavelengths", None)
            count = int(getattr(wavelengths, "NumberOfWavelengths", 0)) if wavelengths else 0
            get_wavelength = getattr(wavelengths, "GetWavelength", None)
            data["wavelengths"] = (
                [self._read_wavelength(get_wavelength(index)) for index in range(1, count + 1)]
                if callable(get_wavelength)
                else []
            )
        if include_surfaces and lde is not None:
            data["surfaces"] = [
                self.get_surface(index) for index in range(data["number_of_surfaces"])
            ]
        return data

    @staticmethod
    def _read_field(field: Any) -> dict[str, Any]:
        return {
            "x": float(getattr(field, "X", 0.0)),
            "y": float(getattr(field, "Y", 0.0)),
            "weight": float(getattr(field, "Weight", 1.0)),
        }

    @staticmethod
    def _read_wavelength(wavelength: Any) -> dict[str, Any]:
        return {
            "wavelength": float(getattr(wavelength, "Wavelength", 0.0)),
            "weight": float(getattr(wavelength, "Weight", 1.0)),
        }

    def get_surface(self, surface_number: int) -> dict[str, Any]:
        surface = self._surface(surface_number)
        return {
            "surface_number": surface_number,
            "radius": compatible_radius(getattr(surface, "Radius", 0.0)),
            "thickness": float(getattr(surface, "Thickness", 0.0)),
            "material": str(getattr(surface, "Material", "")),
            "semi_diameter": float(getattr(surface, "SemiDiameter", 0.0)),
            "conic": float(getattr(surface, "Conic", 0.0)),
            "comment": str(getattr(surface, "Comment", "")),
            "is_stop": bool(getattr(surface, "IsStop", False)),
            "type": str(getattr(getattr(surface, "Type", None), "Name", "Standard")),
        }

    def _surface(self, surface_number: int) -> Any:
        system = self._require_system()
        lde = get_member(system, "LDE")
        count = int(getattr(lde, "NumberOfSurfaces", 0))
        index = count - 1 if surface_number == -1 else surface_number
        if index < 0 or index >= count:
            raise BackendError(
                "get_surface",
                f"surface {surface_number} is out of range 0..{count - 1}",
            )
        return get_member(lde, "GetSurfaceAt")(index)

    def set_surface(
        self,
        surface_number: int,
        *,
        radius: float | None = None,
        thickness: float | None = None,
        material: str | None = None,
        semi_diameter: float | None = None,
        conic: float | None = None,
        comment: str | None = None,
        is_stop: bool | None = None,
        **unverified: Any,
    ) -> dict[str, Any]:
        if unverified:
            names = ", ".join(sorted(unverified))
            raise UnsupportedOperationError("set_surface", f"unverified properties: {names}")
        surface = self._surface(surface_number)
        changes = {
            "Radius": radius,
            "Thickness": thickness,
            "Material": material,
            "SemiDiameter": semi_diameter,
            "Conic": conic,
            "Comment": comment,
            "IsStop": is_stop,
        }
        for name, value in changes.items():
            if value is not None:
                setattr(surface, name, value)
        return self.get_surface(surface_number)

    def add_surface(
        self,
        *,
        insert_at: int = 0,
        radius: float = 0.0,
        thickness: float = 0.0,
        material: str = "",
        comment: str = "",
    ) -> dict[str, Any]:
        system = self._require_system()
        lde = get_member(system, "LDE")
        count = int(getattr(lde, "NumberOfSurfaces", 0))
        index = count - 1 if insert_at == 0 else insert_at
        if index <= 0 or index >= count:
            raise BackendError("add_surface", f"insert_at must be 1..{max(count - 1, 1)} or 0")
        surface = get_member(lde, "InsertNewSurfaceAt")(index)
        surface.Radius = radius
        surface.Thickness = thickness
        surface.Material = material
        surface.Comment = comment
        return self.get_surface(index)

    def ray_trace(
        self,
        *,
        hx: float = 0.0,
        hy: float = 0.0,
        px: float = 0.0,
        py: float = 0.0,
        wavelength: int = 1,
        surface: int = 0,
    ) -> dict[str, Any]:
        system = self._require_system()
        lde = get_member(system, "LDE")
        to_surface = int(getattr(lde, "NumberOfSurfaces", 0)) - 1 if surface == 0 else surface
        tools = get_member(system, "Tools")
        tool = get_member(tools, "OpenBatchRayTrace")()
        if tool is None:
            raise BackendError("ray_trace", "batch ray trace tool is unavailable")
        data = None
        try:
            api = self._api()
            ray_namespace = get_member(get_member(api, "Tools"), "RayTrace")
            ray_type = get_member(get_member(ray_namespace, "RaysType"), "Real")
            opd_enum = get_member(ray_namespace, "OPDMode")
            opd_none = get_member(opd_enum, "None", "None_")
            data = get_member(tool, "CreateNormUnpol")(1, ray_type, to_surface)
            get_member(data, "AddRay")(wavelength, hx, hy, px, py, opd_none)
            get_member(tool, "RunAndWaitForCompletion")()
            get_member(data, "StartReadingResults")()
            result = get_member(data, "ReadNextResult")()
            values = list(result) if not isinstance(result, list) else result
            if len(values) < 15:
                raise BackendError("ray_trace", f"unexpected ray result length {len(values)}")
            names = (
                "success",
                "ray_number",
                "error_code",
                "vignette_code",
                "x",
                "y",
                "z",
                "l",
                "m",
                "n",
                "l2",
                "m2",
                "n2",
                "opd",
                "intensity",
            )
            converted = dict(zip(names, values, strict=False))
            serialized = to_python(converted)
            if not isinstance(serialized, dict):
                raise BackendError("ray_trace", "serialized ray result is not a mapping")
            return serialized
        finally:
            for resource in (data, tool):
                close = getattr(resource, "Close", None) if resource is not None else None
                if callable(close):
                    close()

    def rms_spot(
        self,
        *,
        hx: float = 0.0,
        hy: float = 0.0,
        wavelength: int = 0,
        reference: str = "centroid",
        sampling: int = 3,
        use_grid: bool = False,
    ) -> dict[str, Any]:
        if use_grid:
            raise UnsupportedOperationError(
                "rms_spot",
                "rectangular grid sampling is not yet implemented",
            )
        reference_key = reference.strip().lower()
        if reference_key not in {"centroid", "chief"}:
            raise BackendError("rms_spot", "reference must be 'centroid' or 'chief'")
        system = self._require_system()
        system_data = getattr(system, "SystemData", None)
        fields = getattr(system_data, "Fields", None)
        get_field = getattr(fields, "GetField", None)
        field_row = get_field(1) if callable(get_field) else None
        original_field: tuple[Any, Any, Any] | None = None
        if field_row is not None:
            original_field = (field_row.X, field_row.Y, field_row.Weight)
        field = 1
        try:
            if field_row is not None:
                field_row.X = hx
                field_row.Y = hy
            operand_name = "RSCE" if reference_key == "centroid" else "RSRE"
            mfe = get_member(system, "MFE")
            editors = get_member(self._api(), "Editors")
            mfe_namespace = get_member(editors, "MFE")
            operand_enum = get_member(mfe_namespace, "MeritOperandType")
            operand = get_member(operand_enum, operand_name)
            # GetOperandValue is the stable, non-mutating ZOS-API route. RSCE/RSRE
            # use Int1=sampling, Int2=wavelength and Data1=field.
            value = get_member(mfe, "GetOperandValue")(
                operand, sampling, wavelength, float(field), 0.0, 0.0, 0.0, 0.0, 0.0
            )
        finally:
            if field_row is not None and original_field is not None:
                field_row.X, field_row.Y, field_row.Weight = original_field
        return {
            "rms_spot_radius": float(value),
            "units": "lens units",
            "field": field,
            "wavelength": wavelength,
            "sampling": sampling,
            "reference": reference_key,
            "hx": hx,
            "hy": hy,
            "use_grid": use_grid,
        }

    def release_handle(self, handle: str) -> dict[str, Any]:
        return {"released": self._handles.release(handle), "handle": handle}
