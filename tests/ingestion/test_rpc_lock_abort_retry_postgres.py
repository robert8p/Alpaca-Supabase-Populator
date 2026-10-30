"""Real disposable-PG transactions with an explicitly simulated HTTP boundary.

This is not a PostgREST server test and makes no production/provider request.
The opener executes the real isolated authenticated SQL RPC in a fresh
transaction, then represents its native database error using PostgREST's
documented four-field JSON format. Lost acknowledgements occur after commit.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from astra_ingestion import rpc_store as rpc
from astra_ingestion.backfill_worker_v2 import BackfillWorker
from astra_ingestion.store import LeaseLost
import test_backfill_claim_capability_filter_v2 as base
import test_backfill_planner_v2 as planner
from test_rpc_lock_abort_retry import ENDPOINT, SECRET, error_response
from test_rpc_store import PUBLIC_KEY, Reply

ROOT = Path(__file__).resolve().parents[2]
LIVE_SOURCE_CAPTURES = (
    ("review/recovery-v74/retry_closure_root_definitions_v74.json",
     "2703407b0831de5ee13a96406964a44e8dd54b809b56b47cae1f958c2f976e61", "functions"),
    ("review/recovery-v74/retry_closure_callees_and_catalog_v74.json",
     "74d74e5384fbb136ecebecee81583b45dec706ec9668da2fc7645ddfc851420f", "selected_functions"),
)
GATE = 706314020261028
LATE_GATE = 706314020269974
RESULT = {"layers": {"postgresql": "ACTUAL_DISPOSABLE", "http": "SIMULATED_DOCUMENTED_POSTGREST_ENVELOPE",
                     "postgrest_server": "NOT_RUN", "production": "NOT_RUN"}, "cases": {}}


class DatabaseOpener:
    """Test-only adapter; runtime still sends the fixed production-origin URL."""
    def __init__(self, case, *, before=None, after_abort=None, lose_ack=None):
        self.case = case
        self.before = before
        self.after_abort = after_abort
        self.lose_ack = lose_ack
        self.calls = []
        self.errors = []
        self.transactions = []

    def open(self, request, timeout):
        case = self.case
        case.assertEqual(request.full_url, ENDPOINT)
        case.assertEqual(request.get_method(), "POST")
        document = json.loads(request.data)
        operation = document["operation"]
        self.calls.append((operation, request.data, timeout))
        if self.before:
            self.before(operation)
        # f.rpc creates, commits/rolls back and closes a different connection
        # for every attempt, with the actual gateway role and capability checks.
        try:
            envelope = case.f.rpc(operation, document["payload"], actor="worker",
                                  token=request.get_header("X-astra-ingestion-token"))
        except case.f.psycopg.Error as error:
            code = error.sqlstate
            self.errors.append((operation, code))
            self.transactions.append("ROLLED_BACK")
            response, _ = error_response(
                status=401 if code == "PT401" else 403 if code == "PT403" else 500,
                value={"code": code, "message": error.diag.message_primary,
                       "details": error.diag.message_detail, "hint": error.diag.message_hint})
            if self.after_abort:
                self.after_abort(operation, code)
            raise response from None
        self.transactions.append("COMMITTED")
        if operation == self.lose_ack:
            raise TimeoutError(SECRET)
        return Reply(raw=json.dumps(envelope).encode())


class ReferenceProvider:
    def __init__(self, case):
        self.case = case
        self.fetch_count = 0
        self.last_payload = None

    def supported_kinds(self):
        return ("alpaca_reference",)

    def require_credentials(self, _claim):
        pass

    def fetch(self, claim):
        self.fetch_count += 1
        payload = self.case.page(claim)
        self.last_payload = {k: value for k, value in payload.items() if k != "claim"}
        return SimpleNamespace(records=payload["records"], body_sha256=payload["body_sha256"],
                               payload=lambda: self.last_payload)


class PostgreSQLAdmissionTests(unittest.TestCase):
    def test_missing_dsn_is_an_error_in_dedicated_ingestion_gate(self):
        with patch.dict(os.environ, {"GITHUB_WORKFLOW": "ASTRA ingestion qualification"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ASTRA_INGESTION_POSTGRES_TEST_URL is required"):
                PostgreSQLLockAbortTests.setUpClass()

    def test_missing_dsn_is_an_explicit_skip_in_other_contexts(self):
        for workflow in (None, "release-gate"):
            with self.subTest(workflow=workflow):
                values = {} if workflow is None else {"GITHUB_WORKFLOW": workflow}
                with patch.dict(os.environ, values, clear=True):
                    with self.assertRaisesRegex(unittest.SkipTest, "dedicated ASTRA ingestion qualification gate"):
                        PostgreSQLLockAbortTests.setUpClass()


class PostgreSQLLockAbortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL"):
            if os.environ.get("GITHUB_WORKFLOW") == "ASTRA ingestion qualification":
                raise RuntimeError("ASTRA_INGESTION_POSTGRES_TEST_URL is required by ASTRA ingestion qualification")
            raise unittest.SkipTest("Disposable PostgreSQL is exercised by the dedicated ASTRA ingestion qualification gate")
        base.CapabilityFilterPostgreSQLTests.setUpClass.__func__(cls)
        f = cls.fixture("runTest")
        cls.live_rows = []
        for relative, expected, key in LIVE_SOURCE_CAPTURES:
            raw = (ROOT / relative).read_bytes()
            if sha256(raw).hexdigest() != expected:
                raise AssertionError("Frozen live function capture changed")
            rows = json.loads(raw)[0][key]
            for row in rows:
                if sha256(row["definition"].encode()).hexdigest() != row["source_sha256"]:
                    raise AssertionError("Captured function source does not match its pin")
            cls.live_rows.extend(rows)
        with f.admin() as conn:
            # Build the established disposable planner dependencies first,
            # then install the exact freshly captured roots and callees.
            # Only fixture identifiers/retained-source relations change.
            for filename in ("astra_backfill_planner_v2.sql", "astra_backfill_planner_batch_v2.sql",
                             "astra_backfill_adaptive_pages_v2.sql"):
                conn.execute(cls.rewrite((ROOT / "sql" / filename).read_text()))
            for row in cls.live_rows:
                definition = cls.rewrite(row["definition"])
                definition = definition.replace("public.astra_ingestion_rpc_v1", "public." + f.endpoint)
                definition = re.sub(r"\banon\b", f.gateway, definition)
                conn.execute(definition)
            RESULT["postgresql_version"] = conn.execute("SHOW server_version").fetchone()["server_version"]
            conn.execute(f"CREATE TABLE {f.schema}.retry_fault_probe(id bigint GENERATED ALWAYS AS IDENTITY, note text)")
        cls.production_normalization = dict(sorted(
            [(after, before) for before, after in cls.replacements] + [
            ("public." + f.endpoint, "public.astra_ingestion_rpc_v1"),
            (f.schema, "astra_ingestion_v1"), (f.owner, "astra_ingestion_rpc_owner_v1"),
            (f.gateway, "anon"), (f.auth_schema, "auth")], key=lambda item: len(item[0]), reverse=True))
        RESULT["fixture_construction"] = {
            "planner": "published planner and one-member batch forwards",
            "page_limit": "unchanged published adaptive-page schema, guard and wiring",
            "functions": "six live roots and eighteen live callees; exact captured sources",
            "identifier_substitutions": "reverse the established fixture's explicit replacements for source hashing",
            "source_admission": "all twenty-four normalized definitions must match their fresh live pins",
            "unexecuted_branches": "no relay, provider, production, or old-estate formula execution",
        }

    rewrite = classmethod(base.CapabilityFilterPostgreSQLTests.rewrite.__func__)
    full_query = staticmethod(base.CapabilityFilterPostgreSQLTests.full_query)
    task = base.CapabilityFilterPostgreSQLTests.task
    call = base.CapabilityFilterPostgreSQLTests.call
    claim = base.CapabilityFilterPostgreSQLTests.claim
    page = base.CapabilityFilterPostgreSQLTests.page
    fence = staticmethod(base.CapabilityFilterPostgreSQLTests.fence)

    def setUp(self):
        # The old capability fixture's per-test setup reinstalls an earlier
        # wrapper. Use its unchanged base data fixture while retaining the
        # freshly captured function definitions installed above.
        base.runtime.BackfillRuntimeTests.setUp(self)
        with self.f.admin() as conn:
            conn.execute(f"DROP TRIGGER IF EXISTS retry_fixture_fault ON {self.f.schema}.backfill_runs_v2")
            conn.execute(f"TRUNCATE {self.f.schema}.retry_fault_probe RESTART IDENTITY")
        self.enterContext(patch.object(rpc, "sleep", lambda _delay: None))

    def store(self, **kwargs):
        opener = DatabaseOpener(self, **kwargs)
        return rpc.RpcStore(rpc.PROJECT_URL, PUBLIC_KEY, self.f.tokens["worker"], opener=opener), opener

    def totals(self):
        with self.f.admin() as conn:
            run = dict(conn.execute(f"SELECT pages_committed,records_committed,requests_reserved FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s", (self.run,)).fetchone())
            run["readbacks"] = conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_readbacks_v2 WHERE run_id=%s", (self.run,)).fetchone()["n"]
            return run

    def hold(self, key=GATE):
        conn = self.f.admin()
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
        self.addCleanup(conn.close)
        return conn

    def release(self, conn):
        if not conn.closed:
            conn.rollback()
            conn.close()

    def fault(self, statement):
        with self.f.admin() as conn:
            conn.execute(f'''CREATE OR REPLACE FUNCTION {self.f.schema}.retry_fixture_fault_fn()
                RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $test$
                BEGIN
                  IF NEW.pages_committed>OLD.pages_committed THEN
                    INSERT INTO {self.f.schema}.retry_fault_probe(note) VALUES('late transactional fault reached');
                    {statement}
                  END IF;
                  RETURN NEW;
                END $test$''')
            conn.execute(f'''CREATE TRIGGER retry_fixture_fault AFTER UPDATE ON {self.f.schema}.backfill_runs_v2
                             FOR EACH ROW EXECUTE FUNCTION {self.f.schema}.retry_fixture_fault_fn()''')

    def normalized(self, definition):
        for before, after in self.production_normalization.items():
            definition = definition.replace(before, after)
        return definition

    def test_exact_auth_private_source_contract_and_native_gate_retry(self):
        self.task()
        with self.f.admin() as conn:
            sources = {}
            catalog = conn.execute('''SELECT p.proname,pg_get_function_identity_arguments(p.oid) args,
                pg_get_functiondef(p.oid) definition,p.provolatile,p.prosecdef,p.proconfig
                FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname=%s OR (n.nspname='public' AND p.proname=%s)
                ORDER BY n.nspname,p.proname,p.oid''', (self.f.schema, self.f.endpoint)).fetchall()
            RESULT["normalized_function_catalog"] = [{
                "name": "public.astra_ingestion_rpc_v1" if row["proname"] == self.f.endpoint else "astra_ingestion_v1." + row["proname"],
                "identity_arguments": self.normalized(row["args"]),
                "definition": self.normalized(row["definition"]),
                "sha256": sha256(self.normalized(row["definition"]).encode()).hexdigest(),
                "volatility": row["provolatile"], "security_definer": row["prosecdef"], "config": row["proconfig"],
            } for row in catalog]
            RESULT["normalized_trigger_catalog"] = [{
                "table": self.normalized(row["table_name"]), "name": row["tgname"], "enabled": row["tgenabled"],
                "definition": self.normalized(row["definition"]),
                "function": self.normalized(row["function_name"]),
            } for row in conn.execute('''SELECT c.oid::regclass::text table_name,t.tgname,t.tgenabled,
                pg_get_triggerdef(t.oid,true) definition,t.tgfoid::regprocedure::text function_name
                FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=%s AND NOT t.tgisinternal ORDER BY c.relname,t.tgname''', (self.f.schema,))]
            for row in self.live_rows:
                signature = self.rewrite(row["signature"]).replace(
                    "public.astra_ingestion_rpc_v1", "public." + self.f.endpoint)
                definition = conn.execute("SELECT pg_get_functiondef(%s::regprocedure) d", (signature,)).fetchone()["d"]
                actual = sha256(self.normalized(definition).encode()).hexdigest()
                self.assertEqual(actual, row["source_sha256"], row["signature"])
                self.assertNotIn("response.status", definition)
                sources[row["signature"]] = actual
            RESULT["exact_dispatch_pins"] = sources
        before = self.totals()
        holder = self.hold()
        def aborted(operation, code):
            self.assertEqual((operation, code), ("backfill_claim", "55P03"))
            self.assertEqual(self.totals(), before)
            self.release(holder)
        store, opener = self.store(after_abort=aborted)
        claim = store._call("backfill_claim", {"worker_id": "retry-worker", "lease_seconds": 90,
            "supported_kinds": ["alpaca_reference"], "source_revision": "fixture"})
        self.assertEqual(claim["generation"], 1)
        self.assertEqual(claim["page_attempts"], 1)
        self.assertEqual(opener.transactions, ["ROLLED_BACK", "COMMITTED"])
        self.assertEqual(opener.calls[0][1], opener.calls[1][1])
        RESULT["cases"]["native_outer_gate"] = {"sqlstate": "55P03", "transaction_outcomes": opener.transactions,
            "claim_generation": 1, "page_attempts": 1, "provider_calls": 0}

    def test_late_native_abort_rolls_back_writes_and_commit_fetches_once(self):
        task = self.task()
        self.fault(f"PERFORM pg_advisory_xact_lock({LATE_GATE});")
        holder = self.hold(LATE_GATE)
        reached = []
        def aborted(operation, code):
            self.assertEqual((operation, code), ("backfill_commit", "55P03"))
            self.assertEqual(self.totals(), {"pages_committed": 0, "records_committed": 0, "requests_reserved": 1, "readbacks": 0})
            with self.f.admin() as conn:
                self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.retry_fault_probe").fetchone()["n"], 0)
                self.assertTrue(conn.execute(f"SELECT is_called FROM {self.f.schema}.retry_fault_probe_id_seq").fetchone()["is_called"])
                row = conn.execute(f"SELECT page_no,status,records_committed FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s", (task,)).fetchone()
                self.assertEqual(row, {"page_no": 0, "status": "RUNNING", "records_committed": 0})
            reached.append(True)
            self.release(holder)
        store, opener = self.store(after_abort=aborted)
        provider = ReferenceProvider(self)
        BackfillWorker(store, provider, worker_id="retry-worker").run_once()
        self.assertEqual(reached, [True])
        self.assertEqual(provider.fetch_count, 1)
        self.assertEqual(self.totals(), {"pages_committed": 1, "records_committed": 1, "requests_reserved": 1, "readbacks": 1})
        commits = [data for operation, data, _ in opener.calls if operation == "backfill_commit"]
        self.assertEqual(len(commits), 2)
        self.assertEqual(commits[0], commits[1])
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.retry_fault_probe").fetchone()["n"], 1)
        RESULT["cases"]["late_native_commit_abort"] = {"sqlstate": "55P03", "rolled_back_after_writes": True,
            "same_commit_bytes": True, "provider_fetches": 1, "final": self.totals(), "sequence_gap_expected": True}

    def test_committed_but_lost_ack_is_never_retried(self):
        self.task()
        store, opener = self.store(lose_ack="backfill_commit")
        provider = ReferenceProvider(self)
        with self.assertRaises(rpc.RpcPersistenceError) as caught:
            BackfillWorker(store, provider, worker_id="retry-worker").run_once()
        self.assertEqual(caught.exception.rpc_failure_reason, "TRANSPORT_ERROR")
        self.assertEqual(provider.fetch_count, 1)
        self.assertEqual([operation for operation, _, _ in opener.calls], ["backfill_claim", "backfill_reserve", "backfill_commit"])
        self.assertEqual(opener.transactions, ["COMMITTED"] * 3)
        self.assertEqual(self.totals(), {"pages_committed": 1, "records_committed": 1, "requests_reserved": 1, "readbacks": 0})
        RESULT["cases"]["committed_lost_ack"] = {"actual_commit": True, "resends": 0, "provider_fetches": 1,
            "fatal_reason": caught.exception.rpc_failure_reason, "final": self.totals()}

    def test_reserved_but_lost_ack_never_fetches(self):
        self.task()
        store, opener = self.store(lose_ack="backfill_reserve")
        provider = ReferenceProvider(self)
        with self.assertRaises(rpc.RpcPersistenceError):
            BackfillWorker(store, provider, worker_id="retry-worker").run_once()
        self.assertEqual(provider.fetch_count, 0)
        self.assertEqual([operation for operation, _, _ in opener.calls], ["backfill_claim", "backfill_reserve"])
        self.assertEqual(self.totals(), {"pages_committed": 0, "records_committed": 0, "requests_reserved": 1, "readbacks": 0})
        RESULT["cases"]["reservation_lost_ack"] = {"resends": 0, "provider_fetches": 0, "reservation_count": 1}

    def test_retry_rechecks_real_authority_and_never_renews_or_refetches(self):
        cases = ("owner", "generation", "run_fence", "lease", "run_paused", "credential_revoked", "credential_expired")
        checked = []
        for index, condition in enumerate(cases):
            with self.subTest(condition=condition):
                if index:
                    self.setUp()
                task = self.task()
                self.fault("RAISE EXCEPTION USING ERRCODE='55P03',MESSAGE='synthetic late abort for authority transition';")
                def aborted(operation, code):
                    self.assertEqual((operation, code), ("backfill_commit", "55P03"))
                    with self.f.admin() as conn:
                        conn.execute(f"DROP TRIGGER retry_fixture_fault ON {self.f.schema}.backfill_runs_v2")
                        if condition == "owner":
                            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET owner='another-worker' WHERE id=%s", (task,))
                        elif condition == "generation":
                            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET generation=generation+1 WHERE id=%s", (task,))
                        elif condition == "run_fence":
                            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET fence=fence+1 WHERE id=%s", (self.run,))
                        elif condition == "lease":
                            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s", (task,))
                        elif condition == "run_paused":
                            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED' WHERE id=%s", (self.run,))
                        elif condition == "credential_revoked":
                            conn.execute(f"UPDATE {self.f.schema}.runtime_credentials SET revoked_at=clock_timestamp() WHERE actor='worker'")
                        elif condition == "credential_expired":
                            conn.execute(f"UPDATE {self.f.schema}.runtime_credentials SET created_at=clock_timestamp()-interval '2 seconds',expires_at=clock_timestamp()-interval '1 second' WHERE actor='worker'")
                store, opener = self.store(after_abort=aborted)
                # Later authentication failure is not an abort eligible for a
                # third retry, and must not rerun this transition callback.
                original_callback = opener.after_abort
                opener.after_abort = lambda operation, code: original_callback(operation, code) if code == "55P03" else None
                provider = ReferenceProvider(self)
                if condition.startswith("credential"):
                    with self.assertRaises(rpc.RpcAuthenticationError):
                        BackfillWorker(store, provider, worker_id="retry-worker").run_once()
                else:
                    outcome = BackfillWorker(store, provider, worker_id="retry-worker").run_once()
                    self.assertEqual(outcome["state"], "ownership_lost")
                self.assertEqual(provider.fetch_count, 1)
                self.assertEqual(len([1 for operation, _, _ in opener.calls if operation == "backfill_commit"]), 2)
                self.assertEqual(self.totals()["pages_committed"], 0)
                self.assertEqual(self.totals()["requests_reserved"], 1)
                checked.append(condition)
        RESULT["cases"]["authority_rechecks"] = checked

    def test_planner_gate_abort_retries_without_advancing_cursor_twice(self):
        # This supplies the real frozen member list/calendar through the
        # established planner fixture, without weakening production guards.
        planner.BackfillPlannerTests.setUp(self)
        holder = self.hold()
        before = self.totals()
        def aborted(operation, code):
            self.assertEqual((operation, code), ("backfill_plan_next", "55P03"))
            self.assertEqual(self.totals(), before)
            with self.f.admin() as conn:
                self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s", (self.run,)).fetchone()["n"], 0)
            self.release(holder)
        store, opener = self.store(after_abort=aborted)
        result = store._call("backfill_plan_next", {"run_id": self.run, "member_limit": 1,
            "supported_kinds": planner.KINDS, "capability_revision": "retry-fixture"})
        self.assertEqual(result["planned_members"], 1)
        self.assertEqual(result["next_selection_order"], 2)
        self.assertEqual(opener.transactions, ["ROLLED_BACK", "COMMITTED"])
        self.assertEqual(opener.calls[0][1], opener.calls[1][1])
        self.assertEqual(self.totals()["requests_reserved"], 0)
        RESULT["cases"]["planner_native_gate"] = {"sqlstate": "55P03", "planned_members": 1,
            "next_selection_order": 2, "provider_requests": 0, "transaction_outcomes": opener.transactions}


if __name__ == "__main__":
    unittest.main()
