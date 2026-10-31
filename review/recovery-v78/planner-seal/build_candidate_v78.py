from pathlib import Path
import json,hashlib,re,difflib
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'review/recovery-v78/planner-seal'
ret=json.loads((ROOT/'review/recovery-v78/planner-seal-independent/retained_seal_three_function_definitions_v78.json').read_text())
delta=json.loads((ROOT/'review/recovery-v78/planner-seal-independent/independent_expected_predicate_delta_v78.json').read_text())
old=delta['old_predicate'];new=delta['new_predicate']
rows=ret['functions']
allpins=[]
s=(ROOT/'review/recovery-v76/claim-stall/claim_postinstall_full_source_readback_v76.sql').read_text()+'\n'+(ROOT/'review/recovery-v77/defer-activation/defer_activation_source_effect_readonly_v77.sql').read_text()
for m in re.finditer(r'\{[^{}]*"signature"[^{}]*\}',s):
 try: p=json.loads(m.group())
 except ValueError: continue
 if 'source_sha256' in p: allpins.append(p)
want={r['signature'] for r in rows}|{'astra_ingestion_v1.backfill_plan_next_v2(jsonb)','astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)','astra_ingestion_v1.backfill_maintain_v2(integer)','astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)','astra_ingestion_v1.rpc_dispatch(text,jsonb)','public.astra_ingestion_rpc_v1(text,jsonb)'}
pins=list({p['signature']:p for p in allpins if p['signature'] in want}.values())
assert len(pins)==9,(len(pins),want-{p['signature'] for p in pins})
integrity=json.loads((ROOT/'review/recovery-v78/planner-seal-independent/retained_integrity_helper_definitions_v78.json').read_text())
for row in integrity['functions']:
 assert hashlib.sha256(row['definition'].encode()).hexdigest()==row['source_sha256']
 if row['signature'] not in {p['signature'] for p in pins}:
  pins.append({k:row[k] for k in ('signature','oid','source_sha256','metadata_sha256')})
assert len(pins)==13
changes=[]
for row in rows:
 raw=row['definition'];assert hashlib.sha256(raw.encode()).hexdigest()==row['source_sha256']
 count=2 if '.backfill_plan_snapshot_v2(' in row['signature'] else 1 if '.backfill_seal_plan_v2(' in row['signature'] else 0
 if not count:continue
 assert raw.count(old)==count,(row['signature'],raw.count(old),old)
 revised=raw.replace(old,new);assert revised.replace(new,old)==raw
 changes.append(dict(row,original_definition=raw,candidate_definition=revised,candidate_source_sha256=hashlib.sha256(revised.encode()).hexdigest(),predicate_replacements=count))
