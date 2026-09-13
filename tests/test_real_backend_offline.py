from __future__ import annotations

import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

from zemax_mcp.errors import BackendError, ConnectionError, UnsupportedOperationError
from zemax_mcp.zos.discovery import ZOSInstallation
from zemax_mcp.zos.loader import LoadedZOSAPI
from zemax_mcp.zos.protocol import ApplicationOwnership
from zemax_mcp.zos.real_backend import RealZOSBackend


class Surface:
    def __init__(self, number: int) -> None:
        self.Radius = float(number)
        self.Thickness = 1.0
        self.Material = ""
        self.SemiDiameter = 5.0
        self.Conic = 0.0
        self.Comment = f"S{number}"
        self.IsStop = number == 1
        self.Type = SimpleNamespace(Name="Standard")


class LDE:
    def __init__(self) -> None:
        self.surfaces = [Surface(0), Surface(1), Surface(2)]

    @property
    def NumberOfSurfaces(self) -> int:
        return len(self.surfaces)

    def GetSurfaceAt(self, index: int) -> Surface:
        return self.surfaces[index]

    def InsertNewSurfaceAt(self, index: int) -> Surface:
        surface = Surface(index)
        self.surfaces.insert(index, surface)
        return surface


class IndexedCollection:
    def __init__(self, values: list[Any], getter_name: str) -> None:
        self.values = values
        self.getter_name = getter_name

    def __getattr__(self, name: str) -> Any:
        if name == self.getter_name:
            return lambda index: self.values[index - 1]
        raise AttributeError(name)


class MFE:
    def GetOperandValue(self, *_args: Any) -> float:
        return 4.25


class System:
    def __init__(self) -> None:
        self.SystemFile = "C:/lens.zos"
        self.Mode = "Sequential"
        self.LDE = LDE()
        self.SystemData = SimpleNamespace(
            Fields=IndexedCollection([SimpleNamespace(X=0.0, Y=5.0, Weight=1.0)], "GetField"),
            Wavelengths=IndexedCollection(
                [SimpleNamespace(Wavelength=0.55, Weight=1.0)], "GetWavelength"
            ),
        )
        self.SystemData.Fields.NumberOfFields = 1
        self.SystemData.Wavelengths.NumberOfWavelengths = 1
        self.MFE = MFE()
        self.saved: list[str] = []
        self.loaded: list[tuple[str, bool]] = []
        self.new_calls: list[bool] = []
        self.close_calls: list[bool] = []

    def Close(self, save: bool) -> bool:
        self.close_calls.append(save)
        return True

    def LoadFile(self, path: str, save_if_needed: bool) -> bool:
        self.loaded.append((path, save_if_needed))
        return True

    def SaveAs(self, path: str) -> bool:
        self.saved.append(path)
        return True

    def Save(self) -> bool:
        self.saved.append(self.SystemFile)
        return True

    def New(self, save: bool) -> None:
        self.new_calls.append(save)


class Application:
    IsValidLicenseForAPI = True

    def __init__(self) -> None:
        self.PrimarySystem = System()
        self.closed = False
        self.created_system_types: list[Any] = []
        self.loaded_systems: list[str] = []

    def LoadNewSystem(self, path: str) -> System:
        self.loaded_systems.append(path)
        self.PrimarySystem = System()
        self.PrimarySystem.SystemFile = path
        return self.PrimarySystem

    def CreateNewSystem(self, system_type: Any) -> System:
        self.created_system_types.append(system_type)
        self.PrimarySystem = System()
        return self.PrimarySystem

    def CloseApplication(self) -> None:
        self.closed = True


class Connection:
    def __init__(self) -> None:
        self.application = Application()

    def CreateNewApplication(self) -> Application:
        return self.application

    def ConnectAsExtension(self, _instance: int) -> Application:
        return self.application


@pytest.fixture
def backend(tmp_path: Path) -> RealZOSBackend:
    api = SimpleNamespace(
        ZOSAPI_Connection=Connection,
        SystemType=SimpleNamespace(Sequential="Sequential"),
        Editors=SimpleNamespace(
            MFE=SimpleNamespace(MeritOperandType=SimpleNamespace(RSCE="RSCE", RSRE="RSRE"))
        ),
    )
    loaded = LoadedZOSAPI(
        cast(ModuleType, api),
        cast(ModuleType, SimpleNamespace()),
        None,
        None,
        threading.get_ident(),
    )
    installation = ZOSInstallation(
        install_dir=tmp_path,
        zosapi_dir=tmp_path,
        zosapi_dll=tmp_path / "ZOSAPI.dll",
        interfaces_dll=tmp_path / "ZOSAPI_Interfaces.dll",
    )
    return RealZOSBackend(installation=installation, loader=lambda _installation: loaded)


def test_offline_backend_connection_status_and_disconnect(backend: RealZOSBackend) -> None:
    metadata = backend.connect()
    assert metadata["connected"] is True
    assert metadata["application_connected"] is True
    assert metadata["system_connected"] is True
    assert backend.ownership is ApplicationOwnership.OWNED
    assert backend.connect()["connected"] is True
    with pytest.raises(ConnectionError, match="different mode"):
        backend.connect("extension")

    application = backend._application
    assert application is not None
    backend.disconnect()
    assert application.closed is True
    assert backend.connected is False
    assert backend.status()["ownership"] == "none"


