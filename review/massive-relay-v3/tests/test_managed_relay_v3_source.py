"""Exact source/diff/probe pin checks for the separately reviewed v3 package."""
from hashlib import sha256
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]
V3=ROOT/'review/massive-relay-v3'
V2_SQL=ROOT/'review/massive-relay-v2/candidates/sql/astra_backfill_massive_relay_v2.sql'
V3_SQL=V3/'candidates/sql/astra_backfill_massive_relay_v3.sql'
V2_ID='managed-massive-relay-v2-review-20261030'
V3_ID='managed-massive-relay-v3-review-20261030'
V2_SCOPE='7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe'


class VersionedSourceTests(unittest.TestCase):
    def test_all_frozen_v2_payloads_remain_byte_identical(self):
        manifest=json.loads((ROOT/'evidence/replacement-managed-relay-review-manifest-v2.json').read_text())
        self.assertEqual(len(manifest['files']),19)
        for entry in manifest['files']:
            with self.subTest(path=entry['path']):
                data=(ROOT/entry['path']).read_bytes()
                self.assertEqual(len(data),entry['bytes'])
                self.assertEqual(sha256(data).hexdigest(),entry['sha256'])
        self.assertEqual(sha256(V2_SQL.read_bytes()).hexdigest(),'4be1c6d145949f4cda35a1cef7772da93137e3f102f045f1a7507ea66a16652d')

    def test_candidate_diff_has_only_declared_version_and_exact_terminal_variation(self):
        scope=json.loads((ROOT/'evidence/replacement-managed-relay-review-scope-v3.json').read_text())
        digest=sha256(json.dumps(scope,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        before=V2_SQL.read_text()
        expected=before.replace('BEGIN_V2','BEGIN_V3').replace('END_V2','END_V3')
        expected=expected.replace(V2_ID,V3_ID).replace(V2_SCOPE,digest)
        expected=expected.replace("tag||'astra_backfill_massive_relay_v2'||tag","tag||'astra_backfill_massive_relay_v3'||tag")
        expected=expected.replace("  IF transport_suffix<>expected_suffix THEN\n",
            "  -- v3 accepts two exact transport byte strings: the reviewed wrapper with\n"
            "  -- its final LF, or the same wrapper ending at the commit semicolon.\n"
            "  -- No trimming, normalization, ignored comments or additional SQL is allowed.\n"
            "  IF transport_suffix<>expected_suffix\n"
            "   AND transport_suffix<>left(expected_suffix,length(expected_suffix)-1) THEN\n")
        self.assertEqual(V3_SQL.read_text(),expected)
        self.assertEqual(scope['review_id'],V3_ID)
        self.assertNotEqual(digest,V2_SCOPE)
        self.assertEqual(scope['protocol'],'astra-massive-relay-v2')
        self.assertIn("confirmed<clock_timestamp()-interval '15 minutes'",expected)
        self.assertIn("confirmed>clock_timestamp()+interval '1 minute'",expected)

    def test_two_wrapper_templates_differ_only_in_one_terminal_lf(self):
        with_lf=(V3/'apply-migration-wrapper-final-lf.txt').read_bytes()
        without_lf=(V3/'apply-migration-wrapper-no-final-lf.txt').read_bytes()
        self.assertEqual(with_lf,without_lf+b'\n')
        self.assertTrue(with_lf.endswith(b'commit;\n'))
        self.assertEqual(with_lf.count(b'<EXACT_APPROVED_MIGRATION_BYTES>'),2)
        scope=json.loads((ROOT/'evidence/replacement-managed-relay-review-scope-v3.json').read_text())
        self.assertEqual(sha256(with_lf).hexdigest(),scope['installer_transport']['wrapper_template_final_lf_sha256'])
        self.assertEqual(sha256(without_lf).hexdigest(),scope['installer_transport']['wrapper_template_no_final_lf_sha256'])

    def test_abort_probe_parser_is_byte_identical_except_named_probe_boundaries(self):
        installer=V3_SQL.read_text()
        probe=(V3/'transport_readonly_probe_v3.sql').read_text()
        parser=installer.split('DO $preflight$\n',1)[1].split(" IF to_regclass('astra_ingestion_v1.backfill_relay_dispatches_v2')",1)[0]
        probe_parser=probe.split('DO $preflight$\n',1)[1].split(" IF current_setting('transaction_read_only')",1)[0]
        expected=parser.replace('ASTRA_RELAY_REVIEW_SQL_','ASTRA_RELAY_TRANSPORT_PROBE_SQL_')
        expected=expected.replace("tag||'astra_backfill_massive_relay_v3'||tag","tag||'astra_backfill_massive_relay_v3_transport_probe'||tag")
        self.assertEqual(probe_parser,expected)
        self.assertIn('SET LOCAL transaction_read_only=on;',probe)
        self.assertIn("RAISE EXCEPTION USING ERRCODE='P0001'",probe)
        self.assertNotIn('CREATE TABLE astra_ingestion_v1.',probe)
        self.assertNotIn('UPDATE astra_ingestion_v1.',probe)
        self.assertNotIn('GRANT ',probe)
        packet=json.loads((V3/'transport_readonly_probe_action_v3.json').read_text())
        self.assertEqual(packet['arguments']['query'],probe)
        self.assertEqual(packet['sha256'],sha256(probe.encode()).hexdigest())
        self.assertEqual(packet['bytes'],len(probe.encode()))
        self.assertTrue(packet['not_an_installation_attempt'])


if __name__=='__main__': unittest.main()