expected={'astra_ingestion_v1.backfill_plan_snapshot_v2(text,integer)':'8b8f595bfca0e6ddf74aa12271314620b8364df26079cd86f843a4a81f92b18f','astra_ingestion_v1.backfill_seal_plan_v2(text,bigint,text,jsonb)':'a93e5fbede881afc9e813e8eaaec1c300d636e008fe8c3423d478d55243d2ba1'}
assert all(c['candidate_source_sha256']==expected[c['signature']] for c in changes)
def migration(restore=False):
 before={c['signature']:c['candidate_source_sha256'] if restore else c['source_sha256'] for c in changes}
 after={c['signature']:c['source_sha256'] if restore else c['candidate_source_sha256'] for c in changes}
 selected=[dict(p,source_sha256=before.get(p['signature'],p['source_sha256'])) for p in pins]
 afterpins=[dict(p,source_sha256=after.get(p['signature'],p['source_sha256'])) for p in pins]
 def lit(x):return "'"+json.dumps(x,separators=(',',':')).replace("'","''")+"'::jsonb"
 calls='\n'.join(' EXECUTE $definition'+str(i)+'$'+c['original_definition' if restore else 'candidate_definition']+'$definition'+str(i)+'$;' for i,c in enumerate(changes))
 return f'''-- v78: {'Guarded inverse' if restore else 'Align static-plan pending predicates with the existing snapshot eligibility'}.
-- Exactly two existing helpers and three predicates. No grants, new operation,
-- counter repair, broad plan_static exclusion, retry/deadline or worker change.
BEGIN;
SET LOCAL statement_timeout='8s';SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $v78$
DECLARE r astra_ingestion_v1.backfill_runs_v2%ROWTYPE;a astra_ingestion_v1.backfill_runs_v2%ROWTYPE;
 before_pins jsonb:={lit(selected)};
 after_pins jsonb:={lit(afterpins)};
 ok boolean;
BEGIN
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030' FOR UPDATE;
 IF r.status<>'ACTIVE' OR r.fence<>1 OR r.metadata->>'implementation_owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
  OR NOT COALESCE(isfinite((r.metadata->>'implementation_lease_until')::timestamptz) AND (r.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()+interval '1 minute',false)
  OR r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR r.cohort_manifest_sha256<>'4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  OR r.target_start<>'2025-09-01'::date OR r.target_end<>'2026-07-31'::date
  OR r.metadata#>>'{{implementation_reporting_policy,mode}}' IS DISTINCT FROM 'DOT_CONSOLIDATED_CHECKPOINTS_ONLY'
  OR NOT COALESCE((SELECT count(*)=3000 AND encode(sha256(convert_to(string_agg(member_id,E'\\n' ORDER BY selection_order,member_id),'UTF8')),'hex')='a83310df6a6465ce8d37ffd5352095f6e38d91a3204afd8807fff39092cfd85e' FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id),false)
 THEN RAISE EXCEPTION 'v78 requires the current finite existing controller, fixed cohort and unchanged scope'; END IF;
 {'-- Restore preserves any already committed seal; it never resets a manifest.' if restore else "IF r.metadata->>'planner_phase' IS DISTINCT FROM 'SEAL' OR r.metadata->'planning_complete' IS DISTINCT FROM 'false'::jsonb OR r.metadata->>'planner_next_selection_order' IS DISTINCT FROM '3001' OR r.metadata->>'planner_next_breadth_index' IS DISTINCT FROM '230' THEN RAISE EXCEPTION 'v78 only repairs the reconciled unsealed final planner phase'; END IF;"}
 SELECT count(*)=13 AND bool_and(COALESCE(p.oid::text=e.v->>'oid'
  AND encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex')=e.v->>'source_sha256'
  AND encode(sha256(convert_to((to_jsonb(p)-'prosrc')::text,'UTF8')),'hex')=e.v->>'metadata_sha256',false)) INTO ok
 FROM jsonb_array_elements(before_pins) e(v) LEFT JOIN pg_proc p ON p.oid=to_regprocedure(e.v->>'signature');
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'v78 exact source/OID/full metadata guard failed; reconcile, do not replay'; END IF;
{calls}
 SELECT count(*)=13 AND bool_and(COALESCE(p.oid::text=e.v->>'oid'
  AND encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex')=e.v->>'source_sha256'
  AND encode(sha256(convert_to((to_jsonb(p)-'prosrc')::text,'UTF8')),'hex')=e.v->>'metadata_sha256',false)) INTO ok
 FROM jsonb_array_elements(after_pins) e(v) LEFT JOIN pg_proc p ON p.oid=to_regprocedure(e.v->>'signature');
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'v78 post-replacement source/OID/full metadata differs'; END IF;
 SELECT * INTO STRICT a FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=r.id;
 IF to_jsonb(a) IS DISTINCT FROM to_jsonb(r) THEN RAISE EXCEPTION 'v78 altered run state or accounting'; END IF;
END $v78$;
COMMIT;
'''
outputs={}
for name,restore in [('sql/astra_backfill_seal_dynamic_exclusions_v78.sql',False),('sql/astra_backfill_seal_dynamic_exclusions_restore_v78.sql',True)]:
 p=ROOT/name;p.write_text(migration(restore));outputs[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
archive={'schema':'astra.planner-seal-dynamic-exclusion-candidate/2','prior_nine_pin_candidate':'review/recovery-v78/planner-seal/prior_nine_pin_candidate/candidate_archive_v78.json','integrity_dependency_receipt':'review/recovery-v78/planner-seal/integrity_helper_hash_readback_v78.json','status':'LOCAL_CANDIDATE_NOT_APPLIED','source_binding_receipt':'review/recovery-v78/planner-seal/three_function_hash_readback_v78.json','live_affected_receipt':'review/recovery-v78/planner-seal/affected_row_classification_evidence_v78.json','live_affected_receipt_sha256':'2faae604a9ddb3397a033e6c6ac9d0790867881537dbd927ce316747f2362f83','functions':changes,'protected_function_pins':pins,'old_predicate':old,'new_predicate':new,'files':outputs,'security_diff':{'new_grants':False,'owner_or_acl_changes':False,'new_routes':False,'authentication_changes':False,'source_cost_scope_changes':False,'counter_or_manifest_mutation':False,'broad_plan_static_exclusion':False},'required_gates':['meaningful actual PostgreSQL qualification','independent review','exact source/control readback','publication exact-head CI','root-only guarded installation and source/acquisition readback']}
(OUT/'candidate_archive_v78.json').write_text(json.dumps(archive,indent=2,sort_keys=True)+'\n')
diff=''.join(''.join(difflib.unified_diff(c['original_definition'].splitlines(True),c['candidate_definition'].splitlines(True),fromfile=c['signature']+' original',tofile=c['signature']+' candidate')) for c in changes)
(OUT/'candidate_predicate_diff_v78.patch').write_text(diff)
print(json.dumps({'files':outputs,'archive_sha256':hashlib.sha256((OUT/'candidate_archive_v78.json').read_bytes()).hexdigest(),'candidate_hashes':expected,'predicate_changes':sum(c['predicate_replacements'] for c in changes)}))
