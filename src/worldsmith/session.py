"""Player-facing session state for a world and its retained timelines."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from .errors import NotFoundError, ValidationError
from .logging import log_event
from .simulation import World, create_demo_world

SESSION_VERSION = 2


@dataclass
class WorldSettings:
    """Reviewable creation choices retained with the world session."""

    name: str
    seed: int
    region_style: str = "temperate"
    civilization_count: int = 3


class WorldSession:
    """Owns the Prime world, alternate worlds, and current player selection."""

    def __init__(self, settings: WorldSettings, prime: World) -> None:
        self.settings = settings
        self.timelines: dict[str, World] = {prime.timeline.id: prime}
        self.active_timeline_id = prime.timeline.id
        self.migration_history: list[str] = []

    @property
    def active(self) -> World:
        return self.timelines[self.active_timeline_id]

    @classmethod
    def create(
        cls, name: str, seed: int, region_style: str = "temperate"
    ) -> WorldSession:
        settings = WorldSettings(name=name, seed=seed, region_style=region_style)
        world = create_demo_world(seed)
        world.id = f"world-{name.lower().replace(' ', '-') or 'unnamed'}"
        world.name = name
        return cls(settings, world)

    def branch(self, event_id: str, branch_name: str) -> World:
        branch_id = branch_name.lower().replace(" ", "-")
        if not branch_id:
            raise ValidationError("branch name is required")
        timeline_id = f"timeline-{branch_id}"
        if timeline_id in self.timelines:
            raise ValidationError("a timeline with that name already exists")
        alternate = self.active.branch(event_id, branch_id)
        self.timelines[alternate.timeline.id] = alternate
        self.active_timeline_id = alternate.timeline.id
        log_event(
            "timeline_created",
            timeline_id=alternate.timeline.id,
            parent_timeline_id=alternate.timeline.parent_timeline_id,
            branch_event_id=event_id,
        )
        return alternate

    def select_timeline(self, timeline_id: str) -> World:
        if timeline_id not in self.timelines:
            raise NotFoundError(f"unknown timeline: {timeline_id}")
        self.active_timeline_id = timeline_id
        return self.active

    def timeline_summaries(self) -> list[str]:
        rows = []
        for timeline_id, world in sorted(self.timelines.items()):
            marker = "ACTIVE" if timeline_id == self.active_timeline_id else "      "
            parent = world.timeline.parent_timeline_id or "none"
            rows.append(
                f"[{marker}] {timeline_id}: year {world.year}; parent {parent}; "
                f"events {len(world.events)}"
            )
        return rows

    def compare_to_prime(self) -> dict[str, str]:
        prime = self.timelines["timeline-prime"]
        return prime.compare(self.active)

    def validate(self) -> None:
        if self.active_timeline_id not in self.timelines:
            raise ValidationError("active timeline is missing")
        if "timeline-prime" not in self.timelines:
            raise ValidationError("Prime timeline is missing")
        for timeline_id, world in self.timelines.items():
            if timeline_id != world.timeline.id:
                raise ValidationError("timeline key and world metadata disagree")
            world._invariants()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "version": SESSION_VERSION,
            "settings": asdict(self.settings),
            "active_timeline_id": self.active_timeline_id,
            "migration_history": self.migration_history,
            "timelines": {
                timeline_id: world.to_dict()
                for timeline_id, world in sorted(self.timelines.items())
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldSession:
        data = migrate_session(data)
        timelines = {
            timeline_id: World.from_dict(payload)
            for timeline_id, payload in data["timelines"].items()
        }
        session = cls(WorldSettings(**data["settings"]), timelines["timeline-prime"])
        session.timelines = timelines
        session.active_timeline_id = data["active_timeline_id"]
        session.migration_history = list(data.get("migration_history", []))
        session.validate()
        return session


def migrate_session(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade supported session schemas without changing canonical history."""
    version = data.get("version")
    if version == SESSION_VERSION:
        return data
    if version != 1:
        raise ValidationError(f"unsupported session version: {version}")
    migrated = deepcopy(data)
    migrated["version"] = SESSION_VERSION
    migrated["settings"].setdefault("civilization_count", 3)
    migrated["migration_history"] = [*migrated.get("migration_history", []), "1->2"]
    log_event("session_migrated", from_version=1, to_version=SESSION_VERSION)
    return migrated
