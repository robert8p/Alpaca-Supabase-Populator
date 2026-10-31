#!/usr/bin/env python3
"""Run one fixed, read-only exact-byte probe through an existing psql connection.

This runner cannot execute the relay migration or accept arbitrary SQL. It does
not inspect credentials, create connection profiles, record approval, or retry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


PROBE_PATH = Path(__file__).with_name("native_readonly_probe.sql")
PROBE_SHA256 = "2a292e5b12394f0c5b4ddc455f7c04291ff61956c5b2565e302e8e9d526b526e"
PROBE_BYTES = 712
PROBE_ID = "astra-native-readonly-exact-transport-v2"
LOCAL_QUALIFICATION_CONNECTION = (
    "host=127.0.0.1 hostaddr=127.0.0.1 port=55432 dbname=astra_ingestion_qualification "
    "user=postgres connect_timeout=5"
)
PSQL_TIMEOUT_SECONDS = 12


class ProbePreparationError(ValueError):
    """A fixed input or explicit connection selection failed validation."""


def checked_probe_bytes() -> bytes:
    payload = PROBE_PATH.read_bytes()
    if (
        len(payload) != PROBE_BYTES
        or hashlib.sha256(payload).hexdigest() != PROBE_SHA256
        or not payload.endswith(b"\n")
    ):
        raise ProbePreparationError("Fixed read-only probe bytes do not match the reviewed probe")
    return payload


def build_command(*, service: str | None, local_qualification: bool,
                  owner_confirmed: bool, payload: bytes) -> list[str]:
    # Validate again at the subprocess boundary; callers cannot substitute SQL.
    if len(payload) != PROBE_BYTES or hashlib.sha256(payload).hexdigest() != PROBE_SHA256:
        raise ProbePreparationError("Only the fixed read-only probe is executable")
    if local_qualification:
        if service is not None:
            raise ProbePreparationError("Select exactly one explicit connection mode")
        connection = LOCAL_QUALIFICATION_CONNECTION
    else:
        if not owner_confirmed or service is None:
            raise ProbePreparationError("An existing owner-authorized service must be confirmed")
        if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", service) is None:
            raise ProbePreparationError("Service must be a simple existing libpq service name")
        connection = f"service={service} connect_timeout=5"
    # --command passes this exact UTF-8 string as one request. No shell, file
    # parser, statement splitting, .strip(), newline conversion or psqlrc.
    return [
        "psql", "--no-psqlrc", "--no-password", "--quiet", "--tuples-only",
        "--no-align", "--set", "ON_ERROR_STOP=1", "--dbname", connection,
        "--command", payload.decode("utf-8"),
    ]


def assess_result(returncode: int, stdout: str, stderr: str, *, mode: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "probe_id": PROBE_ID,
        "connection_mode": mode,
        "probe_sha256": PROBE_SHA256,
        "probe_bytes": PROBE_BYTES,
        "transport_probe_passed": False,
        "production_ready": False,
        "migration_executed": False,
        "approval_recorded": False,
        "psql_returncode": returncode,
    }
    # Raw errors may contain connection details. Return only bounded metadata.
    if returncode != 0:
        result.update(
            status="PSQL_FAILED_NO_RETRY",
            stderr_bytes=len(stderr.encode("utf-8")),
            stderr_sha256=hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        )
        return result
    lines = [line for line in stdout.splitlines() if line.strip()]
    try:
        observed = json.loads(lines[0]) if len(lines) == 1 and len(stdout) <= 4096 else None
    except (ValueError, TypeError):
        observed = None
    expected = {
        "probe_id": PROBE_ID,
        "transaction_read_only": "on",
        "query_utf8_bytes": PROBE_BYTES,
        "query_sha256": PROBE_SHA256,
        "final_byte_ascii": 10,
    }
    if not isinstance(observed, dict) or observed != expected:
        result.update(
            status="READ_ONLY_EXACT_BYTE_PROBE_FAILED",
            stdout_bytes=len(stdout.encode("utf-8")),
            stdout_sha256=hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        )
        return result
    result.update(
        status="READ_ONLY_EXACT_BYTE_PROBE_PASSED",
        transport_probe_passed=True,
        observed=observed,
        readiness_note=(
            "This proves only the selected connection's read-only transport. "
            "The existing controller must reconcile the production target and hold, "
            "then obtain fresh action-time confirmation before any unchanged relay application."
        ),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--service", help="Name of an already configured owner-authorized libpq service")
    target.add_argument("--local-qualification", action="store_true",
                        help="Use only the fixed disposable loopback qualification database")
    parser.add_argument("--owner-confirms-existing-authorized-connection", action="store_true")
    args = parser.parse_args(argv)
    mode = "DISPOSABLE_LOCAL_QUALIFICATION" if args.local_qualification else "OWNER_EXISTING_SERVICE"
    try:
        command = build_command(
            service=args.service,
            local_qualification=args.local_qualification,
            owner_confirmed=args.owner_confirms_existing_authorized_connection,
            payload=checked_probe_bytes(),
        )
        completed = subprocess.run(
            command, shell=False, capture_output=True, text=True, encoding="utf-8",
            check=False, timeout=PSQL_TIMEOUT_SECONDS,
        )
        result = assess_result(completed.returncode, completed.stdout, completed.stderr, mode=mode)
    except ProbePreparationError as exc:
        result = {"status": "PREPARATION_REJECTED", "reason": str(exc),
                  "transport_probe_passed": False, "production_ready": False,
                  "migration_executed": False, "approval_recorded": False}
    except subprocess.TimeoutExpired:
        result = {"status": "BOUNDED_CLIENT_TIMEOUT_NO_RETRY", "timeout_seconds": PSQL_TIMEOUT_SECONDS,
                  "transport_probe_passed": False, "production_ready": False,
                  "migration_executed": False, "approval_recorded": False}
    except (OSError, UnicodeError):
        result = {"status": "LOCAL_CLIENT_OR_FIXED_FILE_UNAVAILABLE_NO_RETRY",
                  "transport_probe_passed": False, "production_ready": False,
                  "migration_executed": False, "approval_recorded": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["transport_probe_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
