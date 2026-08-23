import json
import tempfile
import unittest
from pathlib import Path

from rule_registry import RegistryError, RuleRegistry, load_registry

class RuleRegistryTests(unittest.TestCase):
    def write_registry(self, directory, data):
        path = Path(directory) / "rules.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_load_buff_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_registry(
                directory,
                {
                    "version": "buff-test-1",
                    "buffs": {
                        "100": {
                            "kind": "damage_percent",
                            "value": 0.1,
                        }
                    },
                },
            )
            registry = load_registry("buff", path)
            self.assertEqual(registry.version, "buff-test-1")
            self.assertTrue(registry.contains(100))
            self.assertEqual(registry.require("100")["value"], 0.1)

    def test_load_job_registry_with_patch(self):
        registry = RuleRegistry(
            "job",
            {
                "version": "job-test-1",
                "patch": "7.x",
                "jobs": {"NIN": {"role": "melee"}},
            },
        )
        self.assertEqual(registry.patch, "7.x")
        self.assertEqual(registry.get("NIN")["role"], "melee")

    def test_missing_version_is_rejected(self):
        with self.assertRaises(RegistryError):
            RuleRegistry("mitigation", {"mitigations": {}})

    def test_wrong_collection_type_is_rejected(self):
        with self.assertRaises(RegistryError):
            RuleRegistry(
                "encounter",
                {"version": "x", "encounters": []},
            )

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(RegistryError):
            RuleRegistry("unknown", {"version": "x"})

    def test_export_is_isolated_copy(self):
        registry = RuleRegistry(
            "alias",
            {
                "version": "alias-test-1",
                "aliases": {"foo": "bar"},
            },
        )
        exported = registry.as_dict()
        exported["aliases"]["foo"] = "changed"
        self.assertEqual(registry.get("foo"), "bar")

if __name__ == "__main__":
    unittest.main()
