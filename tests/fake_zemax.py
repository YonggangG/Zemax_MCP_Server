"""Deterministic, stateful OpticStudio/ZOS-API test double.

This module deliberately has no dependency on pythonnet, OpticStudio, or the package
under test.  It is reusable by unit tests and by downstream contributors while the
production adapter evolves.
"""

from __future__ import annotations

import copy
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class FakeZemaxError(RuntimeError):
    """Base exception raised by the fake backend."""


class FakeLicenseError(FakeZemaxError):
    """Raised when the configured fake license is unavailable."""


class FakeThreadAffinityError(FakeZemaxError):
    """Raised when a COM-like object is touched from the wrong thread."""


class FakeConnectionError(FakeZemaxError):
    """Raised for invalid connection/session operations."""


@dataclass
class FakeSurface:
    number: int
    radius: float = 0.0
    thickness: float = 0.0
    material: str = ""
    semi_diameter: float = 1.0
    conic: float = 0.0
    comment: str = ""
    is_stop: bool = False
    solves: dict[str, dict[str, Any]] = field(default_factory=dict)
    parameters: dict[int, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "radius": self.radius,
            "thickness": self.thickness,
            "material": self.material,
            "semi_diameter": self.semi_diameter,
            "conic": self.conic,
            "comment": self.comment,
            "is_stop": self.is_stop,
            "solves": copy.deepcopy(self.solves),
            "parameters": dict(self.parameters),
        }


@dataclass
class FakeSystemState:
    title: str = "Untitled"
    aperture_type: str = "EPD"
    aperture_value: float = 10.0
    afocal: bool = False
    ray_aiming: str = "Off"
    fields: list[dict[str, float]] = field(
        default_factory=lambda: [{"x": 0.0, "y": 0.0, "weight": 1.0}]
    )
    wavelengths: list[dict[str, float]] = field(
        default_factory=lambda: [{"wavelength": 0.5875618, "weight": 1.0}]
    )
    primary_wavelength: int = 1
    surfaces: list[FakeSurface] = field(
        default_factory=lambda: [
            FakeSurface(0, comment="OBJECT", thickness=float("inf")),
            FakeSurface(1, comment="STOP", is_stop=True, thickness=10.0),
            FakeSurface(2, comment="IMAGE"),
        ]
    )
    merit_operands: list[dict[str, Any]] = field(default_factory=list)
    configurations: list[dict[str, Any]] = field(default_factory=lambda: [{}])
    current_configuration: int = 1


