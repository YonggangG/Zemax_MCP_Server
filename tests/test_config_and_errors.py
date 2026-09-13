from __future__ import annotations

import pytest

from zemax_mcp.config import RuntimeConfig
from zemax_mcp.errors import (
    BackendError,
    ConfigurationError,
    InvalidHandleError,
    UnsupportedOperationError,
    ZemaxError,
)
from zemax_mcp.zos.protocol import ConnectionMode


def test_runtime_config_parses_environment_without_global_state() -> None:
    config = RuntimeConfig.from_env(
        {
            "ZEMAX_MCP_INSTALL_DIR": " ~/OpticStudio ",
            "ZEMAX_MCP_ZOSAPI_PATH": " ~/ZOS-API ",
            "ZEMAX_MCP_CONNECTION_MODE": " EXTENSION ",
            "ZEMAX_MCP_INSTANCE_ID": "3",
            "ZEMAX_MCP_WORKER_NAME": "worker-test",
        }
    )
    assert config.connection_mode is ConnectionMode.EXTENSION
    assert config.instance_id == 3
    assert config.worker_name == "worker-test"
    assert config.install_dir is not None
    assert config.zosapi_path is not None


@pytest.mark.parametrize(
    ("environment", "fragment"),
    [
        ({"ZEMAX_MCP_CONNECTION_MODE": "remote"}, "standalone"),
        ({"ZEMAX_MCP_INSTANCE_ID": "x"}, "integer"),
        ({"ZEMAX_MCP_INSTANCE_ID": "-1"}, "non-negative"),
        ({"ZEMAX_MCP_WORKER_NAME": " "}, "may not be empty"),
    ],
)
def test_runtime_config_validation_errors_are_actionable(
    environment: dict[str, str], fragment: str
) -> None:
    with pytest.raises(ConfigurationError, match=fragment):
        RuntimeConfig.from_env(environment)


def test_error_hierarchy_preserves_operation_and_handle_context() -> None:
    backend = BackendError("ray_trace", "failed")
    assert isinstance(backend, ZemaxError)
    assert backend.operation == "ray_trace"
    assert str(backend) == "ray_trace: failed"

    unsupported = UnsupportedOperationError("hammer")
    assert isinstance(unsupported, NotImplementedError)
    assert unsupported.operation == "hammer"

    invalid = InvalidHandleError("surface:9")
    assert isinstance(invalid, KeyError)
    assert invalid.handle == "surface:9"
    assert "surface:9" in str(invalid)
