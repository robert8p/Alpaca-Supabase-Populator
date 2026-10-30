"""Prepare three pure reads from the actual contract admission definition."""
from hashlib import sha256
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
helpers=json.loads((HERE/'live_maintenance_page_seed_helpers_1339.json').read_text())
admit=next(x for x in helpers if x['proname']=='backfill_contract_admit_page_v2')
extra=json.loads((HERE/'live_contract_seed_state_helpers_1344.json').read_text())[0]['evidence']['functions']
extra+=json.loads((HERE/'live_contract_date_stamp_helpers_1346.json').read_text())
defs={x['proname']:x for x in [admit,*extra]}
source=admit['definition']
parse=source[source.index(" SELECT COALESCE(jsonb_agg(jsonb_build_object('ordinal'"):source.index(';\n FOR syms,grp IN')].strip()
parse=parse.replace(' INTO rows','').replace('t.id','$1').replace('p_page','$2').replace('t.scope','$3')
anti=source[source.index(' FOR syms,grp IN\n')+len(' FOR syms,grp IN\n'):source.index('\n LOOP\n  scope:=')].strip()
links=source[source.index(" SELECT t.run_id,t.id,p_page,(x->>'ordinal')"):source.index(' ON CONFLICT DO NOTHING;\n GET DIAGNOSTICS linked')].strip()
def bind(query):
    return query.replace('jsonb_array_elements(rows)','jsonb_array_elements($1)').replace('t.run_id','$2').replace('t.id','$3').replace('p_page','$4').replace(',a,b,',',$5,$6,')
