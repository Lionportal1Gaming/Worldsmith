"""Stable error vocabulary shared by simulation, persistence, and presentation."""

from __future__ import annotations


class WorldsmithError(Exception):
    """Base error safe to present to an adapter or player-facing UI."""


class ValidationError(WorldsmithError, ValueError):
    """A command or authoritative state violates an explicit contract."""


class NotFoundError(WorldsmithError, KeyError):
    """A stable entity or timeline reference could not be resolved."""


class SaveError(WorldsmithError, ValueError):
    """A save cannot be safely written, migrated, loaded, or recovered."""
