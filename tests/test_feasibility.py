from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from worldsmith.persistence import SaveError, load_world, save_world
from worldsmith.simulation import create_demo_world


class FeasibilityTests(unittest.TestCase):
    def test_seeded_clock_is_reproducible_for_500_years(self) -> None:
        first, second = create_demo_world(7), create_demo_world(7)
        first.advance(500)
        second.advance(500)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_save_load_has_no_meaningful_difference_and_backup_exists(self) -> None:
        world = create_demo_world()
        world.advance(50)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            save_world(world, path)
            save_world(world, path)
            self.assertEqual(world.to_dict(), load_world(path).to_dict())
            self.assertTrue(path.with_suffix(".json.bak").exists())

    def test_corrupt_and_version_mismatch_saves_fail_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("not-json")
            with self.assertRaises(SaveError):
                load_world(path)

    def test_intervention_has_understandable_downstream_difference(self) -> None:
        baseline, changed = create_demo_world(11), create_demo_world(11)
        baseline.advance(200)
        changed.intervene("miracle", min(changed.settlements), 30)
        changed.advance(200)
        self.assertNotEqual(baseline.to_dict(), changed.to_dict())
        self.assertTrue(any(event.type == "miracle" for event in changed.events))

    def test_belief_can_diverge_from_truth(self) -> None:
        world = create_demo_world()
        event = world.intervene("natural_disaster", min(world.settlements), 8)
        self.assertIn("divinely triggered", event.truth)
        self.assertGreater(len(set(event.interpretations.values())), 1)

    def test_branch_preserves_prime_and_progresses_independently(self) -> None:
        prime = create_demo_world()
        prime.advance(200)
        point = prime.events[-1].id
        branch = prime.branch(point, "branch-a")
        before = prime.to_dict()
        branch.intervene("bless", min(branch.civilizations), 10)
        branch.advance(40)
        self.assertEqual(before, prime.to_dict())
        self.assertNotEqual(prime.to_dict(), branch.to_dict())
        self.assertEqual(branch.timeline.parent_timeline_id, "timeline-prime")

    def test_chronicle_is_derived_and_filterable(self) -> None:
        world = create_demo_world()
        world.advance(30)
        self.assertTrue(world.chronicle())
        self.assertTrue(
            all("migration" in row for row in world.chronicle(event_type="migration"))
        )

    def test_event_ledger_has_stable_fields_and_required_event_types(self) -> None:
        world = create_demo_world()
        world.advance(100)
        world.year = 22
        next(iter(world.relationships.values())).score = -99
        world.advance(1)
        collapsed = next(iter(world.civilizations.values()))
        collapsed.population = 0
        world.advance(1)
        world.intervene("natural_disaster", min(world.settlements), 1)
        for event_type in ("migration", "famine", "religious_movement"):
            world.emit(
                event_type,
                [collapsed.id],
                None,
                [],
                {},
                2,
                f"Ledger test: {event_type}.",
            )
        kinds = {event.type for event in world.events}
        self.assertTrue(
            {
                "settlement_founded",
                "ruler_death",
                "war_declared",
                "war_concluded",
                "migration",
                "famine",
                "religious_movement",
                "civilization_collapse",
                "natural_disaster",
            }.issubset(kinds)
        )
        event = world.events[-1]
        self.assertTrue(event.id and isinstance(event.year, int) and event.participants)
        self.assertIsInstance(event.effects, dict)

    def test_500_year_run_is_preliminarily_performant(self) -> None:
        start = time.perf_counter()
        world = create_demo_world()
        world.advance(500)
        self.assertLess(time.perf_counter() - start, 3.0)
        self.assertGreater(len(world.events), 3)


if __name__ == "__main__":
    unittest.main()
