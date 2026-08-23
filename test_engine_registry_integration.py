import unittest
from pathlib import Path

from damage_allocation_engine import load_rules as load_buff
from healing_mitigation_engine import load as load_mitigation
from job_analysis_engine import load_rules as load_job
from job_boss_analysis_engine import load as load_encounter

ROOT = Path(__file__).parent

class EngineRegistryIntegrationTests(unittest.TestCase):
    def test_existing_files_through_engine_loaders(self):
        cases = [
            (load_buff, "allocation_rules.example.json", "buffs"),
            (load_mitigation, "mitigation_rules.example.json", "mitigations"),
            (load_job, "job_rules.example.json", "jobs"),
            (load_encounter, "boss_rules.example.json", "encounters"),
        ]

        for loader, filename, key in cases:
            with self.subTest(filename=filename):
                data = loader(ROOT / filename)
                self.assertTrue(data["version"])
                self.assertIsInstance(data[key], dict)
                self.assertTrue(data[key])

    def test_default_rules_remain_available(self):
        for loader in (
            load_buff,
            load_mitigation,
            load_job,
            load_encounter,
        ):
            with self.subTest(loader=loader.__module__):
                data = loader(None)
                self.assertTrue(data["version"])

if __name__ == "__main__":
    unittest.main()