class FakeSystem:
    """Small state machine modeling the subset every adapter layer needs."""

    def __init__(self, app: FakeApplication, state: FakeSystemState | None = None) -> None:
        self._app = app
        self.state = state or FakeSystemState()
        self.file_path: str | None = None
        self.closed = False
        self.revision = 0

    def _check(self, operation: str) -> None:
        self._app._check(operation)
        if self.closed:
            raise FakeConnectionError("optical system is closed")

    def _mutated(self, operation: str, **details: Any) -> None:
        self.revision += 1
        self._app.calls.append((operation, details))

    @property
    def surfaces(self) -> list[FakeSurface]:
        self._check("get_surfaces")
        return self.state.surfaces

    def get_surface(self, number: int) -> FakeSurface:
        self._check("get_surface")
        try:
            return self.state.surfaces[number]
        except (IndexError, TypeError) as exc:
            raise IndexError(f"surface {number} does not exist") from exc

    def add_surface(
        self,
        *,
        insert_at: int | None = None,
        radius: float = 0.0,
        thickness: float = 0.0,
        material: str = "",
        comment: str = "",
    ) -> FakeSurface:
        self._check("add_surface")
        image_index = len(self.state.surfaces) - 1
        index: int = image_index if insert_at is None or insert_at == 0 else insert_at
        if not 1 <= index <= image_index:
            raise ValueError("surface insertion point must be before the image surface")
        surface = FakeSurface(index, radius, thickness, material, comment=comment)
        self.state.surfaces.insert(index, surface)
        for number, item in enumerate(self.state.surfaces):
            item.number = number
        self._mutated("add_surface", insert_at=index)
        return surface

    def set_surface(self, number: int, **changes: Any) -> FakeSurface:
        surface = self.get_surface(number)
        allowed = {
            "radius",
            "thickness",
            "material",
            "semi_diameter",
            "conic",
            "comment",
            "is_stop",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unsupported surface properties: {sorted(unknown)}")
        for key, value in changes.items():
            setattr(surface, key, value)
        if changes.get("is_stop"):
            for item in self.state.surfaces:
                if item is not surface:
                    item.is_stop = False
        self._mutated("set_surface", number=number, changes=copy.deepcopy(changes))
        return surface

    def set_fields(self, fields: list[dict[str, float]]) -> None:
        self._check("set_fields")
        if not fields:
            raise ValueError("at least one field is required")
        self.state.fields = copy.deepcopy(fields)
        self._mutated("set_fields", count=len(fields))

    def set_wavelengths(self, wavelengths: list[dict[str, float]], primary: int = 1) -> None:
        self._check("set_wavelengths")
        if not wavelengths:
            raise ValueError("at least one wavelength is required")
        if not 1 <= primary <= len(wavelengths):
            raise ValueError("primary wavelength is out of range")
        self.state.wavelengths = copy.deepcopy(wavelengths)
        self.state.primary_wavelength = primary
        self._mutated("set_wavelengths", count=len(wavelengths), primary=primary)

    def ray_trace(
        self,
        hx: float = 0.0,
        hy: float = 0.0,
        px: float = 0.0,
        py: float = 0.0,
        wavelength: int = 1,
        surface: int = 0,
    ) -> dict[str, Any]:
        self._check("ray_trace")
        if any(abs(value) > 1 for value in (hx, hy, px, py)):
            raise ValueError("normalized field and pupil coordinates must be in [-1, 1]")
        if not 1 <= wavelength <= len(self.state.wavelengths):
            raise ValueError("wavelength number is out of range")
        target = len(self.state.surfaces) - 1 if surface == 0 else surface
        self.get_surface(target)
        # Stable formula, intentionally not pretending to be a physical ray trace.
        return {
            "success": True,
            "surface": target,
            "x": round(hx * 10.0 + px * 0.1, 9),
            "y": round(hy * 10.0 + py * 0.1, 9),
            "l": round(px * 0.01, 9),
            "m": round(py * 0.01, 9),
            "n": round(max(0.0, 1.0 - (px * px + py * py) * 0.0001), 9),
            "error_code": 0,
            "vignette_code": 0,
        }

    def rms_spot(self, hx: float = 0.0, hy: float = 0.0, wavelength: int = 0) -> dict[str, Any]:
        self._check("rms_spot")
        if wavelength < 0 or wavelength > len(self.state.wavelengths):
            raise ValueError("wavelength number is out of range")
        radius = round(1.25 + 2.5 * (hx * hx + hy * hy) ** 0.5 + 0.01 * self.revision, 6)
        return {"rms_radius_um": radius, "units": "um", "ray_count": 36}

    def fft_mtf(self, maximum_frequency: float) -> dict[str, Any]:
        self._check("fft_mtf")
        if maximum_frequency <= 0:
            raise ValueError("maximum frequency must be positive")
        frequencies = [round(maximum_frequency * i / 4, 6) for i in range(5)]
        fields = []
        for field_number, _field in enumerate(self.state.fields, start=1):
            scale = 1.0 - 0.05 * (field_number - 1)
            values = [round(max(0.0, scale * (1.0 - 0.8 * i / 4)), 6) for i in range(5)]
            fields.append({"field": field_number, "tangential": values, "sagittal": values})
        return {"frequency_cyc_per_mm": frequencies, "fields": fields}

    def add_operand(self, operand_type: str, **parameters: Any) -> int:
        self._check("add_operand")
        if len(operand_type) != 4 or not operand_type.isascii():
            raise ValueError("operand type must be a four-character code")
        self.state.merit_operands.append(
            {"type": operand_type.upper(), **copy.deepcopy(parameters)}
        )
        row = len(self.state.merit_operands)
        self._mutated("add_operand", row=row, operand_type=operand_type.upper())
        return row

    def optimize(self, cycles: int = 1) -> dict[str, Any]:
        self._check("optimize")
        if cycles < 0:
            raise ValueError("cycles cannot be negative")
        initial = round(10.0 + len(self.state.merit_operands), 6)
        final = round(initial / (1.0 + max(cycles, 1)), 6)
        self._mutated("optimize", cycles=cycles)
        return {"initial_merit": initial, "final_merit": final, "cycles": cycles}

    def snapshot(self) -> dict[str, Any]:
        self._check("snapshot")
        return {
            "title": self.state.title,
            "aperture_type": self.state.aperture_type,
            "aperture_value": self.state.aperture_value,
            "afocal": self.state.afocal,
            "ray_aiming": self.state.ray_aiming,
            "fields": copy.deepcopy(self.state.fields),
            "wavelengths": copy.deepcopy(self.state.wavelengths),
            "primary_wavelength": self.state.primary_wavelength,
            "surfaces": [surface.as_dict() for surface in self.state.surfaces],
            "merit_operands": copy.deepcopy(self.state.merit_operands),
            "configurations": copy.deepcopy(self.state.configurations),
            "current_configuration": self.state.current_configuration,
            "revision": self.revision,
        }

    def save(self, file_path: str | Path | None = None) -> str:
        self._check("save")
        path = str(file_path or self.file_path or "")
        if not path:
            raise ValueError("a file path is required for an unsaved system")
        self.file_path = path
        self._app.saved_files[path] = self.snapshot()
        self._app.calls.append(("save", {"file_path": path}))
        return path


class FakeApplication:
    """COM-like application with license, lifecycle, and thread affinity."""

    def __init__(
        self,
        *,
        licensed: bool = True,
        enforce_thread_affinity: bool = True,
        owner_thread_id: int | None = None,
    ) -> None:
        if not licensed:
            raise FakeLicenseError("OpticStudio license is unavailable")
        self.owner_thread_id = owner_thread_id or threading.get_ident()
        self.enforce_thread_affinity = enforce_thread_affinity
        self.closed = False
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.call_thread_ids: list[int] = []
        self.saved_files: dict[str, dict[str, Any]] = {}
        self.PrimarySystem = FakeSystem(self)

    def _check(self, operation: str) -> None:
        self.call_thread_ids.append(threading.get_ident())
        if self.closed:
            raise FakeConnectionError("OpticStudio application is closed")
        if self.enforce_thread_affinity and threading.get_ident() != self.owner_thread_id:
            raise FakeThreadAffinityError(
                f"{operation} called on thread {threading.get_ident()}, "
                f"expected {self.owner_thread_id}"
            )

    def new_system(self) -> FakeSystem:
        self._check("new_system")
        self.PrimarySystem.closed = True
        self.PrimarySystem = FakeSystem(self)
        self.calls.append(("new_system", {}))
        return self.PrimarySystem

    def open_file(self, file_path: str | Path) -> FakeSystem:
        self._check("open_file")
        path = str(file_path)
        if path not in self.saved_files:
            raise FileNotFoundError(path)
        raw = copy.deepcopy(self.saved_files[path])
        surfaces = [FakeSurface(**item) for item in raw.pop("surfaces")]
        raw.pop("revision", None)
        state = FakeSystemState(surfaces=surfaces, **raw)
        self.PrimarySystem.closed = True
        self.PrimarySystem = FakeSystem(self, state)
        self.PrimarySystem.file_path = path
        self.calls.append(("open_file", {"file_path": path}))
        return self.PrimarySystem

    def close(self) -> None:
        self._check("close")
        self.PrimarySystem.closed = True
        self.closed = True
        self.calls.append(("close", {}))


class FakeConnection:
    """Factory/session fake suitable for dependency injection into an adapter."""

    def __init__(
        self, application_factory: Callable[..., FakeApplication] = FakeApplication
    ) -> None:
        self.application_factory = application_factory
        self.application: FakeApplication | None = None
        self.mode: str | None = None
        self.connect_count = 0

    @property
    def connected(self) -> bool:
        return self.application is not None and not self.application.closed

    def connect(self, mode: str = "standalone", instance_id: int = 0) -> FakeApplication:
        if self.connected:
            raise FakeConnectionError("already connected")
        if mode not in {"standalone", "extension"}:
            raise ValueError("mode must be 'standalone' or 'extension'")
        self.mode = mode
        self.connect_count += 1
        self.application = self.application_factory()
        self.application.calls.append(("connect", {"mode": mode, "instance_id": instance_id}))
        return self.application

    def disconnect(self) -> None:
        if not self.connected or self.application is None:
            raise FakeConnectionError("not connected")
        self.application.close()

    def restart(self) -> FakeApplication:
        mode = self.mode or "standalone"
        if self.connected:
            self.disconnect()
        return self.connect(mode)

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "mode": self.mode,
            "connect_count": self.connect_count,
        }


