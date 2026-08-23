from __future__ import annotations

import time
import unittest
from random import Random

from worldsmith.errors import ValidationError
from worldsmith.simulation import create_demo_world, generate_world


class WorldSimulationTests(unittest.TestCase):
    def test_generation_is_seeded_geographic_and_validated(self) -> None:
        first = generate_world(2026, "Aster", region_count=7, civilization_count=4)
        second = generate_world(2026, "Aster", region_count=7, civilization_count=4)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(len(first.regions), 7)
        self.assertEqual(len(first.civilizations), 4)
        self.assertTrue(all(region.neighbors for region in first.regions.values()))
        self.assertTrue(
            all(resource.amount > 0 for resource in first.resources.values())
        )
        self.assertTrue(all(civ.population > 0 for civ in first.civilizations.values()))
        first.validate_generation()
        with self.assertRaises(ValidationError):
            generate_world(1, region_count=2)

        broken = generate_world(2)
        broken.regions[min(broken.regions)].neighbors = ["missing-region"]
        with self.assertRaises(ValidationError):
            broken.validate_generation()

    def test_generation_meets_core_production_budget(self) -> None:
        start = time.perf_counter()
        for seed in range(100):
            generate_world(seed, region_count=12, civilization_count=6)
        self.assertLess(time.perf_counter() - start, 1.0)

    def test_civilization_expands_declines_and_preserves_collapse_history(self) -> None:
        world = create_demo_world(23)
        civ = world.civilizations[min(world.civilizations)]
        civ.population, civ.stability = 260, 80
        for settlement_id in civ.settlement_ids:
            world.settlements[settlement_id].population = 260
        world.year = 18
        world._civilization_expansion(civ, Random("expansion"))
        self.assertGreaterEqual(len(civ.settlement_ids), 2)
        self.assertTrue(
            any(event.type == "settlement_founded" for event in world.events)
        )

        for settlement_id in civ.settlement_ids:
            settlement = world.settlements[settlement_id]
            settlement.population = 0
            settlement.status = "ruins"
        civ.population = 0
        world.advance(1)
        self.assertEqual(civ.status, "collapsed")
        self.assertTrue(
            any(event.type == "civilization_collapse" for event in world.events)
        )

    def test_settlement_lifecycle_keeps_ruins_and_history(self) -> None:
        world = create_demo_world(24)
        settlement = world.settlements[min(world.settlements)]
        event = world.destroy_settlement(settlement.id, "flood")

        self.assertEqual(event.type, "settlement_destroyed")
        self.assertEqual(settlement.status, "ruins")
        self.assertEqual(settlement.ruin_year, world.year)
        self.assertEqual(settlement.population, 0)
        self.assertIn(
            settlement.id,
            world.civilizations[settlement.civilization_id].settlement_ids,
        )

    def test_historical_figures_have_lifecycle_and_legacy(self) -> None:
        world = create_demo_world(25)
        founder = world.people[min(world.people)]
        action = world.record_figure_action(founder.id, "brokered a river compact", 6)
        world.advance(97)

        self.assertEqual(action.type, "historical_figure_action")
        self.assertEqual(founder.legacy, "brokered a river compact")
        self.assertGreaterEqual(founder.reputation, 18)
        self.assertFalse(founder.alive)
        self.assertIsNotNone(founder.death_year)
        self.assertTrue(any(person.relationships for person in world.people.values()))
        self.assertTrue(any(event.type == "ruler_death" for event in world.events))

    def test_diplomacy_and_conflict_record_consequences(self) -> None:
        world = create_demo_world(26)
        relation = next(iter(world.relationships.values()))
        negotiation = world.negotiate(relation.source_id, relation.target_id, "trade")
        relation.score = 80
        world.advance(1)
        self.assertEqual(negotiation.type, "diplomatic_negotiation")
        self.assertIn(negotiation.id, relation.history)
        self.assertIn(relation.status, {"friendly", "allied"})

        relation.score, world.year = -99, 22
        world.advance(1)
        wars = [event for event in world.events if event.type == "war_concluded"]
        self.assertTrue(wars)
        effects = wars[-1].effects
        self.assertIn("population_losses", effects)
        self.assertIn("loser_stability", effects)
        self.assertIn("winner", effects)

    def test_belief_and_migration_record_cultural_consequences(self) -> None:
        world = create_demo_world(27)
        relation = next(iter(world.relationships.values()))
        relation.score = 40
        world.advance(17)
        religion = world.religions[world.civilizations[relation.source_id].religion_id]
        self.assertGreater(
            religion.influence_by_civilization.get(relation.target_id, 0), 0
        )
        self.assertTrue(any(event.type == "belief_spread" for event in world.events))

        world.advance(9)
        migration = [event for event in world.events if event.type == "migration"][-1]
        self.assertIn("push", migration.effects)
        self.assertIn("pull", migration.effects)
        self.assertIn("culture", migration.effects)
        migrating_civ = world.civilizations[migration.participants[0]]
        migrating_religion = world.religions[migrating_civ.religion_id]
        self.assertIn(migration.id, migrating_religion.history)
        self.assertTrue(any(event.type == "belief_declined" for event in world.events))


if __name__ == "__main__":
    unittest.main()
