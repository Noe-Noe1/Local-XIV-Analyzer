from pathlib import Path
import unittest

from rule_registry import load_registry

ROOT = Path(__file__).parent

class RegistryCompatibilityTests(unittest.TestCase):
    def test_all_existing_rule_files(self):
        cases = [
            ("buff", "allocation_rules.example.json", "1822"),
            ("mitigation", "mitigation_rules.example.json", "100"),
            ("job", "job_rules.example.json", "NIN"),
            ("encounter", "boss_rules.example.json", "99"),
        ]

        for kind, filename, identifier in cases:
            with self.subTest(kind=kind):
                registry = load_registry(kind, ROOT / filename)
                self.assertTrue(registry.version)
                self.assertTrue(registry.contains(identifier))
                self.assertIsInstance(
                    registry.require(identifier),
                    dict,
                )

if __name__ == "__main__":
    unittest.main()
