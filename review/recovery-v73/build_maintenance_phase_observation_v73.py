"""Build a reversible, preparation-only diagnostic from the installed v72 body."""
from hashlib import sha256
import difflib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASELINE_PATH = ROOT / 'review/recovery-v72/readback-transaction-race/candidate_maintain_readback_transaction_v72.sql'
BASELINE_PIN = '6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7'
RUN = 'fixed3000-20250901-20260731-v1-20261030'
OWNER = 'root-replacement-20261030T042603Z'
COHORT = '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
DEADLINE = '2026-10-30 15:45:00+00'
PROBE = 'maintenance-global-phase-observation-v73-20261030T1545Z'
ACTION = 'MAINTENANCE_PHASE_OBSERVATION_V73'


def digest(value):
    return sha256(value.encode()).hexdigest()


def block(label, code):
    return ' -- PHASE_OBSERVATION_V73_BEGIN ' + label + '\n' + code + '\n -- PHASE_OBSERVATION_V73_END ' + label + '\n'


baseline = BASELINE_PATH.read_text()
assert digest(baseline) == BASELINE_PIN
candidate = baseline


def insert(before, after):
    global candidate
    assert candidate.count(before) == 1, before
    candidate = candidate.replace(before, after)


phases = [
    ('breadth', 'backfill_breadth_project_pending_v2(2)'),
    ('minute', 'backfill_minute_account_pending_v2(2)'),
    ('identity_discover', 'backfill_identity_discover_pending_v2()'),
    ('identity_refresh', 'backfill_identity_refresh_pending_v2(2)'),
    ('nonminute', 'backfill_nonminute_project_pending_v2(2)'),
    ('s02', 'backfill_s02_maintain_v2()'),
    ('shared', 'backfill_shared_maintain_v2(4)'),
    ('contract', 'backfill_contract_maintain_v2()'),
]
names = [x[0] for x in phases] + ['readback', 'finalize']
variables = (' v_obs_enabled boolean:=false; v_obs_started timestamptz; v_obs_gate timestamptz;\n'
             ' v_obs_admitted timestamptz; v_obs_phases jsonb;\n' +
             '\n'.join(' v_obs_' + name + ' timestamptz;' for name in names))
insert('BEGIN\n -- backfill_bounded_maintenance_wait_v2:',
       block('declarations', variables) + 'BEGIN\n' +
       block('entry', ' v_obs_started:=clock_timestamp();') +
       ' -- backfill_bounded_maintenance_wait_v2:')

scope = """rr.id='__RUN__' AND rr.fence=1
     AND rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL')
     AND rr.cohort_sha256='__COHORT__'
     AND rr.metadata->>'implementation_owner'='__OWNER__'
     AND (rr.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()
     AND clock_timestamp()<'__DEADLINE__'::timestamptz"""
for old, new in [('__RUN__', RUN), ('__COHORT__', COHORT), ('__OWNER__', OWNER), ('__DEADLINE__', DEADLINE)]:
    scope = scope.replace(old, new)
count = """(SELECT count(*) FROM astra_ingestion_v1.backfill_audit_v2 a
      WHERE a.run_id='__RUN__' AND a.action='__ACTION__'
       AND a.source_revision='__PROBE__' AND a.evidence->>'probe_id'='__PROBE__')<4"""
for old, new in [('__RUN__', RUN), ('__ACTION__', ACTION), ('__PROBE__', PROBE)]:
    count = count.replace(old, new)
admission = """ v_obs_gate:=clock_timestamp();
 -- The original VOLATILE function and existing gate serialize RC observations.
 -- Stronger isolation skips only telemetry: no new snapshot or timeout policy.
 IF current_setting('transaction_isolation')='read committed'
  AND v_obs_gate<'__DEADLINE__'::timestamptz THEN
  BEGIN
   SELECT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 rr
    WHERE __SCOPE__) AND __COUNT__ INTO v_obs_enabled;
  EXCEPTION WHEN query_canceled OR assert_failure THEN RAISE;
   WHEN OTHERS THEN v_obs_enabled:=false;
  END;
 END IF;
 IF v_obs_enabled THEN v_obs_admitted:=clock_timestamp(); END IF;"""
admission = admission.replace('__DEADLINE__', DEADLINE).replace('__SCOPE__', scope).replace('__COUNT__', count)
first = ' END;\n PERFORM astra_ingestion_v1.backfill_breadth_project_pending_v2(2);'
insert(first, ' END;\n' + block('admission_after_existing_gate', admission) + first[len(' END;\n'):])
for name, call in phases:
    line = ' PERFORM astra_ingestion_v1.' + call + ';\n'
    insert(line, line + block(name + '_finished',
        ' IF v_obs_enabled THEN v_obs_' + name + ':=clock_timestamp(); END IF;'))
final_loop = " FOR r IN SELECT id FROM astra_ingestion_v1.backfill_runs_v2 WHERE status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') LOOP\n"
insert(final_loop, block('readback_finished', ' IF v_obs_enabled THEN v_obs_readback:=clock_timestamp(); END IF;') + final_loop)

def millis(end, start):
    return 'round(extract(epoch FROM v_obs_' + end + '-v_obs_' + start + ')*1000,3)'

