"""Versioned atomic JSON save/load for authoritative world state."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .errors import SaveError
from .logging import log_event, log_failure
from .session import WorldSession
from .simulation import World


def save_world(world: World, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(world.to_dict(), sort_keys=True, separators=(",", ":"))
    temporary = path.with_suffix(path.suffix + ".tmp")
    backup = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        backup.write_bytes(path.read_bytes())
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    log_event("world_saved", path=path.name, year=world.year)


def load_world(path: Path) -> World:
    try:
        return World.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        log_failure("world_load_failed", path=path.name, error=type(error).__name__)
        raise SaveError(f"cannot load {path}: {error}") from error


def save_session(session: WorldSession, path: Path) -> None:
    """Atomically retain Prime and every alternate timeline in one save file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(session.to_dict(), sort_keys=True, separators=(",", ":"))
    temporary = path.with_suffix(path.suffix + ".tmp")
    backup = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        backup.write_bytes(path.read_bytes())
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    log_event("session_saved", path=path.name, timelines=len(session.timelines))


def load_session(path: Path) -> WorldSession:
    try:
        session = WorldSession.from_dict(json.loads(path.read_text(encoding="utf-8")))
        log_event("session_loaded", path=path.name, timelines=len(session.timelines))
        return session
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        log_failure("session_load_failed", path=path.name, error=type(error).__name__)
        raise SaveError(f"cannot recover session from {path}: {error}") from error
