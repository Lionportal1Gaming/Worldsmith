"""Small structured logging boundary; no adapter logs canonical state itself."""

from __future__ import annotations

import json
import logging
from typing import Any

LOGGER = logging.getLogger("worldsmith")


def log_event(name: str, **fields: Any) -> None:
    """Emit stable event names with JSON fields suitable for automation."""
    LOGGER.info("%s %s", name, json.dumps(fields, default=str, sort_keys=True))


def log_failure(name: str, **fields: Any) -> None:
    """Emit recoverable failures without logging save payloads or secrets."""
    LOGGER.warning("%s %s", name, json.dumps(fields, default=str, sort_keys=True))
