"""Keyboard-first terminal interface for the representative Worldsmith slice."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Iterable
from pathlib import Path

from .persistence import SaveError, load_session, save_session
from .session import WorldSession


class TerminalUI:
    """Small, dependency-free UI that deliberately uses text instead of colour."""

    def __init__(self, write: Callable[[str], None] = print) -> None:
        self.write = write
        self.session: WorldSession | None = None
        self.text_scale = 1
        self.reduced_motion = True

    def _heading(self, title: str) -> None:
        line = "=" * max(18, len(title) + 8)
        self.write(f"\n{line}\n{title.upper()}\n{line}")

    def _world(self):
        if self.session is None:
            raise ValueError("Create or load a world first. Type 'new <name> <seed>'.")
        return self.session.active

    def show_menu(self) -> None:
        self._heading("Main Menu")
        self.write(
            "[FOCUS: command prompt] Text-first controls; no colour is required."
        )
        self.write("World creation: new <name> <seed> [temperate|harsh|lush]")
        self.write("World dashboard: dashboard | Time: advance <years>")
        self.write(
            "Inspect: civ <id> | settlement <id> | person <id> | chronicle [type]"
        )
        self.write(
            "God powers: power <create_resource|bless|curse|natural_disaster|miracle> <target> [amount]"
        )
        self.write(
            "Timelines: branch <event-id> <name> | timelines | timeline <id> | compare"
        )
        self.write(
            "Saves: save <file> | load <file> | Settings: settings [scale 1|2|3]"
        )
        self.write(
            "Accessibility: keyboard only; [ACTIVE]/[WARNING] status markers; reduced motion on."
        )
        self.write("Type help to repeat this menu, or quit to exit.")

    def create_world(self, name: str, seed: int, style: str = "temperate") -> None:
        if style not in {"temperate", "harsh", "lush"}:
            raise ValueError("style must be temperate, harsh, or lush")
        self.session = WorldSession.create(name, seed, style)
        self.session.validate()
        self._heading("World Creation")
        self.write(
            f"Created {name} with recorded seed {seed} and {style} region settings."
        )
        self.write(
            f"[READY] {len(self._world().regions)} regions and "
            f"{len(self._world().civilizations)} initial civilizations validate successfully."
        )

    def dashboard(self) -> None:
        world = self._world()
        self._heading("World Dashboard")
        self.write(
            f"{world.name} | seed {world.seed} | year {world.year} | "
            f"timeline {world.timeline.name} ({world.timeline.id})"
        )
        self.write(
            f"Regions {len(world.regions)} | Civilizations {len(world.civilizations)} | "
            f"Settlements {len(world.settlements)} | People {len(world.people)} | Events {len(world.events)}"
        )
        for civ in sorted(world.civilizations.values(), key=lambda item: item.id):
            self.write(
                f"[CIV] {civ.id} {civ.name}: population {civ.population}, "
                f"stability {civ.stability}, leader {civ.leader_id}"
            )

    def advance(self, years: int) -> None:
        if years not in {1, 10, 100} and years <= 0:
            raise ValueError(
                "advance a positive number of years (recommended: 1, 10, or 100)"
            )
        world = self._world()
        start_events, start_year = len(world.events), world.year
        world.advance(years)
        self._heading("Timeline Control")
        self.write(
            f"Advanced from year {start_year} to {world.year}. "
            f"[EVENTS +{len(world.events) - start_events}]"
        )

    def inspect_civilization(self, civilization_id: str) -> None:
        world = self._world()
        civ = world.civilizations[civilization_id]
        leader = world.people[civ.leader_id]
        religion = world.religions[civ.religion_id]
        self._heading("Civilization Inspection")
        self.write(
            f"{civ.id} {civ.name}: population {civ.population}; stability {civ.stability}; "
            f"leader {leader.name}; religion {religion.name} ({religion.tenet})."
        )
        self.write(f"Settlements: {', '.join(civ.settlement_ids)}")

    def inspect_settlement(self, settlement_id: str) -> None:
        world = self._world()
        settlement = world.settlements[settlement_id]
        region = world.regions[settlement.region_id]
        self._heading("Settlement Inspection")
        self.write(
            f"{settlement.id} {settlement.name}: population {settlement.population}; "
            f"resources {settlement.resources}; region {region.name} (fertility {region.fertility})."
        )

    def inspect_person(self, person_id: str) -> None:
        person = self._world().people[person_id]
        self._heading("Historical Figure Inspection")
        self.write(
            f"{person.id} {person.name}: {person.role}; civilization {person.civilization_id}; "
            f"status {'alive' if person.alive else 'recorded as deceased'}."
        )

    def show_chronicle(self, event_type: str | None = None) -> None:
        world = self._world()
        self._heading("Chronicle")
        rows = world.chronicle(event_type=event_type)
        if not rows:
            self.write("[NOTICE] No matching events.")
            return
        for event in world.events:
            if event_type and event.type != event_type:
                continue
            participants = ", ".join(event.participants)
            causes = ", ".join(event.causes) or "unknown"
            effects = (
                ", ".join(f"{key}={value}" for key, value in event.effects.items())
                or "unknown"
            )
            self.write(
                f"{event.id} | {rows.pop(0)} | participants: {participants} | "
                f"location: {event.location_id or 'unknown'} | causes: {causes} | consequences: {effects}"
            )

    def power(self, kind: str, target_id: str, magnitude: int = 10) -> None:
        event = self._world().intervene(kind, target_id, magnitude)
        self._heading("God Powers")
        self.write(
            f"[IMMEDIATE RESULT] {event.id}: {event.truth} Consequences: {event.effects}. "
            "Advance time to inspect long-term effects."
        )

    def branch(self, event_id: str, name: str) -> None:
        alternate = self.session.branch(event_id, name) if self.session else None
        self._heading("Timeline Browser")
        self.write(
            f"[ACTIVE] Created {alternate.timeline.id} from {event_id} at year {alternate.year}. "
            "Prime remains preserved; apply a different intervention and advance this timeline."
        )

    def timelines(self) -> None:
        if self.session is None:
            self._world()
        self._heading("Timeline Browser")
        for row in self.session.timeline_summaries():
            self.write(row)

    def select_timeline(self, timeline_id: str) -> None:
        if self.session is None:
            self._world()
        selected = self.session.select_timeline(timeline_id)
        self.write(f"[ACTIVE] Selected {selected.timeline.id} at year {selected.year}.")

    def compare(self) -> None:
        if self.session is None:
            self._world()
        self._heading("Timeline Comparison")
        results = self.session.compare_to_prime()
        self.write(" | ".join(f"{key}: {value}" for key, value in results.items()))
        self.write("Comparison labels: unchanged, altered, prevented, new, displaced.")

    def save(self, filename: str) -> None:
        if self.session is None:
            self._world()
        save_session(self.session, Path(filename))
        self.write(
            f"[SAVED] Prime and {len(self.session.timelines) - 1} alternate timeline(s) saved to {filename}."
        )

    def load(self, filename: str) -> None:
        self.session = load_session(Path(filename))
        self.write(
            f"[RECOVERED] Loaded {self.session.settings.name}; "
            f"{len(self.session.timelines)} retained timeline(s), active {self.session.active_timeline_id}."
        )

    def settings(self, scale: int | None = None) -> None:
        if scale is not None:
            if scale not in {1, 2, 3}:
                raise ValueError("text scale must be 1, 2, or 3")
            self.text_scale = scale
        self._heading("Settings")
        self.write(
            f"Text/interface scale: {self.text_scale}; reduced motion: {'on' if self.reduced_motion else 'off'}; "
            "status uses words and symbols, never colour alone."
        )

    def dispatch(self, command: str) -> bool:
        try:
            parts = shlex.split(command)
            if not parts:
                return True
            action, *args = parts
            if action in {"help", "menu"}:
                self.show_menu()
            elif action == "new":
                self.create_world(
                    args[0], int(args[1]), args[2] if len(args) > 2 else "temperate"
                )
            elif action == "dashboard":
                self.dashboard()
            elif action == "advance":
                self.advance(int(args[0]))
            elif action == "civ":
                self.inspect_civilization(args[0])
            elif action == "settlement":
                self.inspect_settlement(args[0])
            elif action == "person":
                self.inspect_person(args[0])
            elif action == "chronicle":
                self.show_chronicle(args[0] if args else None)
            elif action == "power":
                self.power(args[0], args[1], int(args[2]) if len(args) > 2 else 10)
            elif action == "branch":
                self.branch(args[0], args[1])
            elif action == "timelines":
                self.timelines()
            elif action == "timeline":
                self.select_timeline(args[0])
            elif action == "compare":
                self.compare()
            elif action == "save":
                self.save(args[0])
            elif action == "load":
                self.load(args[0])
            elif action == "settings":
                self.settings(int(args[0]) if args else None)
            elif action in {"quit", "exit"}:
                self.write("[EXIT] Session ended. Save a world to retain its history.")
                return False
            else:
                raise ValueError("unknown command; type help")
        except (IndexError, KeyError, SaveError, ValueError) as error:
            self.write(
                f"[ERROR] {error}. Safe next step: type help or correct the command."
            )
        return True


def run(commands: Iterable[str] | None = None) -> TerminalUI:
    """Run interactively, or execute a command iterable for a scripted walkthrough."""
    ui = TerminalUI()
    ui.show_menu()
    if commands is not None:
        for command in commands:
            if not ui.dispatch(command):
                break
        return ui
    while ui.dispatch(input("worldsmith> ")):
        pass
    return ui


if __name__ == "__main__":
    run()
