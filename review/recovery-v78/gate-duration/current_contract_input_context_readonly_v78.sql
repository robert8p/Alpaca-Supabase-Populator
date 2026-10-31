-- Prepared only; no production read budget or activation is granted by this file.
-- Current indexed contract-input context; not historical phase attribution.
-- Root must select one request, recheck this exact file hash, and obtain static review.
-- Expected successful observation transport is a deliberate P0001 exception whose
-- message starts ASTRA_CURRENT_CONTRACT_CONTEXT_V78: and then contains <=32768B JSON.
-- It aborts this read-only transaction; it is not a failed mutation or retry signal.
-- Other SQL errors, missing prefix, invalid JSON or missing evidence fields mean
-- the observation did not complete. Preserve that result; do not retry automatically.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only=on;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $context$
DECLARE
 expected jsonb:='[{"signature":"astra_ingestion_v1.backfill_contract_admit_page_v2(text,integer)","oid":"16061395","source_sha256":"f72da3cb88f30d3ac66e2e20a51bd2dfd55195bc76ae2997decdc6b10020d7c1","metadata_sha256":"93972cb8f42f951d2ddb3cf5007f075ad3be9249c68cd4ce2ccf625765f6253c"},{"signature":"astra_ingestion_v1.backfill_contract_register_child_v2(text)","oid":"16061390","source_sha256":"c5756d3872e552716bffb575025942500946e0e0a8a19c29ef29326b8bc78795","metadata_sha256":"4576bbb21331286f5fa9abfa53636c328ddbeec740c724dd26f428c36306b7bf"},{"signature":"astra_ingestion_v1.backfill_contract_prove_child_v2(text)","oid":"16061389","source_sha256":"bfc62c4adc8272fb6ec2fe2256e96aacfff8ca8ec0daa579db5c48306bc00ff6","metadata_sha256":"62dcf1507147afda188fe6d52d7852189d2a5a3612e1f3db7044101b3f3985be"},{"signature":"astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)","oid":"16050105","source_sha256":"7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4","metadata_sha256":"05efbf80a36ecaf99c1ecf1c3bde8372489963c867bd98708f5fc12223b05f43"},{"signature":"astra_ingestion_v1.rpc_dispatch(text,jsonb)","oid":"15986028","source_sha256":"a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520","metadata_sha256":"1f123366c142c43aadb28a9a4ea3df9e8c376a74a90c69c81b1363c10afeca7e"},{"signature":"astra_ingestion_v1.backfill_contract_maintain_v2()","oid":"16061400","source_sha256":"52007f177dca38faf48fab8773936173519dcbfa54af896b5ef6f902ad64c748","critical_metadata":{"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=20s"],"owner":"16388","security_definer":true}},{"signature":"astra_ingestion_v1.backfill_shared_maintain_v2(integer)","oid":"16050110","source_sha256":"5da488f3e44e2521b64f58230b2bc6db3c34800ae4ac259166f4dc223c8ad2be","critical_metadata":{"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=15s"],"owner":"16388","security_definer":true}},{"signature":"astra_ingestion_v1.monitor_tick_v1()","oid":"15990404","source_sha256":"875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057","metadata_sha256":"ae93dfd4ea8fa09e15bc0f211847e7537da17e2147a7b12dbe5fdd393de54986"},{"signature":"astra_ingestion_v1.backfill_maintain_v2(integer)","oid":"16041463","source_sha256":"6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7","metadata_sha256":"4497ec91787767ee138d167beb19970a5289f9baec3d01c9eeda6962a8d0460d"},{"signature":"astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)","oid":"16040232","source_sha256":"dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf","metadata_sha256":"e7c2c36c0fa1db906255f0194e62ae1d1ebbdf3b11c0fb718723b6ec524a79b6"}]'::jsonb;
 pin jsonb; observed record; r astra_ingestion_v1.backfill_runs_v2%ROWTYPE;
 started_at timestamptz:=clock_timestamp(); result jsonb;
 members integer; active_count integer; index_count integer;