class FakeBackend:
    """Generic backend matching the intended ``zos.protocol.ZOSBackend`` shape."""

    def __init__(
        self, connection: FakeConnection | None = None, *_args: Any, **_kwargs: Any
    ) -> None:
        self.connection = connection or FakeConnection()
        self.operations: list[tuple[str, dict[str, Any], int]] = []

    @property
    def connected(self) -> bool:
        return self.connection.connected

    @property
    def ownership(self) -> str:
        return "owned" if self.connected else "none"

    def connect(
        self, mode: Any = "standalone", instance_id: int = 0, **_kwargs: Any
    ) -> dict[str, Any]:
        mode_value = getattr(mode, "value", mode)
        self.connection.connect(str(mode_value), instance_id)
        return {**self.status(), "ownership": "owned"}

    def disconnect(self, *, save: bool = False, **_kwargs: Any) -> dict[str, Any]:
        if save and self.connection.application is not None:
            self.connection.application.PrimarySystem.save()
        self.connection.disconnect()
        return {"connected": False, "saved": save, "released": True}

    def restart(self) -> dict[str, Any]:
        self.connection.restart()
        return self.status()

    def status(self) -> dict[str, Any]:
        return self.connection.status()

    def dispatch(self, operation: str, /, **params: Any) -> dict[str, Any]:
        return self.execute(operation, params)

    def execute(self, operation: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        args = copy.deepcopy(arguments or {})
        self.operations.append((operation, args, threading.get_ident()))
        if operation == "connect":
            return self.connect(**args)
        if operation == "disconnect":
            return self.disconnect()
        if operation == "restart":
            return self.restart()
        if operation == "status":
            return self.status()
        if not self.connection.connected or self.connection.application is None:
            raise FakeConnectionError(f"operation {operation!r} requires a connection")
        app = self.connection.application
        system = app.PrimarySystem
        dispatch: dict[str, Callable[..., Any]] = {
            "new_system": app.new_system,
            "open_file": app.open_file,
            "save_file": system.save,
            "get_system": system.snapshot,
            "get_surface": lambda **values: system.get_surface(
                values.pop("surface_number", values.pop("number", -999))
            ).as_dict(),
            "add_surface": system.add_surface,
            "set_surface": lambda **values: system.set_surface(
                values.pop("surface_number", values.pop("number", -999)), **values
            ).as_dict(),
            "set_fields": system.set_fields,
            "set_wavelengths": system.set_wavelengths,
            "ray_trace": system.ray_trace,
            "rms_spot": system.rms_spot,
            "fft_mtf": lambda **values: system.fft_mtf(
                values.pop("maximum_frequency", values.pop("frequency", 0.0))
            ),
            "add_operand": lambda **values: {
                "row": system.add_operand(values.pop("operand_type"), **values)
            },
            "optimize": system.optimize,
        }
        try:
            function = dispatch[operation]
        except KeyError as exc:
            raise NotImplementedError(f"unsupported fake operation: {operation}") from exc
        result = function(**args)
        if result is None:
            return {"ok": True}
        if isinstance(result, FakeSystem):
            return result.snapshot()
        if isinstance(result, dict):
            return result
        return {"result": result}


def canonical_json(value: Any) -> str:
    """Serialize responses in the stable form used by protocol assertions."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
