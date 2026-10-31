"""Real PostgreSQL qualification of the isolated ingestion-role template.

Only the explicitly admitted loopback qualification database is accepted.
Every schema and role name is generated locally; the real net schema and
production role names are never changed. Missing test infrastructure skips
these cases explicitly and is not a successful role qualification.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest
import uuid

import test_postgres as postgres_qualification

from astra_ingestion.models import IngestionSpec
from astra_ingestion.store import Store
from astra_ingestion.worker import Worker


ROLE_PATTERN = re.compile(
    r"astra_ingestion_test_(api|worker|outsider)_[0-9a-f]{12}\Z"
)
NET_SCHEMA_PATTERN = re.compile(r"astra_ingestion_test_net_[0-9a-f]{12}\Z")
ROLE_TEMPLATE = Path(__file__).resolve().parents[2] / "sql" / "astra_ingestion_roles.sql"


class AssumedRoleStore(Store):
    """Exercise actual Store operations after PostgreSQL SET ROLE."""

    def __init__(self, database_url, schema, role):
        super().__init__(database_url, test_mode=True, schema=schema)
        if not ROLE_PATTERN.fullmatch(role):
            raise ValueError("Refusing a non-qualification role")
        self.role = role

    def connect(self):
        from psycopg import sql

        conn = super().connect()
        try:
            conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(self.role)))
            conn.commit()
            return conn
        except BaseException:
            conn.close()
            raise


@unittest.skipUnless(
    postgres_qualification.TEST_URL,
    "PostgreSQL role qualification NOT_RUN: ASTRA_INGESTION_POSTGRES_TEST_URL is not set",
)
class IngestionRoleQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the existing exact loopback/database/query-override admission.
        # Import the module, not its TestCase class into this module's globals,
        # so unittest does not accidentally discover the existing tests twice.
        postgres_qualification.PostgreSQLQualificationTests.setUpClass.__func__(cls)
        import psycopg
        from psycopg import sql

        cls.pg_sql = sql
        cls.permission_error = psycopg.errors.InsufficientPrivilege
        cls.test_url = postgres_qualification.TEST_URL
        cls.template = ROLE_TEMPLATE.read_text()

    def setUp(self):
        suffix = uuid.uuid4().hex[:12]
        self.schema = "astra_ingestion_test_" + suffix
        self.net_schema = "astra_ingestion_test_net_" + suffix
        self.api_role = "astra_ingestion_test_api_" + suffix
        self.worker_role = "astra_ingestion_test_worker_" + suffix
        self.outsider_role = "astra_ingestion_test_outsider_" + suffix
        self.roles = [self.api_role, self.worker_role, self.outsider_role]
        self.schemas = [self.schema, self.net_schema]
        self.store = Store(self.test_url, test_mode=True, schema=self.schema)

        # Reject an unexpected collision before registering any cleanup.
        with self.store.connect() as conn:
            collision = conn.execute(
                """SELECT
                    EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=ANY(%s))
                    OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname=ANY(%s))
                    AS collision""",
                (self.schemas, self.roles),
            ).fetchone()["collision"]
            self.assertFalse(collision, "Refusing to adopt existing qualification objects")
        self.addCleanup(self.drop_owned_resources)

        # Simulate explicit and default-ACL leakage without editing global
        # defaults, existing schemas or production-named roles.
        with self.store.connect() as conn:
            conn.execute(
                self.pg_sql.SQL(
                    "CREATE ROLE {} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                ).format(self.pg_sql.Identifier(self.outsider_role))
            )
            for schema in self.schemas:
                conn.execute(
                    self.pg_sql.SQL("CREATE SCHEMA {}").format(self.pg_sql.Identifier(schema))
                )
            conn.execute(
                self.pg_sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA {} "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(self.pg_sql.Identifier(self.schema), self.pg_sql.Identifier(self.outsider_role))
            )
            conn.execute(
                self.pg_sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA {} "
                    "GRANT EXECUTE ON FUNCTIONS TO {}"
                ).format(self.pg_sql.Identifier(self.schema), self.pg_sql.Identifier(self.outsider_role))
            )
            conn.execute(
                self.pg_sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    self.pg_sql.Identifier(self.schema), self.pg_sql.Identifier(self.outsider_role)
                )
            )
            for table in ("http_request_queue", "_http_response"):
                conn.execute(
                    self.pg_sql.SQL("CREATE TABLE {}.{} (id integer PRIMARY KEY, body text)").format(
                        self.pg_sql.Identifier(self.net_schema), self.pg_sql.Identifier(table)
                    )
                )
                conn.execute(
                    self.pg_sql.SQL("INSERT INTO {}.{} VALUES (1, 'private test fixture')").format(
                        self.pg_sql.Identifier(self.net_schema), self.pg_sql.Identifier(table)
                    )
                )
        self.store.migrate()

        self.role_sql = (
            self.template.replace("astra_ingestion_v1", self.schema)
            .replace("astra_ingestion_api", self.api_role)
            .replace("astra_ingestion_worker", self.worker_role)
            .replace("nspname='net'", "nspname='" + self.net_schema + "'")
        )
        self.assertNotIn("nspname='net'", self.role_sql)
        self.assertNotIn("astra_ingestion_v1", self.role_sql)

    def drop_owned_resources(self):
        if not postgres_qualification.SCHEMA_PATTERN.fullmatch(self.schema):
            raise AssertionError("Refusing to remove a non-qualification schema")
        if not NET_SCHEMA_PATTERN.fullmatch(self.net_schema):
            raise AssertionError("Refusing to remove a non-qualification net fixture")
        if not all(ROLE_PATTERN.fullmatch(role) for role in self.roles):
            raise AssertionError("Refusing to remove a non-qualification role")
        with self.store.connect() as conn:
            for schema in self.schemas:
                conn.execute(
                    self.pg_sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        self.pg_sql.Identifier(schema)
                    )
                )
            for role in self.roles:
                conn.execute(
                    self.pg_sql.SQL("DROP ROLE IF EXISTS {}").format(self.pg_sql.Identifier(role))
                )

    def apply_roles(self):
        conn = self.store.connect()
        try:
            conn.execute(self.role_sql)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def read(self, statement, args=()):
        with self.store.snapshot() as conn:
            return conn.execute(statement, args).fetchall()

    def existing_runtime_roles(self):
        return self.read(
            "SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolcreatedb,"
            "rolcreaterole,rolreplication,rolbypassrls "
            "FROM pg_roles WHERE rolname=ANY(%s) ORDER BY rolname",
            ([self.api_role, self.worker_role],),
        )

    def access_snapshot(self):
        # This snapshot detects partial grants, policy changes or RLS changes
        # escaping an aborted setup transaction.
        return {
            "schema": self.read(
                "SELECT nspacl::text AS acl FROM pg_namespace WHERE nspname=%s",
                (self.schema,),
            ),
            "relations": self.read(
                "SELECT c.relname,c.relrowsecurity,c.relacl::text AS acl "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=%s ORDER BY c.relname",
                (self.schema,),
            ),
            "functions": self.read(
                "SELECT p.proname,p.proacl::text AS acl "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname=%s ORDER BY p.proname",
                (self.schema,),
            ),
            "policies": self.read(
                "SELECT tablename,policyname,roles,cmd,qual,with_check "
                "FROM pg_policies WHERE schemaname=%s ORDER BY tablename,policyname",
                (self.schema,),
            ),
        }

    def assert_denied(self, role, statement):
        conn = AssumedRoleStore(self.test_url, self.schema, role).connect()
        try:
            with self.assertRaises(self.permission_error):
                conn.execute(statement)
            conn.rollback()
        finally:
            conn.close()

    def test_intended_grants_real_worker_and_default_acl_cleanup(self):
        # Confirm the fixture actually contains the leak that must be removed.
        before = self.read(
            "SELECT has_table_privilege(%s,%s,'SELECT') AS can_read,"
            "has_function_privilege(%s,%s,'EXECUTE') AS can_execute",
            (
                self.outsider_role, self.schema + ".jobs",
                self.outsider_role, self.schema + ".guard_job_scope()",
            ),
        )[0]
        self.assertEqual(before, {"can_read": True, "can_execute": True})
        self.apply_roles()

        for role in self.existing_runtime_roles():
            self.assertFalse(any(value for key, value in role.items() if key != "rolname"))
        self.assertEqual(len(self.existing_runtime_roles()), 2)
        after = self.read(
            "SELECT has_schema_privilege(%s,%s,'USAGE') AS can_use,"
            "has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE') AS can_read,"
            "has_function_privilege(%s,%s,'EXECUTE') AS can_execute",
            (
                self.outsider_role, self.schema,
                self.outsider_role, self.schema + ".jobs",
                self.outsider_role, self.schema + ".guard_job_scope()",
            ),
        )[0]
        self.assertEqual(after, {"can_use": False, "can_read": False, "can_execute": False})
        state = self.access_snapshot()
        self.assertEqual(len(state["policies"]), 9)
        tables = [r for r in state["relations"] if r["relname"] in {
            "schema_info", "jobs", "partitions", "receipts", "records",
            "verifications", "events", "rejections", "source_limits",
        }]
        self.assertEqual(len(tables), 9)
        self.assertTrue(all(table["relrowsecurity"] for table in tables))

        api = AssumedRoleStore(self.test_url, self.schema, self.api_role)
        worker = AssumedRoleStore(self.test_url, self.schema, self.worker_role)
        self.assertTrue(api.health()["ready"])
        self.assertTrue(worker.health()["ready"])
        job = api.submit_job(
            IngestionSpec.from_dict(postgres_qualification.BASE),
            "role-qualification-001",
        )
        source = postgres_qualification.FixtureSource()
        self.assertEqual(Worker(worker, source).run_once()["state"], "page_committed")
        self.assertEqual(Worker(worker, source).run_once()["state"], "verified")
        final = api.get_job(job["id"])
        self.assertEqual((final["status"], final["verification_status"]), ("completed", "passed"))
        self.assertEqual(source.calls, 1)

        # The invoker trigger still enforces immutable scope for the limited API.
        with self.assertRaises(self.database_error):
            with api.transaction() as conn:
                api.execute(conn, "UPDATE {s}jobs SET spec='{}' WHERE id=?", (job["id"],))
        for role, statement in [
            (self.api_role, f"SELECT * FROM {self.schema}.records"),
            (self.api_role, f"UPDATE {self.schema}.source_limits SET next_request_at=0"),
            (self.worker_role, f"INSERT INTO {self.schema}.jobs(id) VALUES('forbidden')"),
            (self.worker_role, f"UPDATE {self.schema}.records SET payload='{{}}'"),
            (self.worker_role, f"DELETE FROM {self.schema}.receipts"),
            (self.outsider_role, f"SELECT * FROM {self.schema}.jobs"),
        ]:
            self.assert_denied(role, statement)
        for role in (self.api_role, self.worker_role):
            self.assert_denied(role, f"SELECT * FROM {self.net_schema}.http_request_queue")
            self.assert_denied(role, f"INSERT INTO {self.net_schema}.http_request_queue VALUES(2,'forbidden')")

    def test_existing_role_collision_rolls_back_without_adopting_role(self):
        with self.store.connect() as conn:
            conn.execute(
                self.pg_sql.SQL("CREATE ROLE {} NOLOGIN BYPASSRLS").format(
                    self.pg_sql.Identifier(self.worker_role)
                )
            )
        before = self.access_snapshot()
        roles_before = self.existing_runtime_roles()
        with self.assertRaisesRegex(self.database_error, "role name already exists"):
            self.apply_roles()
        self.assertEqual(self.existing_runtime_roles(), roles_before)
        self.assertEqual(len(roles_before), 1)
        self.assertTrue(roles_before[0]["rolbypassrls"])
        self.assertEqual(self.access_snapshot(), before)

    def test_public_pg_net_access_aborts_and_rolls_back_created_roles(self):
        with self.store.connect() as conn:
            conn.execute(
                self.pg_sql.SQL("GRANT USAGE ON SCHEMA {} TO PUBLIC").format(
                    self.pg_sql.Identifier(self.net_schema)
                )
            )
            conn.execute(
                self.pg_sql.SQL("GRANT ALL ON ALL TABLES IN SCHEMA {} TO PUBLIC").format(
                    self.pg_sql.Identifier(self.net_schema)
                )
            )
        # Prove PUBLIC defeats NOINHERIT in this isolated fixture.
        leaked = self.read(
            "SELECT has_schema_privilege(%s,%s,'USAGE') AS can_use,"
            "has_table_privilege(%s,%s,'UPDATE') AS can_change",
            (
                self.outsider_role, self.net_schema,
                self.outsider_role, self.net_schema + ".http_request_queue",
            ),
        )[0]
        self.assertEqual(leaked, {"can_use": True, "can_change": True})
        before = self.access_snapshot()
        with self.assertRaisesRegex(self.database_error, "inherits pg_net access"):
            self.apply_roles()
        self.assertEqual(self.existing_runtime_roles(), [])
        self.assertEqual(self.access_snapshot(), before)
        # Admission is a refusal, never a repair of unrelated provider grants.
        preserved = self.read(
            "SELECT has_schema_privilege(%s,%s,'USAGE') AS can_use,"
            "has_table_privilege(%s,%s,'UPDATE') AS can_change",
            (
                self.outsider_role, self.net_schema,
                self.outsider_role, self.net_schema + ".http_request_queue",
            ),
        )[0]
        self.assertEqual(preserved, leaked)


if __name__ == "__main__":
    unittest.main()
