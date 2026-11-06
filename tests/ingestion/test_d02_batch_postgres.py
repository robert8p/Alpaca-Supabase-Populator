"""Exercise the reusable route in a disposable PostgreSQL 17 database.

The original ten-company pilot is committed before every migration. Each
additional authorisation exists only in this synthetic qualification database.
"""

from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
import unittest

import test_aug_d02_pilot_postgres as pilot


SQL = Path(__file__).resolve().parents[2] / "sql" / "astra_d02_batch_v1.sql"


class ReusableD02Postgres(pilot.DisposableD02Fixture):
    source_company_count = 30

    def setUp(self):
        super().setUp()
        self.assertEqual(self.register(), self.pin)
        self.assertEqual(self.commit(), 10)
        self.original_pilot = self.pilot_snapshot()
        sql = SQL.read_text()
        for original, replacement in (
            ("population_top3000_202608_202609_v1", self.src),
            ("astra_ingestion_v1", self.app),
            ("astra_ingestion_rpc_owner_v1", self.writer),
            ("astra_ingestion_verifier_owner_v1", self.reader),
            (pilot.SOURCE, pilot.sha(self.price)),
        ):
            self.assertIn(original, sql)
            sql = sql.replace(original, replacement)
        self.conn.execute(sql)
        self.attempt = uuid4()
        self.body = self.batch_body(11)
        self.digest = pilot.sha(self.body)

    def pilot_snapshot(self):
        rows = self.conn.execute(
            f"SELECT * FROM {self.app}.aug_d02_pilot_read_v1() ORDER BY ordinal"
        ).fetchall()
        receipts = self.conn.execute(f"SELECT * FROM {self.app}.aug_d02_pilot_receipt_v1").fetchall()
        self.assertEqual((len(rows), len(receipts)), (10, 1))
        return rows, receipts

    def batch_body(self, first, *, members=None, session=pilot.DATE):
        if members is None:
            members = self.source_members[first - 1:first + 9]
        return pilot.compact(dict(schema="astra-d02-batch/v1", date=session, cohort_sha256=pilot.COHORT,
                                  source_sha256=pilot.sha(self.price), members=members))

    def approve(self, *, attempt=None, digest=None, first=11, session=pilot.DATE,
                deadline="clock_timestamp()+interval '15 minutes'"):
        return self.conn.execute(
            f"SELECT {self.app}.d02_batch_approve_v1(%s,%s,%s,%s,{deadline})",
            (attempt or self.attempt, digest or self.digest, session, first),
        ).fetchone()[0]

    def register_batch(self, *, body=None, digest=None, attempt=None):
        return self.conn.execute(
            f"SELECT {self.app}.d02_batch_register_v1(%s,%s,%s)",
            (body or self.body, digest or self.digest, attempt or self.attempt),
        ).fetchone()[0]

    def commit_batch(self, *, attempt=None, digest=None, conn=None):
        return (conn or self.conn).execute(
            f"SELECT {self.app}.d02_batch_commit_v1(%s,%s)",
            (digest or self.digest, attempt or self.attempt),
        ).fetchone()[0]

    def counts(self):
        return self.conn.execute(
            f"SELECT (SELECT count(*) FROM {self.app}.d02_batch_rows_v1),"
            f"(SELECT count(*) FROM {self.app}.d02_batch_receipts_v1)"
        ).fetchone()

    def check_readback(self, first, attempt, digest):
        with self.driver.connect(pilot.URL) as verifier:
            verifier.execute("SET TRANSACTION READ ONLY")
            rows = verifier.execute(
                f"""SELECT ordinal,company_id,ticker,composite_figi,share_class_figi,exchange_mic,issue_type,
                    session_date::text,raw_close,raw_volume,source_row,source_sha256,raw_record_sha256,
                    identity_source_sha256,identity_record_sha256,manifest_sha,attempt,verified,effective_role,caller_role
                    FROM {self.app}.d02_batch_read_v1(%s) ORDER BY ordinal""",
                (attempt,),
            ).fetchall()
        self.assertEqual(len(rows), 10)
        for offset, row in enumerate(rows):
            n = first + offset
            m = self.source_members[n - 1]
            self.assertEqual(row[:-1], (
                n, f"CIK:{n:010d}", f"TEST{n}", f"CF{n}", f"SF{n}", "XNAS", "CS", pilot.DATE,
                10+n, 100+n, n, pilot.sha(self.price), m["raw_record_sha256"], m["identity_source_sha256"],
                m["identity_record_sha256"], digest, attempt, True, self.reader,
            ))
            self.assertNotEqual(row[-1], self.reader)

    @contextmanager
    def as_role(self, role):
        self.conn.execute(f"SET ROLE {role}")
        try:
            yield
        finally:
            self.conn.execute("RESET ROLE")

    def test_two_admissions_independent_readback_and_first_pilot_preserved(self):
        self.assertEqual(self.approve(), self.attempt)
        self.assertEqual(self.register_batch(), self.digest)
        self.assertEqual(self.commit_batch(), 10)
        self.check_readback(11, self.attempt, self.digest)
        # A lost client acknowledgement can be reconciled by attempt, before any replay.
        receipt = self.conn.execute(
            f"SELECT manifest_sha,inserted_count,writer_role FROM {self.app}.d02_batch_receipts_v1 WHERE attempt=%s",
            (self.attempt,),
        ).fetchone()
        self.assertEqual(receipt, (self.digest, 10, self.writer))
        with self.assertRaises(self.driver.Error):
            self.commit_batch()

        other_attempt = uuid4()
        other_body = self.batch_body(21)
        other_digest = pilot.sha(other_body)
        with self.assertRaises(self.driver.Error):
            self.register_batch(body=other_body, digest=other_digest, attempt=other_attempt)
        self.approve(first=21, attempt=other_attempt, digest=other_digest)
        self.register_batch(body=other_body, digest=other_digest, attempt=other_attempt)
        self.assertEqual(self.commit_batch(digest=other_digest, attempt=other_attempt), 10)
        self.check_readback(21, other_attempt, other_digest)
        self.check_readback(11, self.attempt, self.digest)
        self.assertEqual(self.counts(), (20, 2))
        self.assertEqual(self.pilot_snapshot(), self.original_pilot)

    def test_explicit_approval_pin_and_range(self):
        for operation in (self.register_batch, self.commit_batch):
            with self.subTest(operation=operation.__name__), self.assertRaises(self.driver.Error):
                operation()
        for invalid in ({"first": 1}, {"first": 12}, {"session": "2026-08-05"},
                        {"deadline": "clock_timestamp()-interval '1 second'"}):
            with self.subTest(options=invalid), self.assertRaises(self.driver.Error):
                self.approve(**invalid)
        self.approve()
        with self.assertRaises(self.driver.Error):
            self.approve(attempt=uuid4(), digest="f"*64)
        with self.assertRaises(self.driver.Error):
            self.approve(first=21, digest="e"*64)
        with self.assertRaises(self.driver.Error):
            self.register_batch(attempt=uuid4())
        with self.assertRaises(self.driver.Error):
            self.register_batch(body=self.body+" ")
        with self.assertRaises(self.driver.Error):
            self.register_batch(body=self.body+" ", digest=pilot.sha(self.body+" "))
        self.register_batch()
        with self.assertRaises(self.driver.Error):
            self.register_batch()
        with self.assertRaises(self.driver.Error):
            self.commit_batch(digest="c"*64)
        with self.assertRaises(self.driver.Error):
            self.commit_batch(attempt=uuid4())
        self.assertEqual(self.counts(), (0, 0))

    def test_even_pinned_manifest_must_match_date_rank_order_and_native_identity(self):
        members = self.source_members[10:20]
        variants = {
            "date": self.batch_body(11, session="2026-08-05"),
            "ranks": self.batch_body(21),
            "reordered": self.batch_body(11, members=list(reversed(members))),
            "duplicate": self.batch_body(11, members=members[:-1]+[members[0]]),
            "changed class": self.batch_body(11, members=[dict(members[0], share_class_figi="BAD")]+members[1:]),
            "changed native hash": self.batch_body(11, members=[dict(members[0], raw_record_sha256="e"*64)]+members[1:]),
        }
        for label, body in variants.items():
            # Independent disposable approval for each negative case, rolled back in full.
            with self.subTest(label=label), self.conn.transaction(force_rollback=True):
                digest = pilot.sha(body)
                self.approve(digest=digest)
                with self.assertRaises(self.driver.Error), self.conn.transaction():
                    self.register_batch(body=body, digest=digest)
                self.assertEqual(self.counts(), (0, 0))

    def test_write_rollback_and_stop(self):
        self.approve()
        self.register_batch()
        with self.driver.connect(pilot.URL) as client:
            self.assertEqual(self.commit_batch(conn=client), 10)
            client.rollback()
        self.assertEqual(self.counts(), (0, 0))
        self.conn.execute(f"SELECT {self.app}.d02_batch_stop_v1(%s)", (self.attempt,))
        with self.assertRaises(self.driver.Error):
            self.commit_batch()
        self.assertEqual(self.counts(), (0, 0))
        self.assertEqual(self.pilot_snapshot(), self.original_pilot)

    def test_matching_row_reused_conflicting_row_blocks_entire_batch(self):
        self.approve()
        self.register_batch()
        q = self.conn.execute
        seed = f"""INSERT INTO {self.app}.d02_batch_rows_v1(attempt,payload)
                    SELECT %s,jsonb_populate_record(s,%s::jsonb)
                    FROM {self.app}.d02_batch_source_v1(%s) s WHERE s.ordinal=11"""
        # Deliberate fixture-only corrupt row. Keep it across the failed commit,
        # then roll back the whole synthetic scenario before testing a matching row.
        with self.conn.transaction(force_rollback=True):
            q(seed, (self.attempt, '{"raw_close": 9999}', self.attempt))
            with self.assertRaises(self.driver.Error), self.conn.transaction():
                self.commit_batch()
            self.assertEqual(self.counts(), (1, 0))
        q(seed, (self.attempt, "{}", self.attempt))
        self.assertEqual(self.commit_batch(), 9)
        self.check_readback(11, self.attempt, self.digest)
        self.assertEqual(self.counts(), (10, 1))

    def test_missing_source_between_registration_and_write_is_atomic(self):
        self.approve()
        self.register_batch()
        self.conn.execute(f"DELETE FROM {self.src}.ref01_date_record_v4 WHERE ordinal=12")
        with self.assertRaises(self.driver.Error):
            self.commit_batch()
        self.assertEqual(self.counts(), (0, 0))

    def test_role_separation_append_only_and_tampered_source_readback(self):
        self.approve()
        self.register_batch()
        self.commit_batch()
        q = self.conn.execute
        for role in (self.writer, self.reader, self.outsider):
            with self.subTest(role=role), self.as_role(role):
                with self.assertRaises(self.driver.errors.InsufficientPrivilege):
                    self.approve(first=21, attempt=uuid4(), digest="e"*64)
                with self.assertRaises(self.driver.errors.InsufficientPrivilege):
                    q(f"SELECT * FROM {self.src}.source_document")
                self.assertFalse(q("SELECT has_schema_privilege(current_user,%s,'CREATE')",
                                   (self.app,)).fetchone()[0])
                if role != self.writer:
                    with self.assertRaises(self.driver.errors.InsufficientPrivilege):
                        self.commit_batch()
                    with self.assertRaises(self.driver.errors.InsufficientPrivilege):
                        q(f"DELETE FROM {self.app}.d02_batch_rows_v1")
        for table in ("d02_batch_approvals_v1", "d02_batch_manifests_v1", "d02_batch_rows_v1",
                      "d02_batch_receipts_v1"):
            with self.subTest(table=table), self.assertRaises(self.driver.Error):
                q(f"DELETE FROM {self.app}.{table}")
        q(f"UPDATE {self.src}.source_document SET content_text='{{}}' WHERE source_id=%s", (pilot.SOURCE_ID,))
        self.assertEqual(q(f"SELECT count(*),count(*) FILTER (WHERE verified) "
                           f"FROM {self.app}.d02_batch_read_v1(%s)", (self.attempt,)).fetchone(), (10, 0))
        self.assertEqual(self.counts(), (10, 1))