def test_offline_backend_extension_releases_connection(backend: RealZOSBackend) -> None:
    backend.connect("extension", instance_id=2)
    assert backend.ownership is ApplicationOwnership.BORROWED
    application = backend._application
    assert application is not None
    result = backend.disconnect()
    assert result == {
        "connected": False,
        "application_connected": False,
        "system_connected": False,
        "saved": False,
        "released": True,
    }
    assert application.closed is True
    assert backend.connected is False


def test_offline_backend_system_surface_and_file_operations(
    backend: RealZOSBackend, tmp_path: Path
) -> None:
    backend.connect()
    snapshot = backend.get_system()
    assert snapshot["number_of_surfaces"] == 3
    assert snapshot["fields"] == [{"x": 0.0, "y": 5.0, "weight": 1.0}]
    assert snapshot["wavelengths"] == [{"wavelength": 0.55, "weight": 1.0}]
    assert len(snapshot["surfaces"]) == 3
    assert backend._system is not None
    backend._system.LDE.GetSurfaceAt(1).Radius = float("inf")
    assert backend.get_surface(1)["radius"] == 1e20
    assert backend.dispatch("get_surface", surface_number=1)["radius"] == 1e20
    backend.set_surface(1, radius=1e20)
    assert backend.get_surface(1)["radius"] == 1e20

    updated = backend.set_surface(1, radius=20.0, thickness=2.0, material="N-BK7", comment="lens")
    assert updated["radius"] == 20.0
    assert updated["material"] == "N-BK7"
    inserted = backend.add_surface(radius=12.0, material="F2")
    assert inserted["material"] == "F2"
    assert backend.get_surface(-1)["comment"] == "S2"

    path = tmp_path / "design.zos"
    assert backend.open_file(str(path))["loaded"] is True
    assert backend.save_file(str(path))["saved"] is True
    assert backend.save_file()["path"] == "C:/lens.zos"
    assert backend.new_system()["number_of_surfaces"] == 3
    application = backend._application
    assert application is not None
    assert application.created_system_types == ["Sequential"]


def test_offline_backend_close_file_keeps_application_and_loads_new_system(
    backend: RealZOSBackend, tmp_path: Path
) -> None:
    backend.connect()
    application = backend._application
    original_system = backend._system
    assert application is not None
    assert original_system is not None

    result = backend.close_file(save=True)
    assert result == {
        "connected": True,
        "application_connected": True,
        "system_connected": False,
        "saved": True,
        "closed": True,
    }
    assert original_system.close_calls == [True]
    assert application.closed is False
    assert backend.connected is True
    assert backend.system_connected is False
    assert backend.status()["system_connected"] is False
    with pytest.raises(ConnectionError, match="no OpticStudio system"):
        backend.get_system()

    path = tmp_path / "after-close.zos"
    opened = backend.open_file(str(path), save_if_needed=True)
    assert opened["system_connected"] is True
    assert application.loaded_systems == [str(path.resolve())]
    assert backend._system is application.PrimarySystem

    backend.close_file()
    created = backend.new_system(sequential=True)
    assert created["number_of_surfaces"] == 3
    assert application.created_system_types == ["Sequential"]
    assert backend.system_connected is True


def test_offline_backend_disconnect_after_close_file_releases_application(
    backend: RealZOSBackend,
) -> None:
    backend.connect()
    application = backend._application
    assert application is not None
    backend.close_file()

    result = backend.disconnect(save=True)
    assert result == {
        "connected": False,
        "application_connected": False,
        "system_connected": False,
        "saved": False,
        "released": True,
    }
    assert application.closed is True
    assert backend.status()["application_connected"] is False


def test_offline_backend_validation_and_dispatch_translation(backend: RealZOSBackend) -> None:
    with pytest.raises(ConnectionError, match="no OpticStudio system"):
        backend.get_system()
    backend.connect()
    with pytest.raises(BackendError, match="out of range"):
        backend.get_surface(99)
    with pytest.raises(BackendError, match="insert_at"):
        backend.add_surface(insert_at=99)
    with pytest.raises(UnsupportedOperationError, match="unverified"):
        backend.set_surface(1, unsupported=True)
    with pytest.raises(UnsupportedOperationError, match="not verified"):
        backend.dispatch("future-analysis")
    assert backend.dispatch("get.surface", surface_number=1)["surface_number"] == 1


def test_offline_backend_rms_spot_and_handle_release(backend: RealZOSBackend) -> None:
    backend.connect()
    assert backend._system is not None
    field = backend._system.SystemData.Fields.GetField(1)
    initial_field = (field.X, field.Y, field.Weight)
    result = backend.rms_spot(
        hx=0.1,
        hy=0.2,
        wavelength=1,
        sampling=4,
        reference="chief",
        use_grid=False,
    )
    assert result == {
        "rms_spot_radius": 4.25,
        "units": "lens units",
        "field": 1,
        "wavelength": 1,
        "sampling": 4,
        "reference": "chief",
        "hx": 0.1,
        "hy": 0.2,
        "use_grid": False,
    }
    assert (field.X, field.Y, field.Weight) == initial_field
    with pytest.raises(UnsupportedOperationError, match="grid"):
        backend.rms_spot(use_grid=True)
    with pytest.raises(BackendError, match="reference"):
        backend.rms_spot(reference="invalid")
    handle = backend._handles.put(object(), kind="analysis")
    assert backend.release_handle(handle.id)["released"] is True
    assert backend.release_handle(handle.id)["released"] is False


def test_offline_backend_enforces_thread_affinity(backend: RealZOSBackend) -> None:
    backend.status()
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            backend.status()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert len(errors) == 1
    assert isinstance(errors[0], BackendError)
    assert errors[0].operation == "thread_affinity"
