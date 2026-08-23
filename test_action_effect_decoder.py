import unittest

from action_effect_decoder import (
    decode_event,
    serialize_unknown,
    unknown_record,
)


class ActionEffectDecoderTests(unittest.TestCase):
    def test_explicit_fields_are_normalized(self):
        decoded = decode_event({
            "critical": True,
            "isDirectHit": 1,
            "absorbed": "125",
        })
        self.assertTrue(decoded.critical)
        self.assertTrue(decoded.direct_hit)
        self.assertEqual(decoded.absorbed, 125.0)
        self.assertEqual(decoded.source, "explicit_fields")
        self.assertEqual(decoded.confidence, "high")

    def test_unknown_raw_effect_is_preserved(self):
        event = {
            "type": "damage",
            "abilityGameID": 100,
            "rawEffects": ["AA", "BB"],
        }
        record = unknown_record(event)
        self.assertEqual(record["ability_id"], "100")
        self.assertEqual(record["raw_effects"], ["AA", "BB"])
        self.assertIn("raw_effects", serialize_unknown(record))

    def test_known_event_is_not_collected_as_unknown(self):
        event = {"type": "damage", "critical": False}
        self.assertIsNone(unknown_record(event))

    def test_input_must_be_dictionary(self):
        with self.assertRaises(TypeError):
            decode_event([])


if __name__ == "__main__":
    unittest.main()