components = ["'gate_admission_ms'," + millis('gate', 'started')]
previous = 'admitted'
for name in names:
    components.append("'" + name + "_ms'," + millis(name, previous))
    previous = name
append = """ IF v_obs_enabled THEN
  v_obs_finalize:=clock_timestamp();
  BEGIN
   v_obs_phases:=jsonb_build_object(__COMPONENTS__);
   -- Wall-clock reversal omits a sample instead of exporting misleading durations.
   IF v_obs_admitted>=v_obs_gate
    AND NOT EXISTS(SELECT 1 FROM jsonb_each_text(v_obs_phases) x WHERE x.value::numeric<0) THEN
    -- These are existing INSERT/row-lock privileges, not new grants. NOWAIT only
    -- avoids relation/row lock waiting; it cannot bound buffer, IO or commit cost.
    LOCK TABLE astra_ingestion_v1.backfill_audit_v2 IN ROW EXCLUSIVE MODE NOWAIT;
    PERFORM rr.id FROM astra_ingestion_v1.backfill_runs_v2 rr
     WHERE __SCOPE__ FOR SHARE NOWAIT;
    IF FOUND AND __COUNT__ THEN
     INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,action,source_revision,evidence)
     SELECT '__RUN__','__ACTION__','__PROBE__',jsonb_build_object(
      'probe_id','__PROBE__','timing_scope','GLOBAL_MAINTENANCE_BEFORE_TELEMETRY',
      'backend_pid',pg_backend_pid(),'total_ms',__TOTAL__,
      'telemetry_admission_ms',__ADMISSION__,'phases_ms',v_obs_phases)
     WHERE clock_timestamp()<'__DEADLINE__'::timestamptz
      AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 rr WHERE __SCOPE__);
     -- If the optional INSERT itself crossed expiry, roll back only its
     -- diagnostic subtransaction. The caller's later COMMIT is unmeasured.
     IF clock_timestamp()>='__DEADLINE__'::timestamptz
      OR NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 rr WHERE __SCOPE__) THEN
      RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PHASE_OBSERVATION_WINDOW_EXPIRED';
     END IF;
    END IF;
   END IF;
  EXCEPTION WHEN query_canceled OR assert_failure THEN RAISE;
   WHEN OTHERS THEN NULL;
  END;
 END IF;"""
for old, new in [('__COMPONENTS__', ',\n    '.join(components)), ('__SCOPE__', scope), ('__COUNT__', count),
                 ('__RUN__', RUN), ('__ACTION__', ACTION), ('__PROBE__', PROBE), ('__DEADLINE__', DEADLINE),
                 ('__TOTAL__', millis('finalize', 'started')), ('__ADMISSION__', millis('admitted', 'gate'))]:
    append = append.replace(old, new)
ret = " RETURN jsonb_build_object('state','OBSERVED','verified_pages',v_readbacks,'readback_errors',v_errors,'runs',v_final);\n"
insert(ret, block('append_optional_observation', append) + ret)
stripped = re.sub(r'^ -- PHASE_OBSERVATION_V73_BEGIN [^\n]+\n.*?^ -- PHASE_OBSERVATION_V73_END [^\n]+\n', '', candidate,
                  flags=re.MULTILINE | re.DOTALL)
assert stripped == baseline
(HERE / 'baseline_maintain_installed_v73.sql').write_text(baseline)
(HERE / 'candidate_maintain_phase_observation_v73.sql').write_text(candidate)
diff = ''.join(difflib.unified_diff(baseline.splitlines(keepends=True), candidate.splitlines(keepends=True),
                                  fromfile='installed/backfill_maintain_v2.sql', tofile='proposal/backfill_maintain_v2.sql'))
(HERE / 'maintenance_phase_observation_v73.diff').write_text(diff)
manifest = {
    'schema': 'astra.maintenance-phase-observation-derivation/1',
    'status': 'PREPARED_NOT_QUALIFIED_NOT_ACTIVATED',
    'base_commit': '1f1f423e4dd1db87eff92e8687b2d9c49ba63c01',
    'base_tree': '45c5b7d6410f4fba1d154d50debdb3b574c9e86d',
    'baseline_sha256': BASELINE_PIN, 'candidate_sha256': digest(candidate), 'diff_sha256': digest(diff),
    'exact_reverse_to_installed_baseline': True, 'run_id': RUN, 'owner': OWNER, 'fence': 1, 'cohort_sha256': COHORT,
    'observation_deadline_utc': DEADLINE, 'probe_id': PROBE, 'action': ACTION, 'max_committed_samples': 4,
    'admitted_isolation': 'read committed', 'helper_and_loop_phases': names,
    'preserved': ['original gate and BUSY return', 'all helper calls and arguments', 'original readback age and error guards',
                  'global finalizer selection', 'original returned JSON', 'SECURITY DEFINER owner and ACL',
                  'VOLATILE classification', 'empty search path', '8s statement / 2s lock configuration'],
    'permission_inventory': 'review/recovery-v73/live_phase_observation_permission_inventory_v73.json',
    'production_calls': 0, 'activation_selected': False,
}
(HERE / 'maintenance_phase_observation_derivation_v73.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'candidate_sha256': digest(candidate), 'bytes': len(candidate.encode()), 'exact_reverse': True}))
