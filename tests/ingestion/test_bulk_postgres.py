"""Isolated PostgreSQL qualification; NEVER accepts a production DSN.

The production SQL is applied to newly generated local schemas with synthetic
source data. Only source schema names and synthetic evidence pins are replaced;
all validation, inserts, immutable receipt logic and privilege checks are real.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit
import uuid

from astra_ingestion.bulk_scope import FAMILIES, COHORT_SHA256, ACCEPTANCE_SHA256, CONTRACT_SET_SHA256

URL = os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL", "")
ROOT = Path(__file__).resolve().parents[2]
SCOPE_ID = "corrected_company_scope_8e6ca1178f03822c"
SQL_PATH = ROOT / "sql" / "astra_ingestion_bulk_scope_v1.sql"
REPAIR_PATH = ROOT / "sql" / "astra_ingestion_bulk_scope_catalogue_fix_v1.sql"
FORWARD_PATH = ROOT / "sql" / "astra_ingestion_bulk_scope_no_campaign_cutoff_v2.sql"


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@unittest.skipUnless(URL, "PostgreSQL bulk qualification NOT_RUN: explicit local test URL absent")
class BulkPostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = urlsplit(URL)
        if (target.scheme not in {"postgres", "postgresql"}
            or target.hostname not in {"localhost", "127.0.0.1", "::1"}
            or unquote(target.path) != "/astra_ingestion_qualification"
            or target.query or target.fragment):
            raise RuntimeError("bulk tests require disposable loopback astra_ingestion_qualification")
        import psycopg
        cls.pg = psycopg

    def setUp(self):
        token = uuid.uuid4().hex[:12]
        self.dst = "astra_ingestion_bulk_test_" + token
        self.src = "astra_ingestion_source_test_" + token
        self.role = "astra_bulk_reader_test_" + token
        self.conn = self.pg.connect(URL, autocommit=True)
        self.addCleanup(self.cleanup)
        self.conn.execute(f"CREATE SCHEMA {self.dst}; CREATE SCHEMA {self.src}")
        self.conn.execute(f"""
         CREATE TABLE {self.src}.catalog_scope(scope_id text,payload_text text,payload_sha256 text);
         CREATE TABLE {self.src}.ref01_practical_snapshot_v1(snapshot_sha256 text,content jsonb);
         CREATE TABLE {self.src}.ref01_practical_membership_v1(snapshot_sha256 text,acceptance_sha256 text,
           content jsonb,root_acceptance_event_id bigint,independent_review_event_id bigint);
         CREATE TABLE {self.src}.working_accepted_companies_v1(company_id text,selection_order integer,
           cohort_sha256 text,membership_acceptance_sha256 text,membership_accepted boolean,
           exact_global_rank_certified boolean,financial_capitalization_qualified boolean,
           full_period_instrument_coverage_accepted boolean);
         CREATE TABLE {self.src}.catalog_family_contract(scope_id text,family_id text,contract_text text,contract_sha256 text);
         CREATE TABLE {self.src}.catalog_calendar(scope_id text,session_date date,regular_scheduled_minutes integer,
           source_record_text text,source_record_sha256 text,source_receipt_text text,source_receipt_sha256 text);
         CREATE TABLE {self.src}.catalog_d06_preservation(scope_id text,relation_name text,metadata_text text,metadata_sha256 text,
           preservation_state text);
         CREATE TABLE {self.src}.pipeline_event(event_id bigint,event text,details jsonb);
        """)
        source = '{"scope":"synthetic-only"}'
        self.conn.execute(f"INSERT INTO {self.src}.catalog_scope VALUES(%s,%s,%s)", (SCOPE_ID,source,digest(source)))
        cohort_doc = json.dumps({"companies": ["synthetic"], "not_a_real_population": True})
        cohort = self.conn.execute("SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(cohort_doc,)).fetchone()[0]
        member_doc = json.dumps({"membership_accepted": True,"company_count":3000,"membership_only":True})
        acceptance = self.conn.execute("SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(member_doc,)).fetchone()[0]
        self.conn.execute(f"INSERT INTO {self.src}.ref01_practical_snapshot_v1 VALUES(%s,%s::jsonb)",(cohort,cohort_doc))
        self.conn.execute(f"INSERT INTO {self.src}.ref01_practical_membership_v1 VALUES(%s,%s,%s::jsonb,24407,23872)",(cohort,acceptance,member_doc))
        self.conn.execute(f"INSERT INTO {self.src}.working_accepted_companies_v1 SELECT 'synthetic-'||n,n,%s,%s,true,false,false,false FROM generate_series(1,3000)n",(cohort,acceptance))
        contracts=[]
        for family in FAMILIES:
            text=json.dumps({"dependencies":[],"family":family})
            contracts.append((SCOPE_ID,family,text,digest(text)))
        with self.conn.cursor() as cur:
            cur.executemany(f"INSERT INTO {self.src}.catalog_family_contract VALUES(%s,%s,%s,%s)",contracts)
        contract_hash=digest("\n".join(f+":"+h for _,f,_,h in sorted(contracts,key=lambda r:r[1])))
        self.conn.execute(f"""INSERT INTO {self.src}.catalog_calendar
         SELECT %s,d::date,390,'{{}}',%s,'{{}}',%s
         FROM generate_series('2026-08-03'::timestamp,'2026-09-30'::timestamp,'1 day')d
         WHERE extract(isodow from d)<6 AND d::date != '2026-09-07'::date""",(SCOPE_ID,digest('{}'),digest('{}')))
        self.conn.execute(f"INSERT INTO {self.src}.catalog_d06_preservation SELECT %s,'preserved-'||n,'{{}}',%s,'PENDING_EXACT_HASH_CATALOGUE' FROM generate_series(1,1065)n",(SCOPE_ID,digest('{}')))
        self.conn.execute(f"INSERT INTO {self.src}.pipeline_event VALUES(24407,'ROOT_PRACTICAL_COHORT_MEMBERSHIP_ACCEPTANCE_V1',%s::jsonb),(23872,'synthetic-review','{{}}')",(json.dumps({"snapshot_sha256":cohort,"membership_only":True}),))
        preservation_hash=digest("\n".join("preserved-"+str(n)+":"+digest('{}') for n in sorted(range(1,1066),key=lambda n:'preserved-'+str(n))))
        sql = SQL_PATH.read_text() + "\n" + REPAIR_PATH.read_text()
        self.fixture_rewrites=(("astra_ingestion_v1",self.dst),("population_top3000_202608_202609_v1",self.src),
                        (COHORT_SHA256,cohort),(ACCEPTANCE_SHA256,acceptance),(CONTRACT_SET_SHA256,contract_hash),
                        ("87e623c92ea90cc14c8ead2e6141184978542ba0876a9f603317f99f7e3daf4f",preservation_hash),
                        ("969bab3ac1a4348958e6c2cc501462f4ec1bb35cc500779b4327bab17a46835e",digest(source)),
                        ("2026-11-05T02:00:00Z","2099-11-05T02:00:00Z"))
        for old,new in self.fixture_rewrites:
            self.assertIn(old,sql)
            sql=sql.replace(old,new)
        self.conn.execute(sql)

    def cleanup(self):
        try:
            self.conn.execute("RESET ROLE")
            for name in (self.dst,self.src):
                if not re.fullmatch(r"astra_ingestion_(bulk|source)_test_[a-f0-9]{12}",name):
                    raise AssertionError("refusing non-test cleanup")
                self.conn.execute(f"DROP SCHEMA IF EXISTS {name} CASCADE")
            if re.fullmatch(r"astra_bulk_reader_test_[a-f0-9]{12}",self.role):
                self.conn.execute(f"DROP ROLE IF EXISTS {self.role}")
        finally:
            self.conn.close()

    def capture(self, run="synthetic-bulk-001", isolation="REPEATABLE READ"):
        with self.conn.transaction():
            self.conn.execute("SET TRANSACTION ISOLATION LEVEL " + isolation)
            self.conn.execute("SET LOCAL statement_timeout='15s'")
            return self.conn.execute(f"SELECT {self.dst}.capture_retained_top3000_scope_v1(%s)",(run,)).fetchone()[0]

    def counts(self):
        return self.conn.execute(f"SELECT (SELECT count(*) FROM {self.dst}.bulk_scope_capture_v1),(SELECT count(*) FROM {self.dst}.bulk_scope_evidence_v1)").fetchone()


    def forward_migration_sql(self):
        """Use identical throwaway schema/pins as the installed test function."""
        sql = FORWARD_PATH.read_text()
        for old,new in self.fixture_rewrites:
            sql = sql.replace(old,new)
        return sql

    def test_forward_cutoff_removal_preserves_capture_and_reconciliation(self):
        original_receipt = self.capture()
        original_body = self.conn.execute(
            f"SELECT prosrc FROM pg_proc WHERE oid=to_regprocedure('{self.dst}.capture_retained_top3000_scope_v1(text)')"
        ).fetchone()[0]
        old_guard = (" IF clock_timestamp() >= '2099-11-05T02:00:00Z'::timestamptz THEN\\n"
                     "   RAISE EXCEPTION 'completion campaign deadline reached';\\n END IF;\\n")
        self.assertEqual(original_body.count(old_guard),1)
        self.conn.execute(self.forward_migration_sql())
        changed_body = self.conn.execute(
            f"SELECT prosrc FROM pg_proc WHERE oid=to_regprocedure('{self.dst}.capture_retained_top3000_scope_v1(text)')"
        ).fetchone()[0]
        self.assertEqual(changed_body,original_body.replace(old_guard,""))
        self.assertEqual(self.counts(),(1,4136))
        self.assertEqual(self.capture("synthetic-post-forward-reconcile"),original_receipt)
        self.assertEqual(self.counts(),(1,4136))
        with self.assertRaisesRegex(Exception,"body drift"):
            self.conn.execute(self.forward_migration_sql())
        self.conn.execute("ROLLBACK")
        self.assertEqual(self.counts(),(1,4136))

    def test_forward_cutoff_removal_refuses_uncaptured_destination(self):
        with self.assertRaisesRegex(Exception,"required immutable capture receipt"):
            self.conn.execute(self.forward_migration_sql())
        self.conn.execute("ROLLBACK")
        self.assertEqual(self.counts(),(0,0))

    def test_forward_cutoff_removal_refuses_changed_installation(self):
        self.capture()
        original = self.conn.execute(
            f"SELECT pg_get_functiondef('{self.dst}.capture_retained_top3000_scope_v1(text)'::regprocedure)"
        ).fetchone()[0]
        needle="capture requires a consistent repeatable-read transaction"
        self.assertEqual(original.count(needle),1)
        self.conn.execute(original.replace(needle,needle+" altered"))
        before=self.conn.execute(
            f"SELECT prosrc FROM pg_proc WHERE oid=to_regprocedure('{self.dst}.capture_retained_top3000_scope_v1(text)')"
        ).fetchone()[0]
        with self.assertRaisesRegex(Exception,"body drift"):
            self.conn.execute(self.forward_migration_sql())
        self.conn.execute("ROLLBACK")
        after=self.conn.execute(
            f"SELECT prosrc FROM pg_proc WHERE oid=to_regprocedure('{self.dst}.capture_retained_top3000_scope_v1(text)')"
        ).fetchone()[0]
        self.assertEqual(before,after)
        self.assertEqual(self.counts(),(1,4136))

    def test_atomic_full_capture_replay_preserves_receipt(self):
        first=self.capture()
        self.assertEqual(first["evidence_rows"],4136)
        self.assertEqual(first["provider_requests"],0)
        self.assertEqual(first["state"],"CAPTURED_NOT_ADMITTED")
        self.assertEqual(first["historical_coverage"],"NOT_CERTIFIED")
        self.assertEqual(self.counts(),(1,4136))
        self.assertEqual(first,self.capture("synthetic-bulk-reconciliation"))
        self.assertEqual(self.counts(),(1,4136))
        kinds=dict(self.conn.execute(f"SELECT kind,count(*) FROM {self.dst}.bulk_scope_evidence_v1 GROUP BY kind").fetchall())
        self.assertEqual(kinds["company"],3000)
        self.assertEqual(kinds["contract"],24)
        self.assertEqual(kinds["calendar"],42)
        self.assertEqual(kinds["preservation"],1065)

    def test_simulated_client_loss_after_commit_reconciles_without_replay(self):
        first=self.capture()
        # Discard caller result and connection after a real atomic DB commit.
        self.conn.close()
        self.conn=self.pg.connect(URL,autocommit=True)
        self.assertEqual(first,self.capture("synthetic-replacement-run"))
        self.assertEqual(self.counts(),(1,4136))

    def test_inconsistent_transaction_denied(self):
        with self.assertRaisesRegex(Exception,"repeatable-read"):
            self.capture(isolation="READ COMMITTED")
        self.assertEqual(self.counts(),(0,0))

    def test_source_corruption_cases_fail_and_leave_no_partial_evidence(self):
        changes = [
          ("scope source drift",f"UPDATE {self.src}.catalog_scope SET payload_text='{{\"changed\":true}}'"),
          ("cohort source drift",f"UPDATE {self.src}.ref01_practical_snapshot_v1 SET content='{{}}'"),
          ("membership source drift",f"UPDATE {self.src}.ref01_practical_membership_v1 SET content='{{}}'"),
          ("root acceptance",f"UPDATE {self.src}.pipeline_event SET event='wrong' WHERE event_id=24407"),
          ("membership count",f"DELETE FROM {self.src}.working_accepted_companies_v1 WHERE selection_order=1"),
          ("membership count",f"UPDATE {self.src}.working_accepted_companies_v1 SET company_id='duplicate' WHERE selection_order IN (1,2)"),
          ("membership count",f"UPDATE {self.src}.working_accepted_companies_v1 SET cohort_sha256=NULL WHERE selection_order=1"),
          ("membership count",f"UPDATE {self.src}.working_accepted_companies_v1 SET financial_capitalization_qualified=true WHERE selection_order=1"),
          ("contract set drift",f"UPDATE {self.src}.catalog_family_contract SET contract_text='{{}}' WHERE family_id='P01'"),
          ("contract set drift",f"DELETE FROM {self.src}.catalog_family_contract WHERE family_id='CTX14'"),
          ("calendar count",f"UPDATE {self.src}.catalog_calendar SET source_record_text='bad' WHERE session_date='2026-08-03'"),
          ("preservation catalogue",f"UPDATE {self.src}.catalog_d06_preservation SET metadata_text='bad' WHERE relation_name='preserved-1'"),
          ("preservation catalogue",f"DELETE FROM {self.src}.catalog_d06_preservation WHERE relation_name='preserved-1065'"),
          ("preservation catalogue",f"UPDATE {self.src}.catalog_d06_preservation SET relation_name='re-keyed' WHERE relation_name='preserved-1'"),
          ("capture boundary",f"DELETE FROM {self.src}.pipeline_event WHERE event_id=23872"),
        ]
        for expected,query in changes:
            with self.subTest(expected=expected,query=query),self.conn.transaction(force_rollback=True):
                self.conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                self.conn.execute(query)
                with self.assertRaisesRegex(Exception,expected),self.conn.transaction():
                    self.conn.execute(f"SELECT {self.dst}.capture_retained_top3000_scope_v1('synthetic-negative-control')")
            self.assertEqual(self.counts(),(0,0))

    def test_catalogue_patch_cannot_be_reapplied_after_capture(self):
        self.capture()
        # The migration guard is exercised without replacing function source.
        guard=REPAIR_PATH.read_text().split('CREATE OR REPLACE FUNCTION')[0].replace('astra_ingestion_v1',self.dst)
        with self.assertRaisesRegex(Exception,'requires empty reconciled destination'):
            self.conn.execute(guard)
        self.assertEqual(self.counts(),(1,4136))

    def test_changed_source_after_capture_never_overwrites_accepted_receipt(self):
        first=self.capture()
        self.conn.execute(f"UPDATE {self.src}.catalog_calendar SET source_receipt_text='changed' WHERE session_date='2026-08-03'")
        with self.assertRaisesRegex(Exception,"calendar count"):
            self.capture("synthetic-retry-after-drift")
        stored=self.conn.execute(f"SELECT to_jsonb(c) FROM {self.dst}.bulk_scope_capture_v1 c").fetchone()[0]
        self.assertEqual(first,stored)
        self.assertEqual(self.counts(),(1,4136))

    def test_no_update_delete_truncate_even_by_capture_owner(self):
        self.capture()
        for table in ("bulk_scope_capture_v1","bulk_scope_evidence_v1"):
            for command in (f"UPDATE {self.dst}.{table} SET capture_key=capture_key",f"DELETE FROM {self.dst}.{table}",f"TRUNCATE {self.dst}.{table} CASCADE"):
                with self.subTest(command=command),self.assertRaisesRegex(Exception,"immutable"):
                    self.conn.execute(command)
        self.assertEqual(self.counts(),(1,4136))

    def test_restricted_actor_cannot_read_insert_or_invoke(self):
        self.capture()
        self.conn.execute(f"CREATE ROLE {self.role} NOLOGIN NOSUPERUSER NOBYPASSRLS")
        self.conn.execute(f"GRANT USAGE ON SCHEMA {self.dst} TO {self.role}")
        self.conn.execute(f"GRANT SELECT ON {self.dst}.bulk_scope_capture_v1,{self.dst}.bulk_scope_evidence_v1 TO {self.role}")
        self.conn.execute(f"SET ROLE {self.role}")
        self.assertEqual(self.counts(),(0,0))  # actual RLS enforcement, not only ACL introspection
        with self.assertRaisesRegex(Exception,"permission denied"):
            self.capture("synthetic-forbidden-actor")
        with self.assertRaisesRegex(Exception,"permission denied"):
            self.conn.execute(f"INSERT INTO {self.dst}.bulk_scope_capture_v1(capture_key,first_run_id,evidence_rows,evidence_sha256) VALUES('bad','bad',1,%s)",('a'*64,))
        self.conn.execute("RESET ROLE")
        self.assertEqual(self.counts(),(1,4136))

    def test_forged_source_hash_fails_database_constraint(self):
        with self.assertRaisesRegex(Exception,"check constraint"):
            self.conn.execute(f"INSERT INTO {self.dst}.bulk_scope_evidence_v1(capture_key,kind,evidence_key,source_text,source_sha256) VALUES('bad','company','bad','{{}}',%s)",('a'*64,))
        self.assertEqual(self.counts(),(0,0))

    def test_concurrent_capture_fails_closed_without_waiting(self):
        other=self.pg.connect(URL,autocommit=False)
        try:
            other.execute("SELECT pg_advisory_xact_lock(21471926,300024)")
            with self.assertRaisesRegex(Exception,"already owned"):
                self.capture()
            self.assertEqual(self.counts(),(0,0))
        finally:
            other.rollback()
            other.close()

if __name__ == "__main__": unittest.main()
