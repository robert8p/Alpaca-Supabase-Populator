"""Bounded unit checks; no database or credential access."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("native_probe", Path(__file__).with_name("native_readonly_probe.py"))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class NativeReadOnlyProbeTests(unittest.TestCase):
    def test_exact_bytes_one_command_no_shell_file_mode_or_startup_script(self):
        payload = probe.checked_probe_bytes()
        command = probe.build_command(service="owner-existing", local_qualification=False,
                                      owner_confirmed=True, payload=payload)
        self.assertEqual(command[-2:], ["--command", payload.decode("utf-8")])
        self.assertTrue(command[-1].endswith("\n"))
        self.assertEqual(command.count("--command"), 1)
        self.assertIn("--no-psqlrc", command)
        self.assertIn("--no-password", command)
        self.assertNotIn("--file", command)

    def test_sql_substitution_and_newline_loss_fail_before_execution(self):
        payload = probe.checked_probe_bytes()
        for invalid in (payload.rstrip(b"\n"), payload + b"SELECT 1;\n", b"SELECT 1;\n"):
            with self.subTest(payload=invalid[-30:]), self.assertRaises(probe.ProbePreparationError):
                probe.build_command(service="owner-existing", local_qualification=False,
                                    owner_confirmed=True, payload=invalid)

    def test_disposable_target_pins_hostaddr_against_inherited_libpq_routing(self):
        command = probe.build_command(service=None, local_qualification=True,
                                      owner_confirmed=False, payload=probe.checked_probe_bytes())
        connection = command[command.index("--dbname") + 1].split()
        for required in ("host=127.0.0.1", "hostaddr=127.0.0.1", "port=55432",
                         "dbname=astra_ingestion_qualification", "user=postgres"):
            self.assertIn(required, connection)

    def test_connection_parameters_cannot_be_injected(self):
        for service in ("owner-existing password=secret", "host=elsewhere", "x\ny", ""):
            with self.subTest(service=service), self.assertRaises(probe.ProbePreparationError):
                probe.build_command(service=service, local_qualification=False,
                                    owner_confirmed=True, payload=probe.checked_probe_bytes())

    def test_owner_confirmation_is_required_before_any_subprocess(self):
        with mock.patch.object(probe.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(probe.main(["--service", "owner-existing"]), 1)
        run.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())["status"], "PREPARATION_REJECTED")

    def test_only_exact_readonly_receipt_passes_and_never_claims_ready(self):
        observed = {"probe_id": probe.PROBE_ID, "transaction_read_only": "on",
                    "query_utf8_bytes": probe.PROBE_BYTES, "query_sha256": probe.PROBE_SHA256,
                    "final_byte_ascii": 10}
        good = probe.assess_result(0, json.dumps(observed), "", mode="TEST")
        self.assertTrue(good["transport_probe_passed"])
        self.assertFalse(good["production_ready"])
        self.assertFalse(good["migration_executed"])
        for key, value in (("transaction_read_only", "off"), ("query_sha256", "0" * 64),
                           ("final_byte_ascii", 59), ("query_utf8_bytes", probe.PROBE_BYTES - 1)):
            with self.subTest(key=key):
                bad = probe.assess_result(0, json.dumps({**observed, key: value}), "", mode="TEST")
                self.assertFalse(bad["transport_probe_passed"])

    def test_connection_diagnostics_are_not_echoed_and_no_retry_occurs(self):
        completed = mock.Mock(returncode=2, stdout="", stderr="PRIVATE_CONNECTION_DIAGNOSTIC")
        with mock.patch.object(probe.subprocess, "run", return_value=completed) as run, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(probe.main(["--local-qualification"]), 1)
        run.assert_called_once()
        self.assertIs(run.call_args.kwargs["shell"], False)
        self.assertEqual(run.call_args.kwargs["timeout"], 12)
        self.assertNotIn("PRIVATE_CONNECTION_DIAGNOSTIC", out.getvalue())
        self.assertEqual(json.loads(out.getvalue())["status"], "PSQL_FAILED_NO_RETRY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
