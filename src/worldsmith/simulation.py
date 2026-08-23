"""Authoritative world state, simulation, events, interventions, and branching.

This module intentionally keeps prose out of canonical state.  Chronicle text is
derived from Event records and can always be regenerated.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from random import Random
from typing import Any

from .errors import NotFoundError, ValidationError

SAVE_VERSION = 3
EVENT_SCHEMA_VERSION = 1


@dataclass
class Region:
    id: str
    name: str
    fertility: int
    terrain: str = "plains"
    climate: str = "temperate"
    neighbors: list[str] = field(default_factory=list)


@dataclass
class Settlement:
    id: str
    name: str
    civilization_id: str
    region_id: str
    population: int
    resources: int
    culture: str = "local"
    status: str = "active"
    founded_year: int = 0
    ruin_year: int | None = None
    needs: int = 0


@dataclass
class Person:
    id: str
    name: str
    civilization_id: str
    alive: bool = True
    role: str = "ruler"
    birth_year: int = 0
    death_year: int | None = None
    relationships: list[str] = field(default_factory=list)
    reputation: int = 0
    significance: int = 1
    legacy: str = ""


@dataclass
class Civilization:
    id: str
    name: str
    population: int
    leader_id: str
    settlement_ids: list[str] = field(default_factory=list)
    religion_id: str = ""
    stability: int = 60
    territory_region_ids: list[str] = field(default_factory=list)
    culture: str = "local"
    status: str = "active"


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
    status: str = "neutral"
    history: list[str] = field(default_factory=list)


@dataclass
class Religion:
    id: str
    name: str
    civilization_id: str
    tenet: str
    institution: str = "shrine network"
    influence_by_civilization: dict[str, int] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)


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
    schema_version: int = EVENT_SCHEMA_VERSION


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

    def emit(
        self,
        event_type: str,
        participants: list[str],
        location_id: str | None,
        causes: list[str],
        effects: dict[str, Any],
        significance: int,
        truth: str,
        interpretations: dict[str, str] | None = None,
    ) -> Event:
        event = Event(
            self.entity_id("event"),
            self.year,
            event_type,
            participants,
            location_id,
            causes,
            effects,
            [],
            significance,
            truth,
            interpretations or {},
        )
        if self.events:
            event.connected_events.append(self.events[-1].id)
        self.events.append(event)
        return event

    def advance(self, years: int) -> None:
        if years < 0:
            raise ValidationError("years must be non-negative")
        for _ in range(years):
            self.year += 1
            self._advance_year()

    def _advance_year(self) -> None:
        # The derived seed makes results reproducible regardless of call grouping.
        rng = Random(f"{self.seed}:{self.timeline.id}:{self.year}")
        for civilization_id in sorted(self.civilizations):
            civ = self.civilizations[civilization_id]
            if civ.population <= 0 or civ.status == "collapsed":
                if civ.status != "collapsed":
                    civ.status = "collapsed"
                    self.emit(
                        "civilization_collapse",
                        [civ.id],
                        None,
                        [],
                        {"population": 0},
                        7,
                        f"{civ.name} collapsed after losing its population base.",
                    )
                continue
            settlements = [
                self.settlements[s]
                for s in sorted(civ.settlement_ids)
                if self.settlements[s].status == "active"
            ]
            if not settlements:
                civ.population, civ.status = 0, "collapsed"
                self.emit(
                    "civilization_collapse",
                    [civ.id],
                    None,
                    [],
                    {"population": 0},
                    7,
                    f"{civ.name} collapsed after losing every active settlement.",
                )
                continue
            food = sum(
                s.resources + self.regions[s.region_id].fertility for s in settlements
            )
            pressure = max(0, civ.population // 100 - food // 18)
            delta = rng.randint(-3, 6) - pressure
            civ.stability = max(
                0, min(100, civ.stability + rng.randint(-2, 2) - pressure)
            )
            target = settlements[self.year % len(settlements)]
            target.population = max(0, target.population + delta)
            target.needs = max(10, target.population // 8)
            target.resources = max(
                0, target.resources + rng.randint(-1, 3) - pressure - target.needs // 20
            )
            if target.population <= 10:
                self._abandon_settlement(civ, target, "resource collapse")
            civ.population = sum(
                settlement.population
                for settlement in self.settlements.values()
                if settlement.civilization_id == civ.id
                and settlement.status == "active"
            )
            if pressure >= 3 and self.year % 11 == 0:
                self.emit(
                    "famine",
                    [civ.id],
                    settlements[0].id if settlements else None,
                    [],
                    {"population_delta": -pressure},
                    3,
                    f"Resource pressure reduced {civ.name}'s population.",
                )
            self._figure_lifecycle(civ)
            self._religion_evolution(civ, pressure)
            self._civilization_expansion(civ, rng)
        self._relations_and_conflict(rng)
        self._migration(rng)
        self._invariants()

    def _relations_and_conflict(self, rng: Random) -> None:
        for relation_id in sorted(self.relationships):
            relation = self.relationships[relation_id]
            relation.score = max(-100, min(100, relation.score + rng.randint(-2, 2)))
            previous_status = relation.status
            relation.status = (
                "allied"
                if relation.score >= 65
                else "hostile"
                if relation.score <= -65
                else "rival"
                if relation.score <= -35
                else "friendly"
                if relation.score >= 35
                else "neutral"
            )
            if relation.status != previous_status:
                event = self.emit(
                    "diplomatic_status_changed",
                    [relation.source_id, relation.target_id],
                    None,
                    relation.history[-1:],
                    {
                        "from": previous_status,
                        "to": relation.status,
                        "score": relation.score,
                    },
                    3,
                    f"Relations shifted from {previous_status} to {relation.status}.",
                )
                relation.history.append(event.id)
            if relation.status == "allied" and self.year % 29 == 0:
                event = self.emit(
                    "alliance_renewed",
                    [relation.source_id, relation.target_id],
                    None,
                    relation.history[-1:],
                    {"relationship": relation.score},
                    4,
                    "Two civilizations renewed a formal alliance.",
                )
                relation.history.append(event.id)
            if relation.status == "hostile" and self.year % 23 == 0:
                declaration = self.emit(
                    "war_declared",
                    [relation.source_id, relation.target_id],
                    None,
                    relation.history[-1:],
                    {
                        "relationship": relation.score,
                        "cause": "hostile diplomatic history",
                    },
                    5,
                    "Two civilizations declared an abstract conflict after hostile diplomacy.",
                )
                relation.history.append(declaration.id)
                winner_id, loser_id = (
                    (relation.source_id, relation.target_id)
                    if rng.randint(0, 1) == 0
                    else (relation.target_id, relation.source_id)
                )
                winner, loser = (
                    self.civilizations[winner_id],
                    self.civilizations[loser_id],
                )
                active = [
                    self.settlements[s]
                    for s in loser.settlement_ids
                    if self.settlements[s].status == "active"
                ]
                losses = 0
                territory = None
                location_id = None
                if active:
                    target = min(active, key=lambda settlement: settlement.population)
                    losses = min(target.population // 4, rng.randint(4, 18))
                    target.population -= losses
                    territory = target.region_id
                    location_id = target.id
                    if target.population <= 10:
                        self._abandon_settlement(loser, target, "war destruction")
                    if territory in loser.territory_region_ids:
                        loser.territory_region_ids.remove(territory)
                        if territory not in winner.territory_region_ids:
                            winner.territory_region_ids.append(territory)
                loser.stability = max(0, loser.stability - 8)
                winner.stability = min(100, winner.stability + 4)
                conclusion = self.emit(
                    "war_concluded",
                    [relation.source_id, relation.target_id],
                    location_id,
                    [declaration.id],
                    {
                        "winner": winner_id,
                        "population_losses": losses,
                        "territory_claim": territory,
                        "loser_stability": loser.stability,
                    },
                    4,
                    "The conflict concluded with population and political consequences.",
                )
                relation.history.append(conclusion.id)
                relation.score = min(20, relation.score + 22)

    def negotiate(self, source_id: str, target_id: str, offer: str) -> Event:
        """Record a concrete diplomatic choice and its durable relationship effect."""
        relation = next(
            (
                item
                for item in self.relationships.values()
                if item.source_id == source_id and item.target_id == target_id
            ),
            None,
        )
        if relation is None:
            raise NotFoundError(f"relationship:{source_id}:{target_id}")
        shifts = {"trade": 12, "aid": 8, "tribute": 4, "insult": -15}
        if offer not in shifts:
            raise ValidationError("offer must be trade, aid, tribute, or insult")
        before = relation.score
        relation.score = max(-100, min(100, relation.score + shifts[offer]))
        event = self.emit(
            "diplomatic_negotiation",
            [source_id, target_id],
            None,
            relation.history[-1:],
            {"offer": offer, "score_before": before, "score_after": relation.score},
            3,
            f"{self.civilizations[source_id].name} offered {offer} to "
            f"{self.civilizations[target_id].name}.",
        )
        relation.history.append(event.id)
        return event

    def record_figure_action(
        self, person_id: str, action: str, significance: int = 3
    ) -> Event:
        """Give a historical figure an attributable action, reputation, and legacy."""
        person = self.people.get(person_id)
        if person is None:
            raise NotFoundError(person_id)
        if not action.strip() or significance < 1:
            raise ValidationError("action and a positive significance are required")
        person.reputation += significance
        person.significance = max(person.significance, significance)
        person.legacy = action
        return self.emit(
            "historical_figure_action",
            [person.id, person.civilization_id],
            None,
            [],
            {"action": action, "reputation": person.reputation},
            min(10, significance),
            f"{person.name} {action}.",
        )

    def destroy_settlement(self, settlement_id: str, cause: str = "disaster") -> Event:
        """Preserve a settlement as a ruin instead of deleting its history."""
        settlement = self.settlements.get(settlement_id)
        if settlement is None:
            raise NotFoundError(settlement_id)
        if settlement.status != "active":
            raise ValidationError("only active settlements can be destroyed")
        civ = self.civilizations[settlement.civilization_id]
        return self._abandon_settlement(civ, settlement, cause, destroyed=True)

    def _abandon_settlement(
        self,
        civ: Civilization,
        settlement: Settlement,
        reason: str,
        *,
        destroyed: bool = False,
    ) -> Event:
        settlement.status = "ruins"
        settlement.ruin_year = self.year
        population = settlement.population
        settlement.population = 0
        if settlement.region_id in civ.territory_region_ids:
            civ.territory_region_ids.remove(settlement.region_id)
        civ.population = sum(
            candidate.population
            for candidate in self.settlements.values()
            if candidate.civilization_id == civ.id and candidate.status == "active"
        )
        event_type = "settlement_destroyed" if destroyed else "settlement_abandoned"
        return self.emit(
            event_type,
            [civ.id, settlement.id],
            settlement.id,
            [],
            {"reason": reason, "former_population": population, "ruin_year": self.year},
            5,
            f"{settlement.name} became ruins after {reason}.",
        )

    def _figure_lifecycle(self, civ: Civilization) -> None:
        if self.year % 31 == 0:
            person = Person(
                self.entity_id("person"),
                f"{civ.name} Chronicler {self.year}",
                civ.id,
                role="historian",
                birth_year=self.year,
                relationships=[civ.leader_id],
                reputation=2,
                significance=2,
            )
            self.people[person.id] = person
            self.emit(
                "historical_figure_born",
                [person.id, civ.id, civ.leader_id],
                None,
                [],
                {"role": person.role},
                2,
                f"{person.name} was born into {civ.name}.",
            )
        if self.year % 97 == 0:
            former = self.people[civ.leader_id]
            former.alive, former.death_year = False, self.year
            former.legacy = former.legacy or "Ruled through a formative era"
            successor = Person(
                self.entity_id("person"),
                f"{civ.name} Successor {self.year}",
                civ.id,
                role="ruler",
                birth_year=max(0, self.year - 28),
                relationships=[former.id],
                reputation=max(1, former.reputation // 2),
                significance=max(3, former.significance),
            )
            self.people[successor.id] = successor
            civ.leader_id = successor.id
            self.emit(
                "ruler_death",
                [former.id, successor.id, civ.id],
                None,
                [],
                {"legacy": former.legacy, "successor": successor.id},
                5,
                f"{former.name} died and {successor.name} succeeded them.",
            )

    def _religion_evolution(self, civ: Civilization, pressure: int) -> None:
        religion = self.religions[civ.religion_id]
        religion.influence_by_civilization[civ.id] = max(
            0,
            min(
                100, religion.influence_by_civilization.get(civ.id, 100) + 1 - pressure
            ),
        )
        if (pressure >= 3 or civ.stability < 35) and self.year % 11 == 0:
            religion.institution = "reform council"
            event = self.emit(
                "religious_movement",
                [religion.id, civ.id],
                None,
                religion.history[-1:],
                {"institution": religion.institution, "pressure": pressure},
                4,
                f"A reform movement reshaped {religion.name}.",
            )
            religion.history.append(event.id)
        if self.year % 17 == 0:
            friendly = next(
                (
                    relation.target_id
                    for relation in self.relationships.values()
                    if relation.source_id == civ.id and relation.score >= 20
                ),
                None,
            )
            if friendly:
                religion.influence_by_civilization[friendly] = min(
                    100, religion.influence_by_civilization.get(friendly, 0) + 8
                )
                event = self.emit(
                    "belief_spread",
                    [religion.id, civ.id, friendly],
                    None,
                    religion.history[-1:],
                    {"influence": religion.influence_by_civilization[friendly]},
                    3,
                    f"{religion.name} gained followers beyond {civ.name}.",
                )
                religion.history.append(event.id)
        if self.year % 23 == 0:
            foreign = sorted(
                civilization_id
                for civilization_id, influence in religion.influence_by_civilization.items()
                if civilization_id != civ.id and influence > 0
            )
            if foreign:
                target = foreign[0]
                religion.influence_by_civilization[target] = max(
                    0, religion.influence_by_civilization[target] - 2
                )
                event = self.emit(
                    "belief_declined",
                    [religion.id, civ.id, target],
                    None,
                    religion.history[-1:],
                    {"influence": religion.influence_by_civilization[target]},
                    2,
                    f"{religion.name} lost influence in a foreign civilization.",
                )
                religion.history.append(event.id)

    def _civilization_expansion(self, civ: Civilization, rng: Random) -> None:
        if self.year % 19 or civ.population < 180 or civ.stability < 45:
            return
        occupied = {
            settlement.region_id
            for settlement in self.settlements.values()
            if settlement.status == "active"
        }
        candidates = [
            region_id
            for region_id in sorted(self.regions)
            if region_id not in occupied
            and any(
                neighbor in civ.territory_region_ids
                for neighbor in self.regions[region_id].neighbors
            )
        ]
        if candidates:
            region_id = candidates[rng.randrange(len(candidates))]
            _found_settlement(
                self, civ, region_id, f"{civ.name} Outpost {self.year}", rng
            )

    def _migration(self, rng: Random) -> None:
        if self.year % 13:
            return
        for civ in sorted(self.civilizations.values(), key=lambda item: item.id):
            active = [
                self.settlements[settlement_id]
                for settlement_id in civ.settlement_ids
                if self.settlements[settlement_id].status == "active"
            ]
            if not active or civ.population < 20:
                continue
            source = min(active, key=lambda settlement: settlement.resources)
            targets = [
                settlement
                for settlement in self.settlements.values()
                if settlement.status == "active" and settlement.id != source.id
            ]
            if not targets:
                continue
            target = max(
                targets,
                key=lambda settlement: (
                    settlement.resources + self.regions[settlement.region_id].fertility
                ),
            )
            push = max(1, source.needs - source.resources // 3)
            pull = target.resources + self.regions[target.region_id].fertility
            moved = max(1, min(source.population // 10, rng.randint(1, 5) + push // 3))
            source.population -= moved
            target.population += moved
            source_cultures = set(source.culture.replace("; ", " | ").split(" | "))
            target_cultures = set(target.culture.replace("; ", " | ").split(" | "))
            if not source_cultures.issubset(target_cultures):
                target.culture = " | ".join(sorted(source_cultures | target_cultures))
            event = self.emit(
                "migration",
                [civ.id, source.id, target.id],
                target.id,
                [],
                {"moved": moved, "push": push, "pull": pull, "culture": target.culture},
                2,
                f"People migrated from {source.name} toward {target.name} under resource pressure.",
            )
            religion = self.religions[civ.religion_id]
            destination_civ = self.civilizations[target.civilization_id]
            religion.influence_by_civilization[destination_civ.id] = max(
                religion.influence_by_civilization.get(destination_civ.id, 0), moved
            )
            religion.history.append(event.id)

    def intervene(self, kind: str, target_id: str, magnitude: int = 10) -> Event:
        if target_id not in self.settlements and target_id not in self.civilizations:
            raise ValidationError(
                "intervention target must be a settlement or civilization"
            )
        target = self.settlements.get(target_id) or self.civilizations[target_id]
        interpretations: dict[str, str] = {}
        if kind == "create_resource":
            if not isinstance(target, Settlement):
                raise ValidationError("create_resource requires a settlement")
            target.resources += magnitude
            effect, truth = (
                {"resources": magnitude},
                "A resource was created by divine action.",
            )
        elif kind == "bless":
            if not isinstance(target, Civilization):
                raise ValidationError("bless requires a civilization")
            target.stability = min(100, target.stability + magnitude)
            effect, truth = (
                {"stability": magnitude},
                "A civilization received a divine blessing.",
            )
        elif kind == "curse":
            if not isinstance(target, Civilization):
                raise ValidationError("curse requires a civilization")
            target.stability = max(0, target.stability - magnitude)
            effect, truth = (
                {"stability": -magnitude},
                "A civilization received a divine curse.",
            )
        elif kind == "natural_disaster":
            if not isinstance(target, Settlement):
                raise ValidationError("natural_disaster requires a settlement")
            loss = min(target.population, magnitude)
            target.population -= loss
            effect, truth = (
                {"population_delta": -loss},
                "A divinely triggered disaster struck the settlement.",
            )
        elif kind == "miracle":
            if not isinstance(target, Settlement):
                raise ValidationError("miracle requires a settlement")
            target.population += magnitude
            effect, truth = (
                {"population_delta": magnitude},
                "A divine miracle improved survival in the settlement.",
            )
        else:
            raise ValidationError("unknown intervention")
        civ_id = target.civilization_id if isinstance(target, Settlement) else target.id
        religion = self.civilizations[civ_id].religion_id
        interpretations[civ_id] = (
            "Priests described the event as a sign of favor or judgment."
        )
        for other in sorted(self.civilizations):
            if other != civ_id:
                interpretations[other] = "Foreign observers disputed the event's cause."
        return self.emit(
            kind,
            [civ_id, religion, target_id],
            target_id if isinstance(target, Settlement) else None,
            [],
            effect,
            6,
            truth,
            interpretations,
        )

    def branch(self, branch_point_event_id: str, branch_id: str) -> World:
        event = next(
            (item for item in self.events if item.id == branch_point_event_id), None
        )
        if event is None:
            raise NotFoundError(branch_point_event_id)
        clone = World.from_dict(self.to_dict())
        clone.id = branch_id
        clone.timeline = Timeline(
            f"timeline-{branch_id}",
            f"Alternate {branch_id}",
            self.timeline.id,
            event.id,
            event.year,
        )
        clone.events = [item for item in clone.events if item.year <= event.year]
        clone.year = event.year
        return clone

    def chronicle(
        self, event_type: str | None = None, participant: str | None = None
    ) -> list[str]:
        rows = []
        for event in self.events:
            if event_type and event.type != event_type:
                continue
            if participant and participant not in event.participants:
                continue
            rows.append(
                f"Year {event.year}: {event.type.replace('_', ' ')} — {event.truth}"
            )
        return rows

    def compare(self, other: World) -> dict[str, str]:
        prime = {
            (event.year, event.type, tuple(event.participants)): event
            for event in self.events
        }
        alternate = {
            (event.year, event.type, tuple(event.participants)): event
            for event in other.events
        }
        common = set(prime) & set(alternate)
        result = {
            "unchanged": str(len(common)),
            "altered": "0",
            "prevented": "0",
            "new": "0",
            "displaced": "0",
        }
        unmatched_prime, unmatched_alternate = (
            set(prime) - common,
            set(alternate) - common,
        )
        # Same event identity/type but different effect is altered; same identity/type at a
        # different date is displaced.  Remaining unmatched records are prevented or new.
        for key in list(unmatched_prime):
            original = prime[key]
            same = next(
                (
                    candidate
                    for candidate_key, candidate in (
                        (k, alternate[k]) for k in unmatched_alternate
                    )
                    if candidate.type == original.type
                    and set(candidate.participants) == set(original.participants)
                ),
                None,
            )
            if same is None:
                continue
            unmatched_prime.remove(key)
            matched_key = next(k for k in unmatched_alternate if alternate[k] is same)
            unmatched_alternate.remove(matched_key)
            category = "displaced" if same.year != original.year else "altered"
            result[category] = str(int(result[category]) + 1)
        result["prevented"], result["new"] = (
            str(len(unmatched_prime)),
            str(len(unmatched_alternate)),
        )
        return result

    def _invariants(self) -> None:
        for civ in self.civilizations.values():
            if civ.population < 0 or civ.stability < 0 or civ.stability > 100:
                raise ValidationError("invalid civilization state")
        for settlement in self.settlements.values():
            if (
                settlement.population < 0
                or settlement.resources < 0
                or settlement.needs < 0
                or settlement.status not in {"active", "ruins"}
            ):
                raise ValidationError("invalid settlement state")

    def validate_generation(self) -> None:
        """Validate that generated state can support persistent simulation."""
        if len(self.regions) < 3:
            raise ValidationError("world requires at least three regions")
        if not self.civilizations:
            raise ValidationError("world requires at least one civilization")
        for region in self.regions.values():
            if not region.neighbors or any(
                neighbor not in self.regions or neighbor == region.id
                for neighbor in region.neighbors
            ):
                raise ValidationError("invalid regional geography")
        for resource in self.resources.values():
            if resource.region_id not in self.regions or resource.amount < 0:
                raise ValidationError("invalid resource distribution")
        for civ in self.civilizations.values():
            if (
                civ.leader_id not in self.people
                or civ.religion_id not in self.religions
                or not civ.settlement_ids
                or any(
                    settlement_id not in self.settlements
                    for settlement_id in civ.settlement_ids
                )
                or any(
                    region_id not in self.regions
                    for region_id in civ.territory_region_ids
                )
                or civ.status not in {"active", "collapsed"}
            ):
                raise ValidationError("invalid civilization placement")
        for settlement in self.settlements.values():
            if (
                settlement.civilization_id not in self.civilizations
                or settlement.region_id not in self.regions
            ):
                raise ValidationError("invalid settlement ownership")
        for person in self.people.values():
            if person.civilization_id not in self.civilizations or any(
                relation not in self.people for relation in person.relationships
            ):
                raise ValidationError("invalid historical figure")
        for religion in self.religions.values():
            if religion.civilization_id not in self.civilizations or any(
                civilization_id not in self.civilizations
                for civilization_id in religion.influence_by_civilization
            ):
                raise ValidationError("invalid belief system")
        for relation in self.relationships.values():
            if (
                relation.source_id not in self.civilizations
                or relation.target_id not in self.civilizations
                or relation.source_id == relation.target_id
                or not -100 <= relation.score <= 100
            ):
                raise ValidationError("invalid diplomacy")
        known_ids = {
            *self.civilizations,
            *self.settlements,
            *self.people,
            *self.religions,
        }
        for event in self.events:
            if (
                event.schema_version != EVENT_SCHEMA_VERSION
                or not set(event.participants).issubset(known_ids)
                or event.location_id is not None
                and event.location_id not in self.settlements
            ):
                raise ValidationError("invalid historical event")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SAVE_VERSION,
            "id": self.id,
            "seed": self.seed,
            "name": self.name,
            "year": self.year,
            "timeline": asdict(self.timeline),
            "next": self._next,
            "regions": {k: asdict(v) for k, v in self.regions.items()},
            "settlements": {k: asdict(v) for k, v in self.settlements.items()},
            "people": {k: asdict(v) for k, v in self.people.items()},
            "civilizations": {k: asdict(v) for k, v in self.civilizations.items()},
            "resources": {k: asdict(v) for k, v in self.resources.items()},
            "relationships": {k: asdict(v) for k, v in self.relationships.items()},
            "religions": {k: asdict(v) for k, v in self.religions.items()},
            "events": [asdict(v) for v in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> World:
        data = migrate_world(data)
        world = cls(data["id"], data["seed"], data["name"])
        world.year, world.timeline, world._next = (
            data["year"],
            Timeline(**data["timeline"]),
            data["next"],
        )
        for attr, typ in (
            ("regions", Region),
            ("settlements", Settlement),
            ("people", Person),
            ("civilizations", Civilization),
            ("resources", Resource),
            ("relationships", Relationship),
            ("religions", Religion),
        ):
            setattr(
                world, attr, {key: typ(**value) for key, value in data[attr].items()}
            )
        world.events = [Event(**event) for event in data["events"]]
        world.validate_generation()
        return world


def migrate_world(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade supported persistent worlds without changing their history."""
    version = data.get("version")
    if version == SAVE_VERSION:
        return data
    if version not in {1, 2}:
        raise ValidationError("unsupported save version")
    migrated = deepcopy(data)
    region_ids = sorted(migrated["regions"])
    for index, region_id in enumerate(region_ids):
        region = migrated["regions"][region_id]
        region.setdefault("terrain", "plains")
        region.setdefault("climate", "temperate")
        region.setdefault(
            "neighbors",
            [
                region_ids[(index - 1) % len(region_ids)],
                region_ids[(index + 1) % len(region_ids)],
            ]
            if len(region_ids) > 1
            else [],
        )
    for settlement in migrated["settlements"].values():
        settlement.setdefault("culture", "local")
        settlement.setdefault("status", "active")
        settlement.setdefault("founded_year", 0)
        settlement.setdefault("ruin_year", None)
        settlement.setdefault("needs", 0)
    for person in migrated["people"].values():
        person.setdefault("birth_year", 0)
        person.setdefault("death_year", None)
        person.setdefault("relationships", [])
        person.setdefault("reputation", 0)
        person.setdefault("significance", 1)
        person.setdefault("legacy", "")
    for civilization in migrated["civilizations"].values():
        civilization.setdefault("territory_region_ids", [])
        civilization.setdefault("culture", "local")
        civilization.setdefault("status", "active")
    for relationship in migrated["relationships"].values():
        relationship.setdefault("status", "neutral")
        relationship.setdefault("history", [])
    for religion in migrated["religions"].values():
        religion.setdefault("institution", "shrine network")
        religion.setdefault(
            "influence_by_civilization", {religion["civilization_id"]: 100}
        )
        religion.setdefault("history", [])
    settlements_by_region: dict[str, list[str]] = {}
    for settlement_id, settlement in migrated["settlements"].items():
        settlements_by_region.setdefault(settlement["region_id"], []).append(
            settlement_id
        )
    for event in migrated["events"]:
        event.setdefault("schema_version", EVENT_SCHEMA_VERSION)
        if event.get("location_id") in migrated["regions"]:
            participant_settlement = next(
                (
                    participant
                    for participant in event.get("participants", [])
                    if participant in migrated["settlements"]
                ),
                None,
            )
            event["location_id"] = participant_settlement or next(
                iter(settlements_by_region[event["location_id"]]), None
            )
    migrated["version"] = SAVE_VERSION
    return migrated


