"""Replacement worker safety and realistic disposable-PostgreSQL page tests.

Synthetic provider-shaped bars are deliberately used: this suite makes no
provider requests and requires an explicit disposable PostgreSQL URL for SQL.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter
import unittest
from zoneinfo import ZoneInfo

from astra_ingestion.backfill_features_v2 import derive_family
from astra_ingestion.backfill_provider_v2 import (
    BackfillProvider, KINDS, MAX_BODY_BYTES, ProviderPage, canonical,
    parse_response, request_for,
)
from astra_ingestion.backfill_worker_v2 import BackfillWorker, DERIVED_KINDS, fence
from astra_ingestion.rpc_store import MAX_REQUEST_BYTES, RPC_TIMEOUT_SECONDS, RpcPersistenceError

import test_backfill_runtime_v2 as runtime

ROOT = Path(__file__).resolve().parents[2]
METRICS = {}


def sessions(count=26):
    """Actual full NYSE weekdays in this bounded Sep 2-Oct 7 fixture window."""
    result, day = [], date(2025, 9, 2)
    while len(result) < count:
        if day.weekday() < 5:
            result.append({"date": day.isoformat(), "open": "09:30", "close": "16:00"})
        day += timedelta(days=1)
    return result


def synthetic_claim(calendar=None, *, kind="alpaca_stock_bars", family="P01"):
    calendar = calendar or sessions(1)
    return {
        "id": "task-provider-fixture", "run_id": "run-fixture", "owner": "fixture-worker",
        "generation": 1, "run_fence": 1, "page_no": 0, "cursor": None,
        "kind": kind, "family": family, "provider": "Alpaca",
        "scope": {
            "symbols": ["AAPL"], "member_ids": ["member-1"],
            "start": calendar[0]["date"] + "T09:30:00-04:00",
            "end": calendar[-1]["date"] + "T16:00:00-04:00",
            "timeframe": "1Min", "adjustment": "raw", "calendar": calendar,
        },
    }


def synthetic_bar_page(task, count=390):
    bars = []
    for entry in task["scope"]["calendar"]:
        opened = datetime.fromisoformat(entry["date"] + "T09:30:00").replace(
            tzinfo=ZoneInfo("America/New_York"))
        for minute in range(390):
            i = len(bars)
            price = round(237.25 + (i % 91) * .0137, 4)
            bars.append({
                "t": (opened + timedelta(minutes=minute)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "o": round(price - .03, 4), "h": round(price + .07, 4),
                "l": round(price - .08, 4), "c": price,
                "v": 11357 + (i % 173) * 137, "n": 233 + i % 137,
                "vw": round(price - .0093, 4),
            })
            if len(bars) == count:
                break
        if len(bars) == count:
            break
    if len(bars) != count:
        raise ValueError("Fixture calendar too short for requested record count")
    raw = canonical({"bars": {"AAPL": bars}, "next_page_token": None})
    request = request_for(task)
    records, next_cursor, quality = parse_response(task, request, raw)
    return ProviderPage(
        raw_body=raw, body_sha256=sha256(raw.encode()).hexdigest(), http_status=200,
        request_id="synthetic-qualification-000000000000", fetched_at="2026-10-30T05:00:00Z",
        request=request, records=records, next_cursor=next_cursor, quality=quality,
        headers={"content-type": "application/json", "x-request-id": "synthetic-qualification"},
    )


def commit_payload(task, page):
    return {"claim": fence(task), **page.payload(),
            "terminal_state": "INGESTED" if page.records else "NO_DATA_RETURNED"}


def request_size(operation, payload):
    # Exact RpcStore encoding, not an estimate from the original provider body.
    return len(json.dumps({"operation": operation, "payload": payload}, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8"))


def derived_payload(task, rows):
    rows = list(rows)
    calendar = task["scope"]["calendar"]
    result = derive_family("D01", rows, sessions=calendar,
                           target_start=calendar[0]["date"], target_end=calendar[-1]["date"],
                           member_id="member-1")
    lineage = [{"task_id": "source-fixture", "page_no": 0,
                "body_sha256": "a" * 64, "records": len(rows)}]
    raw = canonical({"formula_version": result["formula_version"], "family": "D01",
                     "input_lineage": lineage, "input_sha256": sha256(canonical(rows).encode()).hexdigest(),
                     "rows": result["rows"], "limitations": result.get("limitations", [])})
    return {
        "claim": fence(task), "raw_body": raw, "body_sha256": sha256(raw.encode()).hexdigest(),
        "http_status": 200, "request_id": None, "fetched_at": "2026-10-30T05:00:00Z",
        "request": {"provider": "DERIVED", "formula_version": result["formula_version"], "input_lineage": lineage},
        "records": result["rows"], "next_cursor": None, "terminal_state": "INGESTED",
        "quality": result.get("limitations", []), "headers": {}, "adapter_version": result["formula_version"],
    }


class FixtureProvider:
    def __init__(self, page=None):
        self.page = page or synthetic_bar_page(synthetic_claim(), 1)
        self.fetch_count = 0
        self.credential_checks = 0

    def supported_kinds(self):
        return ("alpaca_stock_bars",)

    def require_credentials(self, _claim):
        self.credential_checks += 1

    def fetch(self, _claim):
        self.fetch_count += 1
        return self.page


class ScriptedStore:
    def __init__(self, claim=None, *, reserve=None, commit_error=None, readback_changes=None):
        self.claim = claim
        self.reserve = reserve or {"state": "reserved"}
        self.commit_error = commit_error
        self.readback_changes = readback_changes or {}
        self.calls = []
        self.payload = None

    def _call(self, operation, payload):
        self.calls.append((operation, payload))
        if operation == "backfill_claim":
            claim, self.claim = self.claim, None
            return claim
        if operation == "backfill_reserve":
            return self.reserve
        if operation == "backfill_commit":
            self.payload = payload
            if self.commit_error is not None:
                raise self.commit_error
            return {"state": "page_committed", "task_status": "INGESTED",
                    "record_count": len(payload["records"]), "body_sha256": payload["body_sha256"]}
        if operation == "backfill_verify":
            item = self.payload
            return {"state": "committed", "task_id": item["claim"]["id"],
                    "page_no": item["claim"]["page_no"], "raw_body": item["raw_body"],
                    "body_sha256": item["body_sha256"], "readback_sha256": item["body_sha256"],
                    "records_sha256": sha256(canonical(item["records"]).encode()).hexdigest(),
                    "record_count": len(item["records"]), "next_cursor": item["next_cursor"],
                    "request": item["request"], "quality": item["quality"],
                    "task_status": "INGESTED", **self.readback_changes}
        raise AssertionError("Unexpected persistence operation: " + operation)


class BackfillWorkerBehaviorTests(unittest.TestCase):
    def test_advertises_only_configured_external_providers(self):
        for key, secret, massive, expected_prefix in (
            ("fixture", "fixture", "", "alpaca_"),
            ("", "", "fixture", "massive_"),
            ("fixture", "", "", None),
        ):
            with self.subTest(provider=expected_prefix):
                store = ScriptedStore()
                provider = BackfillProvider(key, secret, massive)
                worker = BackfillWorker(store, provider)
                self.assertEqual(worker.run_once()["state"], "idle")
                advertised = store.calls[0][1]["supported_kinds"]
                external = [kind for kind in advertised if kind in KINDS]
                self.assertEqual(external, [kind for kind in KINDS if expected_prefix and kind.startswith(expected_prefix)])
                self.assertTrue(set(DERIVED_KINDS).issubset(advertised))

    def test_deferred_reservation_never_fetches_or_commits(self):
        store = ScriptedStore(synthetic_claim(), reserve={"state": "request_deferred", "next_retry_at": "2026-10-30T06:00:00Z"})
        provider = FixtureProvider()
        result = BackfillWorker(store, provider).run_once()
        self.assertEqual(result["state"], "waiting")
        self.assertEqual(provider.fetch_count, 0)
        self.assertEqual([op for op, _ in store.calls], ["backfill_claim", "backfill_reserve"])

    def test_unknown_database_commit_is_fatal_without_source_replay(self):
        store = ScriptedStore(synthetic_claim(), commit_error=RpcPersistenceError("synthetic lost commit acknowledgement"))
        provider = FixtureProvider()
        with self.assertRaises(RpcPersistenceError):
            BackfillWorker(store, provider).run_once()
        self.assertEqual(provider.fetch_count, 1)
        self.assertEqual([op for op, _ in store.calls], ["backfill_claim", "backfill_reserve", "backfill_commit"])
        self.assertNotIn("backfill_defer", [op for op, _ in store.calls])

    def test_post_commit_process_failure_does_not_replay_provider(self):
        store = ScriptedStore(synthetic_claim())
        provider = FixtureProvider()
        def crash(_claim):
            raise RuntimeError("synthetic process failure after durable commit")
        with self.assertRaisesRegex(RuntimeError, "after durable commit"):
            BackfillWorker(store, provider, after_commit=crash).run_once()
        self.assertEqual(provider.fetch_count, 1)
        self.assertEqual([op for op, _ in store.calls].count("backfill_commit"), 1)
        self.assertNotIn("backfill_defer", [op for op, _ in store.calls])

    def test_success_is_reported_only_after_exact_receipt_readback(self):
        store = ScriptedStore(synthetic_claim())
        provider = FixtureProvider()
        result = BackfillWorker(store, provider).run_once()
        self.assertEqual(result["record_count"], 1)
        self.assertEqual(provider.fetch_count, 1)
        self.assertEqual([op for op, _ in store.calls],
                         ["backfill_claim", "backfill_reserve", "backfill_commit", "backfill_verify"])
        verify = store.calls[-1][1]
        self.assertEqual(verify["body_sha256"], provider.page.body_sha256)
        self.assertEqual(verify["page_no"], 0)
        self.assertFalse(verify["include_raw"])

    def test_readback_mismatch_is_fatal_after_commit_without_replay(self):
        for changes in ({"state": "not_committed"}, {"body_sha256": "0" * 64},
                        {"readback_sha256": "0" * 64}, {"record_count": 2}):
            with self.subTest(changes=changes):
                store = ScriptedStore(synthetic_claim(), readback_changes=changes)
                provider = FixtureProvider()
                with self.assertRaises(RpcPersistenceError):
                    BackfillWorker(store, provider).run_once()
                self.assertEqual(provider.fetch_count, 1)
                self.assertEqual([op for op, _ in store.calls],
                                 ["backfill_claim", "backfill_reserve", "backfill_commit", "backfill_verify"])


class BackfillPayloadBoundsTests(unittest.TestCase):
    def test_one_company_one_session_fits_but_month_requires_partition(self):
        measurements = []
        for count in (1, 20):
            task = synthetic_claim(sessions(count), kind="derive_intraday", family="D01")
            source_task = {**task, "kind": "alpaca_stock_bars", "family": "P01"}
            page = synthetic_bar_page(source_task, count * 390)
            start = perf_counter()
            payload = derived_payload(task, page.records)
            elapsed = perf_counter() - start
            metrics = {"companies": 1, "sessions": count, "output_rows": len(payload["records"]),
                       "raw_bytes": len(payload["raw_body"].encode()),
                       "rpc_request_bytes": request_size("backfill_commit", payload),
                       "calculation_and_encoding_seconds": elapsed}
            measurements.append(metrics)
            self.assertEqual(metrics["output_rows"], 390 * count)
            if count == 1:
                self.assertLess(metrics["raw_bytes"], 4 * 1024 * 1024)
                self.assertLess(metrics["rpc_request_bytes"], MAX_REQUEST_BYTES)
            else:
                self.assertGreater(metrics["raw_bytes"], 4 * 1024 * 1024)
                self.assertGreater(metrics["rpc_request_bytes"], MAX_REQUEST_BYTES)
        METRICS["d01_partition"] = measurements
        METRICS["d01_recommended_unit"] = {"companies": 1, "target_sessions": 1,
            "reason": "Full minute grid plus explicit NULL reasons is duplicated in retained raw receipt and normalized commit payload; monthly units exceed both persistence bounds."}


@unittest.skipUnless(os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL"), "Explicit disposable PostgreSQL required")
class BackfillPayloadIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runtime.BackfillRuntimeTests.setUpClass.__func__(cls)

    setUp = runtime.BackfillRuntimeTests.setUp
    task = runtime.BackfillRuntimeTests.task
    call = runtime.BackfillRuntimeTests.call
    claim = runtime.BackfillRuntimeTests.claim
    fence = staticmethod(runtime.BackfillRuntimeTests.fence)

    def test_lost_ack_after_real_commit_restart_does_not_refetch(self):
        task = synthetic_claim()
        self.task(kind="alpaca_stock_bars", family="P01", scope=task["scope"])
        test = self
        class DirectStore:
            def __init__(self, fail_after_commit=False):
                self.fail_after_commit = fail_after_commit
                self.claim = None
                self.operations = []

            def _call(self, operation, payload):
                self.operations.append(operation)
                result = test.call(operation, payload)
                if operation == "backfill_claim":
                    self.claim = result
                if operation == "backfill_commit" and self.fail_after_commit:
                    raise RpcPersistenceError("synthetic lost acknowledgement after real PostgreSQL commit")
                return result

        store = DirectStore(fail_after_commit=True)
        provider = FixtureProvider()
        with self.assertRaises(RpcPersistenceError):
            BackfillWorker(store, provider, worker_id="qualification-before-crash").run_once()
        self.assertEqual(provider.fetch_count, 1)
        self.assertEqual(store.operations, ["backfill_claim", "backfill_reserve", "backfill_commit"])
        readback = self.call("backfill_verify", {"claim": fence(store.claim), "page_no": 0})
        self.assertEqual(readback["body_sha256"], provider.page.body_sha256)
        self.assertEqual(readback["record_count"], 1)
        resumed_provider = FixtureProvider()
        resumed_store = DirectStore()
        self.assertEqual(BackfillWorker(resumed_store, resumed_provider,
                                      worker_id="qualification-after-restart").run_once()["state"], "idle")
        self.assertEqual(resumed_provider.fetch_count, 0)
        self.assertEqual(resumed_store.operations, ["backfill_claim"])

    def test_one_session_d01_receipt_commits_and_retains_field_limitations(self):
        task = synthetic_claim(sessions(1), kind="derive_intraday", family="D01")
        self.task(kind="derive_intraday", family="D01", provider="DERIVED", scope=task["scope"])
        claim = self.claim(["derive_intraday"])
        source_task = {**task, "kind": "alpaca_stock_bars", "family": "P01"}
        page = synthetic_bar_page(source_task, 390)
        payload = derived_payload(claim, page.records)
        self.assertGreater(len(payload["quality"]), 0)
        start = perf_counter()
        result = self.call("backfill_commit", payload)
        elapsed = perf_counter() - start
        self.assertEqual(result["record_count"], 390)
        self.assertEqual(result["task_status"], "IDENTITY_OR_QUALITY_UNRESOLVED")
        self.assertLess(elapsed, 10)
        readback = self.call("backfill_verify", {"claim": fence(claim), "page_no": 0})
        self.assertEqual(readback["readback_sha256"], payload["body_sha256"])
        self.assertEqual(readback["quality"], payload["quality"])
        with self.f.admin() as conn:
            reserved = conn.execute(f"SELECT requests_reserved FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s", (self.run,)).fetchone()["requests_reserved"]
        self.assertEqual(reserved, 0)
        METRICS["d01_commit"] = {"sessions": 1, "records": 390, "commit_transaction_seconds": elapsed,
                                 "task_status": result["task_status"], "external_requests_reserved": reserved,
                                 "limitation_groups_retained": len(payload["quality"])}

    def test_ten_thousand_bars_parse_commit_readback_and_no_replay(self):
        task = synthetic_claim(sessions(26))
        key = self.task(kind=task["kind"], family="P01", scope=task["scope"])
        claim = self.claim(["alpaca_stock_bars"])
        self.assertEqual(claim["id"], key)
        start = perf_counter()
        page = synthetic_bar_page(claim, 10000)
        parse_seconds = perf_counter() - start
        self.assertEqual(len(page.records), 10000)
        self.assertEqual(page.quality, ())
        payload = commit_payload(claim, page)
        raw_bytes = len(page.raw_body.encode())
        rpc_bytes = request_size("backfill_commit", payload)
        self.assertLess(raw_bytes, MAX_BODY_BYTES)
        self.assertLess(rpc_bytes, MAX_REQUEST_BYTES)
        self.assertEqual(self.call("backfill_reserve", {"claim": fence(claim)})["state"], "reserved")
        start = perf_counter()
        result = self.call("backfill_commit", payload)
        commit_seconds = perf_counter() - start
        self.assertEqual(result["task_status"], "INGESTED")
        self.assertEqual(result["record_count"], 10000)
        self.assertLess(commit_seconds, 10.0, "Realistic 10,000-bar commit exceeded the stricter 10-second qualification target")
        start = perf_counter()
        readback = self.call("backfill_verify", {"claim": fence(claim), "page_no": 0})
        verify_seconds = perf_counter() - start
        self.assertEqual(readback["state"], "committed")
        self.assertEqual(readback["record_count"], 10000)
        self.assertEqual(readback["raw_body"], page.raw_body)
        self.assertEqual(readback["body_sha256"], page.body_sha256)
        self.assertEqual(readback["readback_sha256"], page.body_sha256)
        records, next_cursor, quality = parse_response(claim, readback["request"], readback["raw_body"])
        self.assertEqual(records, page.records)
        self.assertIsNone(next_cursor)
        self.assertEqual(quality, ())
        self.assertEqual(self.call("backfill_commit", payload)["state"], "already_committed")
        self.assertIsNone(self.claim(["alpaca_stock_bars"]))
        with self.f.admin() as conn:
            counters = dict(conn.execute(f"SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s", (self.run,)).fetchone())
            postgres_version = conn.execute("SELECT current_setting('server_version') AS version").fetchone()["version"]
        self.assertEqual(counters, {"requests_reserved": 1, "pages_committed": 1, "records_committed": 10000})
        METRICS["provider_page"] = {
            "synthetic": True, "records": 10000, "symbol_count": 1, "calendar_sessions": 26,
            "raw_bytes": raw_bytes, "rpc_request_bytes": rpc_bytes,
            "generation_and_parse_seconds": parse_seconds, "commit_transaction_seconds": commit_seconds,
            "readback_transaction_seconds": verify_seconds, "postgres_version": postgres_version,
            "counters_after_idempotent_reconciliation": counters,
        }


def tearDownModule():
    destination = os.environ.get("ASTRA_BACKFILL_QUALIFICATION_METRICS")
    if destination and METRICS:
        paths = ("astra_ingestion/backfill_worker_v2.py", "astra_ingestion/backfill_provider_v2.py",
                 "astra_ingestion/backfill_features_v2.py", "sql/astra_backfill_runtime_v2.sql",
                 "tests/ingestion/test_backfill_worker_v2.py")
        evidence = {
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "scope": "Disposable local PostgreSQL and synthetic provider-shaped observations; no remote provider requests or production writes.",
            "limits": {"provider_body_bytes": MAX_BODY_BYTES, "commit_raw_bytes": 4 * 1024 * 1024,
                       "rpc_request_bytes": MAX_REQUEST_BYTES, "rpc_transport_timeout_seconds": RPC_TIMEOUT_SECONDS,
                       "commit_qualification_target_seconds": 10},
            "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in paths},
            **METRICS,
        }
        Path(destination).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
