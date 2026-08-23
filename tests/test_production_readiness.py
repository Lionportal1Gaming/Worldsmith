from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from worldsmith.errors import SaveError, ValidationError
from worldsmith.persistence import load_session, save_session
from worldsmith.session import SESSION_VERSION, WorldSession


class ProductionReadinessTests(unittest.TestCase):
    def test_world_generation_regression_fixture_is_stable(self) -> None:
        session = WorldSession.create("Regression", 4242)
        session.active.advance(250)
        payload = json.dumps(session.to_dict(), sort_keys=True, separators=(",", ":"))

        self.assertEqual(len(session.active.events), 29)
        self.assertEqual(
            hashlib.sha256(payload.encode()).hexdigest(),
            "913d153981dec143e07f0f26e9f34f9da359eb7663605d2653c7913ed1a9d9cf",
        )

    def test_invariants_and_event_references_hold_in_long_run(self) -> None:
        session = WorldSession.create("Soak", 91)
        start = time.perf_counter()
        session.active.advance(10_000)
        session.validate()

        world = session.active
        known_ids = {
            *world.civilizations,
            *world.settlements,
            *world.people,
            *world.religions,
        }
        self.assertLess(time.perf_counter() - start, 5.0)
        self.assertEqual(len({event.id for event in world.events}), len(world.events))
        for event in world.events:
            self.assertTrue(set(event.participants).issubset(known_ids))
            self.assertTrue(
                event.location_id is None or event.location_id in world.settlements
            )
            self.assertIsInstance(event.effects, dict)

    def test_version_one_session_migrates_without_changing_history(self) -> None:
        original = WorldSession.create("Migration", 7)
        original.active.advance(25)
        legacy = original.to_dict()
        legacy["version"] = 1
        legacy.pop("migration_history")
        legacy["settings"].pop("civilization_count")

        with self.assertLogs("worldsmith", level="INFO") as logs:
            migrated = WorldSession.from_dict(legacy)

        self.assertEqual(migrated.to_dict()["version"], SESSION_VERSION)
        self.assertEqual(migrated.migration_history, ["1->2"])
        self.assertEqual(migrated.active.events, original.active.events)
        self.assertIn("session_migrated", "\n".join(logs.output))

    def test_unsupported_migration_and_corrupt_save_have_standard_errors(self) -> None:
        with self.assertRaises(ValidationError):
            WorldSession.from_dict({"version": 99})

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.session.json"
            path.write_text("not-json", encoding="utf-8")
            with (
                self.assertLogs("worldsmith", level="WARNING") as logs,
                self.assertRaises(SaveError),
            ):
                load_session(path)
            self.assertIn("session_load_failed", "\n".join(logs.output))

    def test_round_trip_preserves_migrated_session_and_logs_operations(self) -> None:
        session = WorldSession.create("Round Trip", 3)
        session.active.advance(40)
        branch = session.branch(session.active.events[-1].id, "alternate")
        branch.advance(20)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "round-trip.session.json"
            with self.assertLogs("worldsmith", level="INFO") as logs:
                save_session(session, path)
                loaded = load_session(path)
            self.assertEqual(loaded.to_dict(), session.to_dict())
            output = "\n".join(logs.output)
            self.assertIn("session_saved", output)
            self.assertIn("session_loaded", output)


if __name__ == "__main__":
    unittest.main()
