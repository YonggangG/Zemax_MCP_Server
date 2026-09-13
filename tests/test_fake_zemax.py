from __future__ import annotations

import threading

import pytest

from tests.fake_zemax import (
    FakeBackend,
    FakeConnectionError,
    FakeLicenseError,
    FakeThreadAffinityError,
    canonical_json,
)


def test_fake_backend_lifecycle_is_stateful_and_deterministic() -> None:
    backend = FakeBackend()

    assert backend.status() == {"connected": False, "mode": None, "connect_count": 0}
    assert backend.execute("connect", {"mode": "standalone"}) == {
        "connected": True,
        "mode": "standalone",
        "connect_count": 1,
        "ownership": "owned",
    }
    first = backend.execute("get_system")
    second = backend.execute("get_system")
    assert first == second
    assert first["revision"] == 0

    assert backend.execute("disconnect")["connected"] is False
    with pytest.raises(FakeConnectionError, match="requires a connection"):
        backend.execute("get_system")


def test_fake_system_mutations_persist_and_save_open_round_trips() -> None:
    backend = FakeBackend()
    backend.connect()

    inserted = backend.execute(
        "add_surface",
        {"radius": 25.0, "thickness": 2.0, "material": "N-BK7", "comment": "L1"},
    )
    assert inserted["result"].material == "N-BK7"
    backend.execute("set_surface", {"surface_number": 1, "conic": -1.0, "is_stop": True})
    backend.execute("set_fields", {"fields": [{"x": 0.0, "y": 5.0, "weight": 1.0}]})
    saved = backend.execute("save_file", {"file_path": "memory://roundtrip.zos"})
    assert saved == {"result": "memory://roundtrip.zos"}

    backend.execute("new_system")
    assert len(backend.execute("get_system")["surfaces"]) == 3
    reopened = backend.execute("open_file", {"file_path": "memory://roundtrip.zos"})
    assert reopened["surfaces"][1]["conic"] == -1.0
    assert reopened["fields"][0]["y"] == 5.0


def test_representative_fake_operations_cover_multiple_domains() -> None:
    backend = FakeBackend()
    backend.connect()

    ray = backend.execute("ray_trace", {"hx": 0.25, "hy": 0.5, "px": 0.1, "py": -0.2})
    assert ray == {
        "success": True,
        "surface": 2,
        "x": 2.51,
        "y": 4.98,
        "l": 0.001,
        "m": -0.002,
        "n": 0.999995,
        "error_code": 0,
        "vignette_code": 0,
    }
    assert backend.execute("rms_spot", {"hy": 1.0})["rms_radius_um"] == 3.75
    mtf = backend.execute("fft_mtf", {"frequency": 100.0})
    assert mtf["frequency_cyc_per_mm"] == [0.0, 25.0, 50.0, 75.0, 100.0]
    assert backend.execute("add_operand", {"operand_type": "EFFL", "target": 50.0}) == {"row": 1}
    optimized = backend.execute("optimize", {"cycles": 3})
    assert optimized["final_merit"] < optimized["initial_merit"]


def test_fake_reports_useful_validation_and_unsupported_operation_errors() -> None:
    backend = FakeBackend()
    backend.connect()

    with pytest.raises(ValueError, match=r"\[-1, 1\]"):
        backend.execute("ray_trace", {"hx": 2.0})
    with pytest.raises(IndexError, match="surface 99"):
        backend.execute("get_surface", {"surface_number": 99})
    with pytest.raises(NotImplementedError, match="unsupported fake operation"):
        backend.execute("not_a_real_operation")


def test_fake_license_failure_is_explicit() -> None:
    from tests.fake_zemax import FakeApplication

    with pytest.raises(FakeLicenseError, match="license"):
        FakeApplication(licensed=False)


def test_fake_models_com_thread_affinity() -> None:
    backend = FakeBackend()
    backend.connect()
    errors: list[BaseException] = []

    def use_on_wrong_thread() -> None:
        try:
            backend.execute("get_system")
        except BaseException as exc:  # captured from the worker for the assertion
            errors.append(exc)

    worker = threading.Thread(target=use_on_wrong_thread)
    worker.start()
    worker.join()
    assert len(errors) == 1
    assert isinstance(errors[0], FakeThreadAffinityError)


def test_canonical_json_has_stable_compact_order() -> None:
    assert canonical_json({"z": 1, "a": [True, None]}) == '{"a":[true,null],"z":1}'
