"""Authoritative world state, simulation, events, interventions, and branching.

This module intentionally keeps prose out of canonical state.  Chronicle text is
derived from Event records and can always be regenerated.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from random import Random
from typing import Any
from uuid import uuid5, NAMESPACE_URL


SAVE_VERSION = 1


@dataclass
class Region:
    id: str
    name: str
    fertility: int


@dataclass
class Settlement:
    id: str
    name: str
    civilization_id: str
    region_id: str
    population: int
    resources: int


@dataclass
class Person:
    id: str
    name: str
    civilization_id: str
    alive: bool = True
    role: str = "ruler"


@dataclass
class Civilization:
    id: str
    name: str
    population: int
    leader_id: str
    settlement_ids: list[str] = field(default_factory=list)
    religion_id: str = ""
    stability: int = 60


@dataclass
class Resource:
    id: str
    name: str
    region_id: str
    amount: int


@dataclass
class Relationship:
    id: str
    source_id: str
    target_id: str
    score: int


@dataclass
class Religion:
    id: str
    name: str
    civilization_id: str
    tenet: str


@dataclass
class Event:
    id: str
    year: int
    type: str
    participants: list[str]
    location_id: str | None
    causes: list[str]
    effects: dict[str, Any]
    connected_events: list[str]
    significance: int
    truth: str
    interpretations: dict[str, str] = field(default_factory=dict)


@dataclass
class Timeline:
    id: str
    name: str
    parent_timeline_id: str | None
    branch_point_event_id: str | None
    branch_year: int | None


class World:
    """Canonical, serializable state for a single independently simulated world."""

    def __init__(self, world_id: str, seed: int, name: str = "Eryndor") -> None:
        self.id, self.seed, self.name, self.year = world_id, seed, name, 0
        self.timeline = Timeline("timeline-prime", "Prime", None, None, None)
        self.regions: dict[str, Region] = {}
        self.settlements: dict[str, Settlement] = {}
        self.people: dict[str, Person] = {}
        self.civilizations: dict[str, Civilization] = {}
        self.resources: dict[str, Resource] = {}
        self.relationships: dict[str, Relationship] = {}
        self.religions: dict[str, Religion] = {}
        self.events: list[Event] = []
        self._next: dict[str, int] = {}

    def entity_id(self, kind: str) -> str:
        self._next[kind] = self._next.get(kind, 0) + 1
        return f"{kind}-{self._next[kind]:04d}"

    def emit(self, event_type: str, participants: list[str], location_id: str | None,
             causes: list[str], effects: dict[str, Any], significance: int,
             truth: str, interpretations: dict[str, str] | None = None) -> Event:
        event = Event(self.entity_id("event"), self.year, event_type, participants,
                      location_id, causes, effects, [], significance, truth,
                      interpretations or {})
        if self.events:
            event.connected_events.append(self.events[-1].id)
        self.events.append(event)
        return event

    def advance(self, years: int) -> None:
        if years < 0:
            raise ValueError("years must be non-negative")
        for _ in range(years):
            self.year += 1
            self._advance_year()

    def _advance_year(self) -> None:
        # The derived seed makes results reproducible regardless of call grouping.
        rng = Random(f"{self.seed}:{self.timeline.id}:{self.year}")
        for civilization_id in sorted(self.civilizations):
            civ = self.civilizations[civilization_id]
            if civ.population <= 0:
                if not any(event.type == "civilization_collapse" and civ.id in event.participants for event in self.events):
                    self.emit("civilization_collapse", [civ.id], None, [], {"population": 0}, 7,
                              f"{civ.name} collapsed after losing its population base.")
                continue
            settlements = [self.settlements[s] for s in sorted(civ.settlement_ids)]
            food = sum(s.resources + self.regions[s.region_id].fertility for s in settlements)
            pressure = max(0, civ.population // 100 - food // 20)
            delta = rng.randint(-3, 5) - pressure
            civ.population = max(0, civ.population + delta)
            civ.stability = max(0, min(100, civ.stability + rng.randint(-2, 2) - pressure))
            if settlements:
                target = settlements[self.year % len(settlements)]
                target.population = max(0, target.population + delta)
                target.resources = max(0, target.resources + rng.randint(-1, 3) - pressure)
            if pressure >= 3 and self.year % 11 == 0:
                self.emit("famine", [civ.id], settlements[0].id if settlements else None,
                          [], {"population_delta": -pressure}, 3,
                          f"Resource pressure reduced {civ.name}'s population.")
            if civ.stability < 20 and self.year % 17 == 0:
                self.emit("religious_movement", [civ.id, civ.religion_id], None, [],
                          {"stability": civ.stability}, 4,
                          f"A reform movement arose in {civ.name}.")
            if self.year % 97 == 0:
                former = self.people[civ.leader_id]
                former.alive = False
                self.emit("ruler_death", [civ.id, former.id], None, [], {"role": former.role}, 5,
                          f"{former.name}, ruler of {civ.name}, died.")
                successor = Person(self.entity_id("person"), f"{civ.name} Successor", civ.id)
                self.people[successor.id] = successor
                civ.leader_id = successor.id
        self._relations_and_conflict(rng)
        self._migration(rng)
        self._invariants()

    def _relations_and_conflict(self, rng: Random) -> None:
        for relation_id in sorted(self.relationships):
            relation = self.relationships[relation_id]
            relation.score = max(-100, min(100, relation.score + rng.randint(-2, 2)))
            if relation.score < -70 and self.year % 23 == 0:
                self.emit("war_declared", [relation.source_id, relation.target_id], None,
                          [], {"relationship": relation.score}, 5,
                          "Two civilizations declared a limited conflict.")
                relation.score += 18
                self.emit("war_concluded", [relation.source_id, relation.target_id], None,
                          [self.events[-1].id], {"relationship": relation.score}, 4,
                          "The conflict concluded after constrained losses.")

    def _migration(self, rng: Random) -> None:
        if self.year % 13:
            return
        for civ in sorted(self.civilizations.values(), key=lambda item: item.id):
            if len(civ.settlement_ids) < 2 or civ.population < 20:
                continue
            source, target = (self.settlements[s] for s in sorted(civ.settlement_ids)[:2])
            moved = max(1, min(source.population // 10, rng.randint(1, 5)))
            source.population -= moved
            target.population += moved
            self.emit("migration", [civ.id, source.id, target.id], target.id, [],
                      {"moved": moved}, 2, f"People migrated within {civ.name}.")

    def intervene(self, kind: str, target_id: str, magnitude: int = 10) -> Event:
        if target_id not in self.settlements and target_id not in self.civilizations:
            raise ValueError("intervention target must be a settlement or civilization")
        target = self.settlements.get(target_id) or self.civilizations[target_id]
        interpretations: dict[str, str] = {}
        if kind == "create_resource":
            if not isinstance(target, Settlement):
                raise ValueError("create_resource requires a settlement")
            target.resources += magnitude
            effect, truth = {"resources": magnitude}, "A resource was created by divine action."
        elif kind == "bless":
            if not isinstance(target, Civilization):
                raise ValueError("bless requires a civilization")
            target.stability = min(100, target.stability + magnitude)
            effect, truth = {"stability": magnitude}, "A civilization received a divine blessing."
        elif kind == "curse":
            if not isinstance(target, Civilization):
                raise ValueError("curse requires a civilization")
            target.stability = max(0, target.stability - magnitude)
            effect, truth = {"stability": -magnitude}, "A civilization received a divine curse."
        elif kind == "natural_disaster":
            if not isinstance(target, Settlement):
                raise ValueError("natural_disaster requires a settlement")
            loss = min(target.population, magnitude)
            target.population -= loss
            effect, truth = {"population_delta": -loss}, "A divinely triggered disaster struck the settlement."
        elif kind == "miracle":
            if not isinstance(target, Settlement):
                raise ValueError("miracle requires a settlement")
            target.population += magnitude
            effect, truth = {"population_delta": magnitude}, "A divine miracle improved survival in the settlement."
        else:
            raise ValueError("unknown intervention")
        civ_id = target.civilization_id if isinstance(target, Settlement) else target.id
        religion = self.civilizations[civ_id].religion_id
        interpretations[civ_id] = "Priests described the event as a sign of favor or judgment."
        for other in sorted(self.civilizations):
            if other != civ_id:
                interpretations[other] = "Foreign observers disputed the event's cause."
        return self.emit(kind, [civ_id, religion, target_id], getattr(target, "region_id", None),
                         [], effect, 6, truth, interpretations)

    def branch(self, branch_point_event_id: str, branch_id: str) -> "World":
        event = next((item for item in self.events if item.id == branch_point_event_id), None)
        if event is None:
            raise KeyError(branch_point_event_id)
        clone = World.from_dict(self.to_dict())
        clone.id = branch_id
        clone.timeline = Timeline(f"timeline-{branch_id}", f"Alternate {branch_id}",
                                  self.timeline.id, event.id, event.year)
        clone.events = [item for item in clone.events if item.year <= event.year]
        clone.year = event.year
        return clone

    def chronicle(self, event_type: str | None = None, participant: str | None = None) -> list[str]:
        rows = []
        for event in self.events:
            if event_type and event.type != event_type:
                continue
            if participant and participant not in event.participants:
                continue
            rows.append(f"Year {event.year}: {event.type.replace('_', ' ')} — {event.truth}")
        return rows

    def compare(self, other: "World") -> dict[str, str]:
        prime = {(event.year, event.type, tuple(event.participants)): event for event in self.events}
        alternate = {(event.year, event.type, tuple(event.participants)): event for event in other.events}
        common = set(prime) & set(alternate)
        result = {"unchanged": str(len(common)), "altered": "0", "prevented": "0", "new": "0", "displaced": "0"}
        unmatched_prime, unmatched_alternate = set(prime) - common, set(alternate) - common
        # Same event identity/type but different effect is altered; same identity/type at a
        # different date is displaced.  Remaining unmatched records are prevented or new.
        for key in list(unmatched_prime):
            original = prime[key]
            same = next((candidate for candidate_key, candidate in ((k, alternate[k]) for k in unmatched_alternate)
                         if candidate.type == original.type and set(candidate.participants) == set(original.participants)), None)
            if same is None:
                continue
            unmatched_prime.remove(key)
            matched_key = next(k for k in unmatched_alternate if alternate[k] is same)
            unmatched_alternate.remove(matched_key)
            category = "displaced" if same.year != original.year else "altered"
            result[category] = str(int(result[category]) + 1)
        result["prevented"], result["new"] = str(len(unmatched_prime)), str(len(unmatched_alternate))
        return result

    def _invariants(self) -> None:
        for civ in self.civilizations.values():
            if civ.population < 0 or civ.stability < 0 or civ.stability > 100:
                raise AssertionError("invalid civilization state")
        for settlement in self.settlements.values():
            if settlement.population < 0 or settlement.resources < 0:
                raise AssertionError("invalid settlement state")

    def to_dict(self) -> dict[str, Any]:
        return {"version": SAVE_VERSION, "id": self.id, "seed": self.seed, "name": self.name,
                "year": self.year, "timeline": asdict(self.timeline), "next": self._next,
                "regions": {k: asdict(v) for k, v in self.regions.items()},
                "settlements": {k: asdict(v) for k, v in self.settlements.items()},
                "people": {k: asdict(v) for k, v in self.people.items()},
                "civilizations": {k: asdict(v) for k, v in self.civilizations.items()},
                "resources": {k: asdict(v) for k, v in self.resources.items()},
                "relationships": {k: asdict(v) for k, v in self.relationships.items()},
                "religions": {k: asdict(v) for k, v in self.religions.items()},
                "events": [asdict(v) for v in self.events]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "World":
        if data.get("version") != SAVE_VERSION:
            raise ValueError("unsupported save version")
        world = cls(data["id"], data["seed"], data["name"])
        world.year, world.timeline, world._next = data["year"], Timeline(**data["timeline"]), data["next"]
        for attr, typ in (("regions", Region), ("settlements", Settlement), ("people", Person),
                          ("civilizations", Civilization), ("resources", Resource),
                          ("relationships", Relationship), ("religions", Religion)):
            setattr(world, attr, {key: typ(**value) for key, value in data[attr].items()})
        world.events = [Event(**event) for event in data["events"]]
        return world


def create_demo_world(seed: int = 42) -> World:
    world = World("world-eryndor", seed)
    for index, name in enumerate(("Ash Coast", "Green March", "Iron Vale"), 1):
        region = Region(world.entity_id("region"), name, 45 + index * 10)
        world.regions[region.id] = region
    regions = list(sorted(world.regions))
    for index, name in enumerate(("Velar", "Ordan", "Tes"), 1):
        civ_id = world.entity_id("civilization")
        person = Person(world.entity_id("person"), f"{name} Founder", civ_id)
        religion = Religion(world.entity_id("religion"), f"{name} Tradition", civ_id, "ancestral memory")
        settlement = Settlement(world.entity_id("settlement"), f"{name} Hold", civ_id, regions[index - 1], 80 + index * 15, 55)
        civ = Civilization(civ_id, name, settlement.population, person.id, [settlement.id], religion.id)
        world.people[person.id], world.religions[religion.id] = person, religion
        world.settlements[settlement.id], world.civilizations[civ.id] = settlement, civ
        resource = Resource(world.entity_id("resource"), "grain", settlement.region_id, 100)
        world.resources[resource.id] = resource
        world.emit("settlement_founded", [civ.id, settlement.id], settlement.id, [], {"population": settlement.population}, 5, f"{name} founded {settlement.name}.")
    ids = sorted(world.civilizations)
    for source, target in zip(ids, ids[1:] + ids[:1]):
        relation = Relationship(world.entity_id("relationship"), source, target, -35)
        world.relationships[relation.id] = relation
    return world
