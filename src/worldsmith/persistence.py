"""Versioned atomic JSON save/load for authoritative world state."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .simulation import World


class SaveError(ValueError):
    pass


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


def load_world(path: Path) -> World:
    try:
        return World.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise SaveError(f"cannot load {path}: {error}") from error
