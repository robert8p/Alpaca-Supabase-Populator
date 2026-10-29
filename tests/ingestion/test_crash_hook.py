"""Strictly isolated one-shot post-commit process-death qualification hook."""
import contextlib
from io import StringIO
import unittest
from unittest.mock import patch

from astra_ingestion.worker import _qualification_after_commit, Worker

_VALID = {
    "job_id": "astra-postcommit-crash-20261029-0410-job",
    "id": "astra-postcommit-crash-20261029-0410-part",
    "phase": "fetch", "generation": 1, "symbol": "AAPL",
    "start": "2025-09-02T13:30:00Z", "end": "2025-09-02T20:00:00Z",
    "spec": {
        "name": "ASTRA postcommit fault qualification 2026-10-29",
        "symbols": ["AAPL"], "max_requests": 2, "max_records": 250,
        "deadline_seconds": 900,
    },
}


class HostedDeathHookTests(unittest.TestCase):
    def test_exactly_admitted_job_is_the_only_exit_path(self):
        with patch("astra_ingestion.worker.os._exit") as kill, contextlib.redirect_stdout(StringIO()) as output:
            _qualification_after_commit(dict(_VALID))
            kill.assert_called_once_with(87)
        self.assertIn("qual_forced_process_exit_after_durable_commit", output.getvalue())
        self.assertNotIn("secret", output.getvalue())

    def test_every_guard_mismatch_is_noop(self):
        changes = (
            ("job_id", "unrelated-job"), ("id", "unrelated-partition"),
            ("phase", "verify"), ("generation", 2), ("symbol", "MSFT"),
            ("start", "2025-09-02T13:35:00Z"), ("end", "2025-09-02T19:55:00Z"),
        )
        with patch("astra_ingestion.worker.os._exit") as kill, contextlib.redirect_stdout(StringIO()):
            for key, value in changes:
                claim = dict(_VALID); claim[key] = value
                _qualification_after_commit(claim)
            for key, value in (
                ("name", "Other job"), ("symbols", ["MSFT"]),
                ("max_requests", 3), ("max_records", 251), ("deadline_seconds", 901)
            ):
                claim = dict(_VALID); claim["spec"] = {**_VALID["spec"], key: value}
                _qualification_after_commit(claim)
            for malformed in (None, "", {}, [], 1):
                _qualification_after_commit(malformed)
            kill.assert_not_called()

    def test_hook_executes_only_after_durable_commit_returns(self):
        # The Worker is constructed with an after_commit callback; prove
        # the hook is not called before Store.commit_page returns.
        from astra_ingestion.source import FetchResult, parse_page
        from astra_ingestion.models import IngestionSpec
        from unittest.mock import Mock
        spec = IngestionSpec.from_dict({
            "name": _VALID["spec"]["name"], "symbols": ["AAPL"],
            "start": _VALID["start"], "end": _VALID["end"],
            "timeframe": "5Min", "max_requests": 2, "max_records": 250,
            "deadline_seconds": 900,
        })
        claim = {**_VALID, "spec": spec.to_dict(), "next_page_token": None}
        raw = '{"bars":{"AAPL":[{"t":"2025-09-02T13:30:00Z","o":100,"h":101,"l":99,"c":100,"v":1,"n":1,"vw":100}]},"next_page_token":null}'
        events = []
        class Store:
            def claim_next(self, *_): return claim
            def reserve_request(self, *_): events.append("reserve")
            def commit_page(self, *_):
                events.append("committed")
                return {"page_count": 1}
        class Source:
            def fetch_page(self, *_): events.append("fetched"); return FetchResult(raw, None)
        def callback(_claim):
            events.append("hook")
            self.assertEqual(events, ["reserve", "fetched", "committed", "hook"])
        self.assertEqual(Worker(Store(), Source(), worker_id="synthetic", after_commit=callback).run_once()["state"], "page_committed")


if __name__ == "__main__":
    unittest.main()