anti,links=bind(anti),bind(links)
metadata=(HERE/'maintenance_candidate_metadata_readonly_v71.sql').read_text()
prefix=metadata[metadata.index('BEGIN ISOLATION LEVEL'):metadata.index('\n WITH\n')]
prefix=prefix.replace('candidate_result jsonb;',"candidate_result jsonb; v_task astra_ingestion_v1.backfill_tasks_v2; v_rows jsonb; v_plan jsonb; v_nodes jsonb; v_phase record; v_pending boolean; v_source_hash text; v_started timestamptz; v_parse_ms numeric;")
signatures={
    'backfill_contract_admit_page_v2':'text,integer','backfill_page_rows_v2':'text,integer',
    'backfill_contract_key_v2':'text,timestamptz,timestamptz,text,text',
    'backfill_contract_register_child_v2':'text','backfill_contract_enqueue_v2':'text,integer',
    'backfill_contract_child_trigger_v2':'',
    'backfill_date_v2':'text','backfill_stamp_v2':'text',
}
pins=[('astra_ingestion_v1.'+name+'('+sig+')',defs[name]['sha256']) for name,sig in signatures.items()]
addition=',\n'+',\n'.join("  ('%s','%s')"%p for p in pins)
prefix=prefix.replace('\n ) s(signature,expected_sha256)',addition+'\n ) s(signature,expected_sha256)')
body="""
 SELECT * INTO STRICT v_task FROM astra_ingestion_v1.backfill_tasks_v2
 WHERE id='backfill-plan-0a93df963fd7ef5a5c67e7534302d55c4fc5db535c9ff5bb8f7238d78af181e8'
  AND run_id='fixed3000-20250901-20260731-v1-20261030' AND run_fence=1
  AND family='CTX02' AND provider='Alpaca' AND kind='alpaca_option_contracts';
 SELECT p.body_sha256 INTO STRICT v_source_hash FROM astra_ingestion_v1.backfill_pages_v2 p
 JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no)
 WHERE p.task_id=v_task.id AND p.page_no=0 AND p.record_count=1000 AND octet_length(p.raw_body)=705542
  AND p.committed_at='2026-10-30T07:14:07.869655+00:00'::timestamptz
  AND b.actual_records=p.record_count AND p.body_sha256=b.body_sha256 AND b.body_sha256=b.readback_sha256;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_contract_state_v2 WHERE run_id=v_task.run_id AND seed_complete) THEN
  RAISE EXCEPTION 'Retained contract seed completion changed; reconcile reached path';
 END IF;
 SELECT processed_at IS NULL INTO STRICT v_pending FROM astra_ingestion_v1.backfill_contract_enumeration_v2
 WHERE task_id=v_task.id AND page_no=0;
 v_started:=clock_timestamp();
 EXECUTE $parse$__PARSE__$parse$ INTO v_rows USING v_task.id,0,v_task.scope;
 v_parse_ms:=extract(epoch FROM clock_timestamp()-v_started)*1000;
 IF jsonb_array_length(v_rows)<>1000 THEN RAISE EXCEPTION 'Retained contract parse count changed';END IF;
 FOR v_phase IN SELECT * FROM (VALUES
  ('UNREGISTERED_SYMBOL_BATCHES',$read$__ANTI__$read$),
  ('EXISTING_PARENT_LINKS',$read$__LINKS__$read$)
 ) phases(component,read_sql) LOOP
  EXECUTE 'EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,SETTINGS FALSE,FORMAT JSON) '||v_phase.read_sql
   INTO v_plan USING v_rows,v_task.run_id,v_task.id,0,'2025-09-01T00:00:00-04:00'::timestamptz,'2026-07-31T23:59:59-04:00'::timestamptz;
  -- Plans are sanitized to counts, node labels and catalog identifiers only.
  -- No expression, function argument, predicate or source value is returned.
  WITH RECURSIVE nodes(path,node) AS(
   SELECT ARRAY[0::bigint],v_plan->0->'Plan'
   UNION ALL SELECT n.path||c.ordinality,c.value FROM nodes n
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(n.node->'Plans','[]')) WITH ORDINALITY c(value,ordinality)
  )
  SELECT jsonb_agg(jsonb_build_object('path',path,'node_type',node->'Node Type',
   'parent_relationship',node->'Parent Relationship','join_type',node->'Join Type',
   'relation',node->'Relation Name','index',node->'Index Name','actual_rows',node->'Actual Rows',
   'actual_loops',node->'Actual Loops','rows_removed_filter',node->'Rows Removed by Filter',
   'rows_removed_join_filter',node->'Rows Removed by Join Filter',
   'shared_hits',node->'Shared Hit Blocks','shared_reads',node->'Shared Read Blocks',
   'temp_reads',node->'Temp Read Blocks','temp_writes',node->'Temp Written Blocks') ORDER BY path) INTO v_nodes FROM nodes;
  results:=results||jsonb_build_array(jsonb_build_object('component',v_phase.component,
   'planning_ms',v_plan->0->'Planning Time','execution_ms',v_plan->0->'Execution Time','nodes',v_nodes));
 END LOOP;
 candidate_result:=jsonb_build_object('schema','astra.contract-admission-pure-reads/1','complete',true,
  'observed_at',clock_timestamp(),'task_id',v_task.id,'page_no',0,'source_sha256',v_source_hash,
  'admission_currently_pending',v_pending,'seed_complete',true,'parsed_records',jsonb_array_length(v_rows),
  'parsed_rows_sha256',encode(sha256(convert_to(v_rows::text,'UTF8')),'hex'),'parse_elapsed_ms',v_parse_ms,
  'eligible_rows',(SELECT count(*) FROM jsonb_array_elements(v_rows) r WHERE r->'eligible'='true'::jsonb),
  'results',results,'transaction_read_only',current_setting('transaction_read_only'),
  'transaction_isolation',current_setting('transaction_isolation'),'raw_source_or_parsed_rows_returned',false,
  'admission_or_registration_invoked',false,'advisory_lock_acquired',false);
 IF octet_length(candidate_result::text)>60000 THEN RAISE EXCEPTION 'Contract read diagnostic exceeds bounded result size';END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='ASTRA_CONTRACT_READS_V71:'||candidate_result::text;
END $profile$;
ROLLBACK;
""".replace('__PARSE__',parse).replace('__ANTI__',anti).replace('__LINKS__',links)
path=HERE/'contract_admission_reads_readonly_v71.sql'
path.write_text('-- Three unchanged pure SELECTs from current contract admission.\n-- The retained immutable page is fixed; current registry state may have advanced.\n-- This measures direct-role reads, excluding inserts/triggers, locks and cron cached plans.\n'+prefix+body)
(HERE/'contract_admission_read_derivation_v71.json').write_text(json.dumps({
    'source_definition_sha256':admit['sha256'],'additional_pins':dict(pins),
    'sql_sha256':sha256(path.read_bytes()).hexdigest(),
    'rewrites':['Remove INTO target for dynamic parameter binding','Replace exact PL/pgSQL variables with six bound parameters',
                'EXPLAIN existing-link INSERT source SELECT only, without its INSERT','Sanitize plan output to fixed metrics and node labels'],
    'production_calls':0},indent=2)+'\n')
print(json.dumps({'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}))