def generate_world(
    seed: int,
    name: str = "Eryndor",
    region_count: int = 6,
    civilization_count: int = 3,
) -> World:
    """Generate a deterministic, validated persistent world from explicit settings."""
    if region_count < 3 or civilization_count < 1 or civilization_count > region_count:
        raise ValidationError(
            "generation requires 3+ regions and 1..region_count civilizations"
        )
    rng = Random(f"generation:{seed}")
    world = World(f"world-{name.lower().replace(' ', '-') or 'unnamed'}", seed, name)
    terrain = ("coast", "plains", "forest", "hills", "riverland", "highland")
    climate = ("temperate", "cool", "dry", "wet")
    region_names = (
        "Ash Coast",
        "Green March",
        "Iron Vale",
        "Dawn Steppe",
        "Moss Reach",
        "Sunward Basin",
    )
    for index in range(region_count):
        region = Region(
            world.entity_id("region"),
            region_names[index % len(region_names)],
            rng.randint(40, 90),
            terrain[index % len(terrain)],
            climate[rng.randrange(len(climate))],
        )
        world.regions[region.id] = region
    region_ids = sorted(world.regions)
    for index, region_id in enumerate(region_ids):
        region = world.regions[region_id]
        region.neighbors = [
            region_ids[(index - 1) % len(region_ids)],
            region_ids[(index + 1) % len(region_ids)],
        ]
        resource = Resource(
            world.entity_id("resource"),
            ("grain", "timber", "ore", "fish")[index % 4],
            region_id,
            rng.randint(70, 150),
        )
        world.resources[resource.id] = resource
    civ_names = ("Velar", "Ordan", "Tes", "Mira", "Keth", "Soren")
    for index in range(civilization_count):
        civ_name = civ_names[index % len(civ_names)]
        civ_id = world.entity_id("civilization")
        region_id = region_ids[index]
        culture = f"{civ_name.lower()} tradition"
        leader = Person(
            world.entity_id("person"),
            f"{civ_name} Founder",
            civ_id,
            role="founder-ruler",
            reputation=12,
            significance=7,
            legacy="Founded a durable settlement.",
        )
        religion = Religion(
            world.entity_id("religion"),
            f"{civ_name} Tradition",
            civ_id,
            "ancestral memory",
            institution="council of keepers",
            influence_by_civilization={civ_id: 100},
        )
        settlement = Settlement(
            world.entity_id("settlement"),
            f"{civ_name} Hold",
            civ_id,
            region_id,
            rng.randint(90, 150),
            rng.randint(50, 80),
            culture=culture,
            needs=20,
        )
        civilization = Civilization(
            civ_id,
            civ_name,
            settlement.population,
            leader.id,
            [settlement.id],
            religion.id,
            rng.randint(55, 75),
            [region_id],
            culture,
        )
        world.people[leader.id] = leader
        world.religions[religion.id] = religion
        world.settlements[settlement.id] = settlement
        world.civilizations[civ_id] = civilization
        world.emit(
            "settlement_founded",
            [civ_id, settlement.id, leader.id],
            settlement.id,
            [],
            {"population": settlement.population, "culture": culture},
            5,
            f"{civ_name} founded {settlement.name} in {world.regions[region_id].name}.",
        )
    # A second starting settlement supplies a reliable migration route and an early
    # example of settlement-level political ownership.
    if civilization_count < region_count:
        first = world.civilizations["civilization-0001"]
        extra_region = region_ids[civilization_count]
        _found_settlement(world, first, extra_region, "Velar Crossing", rng)
    ids = sorted(world.civilizations)
    for source, target in zip(ids, ids[1:] + ids[:1]):
        relation = Relationship(
            world.entity_id("relationship"), source, target, rng.randint(-45, 35)
        )
        world.relationships[relation.id] = relation
    world._invariants()
    return world


def create_demo_world(seed: int = 42) -> World:
    """Backward-compatible default generation entry point used by the UI/tests."""
    return generate_world(seed)


def _found_settlement(
    world: World, civ: Civilization, region_id: str, name: str, rng: Random
) -> Settlement:
    settlement = Settlement(
        world.entity_id("settlement"),
        name,
        civ.id,
        region_id,
        rng.randint(55, 95),
        rng.randint(35, 65),
        culture=civ.culture,
        founded_year=world.year,
        needs=18,
    )
    world.settlements[settlement.id] = settlement
    civ.settlement_ids.append(settlement.id)
    civ.population += settlement.population
    if region_id not in civ.territory_region_ids:
        civ.territory_region_ids.append(region_id)
    world.emit(
        "settlement_founded",
        [civ.id, settlement.id],
        settlement.id,
        [],
        {"population": settlement.population, "territory": region_id},
        4,
        f"{civ.name} founded {settlement.name} as its territory expanded.",
    )
    return settlement
