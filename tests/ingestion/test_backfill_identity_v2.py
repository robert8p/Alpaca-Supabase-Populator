"""Original-source proof, dated identifier attribution and progressive recalculation."""
import base64
from copy import deepcopy
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest
import uuid
import time

from astra_ingestion.backfill_features_v2 import derive_family
from astra_ingestion.backfill_identity_v2 import (
    IdentityMaterialError, MATERIAL_VERSION, RESOLVED, ASOF_MODE, COHORT_SHA256, apply_identity_material,
    prepare_retained_identity_commit, attach_identity_output,
)
from astra_ingestion.backfill_provider_v2 import ProviderPage, canonical, parse_response, request_for
from astra_ingestion.backfill_worker_v2 import BackfillWorker
import test_backfill_feature_reuse_v2 as cache
import test_backfill_reuse_commit_v2 as pointer

ROOT = Path(__file__).resolve().parents[2]
MEMBER = "CIK:0000320193"
ANCHOR = {"anchor_composite_figi": "BBG000B9XRY4", "anchor_share_class_figi": "BBG001S5N8V8",
          "anchor_security_type": "CS", "anchor_exchange": "XNAS", "anchor_observation_date": "2026-08-03",
          "membership_accepted": True, "cohort_sha256": COHORT_SHA256, "company_id": MEMBER, "anchor_ticker": "AAPL"}
NATIVE = {"cik": "0000320193", "ticker": "AAPL", "composite_figi": "BBG000B9XRY4",
          "share_class_figi": "BBG001S5N8V8", "type": "CS", "primary_exchange": "XNAS",
          "active": True, "market": "stocks", "locale": "us", "currency_name": "usd"}
CALENDAR = [{"date": "2025-09-02", "open": "09:30", "close": "16:00"},
            {"date": "2025-09-03", "open": "09:30", "close": "16:00"}]


def calculation_claim(days=CALENDAR):
    return {"id": "calculation-fixture", "run_id": "run-fixture", "kind": "derive_daily", "family": "D03",
            "scope": {"member_ids": [MEMBER], "symbols": ["AAPL"], "calendar": days,
                      "input_start": days[0]["date"], "target_start": days[-1]["date"], "target_end": days[-1]["date"]}}


def identity_material(claim, resolved=True):
    mappings = []
    for day in claim["scope"]["calendar"]:
        mappings.append({"member_id": MEMBER, "symbol": "AAPL", "market_date": day["date"],
                         "state": RESOLVED if resolved else "IDENTITY_OR_QUALITY_UNRESOLVED",
                         "reason": None if resolved else "DATED_IDENTITY_EVIDENCE_UNAVAILABLE",
                         "cik": "0000320193", "composite_figi": NATIVE["composite_figi"],
                         "share_class_figi": NATIVE["share_class_figi"], "security_type": "CS", "primary_exchange": "XNAS",
                         "historical_symbol": "AAPL", "eligible": True if resolved else None,
                         "anchor_identity": {"member_id": MEMBER, "symbol": "AAPL", "reference_date": "2026-08-03",
                                             "cik": "0000320193", "composite_figi": NATIVE["composite_figi"],
                                             "share_class_figi": NATIVE["share_class_figi"], "security_type": "CS",
                                             "membership_accepted": True, "cohort_sha256": COHORT_SHA256,
                                             "anchor_sha256": sha256(canonical(ANCHOR).encode()).hexdigest()},
                         "identity_anchor": "CIK:0000320193|FIGI:BBG000B9XRY4|CLASS:BBG001S5N8V8" if resolved else None,
                         "evidence_sha256": "a" * 64, "retrospective_only": True,
                         "strict_historical_availability_certified": False})
    return {"version": MATERIAL_VERSION, "run_id": claim["run_id"], "task_id": claim["id"],
            "mappings": mappings, "identity_material_sha256": sha256(canonical(mappings).encode()).hexdigest()}


def daily_rows(calendar=CALENDAR, receipt_mapping=False):
    result = []
    for adjustment in ("raw", "split"):
        task = {"kind": "alpaca_stock_bars", "scope": {"symbols": ["AAPL"], "timeframe": "1Day",
                "adjustment": adjustment, "start": calendar[0]["date"] + "T04:00:00Z",
                "end": calendar[-1]["date"] + "T23:00:00Z", "calendar": calendar}}
        raw = canonical({"bars": {"AAPL": [{"t": day["date"] + "T04:00:00Z", "o": 100+i,
                         "h": 101+i, "l": 99+i, "c": 100+i, "v": 1000+i}
                         for i, day in enumerate(calendar)]}, "next_page_token": None})
        request = request_for(task)
        rows, _, _ = parse_response(task, request, raw)
        if receipt_mapping:
            for row in rows:
                row["provider_symbol_mapping"] = {
                    "provider": request["provider"], "host": request["host"], "path": request["path"], "method": request["method"],
                    "requested_symbol": row["symbol"], "asof": request["params"]["asof"],
                    "source_body_sha256": sha256(raw.encode()).hexdigest(), "request_sha256": sha256(canonical(request).encode()).hexdigest(),
                }
        result.extend(rows)
    return result


