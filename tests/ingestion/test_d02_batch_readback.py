"""Offline regressions for independent batch comparison."""
from decimal import Decimal
import unittest
from uuid import uuid4

from astra_ingestion import aug_d02_pilot as pilot
from astra_ingestion.d02_batch_readback import verify


class BatchReadback(unittest.TestCase):
    def setUp(self):
        self.attempt = uuid4()
        members, bars, self.dest = [], [], []
        for n in range(11, 21):
            ticker = f"TEST{n}"
            raw = '{"T":"%s","t":1785873600000,"o":3,"h":4,"l":2,"c":3,"vw":3,"n":2,"v":17.000000000000001}' % ticker
            m = dict(ordinal=n, company_id=f"CIK:{n:010}", ticker=ticker, exchange_mic="XNAS",
                     issue_type="CS", composite_figi=f"BBG{n:09}", share_class_figi=f"BBG{100+n:09}",
                     source_row=n, raw_record_sha256=pilot.sha(raw.encode()), identity_source_sha256="f"*64,
                     identity_record_sha256="d"*64)
            members.append(m)
            bars.append(dict(source_row=n, raw_record_text=raw))
            self.dest.append(dict(m, session_date=pilot.TRADE_DATE, raw_close=3,
                                  raw_volume=Decimal("17.000000000000001"), verified=True,
                                  effective_role=pilot.VERIFIER_ROLE, source_sha256=pilot.SOURCE_SHA,
                                  attempt=str(self.attempt)))
        self.manifest = pilot.canonical(dict(schema="astra-d02-batch/v1", members=members,
            date=pilot.TRADE_DATE, cohort_sha256=pilot.COHORT_SHA, source_sha256=pilot.SOURCE_SHA)).encode()
        self.pin = pilot.sha(self.manifest)
        self.projection = dict(source_sha256=pilot.SOURCE_SHA, date=pilot.TRADE_DATE, rows=bars)
        for row in self.dest:
            row["manifest_sha"] = self.pin

    def compare(self, rows, first=11, pin=None):
        return verify(self.manifest, pin or self.pin, self.attempt, first, self.projection, rows)

    def test_exact_readback_and_batch_binding(self):
        self.assertEqual(self.compare(list(reversed(self.dest)))["verified"], 10)
        with self.assertRaises(pilot.PilotError):
            self.compare(self.dest, first=21)
        with self.assertRaises(pilot.PilotError):
            self.compare(self.dest, pin="f"*64)

    def test_rejects_wrong_key_role_or_value(self):
        for changes in ({"share_class_figi": "other"}, {"attempt": str(uuid4())},
                        {"effective_role": "postgres"}, {"raw_volume": 17}, {"verified": False}):
            with self.subTest(fields=tuple(changes)), self.assertRaises(pilot.PilotError):
                self.compare([dict(self.dest[0], **changes), *self.dest[1:]])
        with self.assertRaises(pilot.PilotError):
            self.compare([self.dest[1], *self.dest[1:]])
