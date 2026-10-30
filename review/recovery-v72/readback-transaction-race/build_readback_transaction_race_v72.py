"""Prepare one predicate repair from retained live source; never connect to a database."""
from hashlib import sha256
import difflib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V71 = ROOT / 'review/recovery-v71'
LIVE_RUN = 'fixed3000-20250901-20260731-v1-20261030'
OWNER = 'root-replacement-20261030T042603Z'
BASELINE_SHA = 'cd10046d9c9aa15e8bc66724d1258d95151364ffeee9070d761c4f7d930b5859'
RECHECK_SHA = '0ccd4018d16e3ed3932176d2886fe78c2c1b442d70473d71e137d86e7b6dfb37'
OLD = "  WHERE rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') AND NOT EXISTS("
NEW = "  WHERE rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') AND pg.committed_at<transaction_timestamp() AND NOT EXISTS("


def digest(value):
    return sha256(value.encode()).hexdigest()


def build():
    retained = json.loads((V71 / 'live_backfill_maintain_1332.json').read_text())[0]
    baseline = retained['definition']
    assert digest(baseline) == BASELINE_SHA
    assert baseline.count(OLD) == 1
    candidate = baseline.replace(OLD, NEW)
    assert candidate.replace(NEW, OLD) == baseline
    helper = next(x for x in json.loads((V71 / 'live_maintenance_helpers_1335.json').read_text())[0]['evidence']['definitions']
                  if x['proname'] == 'backfill_recheck_page_v2')
    assert digest(helper['definition']) == RECHECK_SHA
    assert "IF p.committed_at>=transaction_timestamp() THEN RAISE EXCEPTION USING ERRCODE='AI005'" in helper['definition']
    metadata = json.dumps(retained['metadata'], sort_keys=True, separators=(',', ':'))
    pins = {
        'backfill_recheck_page_v2(text,integer)': RECHECK_SHA,
        'backfill_dispatch_v2(text,jsonb)': '28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44',
        'rpc_dispatch(text,jsonb)': 'a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520',
    }
    forward = """-- PREPARATION ONLY. One predicate defers pages that the unchanged verifier
-- cannot independently read in this transaction. Existing failure exclusions,
-- verifier, provider paths, gate, limits, exceptions, return and metadata remain.
-- Root must reconcile all other selected forwards before any separate dispatch.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $readback_transaction_race$
DECLARE
 v_before text;
 v_after text;
 v_before_metadata jsonb;
 v_after_metadata jsonb;
 v_other_before jsonb;
 v_other_after jsonb;
 v_expected_metadata constant jsonb := $metadata$__METADATA__$metadata$::jsonb;
 v_old constant text := $selector$__OLD__$selector$;
 v_new constant text := $selector$__NEW__$selector$;
 g record;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s'
  OR current_setting('transaction_read_only')<>'off' THEN
  RAISE EXCEPTION 'Readback transaction repair requires reviewed8-second statement and3-second lock writable bounds';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()
 FOR SHARE;
 IF NOT FOUND OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2
  WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
  RAISE EXCEPTION 'Readback transaction repair owner, lease, active run, fence or fixed cohort differs';
 END IF;
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc'
 INTO STRICT v_before,v_before_metadata FROM pg_proc p
 WHERE p.oid='astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 IF encode(sha256(convert_to(v_before,'UTF8')),'hex')<>'__BEFORE_SHA__'
  OR v_before_metadata IS DISTINCT FROM v_expected_metadata THEN
  RAISE EXCEPTION 'Readback transaction repair exact baseline source or metadata changed; reconcile before replay';
 END IF;
 FOR g IN SELECT * FROM (VALUES
__PINS__
 ) p(signature,expected_sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(g.signature::regprocedure),'UTF8')),'hex')<>g.expected_sha256 THEN
   RAISE EXCEPTION 'Readback transaction repair unchanged verifier or authenticated dispatch source differs';
  END IF;
 END LOOP;
 IF (length(v_before)-length(replace(v_before,v_old,'')))/length(v_old)<>1
  OR strpos(v_before,v_new)>0 THEN
  RAISE EXCEPTION 'Readback transaction repair must change exactly one original selector';
 END IF;
 v_after:=replace(v_before,v_old,v_new);
 IF encode(sha256(convert_to(v_after,'UTF8')),'hex')<>'__AFTER_SHA__'
  OR replace(v_after,v_new,v_old) IS DISTINCT FROM v_before THEN
  RAISE EXCEPTION 'Readback transaction repair candidate is not the reviewed single predicate';
 END IF;
 SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) INTO v_other_before FROM pg_proc p
 WHERE p.pronamespace='astra_ingestion_v1'::regnamespace
  AND p.oid<>'astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 EXECUTE v_after;
 SELECT to_jsonb(p)-'prosrc' INTO STRICT v_after_metadata FROM pg_proc p
 WHERE p.oid='astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) INTO v_other_after FROM pg_proc p
 WHERE p.pronamespace='astra_ingestion_v1'::regnamespace
  AND p.oid<>'astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 IF v_after_metadata IS DISTINCT FROM v_before_metadata OR v_other_after IS DISTINCT FROM v_other_before
  OR pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) IS DISTINCT FROM v_after THEN
  RAISE EXCEPTION 'Readback transaction repair altered metadata, another function or unexpected source';
 END IF;
 -- Recheck the original pins after replacement as well: a source change between
 -- the admission precheck and preservation snapshot must not become baseline.
 FOR g IN SELECT * FROM (VALUES
__PINS__
 ) p(signature,expected_sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(g.signature::regprocedure),'UTF8')),'hex')<>g.expected_sha256 THEN
   RAISE EXCEPTION 'Readback transaction repair verifier or authenticated source changed before completion';
  END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
  WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
   AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
   AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
   AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()) THEN
  RAISE EXCEPTION 'Readback transaction repair run, owner or lease changed before completion';
 END IF;
END $readback_transaction_race$;
COMMIT;
"""
    forward = forward.replace('__METADATA__', metadata).replace('__OLD__', OLD).replace('__NEW__', NEW)
    forward = forward.replace('__BEFORE_SHA__', BASELINE_SHA).replace('__AFTER_SHA__', digest(candidate))
    forward = forward.replace('__PINS__', ',\n'.join("  ('astra_ingestion_v1.%s','%s')" % pair for pair in pins.items()))
    outputs = {
        'baseline_maintain_v2.sql': baseline,
        'candidate_maintain_readback_transaction_v72.sql': candidate,
        'unchanged_recheck_page_v2.sql': helper['definition'],
        'forward_readback_transaction_race_v72.sql': forward,
        'readback_transaction_race_v72.diff': ''.join(difflib.unified_diff(baseline.splitlines(True), candidate.splitlines(True),
            fromfile='retained/cd10046d/backfill_maintain_v2.sql', tofile='candidate/backfill_maintain_v2.sql')),
    }
    for name, source in outputs.items():
        (HERE / name).write_text(source)
    manifest = {
        'schema': 'astra.readback-transaction-race-derivation/1',
        'status': 'PREPARATION_ONLY_NOT_ACTIVATION_AUTHORITY',
        'baseline_sha256': BASELINE_SHA, 'candidate_sha256': digest(candidate),
        'unchanged_recheck_sha256': RECHECK_SHA,
        'function_pins': pins, 'expected_maintain_metadata': retained['metadata'],
        'run': LIVE_RUN, 'owner': OWNER, 'fence': 1,
        'root_source_revision': '536bb850cf5c5653b4865e63db3f20f50a6769a1',
        'predicate_change': {'before': OLD, 'after': NEW, 'occurrences': 1},
        'reversed_candidate_equals_exact_baseline': True,
        'unchanged_verifier_and_auth_pins_rechecked_after_replacement': True,
        'authority': 'Current root instruction: local preparation and disposable-PG qualification only; no production dispatch.',
        'source_receipts': ['review/recovery-v71/live_backfill_maintain_1332.json',
            'review/recovery-v71/live_maintenance_helpers_1335.json',
            'review/recovery-v72/readback_transaction_race_actual_reason_1410.json'],
        'artifacts': {name: {'sha256': digest(source), 'bytes': len(source.encode())} for name, source in outputs.items()},
        'limits': ['Existing READBACK_FAILURE markers remain excluded and unchanged.',
            'Already affected pages require separately authorized exact reconciliation; this forward does not clear failures.',
            'The unchanged verifier remains the independent integrity authority.',
            'Fresh source/metadata/owner/lease reconciliation is required before any root-selected dispatch.'],
        'production_calls': 0,
    }
    (HERE / 'derivation_v72.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'candidate_sha256': digest(candidate), 'forward_sha256': digest(forward),
                      'changed_predicates': 1, 'production_calls': 0}))


if __name__ == '__main__':
    build()
