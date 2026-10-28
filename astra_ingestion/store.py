"""Durable ingestion ledger. No connections or migrations run on import.

PostgreSQL is the deployment backend. SQLite is an explicit local reference
backend used to exercise the same state transitions without cloud credentials.
All application writes serialize through one transaction lock. This deliberately
favours correctness and modest throughput for the bounded first release.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from .models import IngestionSpec, plan_partitions
from .source import record_key

SCHEMA_VERSION = 1
LOCK_ID = 706314020261028
ACTIVE = ("pending", "running", "loaded", "verifying")
TERMINAL = ("verified", "blocked", "failed", "cancelled")


class LeaseLost(RuntimeError):
    pass


class QualityHold(ValueError):
    pass


class RequestDeferred(RuntimeError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def iso(epoch: float | None) -> str | None:
    return None if epoch is None else datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self, database_url: str, *, test_mode: bool = False, schema: str = "astra_ingestion_v1"):
        self.database_url = database_url
        self.sqlite = database_url.startswith("sqlite:///")
        self.test_mode = test_mode
        if not self.sqlite and not database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("Unsupported database URL")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
            raise ValueError("Invalid schema")
        self.schema = schema
        self.prefix = "" if self.sqlite else schema + "."

    def connect(self):
        if self.sqlite:
            conn = sqlite3.connect(self.database_url[len("sqlite://"):], timeout=5, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            return conn
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Install the pinned PostgreSQL runtime dependency") from exc
        options = dict(connect_timeout=10, row_factory=dict_row, prepare_threshold=None, application_name="astra_ingestion",
                       options="-c statement_timeout=10000 -c lock_timeout=3000")
        if not self.test_mode:
            options["sslmode"] = "verify-full"
        return psycopg.connect(self.database_url, **options)

    def execute(self, conn, statement, args=()):
        statement = statement.replace("{s}", self.prefix)
        return conn.execute(statement if self.sqlite else statement.replace("?", "%s"), args)

    def executemany(self, conn, statement, rows):
        statement = statement.replace("{s}", self.prefix)
        if not self.sqlite:
            statement = statement.replace("?", "%s")
        cursor = conn.cursor()
        try:
            cursor.executemany(statement, rows)
        finally:
            cursor.close()

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            if self.sqlite:
                conn.execute("BEGIN IMMEDIATE")
            else:
                conn.execute("BEGIN")
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def snapshot(self):
        conn = self.connect()
        try:
            conn.execute("BEGIN" if self.sqlite else "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def now(self, conn) -> float:
        sql = "SELECT (julianday('now')-2440587.5)*86400.0 AS t" if self.sqlite else "SELECT EXTRACT(EPOCH FROM clock_timestamp()) AS t"
        return float(conn.execute(sql).fetchone()["t"])

    def migration_statements(self):
        tables = [
            "CREATE TABLE IF NOT EXISTS {s}schema_info (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)",
            """CREATE TABLE IF NOT EXISTS {s}jobs (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, scope_hash TEXT NOT NULL,
                name TEXT NOT NULL, spec TEXT NOT NULL, status TEXT NOT NULL,
                verification_status TEXT NOT NULL DEFAULT 'pending',
                created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL,
                last_progress_at DOUBLE PRECISION, deadline_at DOUBLE PRECISION NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 0, record_count INTEGER NOT NULL DEFAULT 0,
                receipt_bytes INTEGER NOT NULL DEFAULT 0, error TEXT)""",
            """CREATE TABLE IF NOT EXISTS {s}partitions (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES {s}jobs(id),
                symbol TEXT NOT NULL, start_at TEXT NOT NULL, end_at TEXT NOT NULL,
                status TEXT NOT NULL, verification_status TEXT NOT NULL DEFAULT 'pending',
                owner TEXT, generation INTEGER NOT NULL DEFAULT 0, lease_until DOUBLE PRECISION,
                retry_count INTEGER NOT NULL DEFAULT 0, next_attempt_at DOUBLE PRECISION NOT NULL DEFAULT 0,
                next_page_token TEXT, page_count INTEGER NOT NULL DEFAULT 0,
                record_count INTEGER NOT NULL DEFAULT 0, request_count INTEGER NOT NULL DEFAULT 0,
                last_progress_at DOUBLE PRECISION, error TEXT,
                UNIQUE(job_id,symbol,start_at,end_at))""",
            """CREATE TABLE IF NOT EXISTS {s}receipts (
                partition_id TEXT NOT NULL REFERENCES {s}partitions(id), page_no INTEGER NOT NULL,
                token_in TEXT, token_out TEXT, request_id TEXT, raw_body TEXT NOT NULL,
                body_sha256 TEXT NOT NULL, received_at DOUBLE PRECISION NOT NULL,
                PRIMARY KEY(partition_id,page_no))""",
            """CREATE TABLE IF NOT EXISTS {s}records (
                partition_id TEXT NOT NULL REFERENCES {s}partitions(id),
                record_key TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(partition_id,record_key))""",
            """CREATE TABLE IF NOT EXISTS {s}verifications (
                partition_id TEXT PRIMARY KEY REFERENCES {s}partitions(id),
                checked_at DOUBLE PRECISION NOT NULL, result TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS {s}events (
                id TEXT PRIMARY KEY, job_id TEXT REFERENCES {s}jobs(id),
                timestamp DOUBLE PRECISION NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS {s}rejections (
                id TEXT PRIMARY KEY, partition_id TEXT NOT NULL REFERENCES {s}partitions(id),
                received_at DOUBLE PRECISION NOT NULL, reason TEXT NOT NULL,
                raw_body TEXT NOT NULL, body_sha256 TEXT NOT NULL)""",
            "CREATE TABLE IF NOT EXISTS {s}source_limits (id TEXT PRIMARY KEY, next_request_at DOUBLE PRECISION NOT NULL)",
            "CREATE INDEX IF NOT EXISTS ingestion_partition_ready ON {s}partitions(status,next_attempt_at)",
            "CREATE INDEX IF NOT EXISTS ingestion_event_job ON {s}events(job_id,timestamp)",
        ]
        return tables

    def migrate(self):
        """Explicit operator/test command, never called by web/worker startup."""
        with self.transaction() as conn:
            if not self.sqlite:
                conn.execute("CREATE SCHEMA IF NOT EXISTS " + self.schema)
                conn.execute("REVOKE ALL ON SCHEMA " + self.schema + " FROM PUBLIC")
            for statement in self.migration_statements():
                self.execute(conn, statement)
            self.execute(conn, "INSERT INTO {s}schema_info(id,version) VALUES(1,?) ON CONFLICT(id) DO NOTHING", (SCHEMA_VERSION,))
            self.execute(conn, "INSERT INTO {s}source_limits(id,next_request_at) VALUES('alpaca',0) ON CONFLICT(id) DO NOTHING")
            version = self.execute(conn, "SELECT version FROM {s}schema_info WHERE id=1").fetchone()
            if version["version"] != SCHEMA_VERSION:
                raise ValueError("Unsupported existing schema version")
            if self.sqlite:
                conn.execute("""CREATE TRIGGER IF NOT EXISTS immutable_job_scope BEFORE UPDATE OF spec,scope_hash,request_key ON jobs
                    BEGIN SELECT RAISE(ABORT,'Job scope is immutable'); END""")
                conn.execute("""CREATE TRIGGER IF NOT EXISTS immutable_partition_scope BEFORE UPDATE OF job_id,symbol,start_at,end_at ON partitions
                    BEGIN SELECT RAISE(ABORT,'Partition scope is immutable'); END""")
            else:
                conn.execute("REVOKE ALL ON ALL TABLES IN SCHEMA " + self.schema + " FROM PUBLIC")
                conn.execute(f"""CREATE OR REPLACE FUNCTION {self.schema}.guard_job_scope() RETURNS trigger
                    LANGUAGE plpgsql SET search_path = '' AS $$
                    BEGIN
                    IF NEW.spec IS DISTINCT FROM OLD.spec OR NEW.scope_hash IS DISTINCT FROM OLD.scope_hash
                       OR NEW.request_key IS DISTINCT FROM OLD.request_key THEN
                      RAISE EXCEPTION 'Job scope is immutable';
                    END IF; RETURN NEW; END $$""")
                conn.execute(f"DROP TRIGGER IF EXISTS immutable_job_scope ON {self.schema}.jobs")
                conn.execute(f"""CREATE TRIGGER immutable_job_scope BEFORE UPDATE ON {self.schema}.jobs
                    FOR EACH ROW EXECUTE FUNCTION {self.schema}.guard_job_scope()""")
                conn.execute(f"REVOKE ALL ON FUNCTION {self.schema}.guard_job_scope() FROM PUBLIC")
                conn.execute(f"""CREATE OR REPLACE FUNCTION {self.schema}.guard_partition_scope() RETURNS trigger
                    LANGUAGE plpgsql SET search_path = '' AS $$
                    BEGIN
                    IF NEW.job_id IS DISTINCT FROM OLD.job_id OR NEW.symbol IS DISTINCT FROM OLD.symbol
                       OR NEW.start_at IS DISTINCT FROM OLD.start_at OR NEW.end_at IS DISTINCT FROM OLD.end_at THEN
                      RAISE EXCEPTION 'Partition scope is immutable';
                    END IF; RETURN NEW; END $$""")
                conn.execute(f"DROP TRIGGER IF EXISTS immutable_partition_scope ON {self.schema}.partitions")
                conn.execute(f"""CREATE TRIGGER immutable_partition_scope BEFORE UPDATE ON {self.schema}.partitions
                    FOR EACH ROW EXECUTE FUNCTION {self.schema}.guard_partition_scope()""")
                conn.execute(f"REVOKE ALL ON FUNCTION {self.schema}.guard_partition_scope() FROM PUBLIC")

    def health(self):
        with self.snapshot() as conn:
            row = self.execute(conn, "SELECT version FROM {s}schema_info WHERE id=1").fetchone()
            if not row or row["version"] != SCHEMA_VERSION:
                raise RuntimeError("Database migration is required")
        return {"ready": True, "schema_version": SCHEMA_VERSION}

    def event(self, conn, job_id, event, detail, now=None):
        self.execute(conn, "INSERT INTO {s}events(id,job_id,timestamp,event,detail) VALUES(?,?,?,?,?)",
                     (str(uuid.uuid4()), job_id, self.now(conn) if now is None else now, event, canonical(detail)))

    @staticmethod
    def public_row(row):
        result = dict(row)
        for key in ("created_at", "updated_at", "last_progress_at", "deadline_at", "next_attempt_at", "lease_until", "timestamp", "checked_at"):
            if key in result:
                result[key] = iso(result[key])
        for key in ("spec", "detail", "result"):
            if key in result and isinstance(result[key], str):
                result[key] = json.loads(result[key])
        result.pop("owner", None)
        return result

    def list_jobs(self, limit=50):
        with self.snapshot() as conn:
            rows = self.execute(conn, "SELECT * FROM {s}jobs ORDER BY created_at DESC LIMIT ?", (max(1, min(int(limit), 100)),)).fetchall()
        return [self.public_row(row) for row in rows]

    def get_job(self, job_id):
        with self.snapshot() as conn:
            row = self.execute(conn, "SELECT * FROM {s}jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return None
            result = self.public_row(row)
            result["partitions"] = [self.public_row(p) for p in self.execute(conn,
                "SELECT * FROM {s}partitions WHERE job_id=? ORDER BY symbol,start_at", (job_id,)).fetchall()]
            proof_rows = self.execute(conn, "SELECT v.* FROM {s}verifications v JOIN {s}partitions p ON p.id=v.partition_id WHERE p.job_id=?", (job_id,)).fetchall()
            proofs = {v["partition_id"]: self.public_row(v) for v in proof_rows}
            for partition in result["partitions"]:
                partition["verification"] = proofs.get(partition["id"])
            result["events"] = [self.public_row(e) for e in self.execute(conn,
                "SELECT timestamp,event,detail FROM {s}events WHERE job_id=? ORDER BY timestamp DESC LIMIT 30", (job_id,)).fetchall()]
            result["coverage_certification"] = "NOT_CERTIFIED"
            result["verification_meaning"] = "Exact retained source response to stored record comparison"
            return result

    def submit_job(self, spec: IngestionSpec, request_key: str):
        if not isinstance(request_key, str) or not 8 <= len(request_key) <= 128 or not re.fullmatch(r"[A-Za-z0-9._:-]+", request_key):
            raise ValueError("A stable 8–128 character idempotency key is required")
        with self.transaction() as conn:
            existing = self.execute(conn, "SELECT id,scope_hash FROM {s}jobs WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                if existing["scope_hash"] != spec.scope_hash:
                    raise ValueError("Idempotency key already belongs to another scope")
                job_id = existing["id"]
            else:
                now = self.now(conn)
                job_id = str(uuid.uuid4())
                self.execute(conn, """INSERT INTO {s}jobs
                    (id,request_key,scope_hash,name,spec,status,created_at,updated_at,deadline_at)
                    VALUES(?,?,?,?,?,'queued',?,?,?)""",
                    (job_id, request_key, spec.scope_hash, spec.name, canonical(spec.to_dict()), now, now, now + spec.deadline_seconds))
                for p in plan_partitions(spec):
                    self.execute(conn, """INSERT INTO {s}partitions(id,job_id,symbol,start_at,end_at,status)
                        VALUES(?,?,?,?,?,'pending')""", (str(uuid.uuid4()), job_id, p["symbol"], p["start"], p["end"]))
                self.event(conn, job_id, "job_admitted", {"scope_hash": spec.scope_hash, "symbols": list(spec.symbols)}, now)
        return self.get_job(job_id)

    def refresh(self, conn, job_id, now):
        job = self.execute(conn, "SELECT status FROM {s}jobs WHERE id=?", (job_id,)).fetchone()
        if job["status"] in ("paused", "cancelled"):
            return
        parts = self.execute(conn, "SELECT status FROM {s}partitions WHERE job_id=?", (job_id,)).fetchall()
        statuses = [p["status"] for p in parts]
        if any(status in ACTIVE for status in statuses):
            status, verification = "running", "pending"
        elif statuses and all(status == "verified" for status in statuses):
            status, verification = "completed", "passed"
        elif "blocked" in statuses:
            status, verification = "blocked", "blocked"
        elif "failed" in statuses:
            status, verification = "failed", "failed"
        else:
            status, verification = "cancelled", "cancelled"
        self.execute(conn, "UPDATE {s}jobs SET status=?,verification_status=?,updated_at=? WHERE id=?", (status, verification, now, job_id))

    def control_job(self, job_id, action):
        if action not in ("pause", "resume", "cancel"):
            raise ValueError("Unsupported control")
        with self.transaction() as conn:
            job = self.execute(conn, "SELECT * FROM {s}jobs WHERE id=?", (job_id,)).fetchone()
            if job is None:
                raise KeyError(job_id)
            now = self.now(conn)
            if action == "resume":
                if job["status"] != "paused":
                    raise ValueError("Only paused jobs can resume; quality holds remain in force")
                if now >= job["deadline_at"]:
                    raise ValueError("The original job deadline has expired; submit a new explicit scope")
                self.execute(conn, "UPDATE {s}jobs SET status='running',updated_at=? WHERE id=?", (now, job_id))
                self.refresh(conn, job_id, now)
            elif action == "pause":
                if job["status"] not in ("queued", "running", "paused"):
                    raise ValueError("Only queued or running jobs can pause")
                self.execute(conn, "UPDATE {s}jobs SET status='paused',updated_at=? WHERE id=?", (now, job_id))
                self.execute(conn, """UPDATE {s}partitions SET
                    status=CASE WHEN status='verifying' THEN 'loaded' ELSE 'pending' END,
                    owner=NULL,lease_until=NULL,generation=generation+1
                    WHERE job_id=? AND status IN ('running','verifying')""", (job_id,))
            else:
                if job["status"] == "completed":
                    raise ValueError("A completed job cannot be cancelled")
                self.execute(conn, "UPDATE {s}jobs SET status='cancelled',verification_status='cancelled',updated_at=? WHERE id=?", (now, job_id))
                self.execute(conn, """UPDATE {s}partitions SET status='cancelled',verification_status='cancelled',
                    owner=NULL,lease_until=NULL,generation=generation+1 WHERE job_id=? AND status IN ('pending','running','loaded','verifying')""", (job_id,))
            self.event(conn, job_id, "job_" + action, {}, now)
        return self.get_job(job_id)

    def claim_next(self, worker_id, lease_seconds=90):
        lease_seconds = max(30, min(int(lease_seconds), 300))
        with self.transaction() as conn:
            now = self.now(conn)
            expired = self.execute(conn, "SELECT id FROM {s}jobs WHERE status IN ('queued','running') AND deadline_at<=?", (now,)).fetchall()
            for job in expired:
                self.execute(conn, """UPDATE {s}partitions SET status='failed',verification_status='failed',
                    owner=NULL,lease_until=NULL,generation=generation+1,error='Whole-job deadline exceeded'
                    WHERE job_id=? AND status IN ('pending','running','loaded','verifying')""", (job["id"],))
                self.execute(conn, "UPDATE {s}jobs SET status='failed',verification_status='failed',error='Whole-job deadline exceeded',updated_at=? WHERE id=?", (now, job["id"]))
                self.event(conn, job["id"], "deadline_exceeded", {}, now)
            p = self.execute(conn, """SELECT p.*,j.spec FROM {s}partitions p JOIN {s}jobs j ON j.id=p.job_id
                WHERE j.status IN ('queued','running') AND j.deadline_at>?
                AND p.next_attempt_at<=? AND
                (p.status IN ('pending','loaded') OR (p.status IN ('running','verifying') AND p.lease_until<=?))
                ORDER BY j.created_at,p.symbol,p.start_at LIMIT 1""", (now, now, now)).fetchone()
            if p is None:
                return None
            result = dict(p)
            phase = "verify" if p["status"] in ("loaded", "verifying") else "fetch"
            status = "verifying" if phase == "verify" else "running"
            generation = p["generation"] + 1
            self.execute(conn, "UPDATE {s}partitions SET status=?,owner=?,generation=?,lease_until=? WHERE id=?",
                         (status, worker_id, generation, now + lease_seconds, p["id"]))
            self.execute(conn, "UPDATE {s}jobs SET status='running',updated_at=? WHERE id=?", (now, p["job_id"]))
            self.event(conn, p["job_id"], "partition_claimed", {"partition_id": p["id"], "generation": generation, "phase": phase}, now)
            result.update(owner=worker_id, generation=generation, phase=phase, status=status, lease_until=now + lease_seconds)
            result["spec"] = json.loads(result["spec"])
            result["start"], result["end"] = result["start_at"], result["end_at"]
            return result

    def owned(self, conn, claim, *, allow_deadline=False):
        now = self.now(conn)
        p = self.execute(conn, "SELECT * FROM {s}partitions WHERE id=?", (claim["id"],)).fetchone()
        if not p or p["owner"] != claim["owner"] or p["generation"] != claim["generation"] or not p["lease_until"] or p["lease_until"] <= now:
            raise LeaseLost("Worker ownership is no longer valid")
        job = self.execute(conn, "SELECT * FROM {s}jobs WHERE id=?", (p["job_id"],)).fetchone()
        if job["status"] != "running" or (not allow_deadline and job["deadline_at"] <= now):
            raise LeaseLost("Job is stopped or its deadline has expired")
        return p, job, now

    def reserve_request(self, claim):
        with self.transaction() as conn:
            p, job, now = self.owned(conn, claim)
            if p["status"] != "running":
                raise LeaseLost("Not a fetch claim")
            spec = IngestionSpec.from_dict(json.loads(job["spec"]))
            if job["request_count"] >= spec.max_requests:
                raise QualityHold("Whole-job provider request budget exhausted")
            next_at = self.execute(conn, "SELECT next_request_at FROM {s}source_limits WHERE id='alpaca'").fetchone()["next_request_at"]
            if next_at >= job["deadline_at"]:
                raise QualityHold("Provider not-before time exceeds this job's admitted deadline")
            if next_at > now:
                self.execute(conn, "UPDATE {s}partitions SET status='pending',owner=NULL,lease_until=NULL,next_attempt_at=? WHERE id=?", (next_at, p["id"]))
                deferred = True
            else:
                self.execute(conn, "UPDATE {s}source_limits SET next_request_at=? WHERE id='alpaca'", (now + 2.0,))
                self.execute(conn, "UPDATE {s}jobs SET request_count=request_count+1,updated_at=? WHERE id=?", (now, job["id"]))
                self.execute(conn, "UPDATE {s}partitions SET request_count=request_count+1 WHERE id=?", (p["id"],))
                deferred = False
        if deferred:
            raise RequestDeferred("Shared provider pacing")

    def commit_page(self, claim, fetched, parsed):
        with self.transaction() as conn:
            p, job, now = self.owned(conn, claim)
            if p["status"] != "running" or p["next_page_token"] != claim["next_page_token"]:
                raise LeaseLost("Page checkpoint moved")
            body_sha = hashlib.sha256(fetched.raw_text.encode("utf-8")).hexdigest()
            if body_sha != parsed.response_sha256:
                raise QualityHold("Source receipt hash does not match")
            if parsed.next_page_token is not None:
                if parsed.next_page_token == p["next_page_token"] or self.execute(conn,
                    "SELECT 1 FROM {s}receipts WHERE partition_id=? AND token_in=?",
                    (p["id"], parsed.next_page_token)).fetchone():
                    raise QualityHold("Provider repeated a pagination token")
            keys = [record_key(record) for record in parsed.records]
            previous = {}
            for start in range(0, len(keys), 400):
                chunk = keys[start:start + 400]
                rows = self.execute(conn, "SELECT record_key,payload FROM {s}records WHERE partition_id=? AND record_key IN (" + ",".join("?" for _ in chunk) + ")", (p["id"], *chunk)).fetchall()
                previous.update({row["record_key"]: row["payload"] for row in rows})
            inserts = []
            for record in parsed.records:
                key, payload = record_key(record), canonical(record)
                if record["symbol"] != p["symbol"]:
                    raise QualityHold("Record is outside the immutable partition")
                if key in previous and previous[key] != payload:
                    raise QualityHold("Conflicting source values for an existing record key")
                if key not in previous:
                    inserts.append((p["id"], key, payload))
                    previous[key] = payload
            spec = IngestionSpec.from_dict(json.loads(job["spec"]))
            if job["record_count"] + len(inserts) > spec.max_records:
                raise QualityHold("Whole-job record budget exhausted")
            body_bytes = len(fetched.raw_text.encode("utf-8"))
            if job["receipt_bytes"] + body_bytes > 33_554_432:
                raise QualityHold("Whole-job retained source budget exceeded (32 MiB)")
            if parsed.next_page_token is None and p["record_count"] + len(inserts) == 0:
                raise QualityHold("No source records for an expected partition; explicit coverage review required")
            self.execute(conn, """INSERT INTO {s}receipts
                (partition_id,page_no,token_in,token_out,request_id,raw_body,body_sha256,received_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (p["id"], p["page_count"], p["next_page_token"], parsed.next_page_token,
                 fetched.request_id, fetched.raw_text, body_sha, now))
            self.executemany(conn, "INSERT INTO {s}records(partition_id,record_key,payload) VALUES(?,?,?)", inserts)
            status = "loaded" if parsed.next_page_token is None else "pending"
            # Recheck using database time after all potentially expensive writes.
            # Any expiry rolls back both source receipt and record effects.
            self.owned(conn, claim)
            self.execute(conn, """UPDATE {s}partitions SET status=?,next_page_token=?,page_count=page_count+1,
                record_count=record_count+?,owner=NULL,lease_until=NULL,last_progress_at=?,next_attempt_at=0,error=NULL WHERE id=?""",
                (status, parsed.next_page_token, len(inserts), now, p["id"]))
            self.execute(conn, "UPDATE {s}jobs SET record_count=record_count+?,receipt_bytes=receipt_bytes+?,updated_at=?,last_progress_at=? WHERE id=?", (len(inserts), body_bytes, now, now, job["id"]))
            self.event(conn, job["id"], "page_committed", {"partition_id": p["id"], "page": p["page_count"], "records": len(inserts), "receipt_sha256": body_sha}, now)
        return {"records": len(inserts), "phase": "verify" if status == "loaded" else "fetch"}

    def verification_material(self, claim):
        # A fresh, consistent read transaction, independent of the page write.
        with self.snapshot() as conn:
            receipts = [dict(r) for r in self.execute(conn, "SELECT * FROM {s}receipts WHERE partition_id=? ORDER BY page_no", (claim["id"],)).fetchall()]
            records = []
            for row in self.execute(conn, "SELECT record_key,payload FROM {s}records WHERE partition_id=? ORDER BY record_key", (claim["id"],)).fetchall():
                payload = json.loads(row["payload"])
                if row["record_key"] != record_key(payload):
                    raise QualityHold("Stored record key does not match its payload")
                records.append(payload)
        return receipts, records

    def finish_verification(self, claim, result):
        with self.transaction() as conn:
            p, job, now = self.owned(conn, claim)
            if p["status"] != "verifying":
                raise LeaseLost("Not a verification claim")
            passed = result["status"] == "passed"
            self.execute(conn, """INSERT INTO {s}verifications(partition_id,checked_at,result) VALUES(?,?,?)
                ON CONFLICT(partition_id) DO UPDATE SET checked_at=excluded.checked_at,result=excluded.result""",
                (p["id"], now, canonical(result)))
            self.owned(conn, claim)
            self.execute(conn, """UPDATE {s}partitions SET status=?,verification_status=?,owner=NULL,
                lease_until=NULL,last_progress_at=?,error=? WHERE id=?""",
                ("verified" if passed else "blocked", "passed" if passed else "failed", now,
                 None if passed else "Source-to-target reconciliation failed", p["id"]))
            self.execute(conn, "UPDATE {s}jobs SET last_progress_at=?,updated_at=? WHERE id=?", (now, now, job["id"]))
            self.event(conn, job["id"], "verification_" + ("passed" if passed else "failed"), {"partition_id": p["id"], **result}, now)
            self.refresh(conn, job["id"], now)

    def fail_claim(self, claim, *, code, message, retryable=False, retry_after=0, raw_response=None):
        with self.transaction() as conn:
            p, job, now = self.owned(conn, claim, allow_deadline=True)
            failures = p["retry_count"] + 1
            delay = float(retry_after)
            proposed = now + max(delay, 5.0 * failures) if math.isfinite(delay) else float("inf")
            retry = bool(retryable and failures < 2 and proposed < job["deadline_at"])
            if retryable and proposed >= job["deadline_at"]:
                message = str(message) + "; provider wait exceeds the original job deadline"
            if retry:
                status = "loaded" if p["status"] == "verifying" else "pending"
                next_at = proposed
                verification = "pending"
            else:
                status, verification = ("failed", "failed") if retryable else ("blocked", "blocked")
                next_at = 0
            # Caller supplies controlled messages, never HTTP headers or credentials.
            reason = (str(code) + ": " + str(message))[:500]
            self.execute(conn, """UPDATE {s}partitions SET status=?,verification_status=?,owner=NULL,
                lease_until=NULL,retry_count=?,next_attempt_at=?,error=? WHERE id=?""",
                (status, verification, failures, next_at, reason, p["id"]))
            if retry_after and retryable:
                current = self.execute(conn, "SELECT next_request_at FROM {s}source_limits WHERE id='alpaca'").fetchone()["next_request_at"]
                self.execute(conn, "UPDATE {s}source_limits SET next_request_at=? WHERE id='alpaca'", (max(current, min(now + delay, 253402300799.0) if math.isfinite(delay) else 253402300799.0),))
            if raw_response is not None:
                if len(raw_response.encode("utf-8")) > 2_097_152:
                    raw_response = "[Response exceeds retained-body bound]"
                self.execute(conn, "INSERT INTO {s}rejections(id,partition_id,received_at,reason,raw_body,body_sha256) VALUES(?,?,?,?,?,?)",
                    (str(uuid.uuid4()), p["id"], now, reason, raw_response, hashlib.sha256(raw_response.encode()).hexdigest()))
            self.event(conn, job["id"], "retry_scheduled" if retry else "partition_" + status,
                       {"partition_id": p["id"], "symbol": p["symbol"], "reason": reason, "next_attempt_at": iso(next_at) if next_at else None}, now)
            self.refresh(conn, job["id"], now)
