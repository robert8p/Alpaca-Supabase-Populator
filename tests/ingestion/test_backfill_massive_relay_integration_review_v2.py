"""Qualify the authorized active worker against the immutable reviewed patch/base."""
from hashlib import sha256
import difflib
import json
import os
from pathlib import Path
import types
import unittest
from unittest.mock import patch
from urllib.error import URLError

from astra_ingestion.backfill_massive_relay_v2 import MassiveRelay, ProviderWithManagedMassive
from astra_ingestion.config import Settings
from astra_ingestion.rpc_store import PROJECT_URL
import test_backfill_massive_relay_v2 as relay_fixture

ROOT=Path(__file__).resolve().parents[2]
REVIEW=ROOT/'review/massive-relay-v2'
BASELINE=ROOT/'review/massive-relay-v3/activation/baseline_backfill_worker_v2.py'


class RelayIntegrationReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module=types.ModuleType('astra_ingestion._managed_relay_integration_review')
        cls.module.__package__='astra_ingestion'
        source=(ROOT/'astra_ingestion/backfill_worker_v2.py').read_text()
        exec(compile(source,'authorized-active-worker','exec'),cls.module.__dict__)

    def test_exact_patch_frozen_base_and_active_worker_match_review_hashes(self):
        metadata=json.loads((REVIEW/'worker-integration-review.json').read_text())
        base=BASELINE.read_bytes()
        active=(ROOT/'astra_ingestion/backfill_worker_v2.py').read_bytes()
        proposed=(REVIEW/'backfill_worker_v2.py.proposed').read_bytes()
        diff=(REVIEW/'worker-integration.patch').read_bytes()
        self.assertEqual(sha256(base).hexdigest(),metadata['base_worker_sha256'])
        self.assertEqual(sha256(proposed).hexdigest(),metadata['proposed_worker_sha256'])
        self.assertEqual(active,proposed)
        self.assertEqual(sha256(diff).hexdigest(),metadata['patch_sha256'])
        actual=''.join(difflib.unified_diff(base.decode().splitlines(True),proposed.decode().splitlines(True),
            fromfile='a/astra_ingestion/backfill_worker_v2.py',tofile='b/astra_ingestion/backfill_worker_v2.py'))
        self.assertEqual(actual,diff.decode())
        sql=(ROOT/'review/massive-relay-v3/candidates/sql/astra_backfill_massive_relay_v3.sql').read_text()
        for value in (metadata['base_worker_sha256'],metadata['proposed_worker_sha256'],metadata['patch_sha256']):
            self.assertIn(value,sql)

    def test_active_constructor_uses_actual_auth_readiness_without_starting_queue_or_provider_fetch(self):
        settings=Settings(api_url=PROJECT_URL,publishable_key=relay_fixture.PUBLIC,rpc_token=relay_fixture.TOKEN,
            api_key='fixture-alpaca',secret_key='fixture-alpaca-secret')
        for response,ready in [({'ready':True},True),({'ready':False},False),(URLError('unavailable'),False)]:
            with self.subTest(ready=ready,response=type(response).__name__):
                opener=relay_fixture.Opener(response)
                relay=MassiveRelay(PROJECT_URL,relay_fixture.PUBLIC,relay_fixture.TOKEN,opener=opener)
                store=object()
                with patch.dict(os.environ,{},clear=True),patch('astra_ingestion.backfill_massive_relay_v2.MassiveRelay',return_value=relay):
                    worker=self.module.from_settings(store,settings)
                self.assertIs(worker.store,store);self.assertIsInstance(worker.provider,ProviderWithManagedMassive)
                self.assertEqual(any(k.startswith('massive_') for k in worker.supported_kinds),ready)
                self.assertIn('alpaca_news',worker.supported_kinds)
                self.assertIn('retained_identity',worker.supported_kinds);self.assertIn('retained_massive_archive',worker.supported_kinds)
                self.assertEqual(worker.plan_member_limit,5);self.assertEqual(len(opener.calls),1)
                self.assertEqual(json.loads(opener.calls[0][0].data),{'action':'probe'})

    def test_active_local_database_and_direct_massive_paths_do_not_send_relay_probe(self):
        with patch.dict(os.environ,{},clear=True),patch('astra_ingestion.backfill_massive_relay_v2.MassiveRelay') as constructor:
            worker=self.module.from_settings(object(),Settings(api_key='fixture',secret_key='fixture'))
            constructor.assert_not_called()
            self.assertNotIsInstance(worker.provider,ProviderWithManagedMassive)
        settings=Settings(api_url=PROJECT_URL,publishable_key=relay_fixture.PUBLIC,rpc_token=relay_fixture.TOKEN,
            api_key='fixture',secret_key='fixture')
        opener=relay_fixture.Opener();relay=MassiveRelay(PROJECT_URL,relay_fixture.PUBLIC,relay_fixture.TOKEN,opener=opener)
        with patch.dict(os.environ,{'MASSIVE_API_KEY':'existing-direct-fixture'},clear=True),patch('astra_ingestion.backfill_massive_relay_v2.MassiveRelay',return_value=relay):
            worker=self.module.from_settings(object(),settings)
        self.assertIn('massive_news',worker.supported_kinds);self.assertFalse(worker.provider.relay_active)
        self.assertEqual(opener.calls,[])


if __name__=='__main__':unittest.main()
