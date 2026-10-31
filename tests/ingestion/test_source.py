from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import io
import json
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from astra_ingestion.models import IngestionSpec, plan_partitions
from astra_ingestion.source import AlpacaSource, MAX_RESPONSE_BYTES, SourceError, parse_page, record_key


START = "2025-09-02T13:30:00Z"
END = "2025-09-02T20:00:00Z"


def bar(**changes):
    value = {"t": START, "o": 100, "h": 102, "l": 99, "c": 101, "v": 2000, "n": 20, "vw": 100.5}
    value.update(changes)
    return value


def parse(body):
    return parse_page(json.dumps(body), symbol="AAPL", start=START, end=END, timeframe="5Min")


class Response(io.BytesIO):
    def __init__(self, body, headers=None, status=200):
        super().__init__(body)
        self.headers = headers or {}
        self.status = status


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.spec = IngestionSpec.from_dict({"symbols": ["AAPL"], "start": START, "end": END})
        self.partition = plan_partitions(self.spec)[0]

    def test_source_values_are_exact_and_canonical(self):
        raw = '{"bars":{"AAPL":[{"t":"2025-09-02T09:30:00-04:00","o":100.0000,"h":102,"l":99,"c":101,"v":2000,"n":20,"vw":100.1234567890123456789012345678}]},"next_page_token":"next"}'
        page = parse_page(raw, symbol="AAPL", start=START, end=END, timeframe="5Min")
        self.assertEqual(page.records[0]["vwap"], "100.1234567890123456789012345678")
        self.assertEqual(page.records[0]["open"], "100")
        self.assertEqual(page.records[0]["trade_count"], "20")
        self.assertEqual(record_key(page.records[0]), "AAPL|" + START)
        self.assertEqual(page.next_page_token, "next")
        self.assertEqual(len(page.response_sha256), 64)

    def test_identical_duplicates_collapse_but_conflicts_fail(self):
        page = parse({"bars": {"AAPL": [bar(), bar()]}})
        self.assertEqual(len(page.records), 1)
        with self.assertRaises(SourceError):
            parse({"bars": {"AAPL": [bar(), bar(c=100)]}})

    def test_invalid_rows_are_not_removed_from_successful_output(self):
        cases = [
            {"bars": {"MSFT": [bar()]}}, {"bars": {"AAPL": None}}, {}, {"bars": None},
            {"bars": {"AAPL": [bar(t=END)]}}, {"bars": {"AAPL": [bar(t="2025-09-02T13:29:59Z")]}},
            {"bars": {"AAPL": [bar(o=0)]}}, {"bars": {"AAPL": [bar(h=99)]}},
            {"bars": {"AAPL": [bar(v=-1)]}}, {"bars": {"AAPL": [bar(n=1.5)]}},
            {"bars": {"AAPL": [bar(c=True)]}}, {"bars": {"AAPL": [bar(o="100")]}},
            {"bars": {"AAPL": [bar(v=float("nan"))]}}, {"bars": {}, "next_page_token": ""},
        ]
        for body in cases:
            with self.subTest(body=body), self.assertRaises(SourceError) as caught:
                parse(body)
            self.assertFalse(caught.exception.retryable)

    def test_duplicate_json_keys_are_rejected(self):
        raw = '{"bars":{},"bars":{"AAPL":[]}}'
        with self.assertRaises(SourceError):
            parse_page(raw, symbol="AAPL", start=START, end=END, timeframe="5Min")

    def test_empty_source_is_preserved_for_coverage_decision(self):
        self.assertEqual(parse({"bars": {}}).records, ())

    def test_fetch_is_one_bounded_request_and_preserves_end_exclusion(self):
        calls = []
        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(b'{"bars":{}}', {"x-request-id": "request-1"})
        result = AlpacaSource("key", "secret", opener).fetch_page(self.spec, self.partition, "cursor-1")
        self.assertEqual(result.request_id, "request-1")
        self.assertEqual(len(calls), 1)
        request, timeout = calls[0]
        query = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(urlparse(request.full_url).netloc, "data.alpaca.markets")
        self.assertEqual(query["end"], ["2025-09-02T19:59:59.999999Z"])
        self.assertEqual(query["page_token"], ["cursor-1"])
        self.assertEqual(timeout, 20)

    def test_rate_limits_are_returned_for_durable_wait_without_hidden_retries(self):
        calls = []
        def opener(request, timeout):
            calls.append(1)
            raise HTTPError(request.full_url, 429, "secret must not leak", {"Retry-After": "90"}, None)
        with self.assertRaises(SourceError) as caught:
            AlpacaSource("key", "secret", opener).fetch_page(self.spec, self.partition)
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(caught.exception.retry_after, 90)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("secret", str(caught.exception))

    def test_retry_after_http_date_is_respected(self):
        due = datetime.now(timezone.utc) + timedelta(seconds=180)
        def opener(request, timeout):
            raise HTTPError(request.full_url, 429, "rate limit", {"Retry-After": format_datetime(due)}, None)
        with self.assertRaises(SourceError) as caught:
            AlpacaSource("key", "secret", opener).fetch_page(self.spec, self.partition)
        self.assertGreaterEqual(caught.exception.retry_after, 178)

    def test_authorization_errors_do_not_fall_back_or_retry(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 403, "forbidden", {}, None)
        with self.assertRaises(SourceError) as caught:
            AlpacaSource("key", "secret", opener).fetch_page(self.spec, self.partition)
        self.assertFalse(caught.exception.retryable)

    def test_transport_failure_and_oversized_payload(self):
        def unavailable(request, timeout):
            raise URLError("sensitive-proxy-detail")
        with self.assertRaises(SourceError) as caught:
            AlpacaSource("key", "secret", unavailable).fetch_page(self.spec, self.partition)
        self.assertTrue(caught.exception.retryable)
        self.assertNotIn("sensitive", str(caught.exception))
        def oversized(request, timeout):
            return Response(b"x" * (MAX_RESPONSE_BYTES + 1))
        with self.assertRaises(SourceError) as caught:
            AlpacaSource("key", "secret", oversized).fetch_page(self.spec, self.partition)
        self.assertEqual(caught.exception.code, "response_too_large")


if __name__ == "__main__":
    unittest.main()
