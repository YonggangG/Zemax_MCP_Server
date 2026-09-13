"""Small, side-effect-free logging helpers."""

from __future__ import annotations

import logging
import os
from typing import TextIO

_LOGGER_NAME = "zemax_mcp"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a package logger without configuring global logging."""
    return logging.getLogger(_LOGGER_NAME if name is None else f"{_LOGGER_NAME}.{name}")


def configure_logging(
    level: str | int | None = None,
    *,
    stream: TextIO | None = None,
    force: bool = False,
) -> logging.Logger:
    """Configure only the package logger and return it.

    Applications remain in control of the root logger. Repeated calls do not add
    duplicate handlers unless ``force`` is requested.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    configured_level = level if level is not None else os.getenv("ZEMAX_MCP_LOG_LEVEL", "INFO")
    if isinstance(configured_level, str):
        numeric_level = logging.getLevelNamesMapping().get(configured_level.upper())
        if numeric_level is None:
            raise ValueError(f"invalid log level: {configured_level!r}")
    else:
        numeric_level = configured_level

    if force:
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
    if not logger.handlers:
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(numeric_level)
    logger.propagate = False
    return logger
