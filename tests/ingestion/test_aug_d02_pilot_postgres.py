"""Real PostgreSQL tests for the private one-shot D02 pilot.

Synthetic source witnesses use test-specific hashes. The shipped SQL must pin
the separately approved genuine manifest, whose licensed contents stay private.
"""
import hashlib
import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit
from uuid import uuid4

SQL = Path(__file__).resolve().parents[2] / "sql" / "astra_aug_d02_pilot_v1.sql"
MANIFEST = "61860ca4d4829f4f33459e9ebc0bad1c220a4552bfd5d9097d3a46af527717e4"
COHORT = "2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec"
ANCHORS = "f48b5796245916e46580dbf0c5e5c9e81338a0861f8d0a3004024c78c2215667"
SOURCE = "81e74427cd1365680d18cdaa31e5950bf601087e3bb0c11a13b2bfd14f4c93ae"
SOURCE_ID = "d02-daily-v2:7d9ac7ffe6757bdf8c19748275d87dc9b26d32cac5334a6deae52dc5c54b0d43:source"
ATTEMPT = "e3d0a2e8-ee58-5e31-ac5a-cd1dbe34f54a"
DATE = "2026-08-04"
URL = os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compact(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


class DisposableD02Fixture(unittest.TestCase):
    source_company_count = 10

    @classmethod
    def setUpClass(cls):
        if not URL and os.environ.get("GITHUB_JOB") == "qualify":
            raise AssertionError("Required PostgreSQL CI test database is absent")
        if not URL:
            raise unittest.SkipTest("NOT RUN: disposable loopback PostgreSQL 17 required")
        url = urlsplit(URL)
        if url.hostname not in {"localhost", "127.0.0.1", "::1"} or "qualification" not in url.path or url.query:
            raise AssertionError("Refusing non-disposable test database")
        import psycopg
        cls.driver = psycopg
        cls.conn = psycopg.connect(URL, autocommit=True)
        cls.addClassCleanup(cls.conn.close)
        if cls.conn.info.server_version < 170000:
            raise AssertionError("Qualification requires PostgreSQL 17 or later")

    def setUp(self):
        uid = uuid4().hex[:12]
        self.app = "augtest_app_" + uid
        self.src = "augtest_src_" + uid
        self.writer = "augtest_writer_" + uid
        self.reader = "augtest_reader_" + uid
        self.outsider = "augtest_outsider_" + uid
        q = self.conn.execute
        self.addCleanup(self.cleanup)
        for r in (self.writer, self.reader, self.outsider):
            q(f"CREATE ROLE {r} NOLOGIN NOINHERIT")
        q(f"CREATE SCHEMA {self.app}")
        q(f"CREATE SCHEMA {self.src}")
        q(f"GRANT USAGE ON SCHEMA {self.app} TO {self.writer},{self.reader},{self.outsider}")
        q(f"""CREATE TABLE {self.src}.source_document(source_id text PRIMARY KEY,source_sha256 text,
             content_text text,content_bytes int,source_provider text,source_uri text,evidence jsonb)""")
        q(f"""CREATE TABLE {self.app}.bulk_scope_evidence_v1(capture_key text,kind text,
             evidence_key text,source_sha256 text,source_text text)""")
        q(f"""CREATE TABLE {self.src}.ref01_date_record_v4(company_id text,point_date date,
             ordinal int,identity_state text,record_sha256 text,content jsonb)""")
        q(f"""CREATE TABLE {self.src}.ref01_practical_dated_instrument_v3(company_id text,
             point_date date,cohort_sha256 text,ticker text,record_sha256 text,content jsonb)""")
        prices, refs, members, anchor_lines = [], [], [], []
        for n in range(1, self.source_company_count + 1):
            cik, symbol = f"{n:010d}", f"TEST{n}"
            cf, sf, venue, issue = f"CF{n}", f"SF{n}", "XNAS", "CS"
            member = dict(ordinal=n,company_id="CIK:"+cik,ticker=symbol,composite_figi=cf,
                          share_class_figi=sf,exchange_mic=venue,issue_type=issue,source_row=n)
            anchor_lines.append("|".join(map(str,(n,"CIK:"+cik,symbol,cf,sf,venue,issue))))
            members.append(member)
            prices.append({"T":symbol,"c":10+n,"v":100+n,"t":1785816000000})
            refs.append(dict(cik=cik,ticker=symbol,composite_figi=cf,share_class_figi=sf,primary_exchange=venue,
                             type=issue,market="stocks",locale="us",active=True,currency_name="usd"))
        self.price = compact({"results":prices})
        ref_body = compact({"results":refs})
        uri = "https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/2026-08-04?adjusted=false&include_otc=false"
        for key, body, url in [(SOURCE_ID,self.price,uri),("synthetic-reference",ref_body,"test-ref")]:
            q(f"INSERT INTO {self.src}.source_document VALUES(%s,%s,%s,%s,'Massive',%s,%s::jsonb)",
              (key,sha(body),body,len(body.encode()),url,compact({"as_of":DATE})))
        def pg_hash(value):
            return q("SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(compact(value),)).fetchone()[0]
        for n,m in enumerate(members):
            record = dict(source_record=refs[n],source_sha256=sha(ref_body))
            refsha = pg_hash(record)
            cross = {"source_record_sha256":refsha}
            cm = dict(company_id=m["company_id"],selection_order=n+1,cohort_sha256=COHORT,
                      anchor_ticker=m["ticker"],anchor_exchange=m["exchange_mic"],anchor_composite_figi=m["composite_figi"],
                      anchor_share_class_figi=m["share_class_figi"],anchor_security_type=m["issue_type"],
                      membership_accepted=True,membership_acceptance_sha256="20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9")
            q(f"""INSERT INTO {self.app}.bulk_scope_evidence_v1 VALUES('top3000-augsep2026-retained-scope-v1',
              'company',%s,%s,%s)""",(m["company_id"],sha(compact(cm)),compact(cm)))
            q(f"INSERT INTO {self.src}.ref01_date_record_v4 VALUES(%s,%s,%s,'FROZEN_ANCHOR_TICKER_AND_TWO_FIGI_MATCH',%s,%s::jsonb)",
              (m["company_id"],DATE,n+1,refsha,compact(record)))
            q(f"INSERT INTO {self.src}.ref01_practical_dated_instrument_v3 VALUES(%s,%s,%s,%s,%s,%s::jsonb)",
              (m["company_id"],DATE,COHORT,m["ticker"],pg_hash(cross),compact(cross)))
            m.update(identity_record_sha256=refsha,identity_source_sha256=sha(ref_body),raw_record_sha256=pg_hash(prices[n]))
        self.manifest = compact(dict(schema="astra-aug-d02-pilot/v1",date=DATE,cohort_sha256=COHORT,
                                     source_sha256=sha(self.price),members=members[:10]))
        self.source_members = members
        self.pin = sha(self.manifest)
        sql = SQL.read_text()
        # Parameterise *only* fixture schemas, role names and the pins derived
        # from these synthetic inputs. The production installer has no override.
        for old,new in [("population_top3000_202608_202609_v1",self.src),("astra_ingestion_v1",self.app),
                        ("astra_ingestion_rpc_owner_v1",self.writer),("astra_ingestion_verifier_owner_v1",self.reader),
                        (MANIFEST,self.pin),(SOURCE,sha(self.price)),(ANCHORS,sha("\n".join(anchor_lines[:10])))]:
            self.assertIn(old,sql)
            sql = sql.replace(old,new)
        q(sql)

    def cleanup(self):
        q = self.conn.execute
        q("ROLLBACK")
        q("RESET ROLE")
        for s in (self.app,self.src):
            q(f"DROP SCHEMA IF EXISTS {s} CASCADE")
        for r in (self.writer,self.reader,self.outsider):
            q(f"DROP ROLE IF EXISTS {r}")

    def register(self, when="clock_timestamp()+interval '15 minutes'"):
        return self.conn.execute(f"SELECT {self.app}.aug_d02_pilot_register_v1(%s,%s,%s,{when})",
                                 (self.manifest,self.pin,ATTEMPT)).fetchone()[0]

    def commit(self, attempt=ATTEMPT):
        return self.conn.execute(f"SELECT {self.app}.aug_d02_pilot_commit_v1(%s,%s)",
                                 (self.pin,attempt)).fetchone()[0]


class AugustPilotPostgres(DisposableD02Fixture):
    def test_real_source_to_target_separate_readback_and_duplicate(self):
        self.assertEqual(self.register(),self.pin)
        self.assertEqual(self.commit(),10)
        with self.driver.connect(URL) as other:
            other.execute("SET TRANSACTION READ ONLY")
            result=other.execute(f"""SELECT ordinal,company_id,raw_close,raw_volume,verified,manifest_sha,
                effective_role,caller_role FROM {self.app}.aug_d02_pilot_read_v1() ORDER BY ordinal""").fetchall()
            self.assertEqual(len(result),10)
            for n,row in enumerate(result,1):
                self.assertEqual(row[:7],(n,f"CIK:{n:010d}",10+n,100+n,True,self.pin,self.reader))
                self.assertNotEqual(row[6],row[7])
        with self.assertRaisesRegex(self.driver.Error,"already committed"):
            self.commit()
        self.assertEqual(self.conn.execute(f"SELECT count(*) FROM {self.app}.aug_d02_pilot_receipt_v1").fetchone(),(1,))
        self.conn.execute(f"UPDATE {self.src}.source_document SET content_text='{{}}' WHERE source_id=%s",(SOURCE_ID,))
        self.assertEqual(self.conn.execute(f"SELECT count(*) FILTER (WHERE verified),count(*) FROM {self.app}.aug_d02_pilot_read_v1()").fetchone(),(0,10))

    def test_stops_scope_and_no_partial_write(self):
        with self.assertRaises(self.driver.Error):
            self.register("clock_timestamp()-interval '1 second'")
        self.register()
        with self.assertRaises(self.driver.Error):
            self.commit(str(uuid4()))
        self.conn.execute(f"DELETE FROM {self.src}.ref01_date_record_v4 WHERE ordinal=2")
        with self.assertRaisesRegex(self.driver.Error,"Source missing"):
            self.commit()
        self.assertEqual(self.conn.execute(f"SELECT count(*) FROM {self.app}.aug_d02_pilot_rows_v1").fetchone(),(0,))
        self.conn.execute(f"SELECT {self.app}.aug_d02_pilot_stop_job_v1()")
        with self.assertRaisesRegex(self.driver.Error,"fence rejected"):
            self.commit()

    def test_fixed_manifest_and_actor_privileges(self):
        orig=self.manifest
        self.manifest=self.manifest.replace("TEST1\"", "OTHER\"")
        self.pin=sha(self.manifest)
        with self.assertRaisesRegex(self.driver.Error,"Invalid pilot pin"):
            self.register()
        self.manifest=orig; self.pin=sha(orig)
        self.register()
        q=self.conn.execute
        self.assertEqual(q("SELECT has_schema_privilege(%s,%s,'CREATE'),has_schema_privilege(%s,%s,'CREATE')",
                           (self.writer,self.app,self.reader,self.app)).fetchone(), (False,False))
        for role in (self.reader,self.outsider):
            q(f"SET ROLE {role}")
            try:
                with self.assertRaises(self.driver.errors.InsufficientPrivilege):
                    self.commit()
                with self.assertRaises(self.driver.errors.InsufficientPrivilege):
                    q(f"DELETE FROM {self.app}.aug_d02_pilot_rows_v1")
                with self.assertRaises(self.driver.errors.InsufficientPrivilege):
                    q(f"SELECT * FROM {self.src}.source_document")
            finally:
                q("RESET ROLE")
