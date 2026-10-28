import unittest

from astra_ingestion.reconcile import compare_records


def row(symbol="AAPL", timestamp="2025-09-02T13:30:00Z", close="100"):
    return {"symbol": symbol, "timestamp": timestamp, "close": close}


class ReconcileTests(unittest.TestCase):
    def test_exact_readback_is_order_independent(self):
        expected = [row(), row("MSFT")]
        result = compare_records(expected, list(reversed(expected)))
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["expected_hash"], result["actual_hash"])

    def test_missing_changed_and_extra_are_separate(self):
        expected = [row(), row("MSFT")]
        actual = [row(close="101"), row("NVDA")]
        result = compare_records(expected, actual)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((result["missing_count"], result["changed_count"], result["unexpected_count"]), (1, 1, 1))

    def test_equal_row_counts_do_not_establish_correctness(self):
        result = compare_records([row()], [row(close="100.0")])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["changed_count"], 1)

    def test_duplicate_target_keys_fail(self):
        result = compare_records([row()], [row(), row()])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["actual_duplicate_count"], 1)

    def test_samples_are_bounded_but_all_failures_are_counted(self):
        expected = [row(f"SYM{i}") for i in range(100)]
        result = compare_records(expected, [])
        self.assertEqual(result["missing_count"], 100)
        self.assertEqual(len(result["missing_keys"]), 20)

    def test_additional_target_fields_are_detected(self):
        actual = {**row(), "altered": True}
        self.assertEqual(compare_records([row()], [actual])["changed_count"], 1)


if __name__ == "__main__":
    unittest.main()