class IdentityMaterialTests(unittest.TestCase):
    def test_explicit_asof_alias_uses_frozen_anchor_and_proof_survives_daily_to_breadth(self):
        claim = calculation_claim()
        material = identity_material(claim)
        for entry in material["mappings"]:
            entry["historical_symbol"] = "OLDAPL"
        material["identity_material_sha256"] = sha256(canonical(material["mappings"]).encode()).hexdigest()
        overlay = apply_identity_material(daily_rows(receipt_mapping=True), material, claim)
        self.assertTrue(all(row["identity_attribution_mode"] == ASOF_MODE for row in overlay["rows"]))
        self.assertEqual(overlay["identity_lineage"]["explicit_asof_attributed_member_sessions"], 2)
        result = derive_family("D03", overlay["rows"], sessions=CALENDAR, target_start="2025-09-03", target_end="2025-09-03", member_id=MEMBER)
        output = attach_identity_output(result["rows"], overlay)
        self.assertAlmostEqual(output[0]["values"]["adjusted_ret_1d"], .01)
        body_hash = sha256(canonical({"rows": output}).encode()).hexdigest()
        output[0]["source_lineage"] = {"body_sha256": body_hash}
        breadth = {**claim, "id": "breadth", "kind": "derive_breadth", "family": "CTX06",
                   "scope": {**claim["scope"], "calendar": CALENDAR[1:], "representative_security": {MEMBER: {"symbol": "AAPL"}}}}
        bmaterial = {**material, "task_id": "breadth", "mappings": [dict(material["mappings"][1], input_body_sha256=body_hash)]}
        bmaterial["identity_material_sha256"] = sha256(canonical(bmaterial["mappings"]).encode()).hexdigest()
        carried = apply_identity_material(output, bmaterial, breadth)
        self.assertAlmostEqual(carried["rows"][0]["values"]["adjusted_ret_1d"], .01)
        self.assertTrue(carried["representative_security"][MEMBER]["eligibility_by_date"]["2025-09-03"])
        bmaterial["mappings"][0]["evidence_sha256"] = "b" * 64
        bmaterial["identity_material_sha256"] = sha256(canonical(bmaterial["mappings"]).encode()).hexdigest()
        held = apply_identity_material(output, bmaterial, breadth)
        self.assertIsNone(held["rows"][0]["values"]["adjusted_ret_1d"])
        self.assertIsNotNone(held["rows"][0]["values"]["raw_ret_1d"])

    def test_missing_disabled_or_wrong_asof_cannot_qualify_alias_and_split_disagreement_holds_adjusted_values(self):
        claim = calculation_claim()
        material = identity_material(claim)
        for entry in material["mappings"]:
            entry["historical_symbol"] = "OLDAPL"
        material["identity_material_sha256"] = sha256(canonical(material["mappings"]).encode()).hexdigest()
        for change in ({"asof": None}, {"asof": "-"}, {"asof": "2026-08-04"}, {"requested_symbol": "OTHER"},
                       {"source_body_sha256": "bad"}, {"host": "other-provider.invalid"}):
            with self.subTest(change=change):
                rows = daily_rows(receipt_mapping=True)
                for row in rows:
                    row["provider_symbol_mapping"].update(change)
                mapped = apply_identity_material(rows, material, claim)
                self.assertTrue(all(row["identity_anchor"] is None for row in mapped["rows"]))
        rows = daily_rows(receipt_mapping=True)
        for row in rows:
            if row["adjustment"] == "split":
                row["provider_symbol_mapping"]["asof"] = "2026-08-04"
        mapped = apply_identity_material(rows, material, claim)
        self.assertTrue(all(row["identity_anchor"] is None for row in mapped["rows"]))
        result = derive_family("D03", mapped["rows"], sessions=CALENDAR, target_start="2025-09-03", target_end="2025-09-03", member_id=MEMBER)
        result["rows"] = attach_identity_output(result["rows"], mapped)
        self.assertIsNone(result["rows"][0]["values"]["adjusted_ret_1d"])
        self.assertIsNotNone(result["rows"][0]["values"]["raw_ret_1d"])

    def test_actual_parser_then_identity_overlay_unlocks_adjusted_horizons_without_changing_sources(self):
        calendar = json.loads((ROOT / "evidence/replacement-calendar-v1.json").read_text())["sessions"]
        calendar = [dict(date=e["date"], open=e["open"], close=e["close"]) for e in calendar if "2025-06-05" <= e["date"] <= "2025-09-03"]
        claim = calculation_claim(calendar)
        rows = daily_rows(calendar)
        before = deepcopy(rows)
        missing = derive_family("D03", rows, sessions=calendar, target_start="2025-09-03", target_end="2025-09-03", member_id=MEMBER)
        self.assertIsNone(missing["rows"][0]["values"]["adjusted_ret_60d"])
        overlay = apply_identity_material(rows, identity_material(claim), claim)
        good = derive_family("D03", overlay["rows"], sessions=calendar, target_start="2025-09-03", target_end="2025-09-03", member_id=MEMBER)
        for horizon in (1, 5, 20, 60):
            self.assertAlmostEqual(good["rows"][0]["values"][f"adjusted_ret_{horizon}d"],
                                   good["rows"][0]["values"][f"provider_split_ret_{horizon}d"])
        self.assertEqual(rows, before)
        self.assertFalse(overlay["identity_lineage"]["strict_historical_availability_certified"])

    def test_ticker_only_or_tampered_material_is_rejected(self):
        claim = calculation_claim()
        for field in ("cik", "composite_figi", "share_class_figi", "primary_exchange", "evidence_sha256"):
            material = identity_material(claim)
            material["mappings"][0][field] = None
            material["identity_material_sha256"] = sha256(canonical(material["mappings"]).encode()).hexdigest()
            with self.assertRaises(IdentityMaterialError):
                apply_identity_material(daily_rows(), material, claim)
        material = identity_material(claim)
        material["mappings"][0]["eligible"] = False
        with self.assertRaises(IdentityMaterialError):
            apply_identity_material(daily_rows(), material, claim)

    def test_unresolved_date_removes_legacy_anchor_and_keeps_raw_values(self):
        claim = calculation_claim()
        rows = daily_rows()
        for row in rows:
            row["identity_anchor"] = "unsupported-legacy-identity"
        mapped = apply_identity_material(rows, identity_material(claim, False), claim)
        self.assertTrue(all(row["identity_anchor"] is None for row in mapped["rows"]))
        output = derive_family("D03", mapped["rows"], sessions=CALENDAR, target_start="2025-09-03", target_end="2025-09-03", member_id=MEMBER)
        self.assertIsNotNone(output["rows"][0]["values"]["raw_ret_1d"])
        self.assertIsNone(output["rows"][0]["values"]["adjusted_ret_1d"])

    def test_bounded_original_source_decompression_and_hash_failures(self):
        raw = canonical({"status": "OK", "results": [NATIVE]}).encode()
        compressed = gzip.compress(raw, mtime=0)
        claim = {"id": "source-fixture", "run_id": "run-fixture", "kind": "retained_identity", "owner": "worker",
                 "generation": 1, "run_fence": 1, "page_no": 0, "scope": {"identity_source_id": "source-id"}}
        source = {"task_id": claim["id"], "run_id": claim["run_id"], "source_id": "source-id", "storage_encoding": "gzip",
                  "original_bytes": len(raw), "source_sha256": sha256(raw).hexdigest(),
                  "compressed_sha256": sha256(compressed).hexdigest(), "compressed_body_base64": base64.b64encode(compressed).decode()}
        self.assertEqual(prepare_retained_identity_commit(claim, source)["raw_body"].encode(), raw)
        for change in ({"original_bytes": 10}, {"source_sha256": "0"*64}, {"compressed_sha256": "0"*64},
                       {"original_bytes": 4194305}, {"compressed_body_base64": source["compressed_body_base64"] + "%%%%"}):
            with self.assertRaises(IdentityMaterialError):
                prepare_retained_identity_commit(claim, {**source, **change})


