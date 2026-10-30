"""Independent read-only PostgreSQL wrapper adversary checks; fixed loopback only.

This never installs the relay, records approval, creates objects or invokes a
provider. Every request must end in an intentional exception and rollback.
"""
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic

import psycopg

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "review/massive-relay-v3"
PROBE_SHA = "d5fb3052dab18dd2b7975f9bd0d773f35902de43b805b91cb97ee8f309c9b12f"
SUCCESS = "ASTRA_RELAY_V3_TRANSPORT_PROBE_ACCEPTED "


def main():
    probe_bytes = (BASE / "transport_readonly_probe_v3.sql").read_bytes()
    assert sha256(probe_bytes).hexdigest() == PROBE_SHA
    probe = probe_bytes.decode("utf-8")
    template = (BASE / "apply-migration-wrapper-no-final-lf.txt").read_text()
    template = template.replace("astra_backfill_massive_relay_v3", "astra_backfill_massive_relay_v3_transport_probe")
    template = template.replace("<ACCOUNT_IDENTIFIER>", "independent-local-review")
    wrapped = template.replace("<EXACT_APPROVED_MIGRATION_BYTES>", probe)
    def changed_wrapper(old, new):
        assert old in template
        return template.replace(old, new, 1).replace("<EXACT_APPROVED_MIGRATION_BYTES>", probe)
    tag = "$USQrtAZZkmYPmewYmQrd$"
    cases = [
        ("exact_no_final_lf", wrapped, True),
        ("exact_final_lf", wrapped + "\n", True),
        ("extra_unicode_line_separator", wrapped + "\u2028", False),
        ("extra_form_feed", wrapped + "\f", False),
        ("extra_lf_space", wrapped + "\n ", False),
        ("extra_comment_without_lf", wrapped + "-- invisible tail", False),
        ("altered_history_column", changed_wrapper("(version, name, statements, created_by, idempotency_key, rollback)", "(version, name, statements, created_by, idempotency_key, other_column)"), False),
        ("nonnull_idempotency_key", changed_wrapper("\n  null,\n  null\n)", "\n  'review-key',\n  null\n)"), False),
        ("nonnull_rollback", changed_wrapper("\n  null,\n  null\n)", "\n  null,\n  'review-rollback'\n)"), False),
        ("modified_history_conflict_update", changed_wrapper("created_by = EXCLUDED.created_by;", "created_by = old.created_by;"), False),
        ("nonletter_delimiter", wrapped.replace(tag, "$12345678901234567890$"), False),
        ("nineteen_letter_delimiter", wrapped.replace(tag, "$ABCDEFGHIJKLMNOPQRS$"), False),
        ("twenty_one_letter_delimiter", wrapped.replace(tag, "$ABCDEFGHIJKLMNOPQRSTU$"), False),
        ("account_quote", wrapped.replace("independent-local-review", "review'actor"), False),
        ("body_delimiter_collision", template.replace("<EXACT_APPROVED_MIGRATION_BYTES>", probe.replace("-- Read-only transport", "-- " + tag + "\n-- Read-only transport", 1)), False),
    ]
    out = []
    started = monotonic()
    # Both host and hostaddr are explicit: inherited connection routing cannot
    # change the fixed disposable target. No service/DSN argument is accepted.
    with psycopg.connect(
        "host=127.0.0.1 hostaddr=127.0.0.1 port=55432 dbname=astra_ingestion_qualification user=postgres",
        connect_timeout=5, options="-c default_transaction_read_only=on",
    ) as conn:
        version = conn.execute("SHOW server_version").fetchone()[0]
        conn.rollback()
        for name, sql, should_accept in cases:
            assert should_accept or sql != wrapped, name
            try:
                conn.execute(sql)
            except psycopg.Error as error:
                accepted = bool(error.diag.message_primary and error.diag.message_primary.startswith(SUCCESS))
                assert accepted == should_accept, (name, error.sqlstate)
                if accepted:
                    receipt = json.loads(error.diag.message_primary[len(SUCCESS):])
                    assert receipt["probe_sha256"] == PROBE_SHA
                    assert receipt["probe_bytes"] == len(probe_bytes)
                    assert receipt["final_body_byte_ascii"] == 10
                    assert receipt["history_copy_verified"] is True
                    assert receipt["read_only"] is True
                    assert receipt["migration_applied"] is False
                    assert receipt["approval_modified"] is False
                    assert receipt["provider_requests"] == 0
                out.append({"case": name, "accepted_probe_only": accepted,
                            "sqlstate": error.sqlstate,
                            "input_sha256": sha256(sql.encode()).hexdigest()})
            else:
                raise AssertionError((name, "probe failed to abort"))
            finally:
                conn.rollback()
    print(json.dumps({"state": "PASS", "local_only": True, "server_version": version,
                      "cases": out, "case_count": len(out), "elapsed_seconds": round(monotonic()-started, 3),
                      "probe_sha256": PROBE_SHA, "production_calls": 0, "ddl_writes": 0,
                      "approval_writes": 0, "provider_requests": 0}, indent=2))


if __name__ == "__main__":
    main()
