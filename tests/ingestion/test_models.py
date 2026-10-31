import unittest

from astra_ingestion.models import IngestionSpec, canonical_timestamp, plan_partitions


def spec_dict(**changes):
    value = {"symbols": ["AAPL", "MSFT"], "start": "2025-09-02T13:30:00Z", "end": "2025-09-02T20:00:00Z"}
    value.update(changes)
    return value


class ModelsTests(unittest.TestCase):
    def test_scope_round_trip_is_stable_and_frozen(self):
        spec = IngestionSpec.from_dict(spec_dict())
        self.assertEqual(spec.scope_hash, IngestionSpec.from_dict(spec.to_dict()).scope_hash)
        self.assertEqual(spec.symbols, ("AAPL", "MSFT"))
        with self.assertRaises(AttributeError):
            spec.feed = "iex"

    def test_timezone_equivalence_and_scope_change(self):
        first = IngestionSpec.from_dict(spec_dict())
        equivalent = IngestionSpec.from_dict(spec_dict(start="2025-09-02T09:30:00-04:00"))
        changed = IngestionSpec.from_dict(spec_dict(symbols=["AAPL"]))
        self.assertEqual(first.scope_hash, equivalent.scope_hash)
        self.assertNotEqual(first.scope_hash, changed.scope_hash)

    def test_every_symbol_and_interval_is_preserved(self):
        spec = IngestionSpec.from_dict(spec_dict(end="2025-09-04T20:00:00Z"))
        partitions = plan_partitions(spec)
        self.assertEqual(len(partitions), 6)
        for symbol in spec.symbols:
            rows = [p for p in partitions if p["symbol"] == symbol]
            self.assertEqual(rows[0]["start"], spec.to_dict()["start"])
            self.assertEqual(rows[-1]["end"], spec.to_dict()["end"])
            for before, after in zip(rows, rows[1:]):
                self.assertEqual(before["end"], after["start"])

    def test_invalid_scope_is_rejected_without_silent_filtering(self):
        cases = [
            {"symbols": []}, {"symbols": ["AAPL", "AAPL"]}, {"symbols": ["aapl"]},
            {"symbols": ["AAPL", "BAD/SYMBOL"]}, {"symbols": "AAPL"},
            {"feed": "iex"}, {"adjustment": "all"}, {"timeframe": "1Day"}, {"timeframe": []},
            {"start": "2025-09-02T13:30:00"}, {"start": "2025-08-31T23:59:59Z"},
            {"end": "2026-08-01T00:00:01Z"}, {"end": "2025-09-12T20:00:00Z"},
            {"max_requests": True}, {"max_requests": 201}, {"max_records": 0},
            {"deadline_seconds": 7201}, {"invented_option": True},
        ]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                IngestionSpec.from_dict(spec_dict(**values))

    def test_submicrosecond_precision_is_not_silently_lost(self):
        self.assertEqual(canonical_timestamp("2025-09-02T13:30:00.000000000Z"), "2025-09-02T13:30:00Z")
        with self.assertRaises(ValueError):
            canonical_timestamp("2025-09-02T13:30:00.000000001Z")


if __name__ == "__main__":
    unittest.main()
