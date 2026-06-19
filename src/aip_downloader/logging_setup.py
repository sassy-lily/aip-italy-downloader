"""Logging configuration. Diagnostics go through here, never ``print``."""

from __future__ import annotations

import logging

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Set up root logging once. Idempotent enough for repeated CLI invocations."""
    logging.basicConfig(level=level.upper(), format=_FORMAT)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
