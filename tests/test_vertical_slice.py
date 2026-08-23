from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from worldsmith.benchmark import run_benchmark
from worldsmith.cli import TerminalUI
from worldsmith.persistence import SaveError, load_session, save_session
from worldsmith.session import WorldSession


class VerticalSliceTests(unittest.TestCase):
    def test_creation_records_settings_and_validates_generated_state(self) -> None:
        session = WorldSession.create("Aster", 1234, "lush")

        session.validate()

        self.assertEqual(session.settings.seed, 1234)
        self.assertEqual(session.settings.region_style, "lush")
        self.assertEqual(len(session.active.regions), 3)
        self.assertEqual(len(session.active.civilizations), 3)

    def test_end_to_end_branch_save_load_and_prime_comparison(self) -> None:
        session = WorldSession.create("Aster", 1234)
        prime = session.active
        prime.advance(30)
        event_id = prime.events[-1].id

        branch = session.branch(event_id, "rainy-future")
        branch.intervene("miracle", min(branch.settlements), 20)
        branch.advance(10)
        branch_snapshot = branch.to_dict()
        session.select_timeline("timeline-prime")

        self.assertEqual(session.active.year, 30)
        self.assertNotEqual(session.active.to_dict(), branch_snapshot)
        self.assertGreater(
            int(prime.compare(session.timelines["timeline-rainy-future"])["new"]), 0
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aster.worldsmith.json"
            save_session(session, path)
            loaded = load_session(path)
            self.assertEqual(set(loaded.timelines), set(session.timelines))
            self.assertEqual(
                loaded.timelines["timeline-rainy-future"].timeline.parent_timeline_id,
                "timeline-prime",
            )
            self.assertEqual(loaded.to_dict(), session.to_dict())

            save_session(session, path)
            path.write_text("corrupted", encoding="utf-8")
            with self.assertRaises(SaveError):
                load_session(path)
            self.assertTrue(path.with_suffix(path.suffix + ".bak").exists())
            recovered = load_session(path.with_suffix(path.suffix + ".bak"))
            self.assertEqual(set(recovered.timelines), set(session.timelines))

    def test_chronicle_exposes_links_and_filtering(self) -> None:
        session = WorldSession.create("Aster", 1234)
        world = session.active
        world.advance(13)
        migration = [event for event in world.events if event.type == "migration"]

        self.assertTrue(migration)
        self.assertTrue(world.chronicle(event_type="migration"))
        event = migration[0]
        self.assertTrue(event.participants)
        self.assertIsNotNone(event.location_id)
        self.assertIsInstance(event.causes, list)
        self.assertIsInstance(event.effects, dict)

    def test_keyboard_ui_exposes_all_representative_screens_and_errors(self) -> None:
        lines: list[str] = []
        ui = TerminalUI(lines.append)
        ui.dispatch("help")
        ui.dispatch("new Aster 1234 lush")
        ui.dispatch("dashboard")
        ui.dispatch("advance 10")
        world = ui.session.active
        ui.dispatch(f"civ {min(world.civilizations)}")
        ui.dispatch(f"settlement {min(world.settlements)}")
        ui.dispatch(f"person {min(world.people)}")
        ui.dispatch("chronicle")
        event_id = world.events[-1].id
        ui.dispatch(f"branch {event_id} alternate")
        ui.dispatch(f"power miracle {min(ui.session.active.settlements)} 15")
        ui.dispatch("advance 10")
        ui.dispatch("timelines")
        ui.dispatch("compare")
        ui.dispatch("timeline timeline-prime")
        ui.dispatch("settings 3")
        ui.dispatch("power bless missing")

        transcript = "\n".join(lines)
        for heading in (
            "MAIN MENU",
            "WORLD CREATION",
            "WORLD DASHBOARD",
            "TIMELINE CONTROL",
            "CIVILIZATION INSPECTION",
            "SETTLEMENT INSPECTION",
            "HISTORICAL FIGURE INSPECTION",
            "CHRONICLE",
            "GOD POWERS",
            "TIMELINE BROWSER",
            "TIMELINE COMPARISON",
            "SETTINGS",
        ):
            self.assertIn(heading, transcript)
        self.assertIn("[FOCUS: command prompt]", transcript)
        self.assertIn("never colour alone", transcript)
        self.assertIn("Safe next step", transcript)

    def test_target_slice_operations_meet_preliminary_budget(self) -> None:
        session = WorldSession.create("Aster", 1234)
        start = time.perf_counter()
        session.active.advance(100)
        elapsed = time.perf_counter() - start

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            start = time.perf_counter()
            save_session(session, path)
            save_elapsed = time.perf_counter() - start
            start = time.perf_counter()
            load_session(path)
            load_elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 2.0)
        self.assertLess(save_elapsed, 0.25)
        self.assertLess(load_elapsed, 0.25)

    def test_benchmark_reports_every_gate_e_timing(self) -> None:
        report = run_benchmark()

        self.assertEqual(
            set(report["milliseconds"]),
            {
                "world_generation",
                "advance_1_year",
                "advance_10_years",
                "advance_100_years",
                "timeline_branch",
                "save",
                "load",
            },
        )
        self.assertTrue(all(value >= 0 for value in report["milliseconds"].values()))


if __name__ == "__main__":
    unittest.main()