@unittest.skipUnless(os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL"), "Explicit disposable PostgreSQL required")
class IdentityPostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cache.CompactFeatureReuseTests.setUpClass.__func__(cls)
        f = cls.fixture("runTest")
        cls.replacements = [
            ("market_governance.remediation_source_response_v1", f.schema + ".identity_response_fixture"),
            ("market_governance.remediation_source_batch_v1", f.schema + ".identity_batch_fixture"),
            ("reference.massive_security_master_observation_v1", f.schema + ".identity_observation_fixture"),
        ] + cls.replacements
        with f.admin() as conn:
            conn.execute(f'''CREATE TABLE {f.schema}.identity_batch_fixture(batch_id bigint PRIMARY KEY,provider text,source_type text,
                status text,request_json jsonb,start_ts timestamptz)''')
            conn.execute(f'''CREATE TABLE {f.schema}.identity_response_fixture(source_id uuid PRIMARY KEY,batch_id bigint,http_status integer,
                storage_encoding text,credential_redactions integer,original_bytes bigint,compressed_body bytea,
                source_sha256 bytea,stored_body_sha256 bytea,compressed_sha256 bytea,source_url text,received_at timestamptz)''')
            conn.execute(f'''CREATE TABLE {f.schema}.identity_observation_fixture(observation_id bigint GENERATED ALWAYS AS IDENTITY,
                ticker text,composite_figi text,share_class_figi text,requested_as_of date,source_route text,raw_payload jsonb)''')
            conn.execute(cls.rewrite((ROOT / "sql/astra_backfill_canonical_performance_v2.sql").read_text()))
            conn.execute(cls.rewrite((ROOT / "sql/astra_backfill_family_fairness_v2.sql").read_text()))
            conn.execute(cls.rewrite((ROOT / "sql/astra_backfill_identity_v2.sql").read_text()))
            conn.execute(cls.rewrite((ROOT / "sql/astra_backfill_nonminute_coverage_v2.sql").read_text()))

    rewrite = classmethod(cache.CompactFeatureReuseTests.rewrite.__func__)
    task = pointer.RetainedReuseCommitTests.task
    call = pointer.RetainedReuseCommitTests.call
    claim = pointer.RetainedReuseCommitTests.claim
    fence = staticmethod(pointer.RetainedReuseCommitTests.fence)

    def setUp(self):
        pointer.RetainedReuseCommitTests.setUp(self)
        self.run = "identity-run-" + uuid.uuid4().hex
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED',fence=fence+1 WHERE status='ACTIVE'")
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_runs_v2(id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope)
                VALUES(%s,%s,%s,%s,'synthetic-identity-fixture','{{}}')''', (self.run, "1"*64,
                "2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec",
                "4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f"))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_members_v2(run_id,member_id,selection_order,anchor_ticker,anchor)
                SELECT %s,CASE WHEN g=1 THEN %s ELSE 'fixture-member-'||g END,g,CASE WHEN g=1 THEN 'AAPL' ELSE 'T'||g END,
                CASE WHEN g=1 THEN %s::jsonb ELSE '{{}}'::jsonb END FROM generate_series(1,3000) g''', (self.run, MEMBER, json.dumps(ANCHOR)))
            for table in ("identity_observation_fixture", "identity_response_fixture", "identity_batch_fixture"):
                conn.execute(f"DELETE FROM {self.f.schema}.{table}")

    def seed_source(self, day="2025-09-02", native=None):
        native = native or NATIVE
        source_id = str(uuid.uuid4())
        batch_id = uuid.uuid4().int % 10**12
        raw = canonical({"status": "OK", "results": [native]}).encode()
        compressed = gzip.compress(raw, mtime=0)
        payload = {**native, "_remediation_acquisition": {"source_id": source_id, "source_ordinal": 1,
                   "source_sha256": sha256(raw).hexdigest(), "page_number": 1}}
        with self.f.admin() as conn:
            conn.execute(f"INSERT INTO {self.f.schema}.identity_batch_fixture VALUES(%s,'massive','massive_reference_tickers','COMPLETE',%s,%s)",
                         (batch_id, json.dumps({"reference_date": day}), day + "T00:00:00Z"))
            conn.execute(f"INSERT INTO {self.f.schema}.identity_response_fixture VALUES(%s,%s,200,'gzip',0,%s,%s,%s,%s,%s,%s,'2026-10-08T06:32:50Z')",
                         (source_id, batch_id, len(raw), compressed, sha256(raw).digest(), sha256(raw).digest(), sha256(compressed).digest(),
                          "https://api.massive.com/v3/reference/tickers?market=stocks&date=" + day + "&active=true"))
            conn.execute(f"INSERT INTO {self.f.schema}.identity_observation_fixture(ticker,composite_figi,share_class_figi,requested_as_of,source_route,raw_payload) VALUES(%s,%s,%s,%s,%s,%s)",
                         (native.get("ticker"), native.get("composite_figi"), native.get("share_class_figi"), day,
                          "market_data_remediation_20261008_v1.massive_native_listing_pages_v1", json.dumps(payload)))
        return source_id

    def derived_claim(self):
        scope = calculation_claim()["scope"]
        task_id = self.task(kind="derive_daily", family="D03", provider="DERIVED", scope=scope)
        claim = self.claim(["derive_daily"])
        self.assertEqual(claim["id"], task_id)
        return claim

    def prove_next(self):
        claim = self.claim(["retained_identity"], worker="identity-proof-worker")
        self.assertIsNotNone(claim)
        source = self.call("backfill_identity_source_read", {"claim": self.fence(claim)})
        payload = prepare_retained_identity_commit(claim, source)
        committed = self.call("backfill_identity_source_commit", payload)
        readback = self.call("backfill_verify", {"claim": self.fence(claim), "page_no": 0, "include_raw": False})
        self.assertTrue(readback["verification"]["retained_identity_verification"]["passed"])
        return claim, payload, committed

    def commit_calculation(self, claim, material):
        mapped = apply_identity_material(daily_rows(), material, claim)
        result = derive_family("D03", mapped["rows"], sessions=CALENDAR, target_start="2025-09-03", target_end="2025-09-03", member_id=MEMBER)
        result["rows"] = attach_identity_output(result["rows"], mapped)
        raw = canonical({"rows": result["rows"], "identity_material_sha256": mapped["identity_material_sha256"],
                         "identity_lineage": mapped["identity_lineage"], "formula_version": result["formula_version"]})
        payload = {"claim": self.fence(claim), "raw_body": raw, "body_sha256": sha256(raw.encode()).hexdigest(),
                   "request": {"provider": "DERIVED", "formula_version": result["formula_version"]},
                   "http_status": 200, "fetched_at": "2026-10-30T06:00:00Z", "records": result["rows"], "next_cursor": None,
                   "quality": result["limitations"], "headers": {}, "adapter_version": result["formula_version"]}
        committed = self.call("backfill_commit", payload)
        self.call("backfill_verify", {"claim": self.fence(claim), "page_no": 0})
        return committed, raw

    def commit_current_reference(self, day, native):
        self.task(kind="massive_reference", family="REF01", provider="Massive",
                  scope={"member_ids": [MEMBER], "symbols": ["AAPL"], "asof": day})
        claim = self.claim(["massive_reference"], worker="configured-massive-worker")
        request = request_for(claim)
        raw = canonical({"status": "OK", "results": native})
        rows, cursor, quality = parse_response(claim, request, raw)
        self.call("backfill_reserve", {"claim": self.fence(claim)})
        self.call("backfill_commit", {"claim": self.fence(claim), "raw_body": raw, "body_sha256": sha256(raw.encode()).hexdigest(),
            "http_status": 200, "fetched_at": "2026-10-30T06:00:00Z", "request": request, "records": rows,
            "next_cursor": cursor, "quality": quality, "headers": {}, "adapter_version": "fixture-current-reference-v2"})
        self.call("backfill_verify", {"claim": self.fence(claim), "page_no": 0})
        return claim

    def test_enabled_real_worker_proves_alias_source_and_automatically_recalculates_actual_daily_receipts(self):
        for day in ("2025-09-02", "2025-09-03"):
            self.seed_source(day, {**NATIVE, "ticker": "OLDAPL"})
        source_ids = []
        for basis in ("raw", "split"):
            source_ids.append(self.task(kind="alpaca_stock_bars", family="D02", provider="Alpaca",
                scope={"member_ids": [MEMBER], "symbols": ["AAPL"], "timeframe": "1Day", "adjustment": basis,
                       "start": "2025-09-02T04:00:00Z", "end": "2025-09-03T23:00:00Z", "calendar": CALENDAR}))
        root_id = self.task(kind="derive_daily", family="D03", provider="DERIVED", scope=calculation_claim()["scope"], dependencies=source_ids)
        parent = self
        class Store:
            def _call(self, operation, payload):
                return parent.call(operation, payload)
        class Provider:
            def __init__(self): self.requests = []
            def supported_kinds(self): return ("alpaca_stock_bars",)
            def require_credentials(self, claim): pass
            def fetch(self, claim):
                self.requests.append(claim["id"])
                request = request_for(claim)
                raw = canonical({"bars": {"AAPL": [
                    {"t": "2025-09-02T04:00:00Z", "o": 100, "h": 101, "l": 99, "c": 100, "v": 1000, "n": 100, "vw": 100},
                    {"t": "2025-09-03T04:00:00Z", "o": 101, "h": 102, "l": 100, "c": 101, "v": 1001, "n": 101, "vw": 101}],
                    }, "next_page_token": None})
                rows, cursor, quality = parse_response(claim, request, raw)
                return ProviderPage(raw_body=raw, body_sha256=sha256(raw.encode()).hexdigest(), http_status=200,
                    request_id="synthetic-alpaca-identity", fetched_at="2026-10-30T06:00:00Z", request=request,
                    records=tuple(rows), next_cursor=cursor, quality=tuple(quality), headers={})
        provider = Provider()
        worker = BackfillWorker(Store(), provider, worker_id="actual-identity-worker", identity_enabled=True)
        outcomes = []
        for _ in range(14):
            outcome = worker.run_once()
            outcomes.append(outcome)
            self.assertNotEqual(outcome["state"], "backfill_exception_recorded", outcomes)
            with self.f.admin() as conn:
                proofs = conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_identity_sources_v2 WHERE run_id=%s AND verified", (self.run,)).fetchone()["n"]
                root = conn.execute(f"SELECT raw_body FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s", (root_id,)).fetchone()
            if proofs == 2 and root:
                break
            if outcome["state"] in ("waiting", "idle"):
                time.sleep(.12)
        self.assertEqual(proofs, 2, outcomes)
        self.assertIsNotNone(root, outcomes)
        original_raw = root["raw_body"]
        self.assertIsNone(json.loads(original_raw)["rows"][0]["values"]["adjusted_ret_1d"])
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_identity_refresh_v2 SET ready_after=clock_timestamp()-interval '1 second' WHERE run_id=%s", (self.run,))
        successor = worker.run_once()
        self.assertEqual(successor["state"], "page_committed", successor)
        self.assertNotEqual(successor["task_id"], root_id)
        with self.f.admin() as conn:
            current = conn.execute(f"SELECT p.raw_body,rb.body_sha256,t.scope FROM {self.f.schema}.backfill_pages_v2 p JOIN {self.f.schema}.backfill_readbacks_v2 rb USING(task_id,page_no) JOIN {self.f.schema}.backfill_tasks_v2 t ON t.id=p.task_id WHERE p.task_id=%s", (successor["task_id"],)).fetchone()
            body = json.loads(current["raw_body"])
            self.assertEqual(current["scope"]["identity_refresh_of"], root_id)
            self.assertAlmostEqual(body["rows"][0]["values"]["adjusted_ret_1d"], .01)
            self.assertEqual(body["identity_lineage"]["explicit_asof_attributed_member_sessions"], 2)
            self.assertEqual(body["rows"][0]["identity_input_attribution"]["provider_symbol_mapping"]["asof"], "2026-08-03")
            self.assertEqual(current["body_sha256"], sha256(current["raw_body"].encode()).hexdigest())
            projected = conn.execute(f"SELECT identity_input_attribution FROM {self.f.schema}.backfill_breadth_inputs_v2 WHERE task_id=%s", (successor["task_id"],)).fetchone()
            self.assertTrue(projected["identity_input_attribution"]["all_input_identities_qualified"])
            self.assertEqual(conn.execute(f"SELECT raw_body FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s", (root_id,)).fetchone()["raw_body"], original_raw)
            original_pages = conn.execute(f"SELECT request,raw_body FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=ANY(%s)", (source_ids,)).fetchall()
            self.assertTrue(all(page["request"]["params"]["asof"] == "2026-08-03" for page in original_pages))
            self.assertTrue(all("identity_input_attribution" not in page["raw_body"] for page in original_pages))
            self.assertEqual(conn.execute(f"SELECT requests_reserved FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s", (self.run,)).fetchone()["requests_reserved"], 2)
        self.assertCountEqual(provider.requests, source_ids)

    def test_original_source_proof_resolves_exact_dates_and_preserves_missing_support(self):
        self.seed_source("2025-09-02")
        self.seed_source("2025-09-03")
        claim = self.derived_claim()
        before = self.call("backfill_identity_material", {"claim": self.fence(claim)})
        self.assertTrue(all(e["identity_anchor"] is None for e in before["mappings"]))
        first, payload, committed = self.prove_next()
        self.assertEqual(committed["record_count"], 1)
        self.assertEqual(self.call("backfill_identity_source_commit", payload)["state"], "already_committed")
        self.prove_next()
        material = self.call("backfill_identity_material", {"claim": self.fence(claim)})
        mapped = apply_identity_material(daily_rows(), material, claim)
        values = derive_family("D03", mapped["rows"], sessions=CALENDAR, target_start="2025-09-03", target_end="2025-09-03", member_id=MEMBER)["rows"][0]["values"]
        self.assertAlmostEqual(values["adjusted_ret_1d"], .01)
        self.assertIsNone(values["adjusted_ret_5d"])
        with self.f.admin() as conn:
            counts = conn.execute(f"SELECT requests_reserved,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s", (self.run,)).fetchone()
            self.assertEqual(counts["requests_reserved"], 0)
            self.assertEqual(counts["records_committed"], 2)
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_plan_units_v2 WHERE run_id=%s", (self.run,)).fetchone()["n"], 1)

    def test_wrong_cik_or_share_class_is_held_despite_same_ticker(self):
        self.seed_source(native={**NATIVE, "cik": "0000000001"})
        claim = self.derived_claim()
        self.call("backfill_identity_material", {"claim": self.fence(claim)})
        self.prove_next()
        material = self.call("backfill_identity_material", {"claim": self.fence(claim)})
        self.assertTrue(all(e["identity_anchor"] is None for e in material["mappings"]))
        with self.f.admin() as conn:
            reason = conn.execute(f"SELECT reason FROM {self.f.schema}.backfill_identity_evidence_v2 WHERE run_id=%s", (self.run,)).fetchone()["reason"]
            self.assertEqual(reason, "STABLE_COHORT_IDENTIFIERS_DIFFER")

    def test_dated_alias_is_accepted_by_identifiers_without_changing_fixed_member_or_request_symbol(self):
        self.seed_source(native={**NATIVE, "ticker": "OLDAPL"})
        claim = self.derived_claim()
        self.call("backfill_identity_material", {"claim": self.fence(claim)})
        self.prove_next()
        material = self.call("backfill_identity_material", {"claim": self.fence(claim)})
        row = material["mappings"][0]
        self.assertEqual(row["state"], RESOLVED)
        self.assertEqual(row["symbol"], "AAPL")
        self.assertEqual(row["historical_symbol"], "OLDAPL")
        self.assertEqual(row["member_id"], MEMBER)
        attributed = apply_identity_material(daily_rows(), material, claim)
        wrong_symbol_rows = [r for r in attributed["rows"] if r["market_date"] == "2025-09-02"]
        self.assertTrue(all(r["identity_anchor"] is None for r in wrong_symbol_rows))
        self.assertTrue(all(r["identity_reason"] == "HISTORICAL_SYMBOL_REQUIRES_ALIAS_ACQUISITION" for r in wrong_symbol_rows))

    def test_dated_symbol_conflict_is_held_even_when_both_figis_match(self):
        self.seed_source()
        claim = self.derived_claim()
        self.call("backfill_identity_material", {"claim": self.fence(claim)})
        self.prove_next()
        first = self.call("backfill_identity_material", {"claim": self.fence(claim)})
        self.assertEqual(first["mappings"][0]["state"], RESOLVED)
        self.commit_current_reference("2025-09-02", {**NATIVE, "ticker": "CONTRARY"})
        changed = self.call("backfill_identity_material", {"claim": self.fence(claim)})
        self.assertIsNone(changed["mappings"][0]["identity_anchor"])
        self.assertEqual(changed["mappings"][0]["reason"], "CONFLICTING_OR_UNVERIFIED_DATED_IDENTITY_EVIDENCE")
        self.assertNotEqual(changed["identity_material_sha256"], first["identity_material_sha256"])

    def test_asof_alias_proof_uses_actual_frozen_anchor_and_compact_breadth_projection(self):
        for day in ("2025-09-02", "2025-09-03"):
            self.seed_source(day, {**NATIVE, "ticker": "OLDAPL"})
        claim = self.derived_claim()
        self.call("backfill_identity_material", {"claim": self.fence(claim)})
        self.prove_next()
        self.prove_next()
        material = self.call("backfill_identity_material", {"claim": self.fence(claim)})
        self.assertEqual(material["mappings"][0]["anchor_identity"]["reference_date"], "2026-08-03")
        mapped = apply_identity_material(daily_rows(receipt_mapping=True), material, claim)
        result = derive_family("D03", mapped["rows"], sessions=CALENDAR, target_start="2025-09-03", target_end="2025-09-03", member_id=MEMBER)
        result["rows"] = attach_identity_output(result["rows"], mapped)
        raw = canonical({"rows": result["rows"], "identity_material_sha256": mapped["identity_material_sha256"]})
        self.call("backfill_commit", {"claim": self.fence(claim), "raw_body": raw, "body_sha256": sha256(raw.encode()).hexdigest(),
            "http_status": 200, "fetched_at": "2026-10-30T06:00:00Z", "request": {"provider": "DERIVED"},
            "records": result["rows"], "next_cursor": None, "quality": [], "headers": {}, "adapter_version": result["formula_version"]})
        self.call("backfill_verify", {"claim": self.fence(claim), "page_no": 0})
        with self.f.admin() as conn:
            projected = conn.execute(f"SELECT identity_input_attribution,adjusted_ret_1d FROM {self.f.schema}.backfill_breadth_inputs_v2 WHERE task_id=%s", (claim["id"],)).fetchone()
            self.assertAlmostEqual(float(projected["adjusted_ret_1d"]), .01)
            self.assertEqual(projected["identity_input_attribution"]["provider_symbol_mapping"]["asof"], "2026-08-03")
            current = conn.execute(f"SELECT to_jsonb(c) current FROM {self.f.schema}.backfill_identity_current_v2 c WHERE run_id=%s AND market_date='2025-09-03'", (self.run,)).fetchone()["current"]
            proof_row = result["rows"][0]
            qualified = conn.execute(f"SELECT {self.f.schema}.backfill_identity_price_attribution_v2(%s::jsonb,%s::jsonb,%s::jsonb,'AAPL') q",
                                     (json.dumps(proof_row), json.dumps(current), json.dumps(ANCHOR))).fetchone()["q"]
            self.assertTrue(qualified)
            proof_row = deepcopy(proof_row)
            proof_row["identity_input_attribution"]["provider_symbol_mapping"]["asof"] = "-"
            held = conn.execute(f"SELECT {self.f.schema}.backfill_identity_price_attribution_v2(%s::jsonb,%s::jsonb,%s::jsonb,'AAPL') q",
                                (json.dumps(proof_row), json.dumps(current), json.dumps(ANCHOR))).fetchone()["q"]
            self.assertFalse(held)
        status = self.call("backfill_status", {"run_id": self.run})["runs"][0]
        self.assertEqual(status["identity_sources_verified"], 2)
        self.assertEqual(status["identity_sources_invalidated"], 0)
        self.assertGreaterEqual(status["identity_refresh_pending_count"], 1)
        self.assertIsNotNone(status["identity_refresh_next_retry_at"])

    def test_source_tamper_invalidates_mapping_and_compressed_bytes_never_escape_api_role(self):
        source_id = self.seed_source()
        claim = self.derived_claim()
        self.call("backfill_identity_material", {"claim": self.fence(claim)})
        proof_claim, _, _ = self.prove_next()
        with self.assertRaises(self.f.psycopg.Error):
            self.f.rpc("backfill_identity_source_read", {"claim": self.fence(proof_claim)}, actor="api")
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.identity_response_fixture SET compressed_body='tampered'::bytea WHERE source_id=%s", (source_id,))
            self.assertFalse(conn.execute("SELECT has_table_privilege(%s,%s,'SELECT') allowed", (self.f.outsider, self.f.schema + ".backfill_identity_evidence_v2")).fetchone()["allowed"])
        material = self.call("backfill_identity_material", {"claim": self.fence(claim)})
        self.assertIsNone(material["mappings"][0]["identity_anchor"])

    def test_new_identity_creates_one_immutable_successor_and_does_not_reopen_original(self):
        self.seed_source("2025-09-02")
        self.seed_source("2025-09-03")
        original = self.derived_claim()
        material = self.call("backfill_identity_material", {"claim": self.fence(original)})
        _, original_raw = self.commit_calculation(original, material)
        self.prove_next()
        self.prove_next()
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_identity_refresh_v2 SET ready_after=clock_timestamp()-interval '1 second' WHERE run_id=%s", (self.run,))
        # The ordinary worker claim invokes durable refresh admission itself.
        successor = self.claim(["derive_daily"], worker="after-source-proof-restart")
        self.assertIsNotNone(successor)
        self.assertEqual(successor["scope"]["identity_refresh_of"], original["id"])
        current = self.call("backfill_identity_material", {"claim": self.fence(successor)})
        self.commit_calculation(successor, current)
        self.call("backfill_identity_refresh", {"limit": 8})
        with self.f.admin() as conn:
            old = conn.execute(f"SELECT t.status,p.raw_body FROM {self.f.schema}.backfill_tasks_v2 t JOIN {self.f.schema}.backfill_pages_v2 p ON p.task_id=t.id WHERE t.id=%s", (original["id"],)).fetchone()
            self.assertEqual(old["status"], "IDENTITY_OR_QUALITY_UNRESOLVED")
            self.assertEqual(old["raw_body"], original_raw)
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND scope->>'identity_refresh_of'=%s", (self.run, original["id"])).fetchone()["n"], 1)
            validity = {row["task_id"]: row for row in conn.execute(f"SELECT * FROM {self.f.schema}.backfill_identity_output_validity_v2 WHERE task_id=ANY(%s)", ([original["id"], successor["id"]],)).fetchall()}
            self.assertTrue(validity[original["id"]]["identity_invalidated"])
            self.assertTrue(validity[successor["id"]]["identity_material_current"])
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_plan_units_v2 WHERE run_id=%s", (self.run,)).fetchone()["n"], 1)

    def test_stale_source_claim_and_wrong_original_body_cannot_commit(self):
        self.seed_source()
        original = self.derived_claim()
        self.call("backfill_identity_material", {"claim": self.fence(original)})
        claim = self.claim(["retained_identity"])
        source = self.call("backfill_identity_source_read", {"claim": self.fence(claim)})
        payload = prepare_retained_identity_commit(claim, source)
        wrong = dict(payload, raw_body=payload["raw_body"] + " ")
        rejected = self.f.rpc("backfill_identity_source_commit", wrong, actor="worker")
        self.assertFalse(rejected["ok"])
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s", (claim["id"],)).fetchone()["n"], 0)
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s", (claim["id"],))
        newer = self.claim(["retained_identity"], worker="new-proof-worker")
        self.assertGreater(newer["generation"], claim["generation"])
        rejected = self.f.rpc("backfill_identity_source_commit", payload, actor="worker")
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "lease_lost")

    def test_new_current_reference_conflict_invalidates_adjusted_output_and_recomputes_only_affected_unit(self):
        self.seed_source("2025-09-02")
        self.seed_source("2025-09-03")
        original = self.derived_claim()
        self.call("backfill_identity_material", {"claim": self.fence(original)})
        self.prove_next()
        self.prove_next()
        material = self.call("backfill_identity_material", {"claim": self.fence(original)})
        _, original_raw = self.commit_calculation(original, material)
        self.assertIsNotNone(json.loads(original_raw)["rows"][0]["values"]["adjusted_ret_1d"])
        self.commit_current_reference("2025-09-03", {**NATIVE, "share_class_figi": "BBG000000001"})
        with self.f.admin() as conn:
            validity = conn.execute(f"SELECT * FROM {self.f.schema}.backfill_identity_output_validity_v2 WHERE task_id=%s", (original["id"],)).fetchone()
            self.assertTrue(validity["identity_invalidated"])
            conn.execute(f"UPDATE {self.f.schema}.backfill_identity_refresh_v2 SET ready_after=clock_timestamp()-interval '1 second' WHERE run_id=%s", (self.run,))
        successor = self.claim(["derive_daily"], worker="conflict-recalculation")
        self.assertEqual(successor["scope"]["identity_refresh_of"], original["id"])
        changed = self.call("backfill_identity_material", {"claim": self.fence(successor)})
        self.assertEqual(changed["mappings"][0]["state"], RESOLVED)
        self.assertEqual(changed["mappings"][1]["state"], "IDENTITY_OR_QUALITY_UNRESOLVED")
        _, revised_raw = self.commit_calculation(successor, changed)
        revised = json.loads(revised_raw)["rows"][0]
        self.assertIsNone(revised["values"]["adjusted_ret_1d"])
        self.assertIsNotNone(revised["values"]["raw_ret_1d"])
        with self.f.admin() as conn:
            retained = conn.execute(f"SELECT raw_body FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s", (original["id"],)).fetchone()["raw_body"]
            self.assertEqual(retained, original_raw)

    def test_intraday_identity_overlay_preserves_numeric_receipt_without_recalculation_copy(self):
        self.seed_source("2025-09-02")
        claimant = self.derived_claim()
        self.call("backfill_identity_material", {"claim": self.fence(claimant)})
        intraday_id = self.task(kind="derive_intraday", family="D01", provider="DERIVED",
            scope={"member_ids": [MEMBER], "symbols": ["AAPL"], "calendar": CALENDAR[:1],
                   "input_start": "2025-09-02", "target_start": "2025-09-02", "target_end": "2025-09-02"})
        claim = self.claim(["derive_intraday"])
        row = {"symbol": "AAPL", "member_id": MEMBER, "market_date": "2025-09-02",
               "values": {"close": 101.0, "return_1m": .01}, "formula_version": "original-formula-fixture"}
        raw = canonical({"rows": [row]})
        self.call("backfill_commit", {"claim": self.fence(claim), "raw_body": raw, "body_sha256": sha256(raw.encode()).hexdigest(),
            "http_status": 200, "fetched_at": "2026-10-30T06:00:00Z", "request": {"provider": "DERIVED"},
            "records": [row], "next_cursor": None, "quality": [], "headers": {}, "adapter_version": "original-formula-fixture"})
        self.call("backfill_verify", {"claim": self.fence(claim), "page_no": 0})
        self.prove_next()
        with self.f.admin() as conn:
            delivered = conn.execute(f"SELECT identity_status,source_row FROM {self.f.schema}.backfill_family_d01_v2 WHERE task_id=%s", (intraday_id,)).fetchone()
            self.assertEqual(delivered["identity_status"], RESOLVED)
            self.assertEqual(delivered["source_row"]["values"], row["values"])
            self.assertEqual(delivered["source_row"]["formula_version"], "original-formula-fixture")
            self.assertFalse(delivered["source_row"]["current_identity_resolution"]["strict_historical_availability_certified"])
            conn.execute(f"UPDATE {self.f.schema}.backfill_identity_refresh_v2 SET ready_after=clock_timestamp()-interval '1 second' WHERE run_id=%s", (self.run,))
        self.call("backfill_identity_refresh", {"limit": 8})
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND kind='derive_intraday'", (self.run,)).fetchone()["n"], 1)
            self.assertEqual(conn.execute(f"SELECT raw_body FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s", (intraday_id,)).fetchone()["raw_body"], raw)

    def test_discovery_limit_has_persisted_cursor_and_ordinary_claim_continues_it(self):
        # More than one bounded page of source receipts; discovery must never
        # turn its operational size limit into silent archive exhaustion.
        for _ in range(130):
            self.seed_source("2025-09-02")
        claim = self.derived_claim()
        self.call("backfill_identity_material", {"claim": self.fence(claim)})
        with self.f.admin() as conn:
            state = conn.execute(f"SELECT * FROM {self.f.schema}.backfill_identity_discovered_members_v2 WHERE run_id=%s AND member_id=%s", (self.run, MEMBER)).fetchone()
            self.assertEqual(state["discovered_sources"], 128)
            self.assertFalse(state["complete"])
            self.assertTrue(state["after_source_id"])
        next_claim = self.claim(["retained_identity"], worker="discovery-restart-worker")
        self.assertIsNotNone(next_claim)
        with self.f.admin() as conn:
            state = conn.execute(f"SELECT * FROM {self.f.schema}.backfill_identity_discovered_members_v2 WHERE run_id=%s AND member_id=%s", (self.run, MEMBER)).fetchone()
            self.assertEqual(state["discovered_sources"], 130)
            self.assertTrue(state["complete"])
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND kind='retained_identity'", (self.run,)).fetchone()["n"], 130)


if __name__ == "__main__":
    unittest.main()
