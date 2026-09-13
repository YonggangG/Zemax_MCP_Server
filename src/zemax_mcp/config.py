"""Environment-driven runtime configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigurationError
from .zos.protocol import ConnectionMode

ENV_INSTALL_DIR = "ZEMAX_MCP_INSTALL_DIR"
ENV_ZOSAPI_PATH = "ZEMAX_MCP_ZOSAPI_PATH"
ENV_MODE = "ZEMAX_MCP_CONNECTION_MODE"
ENV_INSTANCE_ID = "ZEMAX_MCP_INSTANCE_ID"
ENV_WORKER_NAME = "ZEMAX_MCP_WORKER_NAME"


def _optional_path(value: str | None) -> Path | None:
    if value is None or not value.strip():
        return None
    return Path(os.path.expandvars(os.path.expanduser(value.strip())))


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Configuration required to discover and host ZOS-API."""

    install_dir: Path | None = None
    zosapi_path: Path | None = None
    connection_mode: ConnectionMode = ConnectionMode.STANDALONE
    instance_id: int = 0
    worker_name: str = "zemax-zos-worker"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> RuntimeConfig:
        source = os.environ if env is None else env
        raw_mode = source.get(ENV_MODE, ConnectionMode.STANDALONE.value)
        try:
            mode = ConnectionMode.coerce(raw_mode)
        except ValueError as exc:
            choices = ", ".join(item.value for item in ConnectionMode)
            raise ConfigurationError(
                f"{ENV_MODE} must be one of {choices}; got {raw_mode!r}"
            ) from exc
        raw_instance = source.get(ENV_INSTANCE_ID, "0")
        try:
            instance_id = int(raw_instance)
        except ValueError as exc:
            raise ConfigurationError(f"{ENV_INSTANCE_ID} must be an integer") from exc
        if instance_id < 0:
            raise ConfigurationError(f"{ENV_INSTANCE_ID} must be non-negative")
        worker_name = source.get(ENV_WORKER_NAME, "zemax-zos-worker").strip()
        if not worker_name:
            raise ConfigurationError(f"{ENV_WORKER_NAME} may not be empty")
        return cls(
            install_dir=_optional_path(source.get(ENV_INSTALL_DIR)),
            zosapi_path=_optional_path(source.get(ENV_ZOSAPI_PATH)),
            connection_mode=mode,
            instance_id=instance_id,
            worker_name=worker_name,
        )
