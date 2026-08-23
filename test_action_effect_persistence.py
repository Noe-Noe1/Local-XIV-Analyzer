import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from act_compat_importer import import_log


class ActionEffectPersistenceTests(unittest.TestCase):
    def test_unknown_raw_effect_is_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "network.log"
            db_path = root / "test.sqlite3"

            lines = [
                "01|2026-01-01T00:00:00+00:00|100|Test Zone",
                "21|2026-01-01T00:00:01+00:00|10000001|Player|100|Action|40000001|Enemy|00000064|ABCDEF12",
            ]
            log_path.write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )

            result = import_log(log_path, db_path)

            with closing(sqlite3.connect(db_path)) as db:
                rows = db.execute(
                    "select event_type,ability_id,reason,"
                    "raw_effects_json "
                    "from unknown_action_effects"
                ).fetchall()

            self.assertEqual(result["encounters"], 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "damage")
            self.assertTrue(rows[0][1])
            self.assertIn("no_supported_explicit_effect_fields", rows[0][2])
            self.assertIn("raw_effects", rows[0][3])


if __name__ == "__main__":
    unittest.main()