BEGIN
 IF current_setting('transaction_read_only')<>'on' OR current_setting('transaction_isolation')<>'repeatable read'
  OR current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'Context-read transaction bounds unavailable'; END IF;
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030';
 IF r.status IS DISTINCT FROM 'ACTIVE' OR r.fence IS DISTINCT FROM 1 OR r.metadata->>'implementation_owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
  OR r.cohort_sha256 IS DISTINCT FROM '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR r.cohort_manifest_sha256 IS DISTINCT FROM '4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  OR r.metadata#>>'{implementation_reporting_policy,mode}' IS DISTINCT FROM 'DOT_CONSOLIDATED_CHECKPOINTS_ONLY'
  OR NOT COALESCE(isfinite((r.metadata->>'implementation_lease_until')::timestamptz)
   AND (r.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()+interval '10 seconds',false) THEN
  RAISE EXCEPTION 'Context-read existing owner, finite lease or fixed scope changed'; END IF;
 SELECT count(*) INTO members FROM (SELECT 1 FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id LIMIT 3001) m;
 SELECT count(*) INTO active_count FROM (SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE status='ACTIVE' LIMIT 2) a;
 IF members<>3000 OR active_count<>1 THEN RAISE EXCEPTION 'Context-read member or active-run bound changed'; END IF;
 FOR pin IN SELECT value FROM jsonb_array_elements(expected) LOOP
  SELECT p.oid::text oid,encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex') source_sha256,
   encode(sha256(convert_to((to_jsonb(p)-'prosrc')::text,'UTF8')),'hex') metadata_sha256,
   p.proowner::text owner,to_jsonb(p.proacl) acl,to_jsonb(p.proconfig) config,p.prosecdef security_definer
   INTO observed FROM pg_catalog.pg_proc p WHERE p.oid=to_regprocedure(pin->>'signature');
  IF NOT FOUND OR observed.oid IS DISTINCT FROM pin->>'oid' OR observed.source_sha256 IS DISTINCT FROM pin->>'source_sha256' THEN
   RAISE EXCEPTION 'Context-read retained function source or OID changed'; END IF;
  IF pin?'metadata_sha256' THEN
   IF observed.metadata_sha256 IS DISTINCT FROM pin->>'metadata_sha256' THEN RAISE EXCEPTION 'Context-read function metadata changed'; END IF;
  ELSIF jsonb_build_object('owner',observed.owner,'acl',observed.acl,'config',observed.config,'security_definer',observed.security_definer)
   IS DISTINCT FROM pin->'critical_metadata' THEN RAISE EXCEPTION 'Context-read retained critical function metadata changed'; END IF;
 END LOOP;
 SELECT count(*) INTO index_count FROM pg_catalog.pg_index i WHERE i.indexrelid IN (
  to_regclass('astra_ingestion_v1.backfill_readback_projection_order_v2'),
  to_regclass('astra_ingestion_v1.backfill_contract_enumeration_pending_v2'),
  to_regclass('astra_ingestion_v1.backfill_tasks_v2_pkey'),
  to_regclass('astra_ingestion_v1.backfill_pages_v2_pkey'),
  to_regclass('astra_ingestion_v1.backfill_readbacks_v2_pkey'),
  to_regclass('astra_ingestion_v1.backfill_contract_registered_children_v2_pkey'),
  to_regclass('astra_ingestion_v1.backfill_contract_child_proofs_v2_pkey'),
  to_regclass('astra_ingestion_v1.backfill_contract_state_v2_pkey'),
  to_regclass('astra_ingestion_v1.backfill_contract_readback_cursor_v2_pkey'))
  AND i.indisvalid AND i.indisready AND i.indislive;
 IF index_count<>9 THEN RAISE EXCEPTION 'Context-read required index unavailable'; END IF;
 IF pg_get_indexdef(to_regclass('astra_ingestion_v1.backfill_readback_projection_order_v2')) IS DISTINCT FROM
  'CREATE INDEX backfill_readback_projection_order_v2 ON astra_ingestion_v1.backfill_readbacks_v2 USING btree (verified_at, task_id, page_no)'
  OR pg_get_indexdef(to_regclass('astra_ingestion_v1.backfill_contract_enumeration_pending_v2')) IS DISTINCT FROM
  'CREATE INDEX backfill_contract_enumeration_pending_v2 ON astra_ingestion_v1.backfill_contract_enumeration_v2 USING btree (run_id, task_id, page_no) WHERE (processed_at IS NULL)' THEN
  RAISE EXCEPTION 'Context-read cursor/index definition changed'; END IF;
 IF pg_total_relation_size('astra_ingestion_v1.backfill_readbacks_v2')>67108864
  OR pg_total_relation_size('astra_ingestion_v1.backfill_contract_enumeration_v2')>16777216 THEN
  RAISE EXCEPTION 'Context-read relation-size ceiling exceeded'; END IF;
 IF (SELECT count(*) FROM astra_ingestion_v1.backfill_contract_readback_cursor_v2 WHERE singleton)<>1 THEN
  RAISE EXCEPTION 'Context-read singleton cursor missing'; END IF;
 WITH c AS MATERIALIZED (
  SELECT verified_at,task_id,page_no FROM astra_ingestion_v1.backfill_contract_readback_cursor_v2 WHERE singleton
 ), next_pages AS MATERIALIZED (
  SELECT b.verified_at,b.task_id,b.page_no FROM astra_ingestion_v1.backfill_readbacks_v2 b CROSS JOIN c
  WHERE (b.verified_at,b.task_id,b.page_no)>(c.verified_at,c.task_id,c.page_no)
  ORDER BY b.verified_at,b.task_id,b.page_no LIMIT 32
 ), next_context AS MATERIALIZED (
  SELECT n.verified_at,n.task_id,n.page_no,t.run_id,t.kind,t.status,t.generation,t.run_fence,
   t.page_no task_pages,t.cursor IS NULL source_cursor_exhausted,
   p.query_complete stored_proof_complete,p.task_pages stored_proof_task_pages,
   p.verified_pages stored_proof_verified_pages,p.verified_records stored_proof_verified_records,p.checked_at,
   reg.task_id IS NOT NULL currently_registered,reg.registered_at,reg.scope_sha256 registration_scope_sha256
  FROM next_pages n
  CROSS JOIN LATERAL (SELECT run_id,kind,status,generation,run_fence,page_no,cursor FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=n.task_id LIMIT 1) t
  LEFT JOIN LATERAL (SELECT query_complete,task_pages,verified_pages,verified_records,checked_at FROM astra_ingestion_v1.backfill_contract_child_proofs_v2 WHERE task_id=n.task_id LIMIT 1) p ON true
  LEFT JOIN LATERAL (SELECT task_id,registered_at,scope_sha256 FROM astra_ingestion_v1.backfill_contract_registered_children_v2 WHERE task_id=n.task_id LIMIT 1) reg ON true
 ), pending AS MATERIALIZED (
  SELECT e.task_id,e.page_no,b.verified_at,b.readback_sha256,b.actual_records
  FROM astra_ingestion_v1.backfill_contract_enumeration_v2 e
  JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no)
  WHERE e.run_id=r.id AND e.processed_at IS NULL ORDER BY e.task_id,e.page_no LIMIT 2
 ), pending_context AS MATERIALIZED (
  SELECT p.*,t.status,t.run_fence,t.generation,pg.http_status,pg.committed_at,pg.record_count,pg.source_bytes,
   pg.body_sha256,p.readback_sha256=pg.body_sha256 AND p.actual_records=pg.record_count matching_stored_hash_count
  FROM pending p
  CROSS JOIN LATERAL (SELECT status,run_fence,generation FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p.task_id LIMIT 1) t
  CROSS JOIN LATERAL (SELECT http_status,committed_at,record_count,source_bytes,body_sha256 FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=p.task_id AND page_no=p.page_no LIMIT 1) pg
 ) SELECT jsonb_build_object(
  'schema','astra.current-contract-input-context/1','started_at',started_at,'observed_at',clock_timestamp(),
  'fixed_run',r.id,'owner',r.metadata->>'implementation_owner','fence',r.fence,'lease_until',r.metadata->>'implementation_lease_until',
  'source_pin_count',jsonb_array_length(expected),'cursor',(SELECT to_jsonb(c) FROM c),
  'seed_state',(SELECT jsonb_build_object('seed_complete',seed_complete,'child_created_at',child_created_at,'child_id',child_id,
   'registered_windows',registered_windows,'new_children_created',new_children_created,'enumeration_pages_processed',enumeration_pages_processed)
   FROM astra_ingestion_v1.backfill_contract_state_v2 WHERE run_id=r.id),
  'next_readback_rows',(SELECT count(*) FROM next_pages),'next_context_rows',(SELECT count(*) FROM next_context),
  'other_run_rows',(SELECT count(*) FROM next_context WHERE run_id<>r.id),
  'fixed_run_next_readbacks',(SELECT COALESCE(jsonb_agg(to_jsonb(n) ORDER BY verified_at,task_id,page_no),'[]') FROM next_context n WHERE run_id=r.id),
  'pending_enumeration_first_two',(SELECT COALESCE(jsonb_agg(to_jsonb(p) ORDER BY task_id,page_no),'[]') FROM pending_context p),
  'pending_enumeration_count_is_total',false,'next_readbacks_are_exact_frozen_batch',false,
  'query_helpers_invoked',false,'provider_requests',0,'application_claims_or_advisory_locks_acquired',false,'historical_holder_mapping_proven',false,
  'phase_cost_measured',false,'application_request_binding_proven',false,'automatic_successor_read_allowed',false,
  'limitations',jsonb_build_array('This is one current MVCC snapshot; ordinary execution may advance cursors after it.',
   'Stored proof and registration fields are metadata, not a newly executed completeness proof.',
   'Other-run counts preserve the global helper boundary; no other-run payload is returned.',
   'Available valid indexes and size/time ceilings bound admission; no actual query plan or historical phase time is measured.',
   'No phase-cost query, instrumentation, migration, retry expansion or production repair is admitted by this result.')
 ) INTO result;
 IF NOT COALESCE(isfinite((r.metadata->>'implementation_lease_until')::timestamptz)
  AND (r.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp(),false) THEN
  RAISE EXCEPTION 'Context-read finite lease missing or expired'; END IF;
 IF octet_length(result::text)>32768 THEN RAISE EXCEPTION 'Context-read output exceeded32KiB'; END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='ASTRA_CURRENT_CONTRACT_CONTEXT_V78:'||result::text;
END $context$;
COMMIT;
