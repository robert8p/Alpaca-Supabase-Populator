-- ASTRA_RELAY_REVIEW_SQL_BEGIN_V2
-- Stateless managed-key adapter authorization in the existing worker RPC.
-- No provider credentials, controller, scheduler, legacy pipeline mutation or service-role client.
-- LOCAL REVIEW CANDIDATE: explicit action-time confirmation is required before applying.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $preflight$
DECLARE approval jsonb; confirmed timestamptz;
 supplied text:=current_query(); reviewed text; remaining text; transport_suffix text;
 start_marker text:='-- ASTRA_RELAY_REVIEW_SQL_'||'BEGIN_V2'||chr(10);
 end_marker text:='-- ASTRA_RELAY_REVIEW_SQL_'||'END_V2'||chr(10);
 transport_prefix text:=E'begin;\n\n-- apply sql from post body\n';
 wrapped boolean; end_at integer; tag_match text[]; tag text; before_account text;
 account_tail text; account_identifier text; expected_suffix text; candidate_sha256 text;
BEGIN
 -- The admitted Supabase transport executes the exact body and stores a
 -- second identical body in a dollar-quoted migration-history insert. Match
 -- that entire transport grammar; never normalize or ignore arbitrary SQL.
 IF left(supplied,length(start_marker))=start_marker THEN
  wrapped:=false;remaining:=supplied;
 ELSIF left(supplied,length(transport_prefix))=transport_prefix THEN
  wrapped:=true;remaining:=substr(supplied,length(transport_prefix)+1);
 ELSE
  RAISE EXCEPTION 'Managed relay transport differs from the reviewed exact SQL or trusted migration wrapper';
 END IF;
 end_at:=strpos(remaining,end_marker);
 IF left(remaining,length(start_marker))<>start_marker OR end_at=0 THEN
  RAISE EXCEPTION 'Managed relay reviewed SQL boundary is missing'; END IF;
 reviewed:=left(remaining,end_at+length(end_marker)-1);
 transport_suffix:=substr(remaining,length(reviewed)+1);
 IF (length(reviewed)-length(replace(reviewed,start_marker,'')))/length(start_marker)<>1
  OR (length(reviewed)-length(replace(reviewed,end_marker,'')))/length(end_marker)<>1 THEN
  RAISE EXCEPTION 'Managed relay executable body has repeated review boundaries'; END IF;
 IF NOT wrapped THEN
  IF transport_suffix<>'' THEN RAISE EXCEPTION 'Managed relay exact submission has unreviewed trailing SQL'; END IF;
 ELSE
  tag_match:=regexp_match(transport_suffix,'\$([A-Za-z]{20})\$');
  tag:='$'||tag_match[1]||'$';
  IF tag IS NULL OR strpos(reviewed,tag)>0 THEN
   RAISE EXCEPTION 'Managed relay migration-history delimiter is invalid'; END IF;
  before_account:=$relay_wrapper_head$;

-- track statements in history table
insert into supabase_migrations.schema_migrations as old
  (version, name, statements, created_by, idempotency_key, rollback)
values (
  to_char(current_timestamp, 'YYYYMMDDHH24MISS'),
  $relay_wrapper_head$||tag||'astra_backfill_massive_relay_v2'||tag||E',\n  array['||tag||reviewed||tag||E'],\n  '||tag;
  IF left(transport_suffix,length(before_account))<>before_account THEN
   RAISE EXCEPTION 'Managed relay history wrapper or duplicated reviewed body differs'; END IF;
  account_tail:=substr(transport_suffix,length(before_account)+1);
  end_at:=strpos(account_tail,tag);
  IF end_at=0 THEN RAISE EXCEPTION 'Managed relay migration-history account boundary is missing'; END IF;
  account_identifier:=left(account_tail,end_at-1);
  IF account_identifier !~ '^[A-Za-z0-9][A-Za-z0-9@._+:/-]{0,253}$' THEN
   RAISE EXCEPTION 'Managed relay migration-history account field differs from the admitted transport'; END IF;
  expected_suffix:=before_account||account_identifier||tag||$relay_wrapper_tail$,
  null,
  null
)
on conflict (idempotency_key) do update set
  version = EXCLUDED.version,
  name = coalesce(EXCLUDED.name, old.name),
  statements = EXCLUDED.statements,
  rollback = EXCLUDED.rollback,
  created_by = EXCLUDED.created_by;

commit;
$relay_wrapper_tail$;
  IF transport_suffix<>expected_suffix THEN
   RAISE EXCEPTION 'Managed relay migration-history suffix has unreviewed SQL'; END IF;
 END IF;
 candidate_sha256:=encode(sha256(convert_to(reviewed,'UTF8')),'hex');
 IF to_regclass('astra_ingestion_v1.backfill_relay_dispatches_v2') IS NOT NULL
  OR to_regprocedure('astra_ingestion_v1.backfill_page_limit_cap_v2(text)') IS NULL THEN
  RAISE EXCEPTION 'Managed relay requires the current bounded replacement runtime and applies once';
 END IF;
 SELECT metadata->'massive_relay_security_confirmation' INTO approval
 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' FOR UPDATE;
 confirmed:=astra_ingestion_v1.backfill_stamp_v2(approval->>'approved_at');
 IF approval->>'state' IS DISTINCT FROM 'APPROVED_AT_ACTION_TIME'
  OR approval->>'review_id' IS DISTINCT FROM 'managed-massive-relay-v2-review-20261030'
  OR approval->>'scope_sha256' IS DISTINCT FROM '7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe'
  OR approval->>'confirmation_source' IS DISTINCT FROM 'EXPLICIT_USER_ACTION_TIME_CONFIRMATION'
  OR length(COALESCE(approval->>'confirmation_ref','')) NOT BETWEEN 1 AND 512
  OR approval->'candidate_applied' IS DISTINCT FROM 'false'::jsonb
  OR approval->>'approved_migration_sha256' IS DISTINCT FROM candidate_sha256
  OR approval->>'approved_rpc_dispatch_sha256' IS DISTINCT FROM '0616b84ec99710083681c2ed7bc2b7dd7acff9ef2f809d84b84c5f724a71fe96'
  OR approval->>'approved_rpc_dispatch_sha256' IS DISTINCT FROM
   encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure),'UTF8')),'hex')
  OR approval->>'approved_edge_index_sha256' IS DISTINCT FROM 'd1cf7bd54392ad834682249cfc33e00cbdcef343fc88053a98c2134330308f97'
  OR approval->>'approved_edge_module_sha256' IS DISTINCT FROM 'bb13314362122485c0f755664ee9e5bd035157df4f03e4984c295ae04b099a83'
  OR approval->>'approved_python_adapter_sha256' IS DISTINCT FROM '76a6eb68f543afdd9637fcafc7d5900cd6e27a802de5ba61b0ea4965cc7b8841'
  OR approval->>'approved_worker_base_sha256' IS DISTINCT FROM '90d048a6c535f7f768050c25e396a923e0e4e211457016757e30af16daface3e'
  OR approval->>'approved_worker_integration_sha256' IS DISTINCT FROM '4427fe549e86922e0a01afde4aad632fd6d2d7c44225dc7ec0ee5dba3eb17a6e'
  OR approval->>'approved_worker_source_sha256' IS DISTINCT FROM 'b682b2425fd226296cdc141ff5936a49a7cac336fe859a02ebbd7faa4adf49c2'
  OR confirmed IS NULL OR confirmed<clock_timestamp()-interval '15 minutes'
  OR confirmed>clock_timestamp()+interval '1 minute' THEN
  RAISE EXCEPTION 'Managed relay is held: exact current action-time security confirmation is required before any DDL or grant';
 END IF;
END $preflight$;

CREATE TABLE astra_ingestion_v1.backfill_relay_dispatches_v2 (
 task_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),
 generation bigint NOT NULL CHECK(generation>0),
 page_no integer NOT NULL CHECK(page_no>=0),
 run_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_runs_v2(id),
 run_fence bigint NOT NULL,
 claim_owner text NOT NULL,
 reserved_at timestamptz NOT NULL,
 dispatch_id uuid NOT NULL UNIQUE,
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 request jsonb NOT NULL CHECK(jsonb_typeof(request)='object'),
 authorized_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 not_after timestamptz NOT NULL,
 PRIMARY KEY(task_id,generation,page_no)
);
CREATE INDEX backfill_relay_run_v2 ON astra_ingestion_v1.backfill_relay_dispatches_v2(run_id,authorized_at);
ALTER TABLE astra_ingestion_v1.backfill_relay_dispatches_v2 ENABLE ROW LEVEL SECURITY;
CREATE TRIGGER backfill_relay_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_relay_dispatches_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_relay_v2(p_operation text,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; r astra_ingestion_v1.backfill_runs_v2;
 expected jsonb; params jsonb; request jsonb; dispatch uuid; path text; symbols text; limit_value integer;
 scope_symbols jsonb; member_count integer; expected_family text;
 start_date date; end_date date; start_stamp timestamptz; end_stamp timestamptz;
 inserted integer; ticket astra_ingestion_v1.backfill_relay_dispatches_v2;
BEGIN
 SELECT * INTO r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030';
 IF NOT FOUND OR r.status<>'ACTIVE'
  OR r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR r.cohort_manifest_sha256<>'4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  OR r.target_start<>'2025-09-01' OR r.target_end<>'2026-07-31' THEN
  RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Managed relay requires the current active fixed replacement run';
 END IF;
 IF r.metadata#>>'{massive_relay_security_confirmation,state}' IS DISTINCT FROM 'APPROVED_AT_ACTION_TIME'
  OR r.metadata#>>'{massive_relay_security_confirmation,review_id}' IS DISTINCT FROM 'managed-massive-relay-v2-review-20261030'
  OR r.metadata#>>'{massive_relay_security_confirmation,scope_sha256}' IS DISTINCT FROM '7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe'
  OR r.metadata#>>'{massive_relay_security_confirmation,confirmation_source}' IS DISTINCT FROM 'EXPLICIT_USER_ACTION_TIME_CONFIRMATION' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Managed relay security confirmation is absent or revoked';
 END IF;
 IF p_operation='backfill_relay_probe' THEN
  IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY[]::text[]) THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Relay probe accepts no parameters'; END IF;
  RETURN jsonb_build_object('state','AUTHORIZED','protocol','astra-massive-relay-v2','run_id',r.id);
 END IF;
 IF p_operation<>'backfill_relay_dispatch' OR octet_length(p_payload::text)>65536
  OR NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['claim','request','dispatch_id'])
  OR NOT astra_ingestion_v1.rpc_keys(p_payload->'claim',ARRAY['id','run_id','owner','generation','run_fence','page_no'])
  OR COALESCE(p_payload->>'dispatch_id','') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid bounded relay dispatch request';
 END IF;
 t:=astra_ingestion_v1.backfill_owned_v2(p_payload->'claim');
 IF t.run_id<>r.id OR t.run_fence<>r.fence OR t.provider<>'Massive'
  OR t.kind NOT IN('massive_reference','massive_news','massive_dividends','massive_splits','massive_short_volume','massive_short_interest')
  OR p_payload#>>'{claim,page_no}' IS DISTINCT FROM t.page_no::text
  OR t.reserved_generation IS DISTINCT FROM t.generation OR t.reserved_page_no IS DISTINCT FROM t.page_no
  OR t.reserved_at IS NULL OR t.requests_reserved<1
  OR LEAST(t.lease_until,t.attempt_deadline)<=clock_timestamp()+interval '1 second' THEN
  RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Relay requires a current counted reservation with sufficient live lease';
 END IF;
 -- A current task is necessary but insufficient: independently enforce the
 -- frozen cohort and mission bounds before allowing use of the managed key.
 scope_symbols:=COALESCE(t.scope->'symbols',jsonb_build_array(t.scope->>'symbol'));
 IF jsonb_typeof(scope_symbols) IS DISTINCT FROM 'array'
  OR jsonb_typeof(t.scope->'member_ids') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Relay requires explicit frozen member and provider anchor arrays'; END IF;
 member_count:=jsonb_array_length(scope_symbols);
 IF member_count NOT BETWEEN 1 AND 100 OR member_count<>jsonb_array_length(t.scope->'member_ids')
  OR (t.kind IN('massive_reference','massive_news') AND member_count<>1)
  OR member_count<>(SELECT count(DISTINCT value) FROM jsonb_array_elements_text(scope_symbols))
  OR member_count<>(SELECT count(DISTINCT value) FROM jsonb_array_elements_text(t.scope->'member_ids'))
  OR EXISTS(
   SELECT 1 FROM jsonb_array_elements_text(scope_symbols) WITH ORDINALITY s(symbol,ord)
   JOIN jsonb_array_elements_text(t.scope->'member_ids') WITH ORDINALITY mi(member_id,ord) USING(ord)
   LEFT JOIN astra_ingestion_v1.backfill_members_v2 m ON m.run_id=r.id AND m.member_id=mi.member_id
   WHERE m.member_id IS NULL OR s.symbol IS DISTINCT FROM m.anchor_ticker
    OR s.symbol !~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$') THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Relay may use only exact frozen member and provider anchor pairs';
 END IF;
 expected_family:=CASE t.kind WHEN 'massive_reference' THEN 'REF01' WHEN 'massive_news' THEN 'N01'
  WHEN 'massive_dividends' THEN 'N02' WHEN 'massive_splits' THEN 'N03'
  WHEN 'massive_short_volume' THEN 'S01' WHEN 'massive_short_interest' THEN 'S02' END;
 IF t.family IS DISTINCT FROM expected_family THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Relay endpoint must match its original mission family'; END IF;
 IF t.kind='massive_reference' THEN
  start_date:=astra_ingestion_v1.backfill_date_v2(t.scope->>'asof');
  IF COALESCE(t.scope->>'asof','') !~ '^\d{4}-\d{2}-\d{2}$'
   OR start_date IS NULL OR start_date<r.target_start OR start_date>r.target_end THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Reference relay as-of date must lie within the fixed target'; END IF;
 ELSIF t.kind='massive_news' THEN
  start_stamp:=astra_ingestion_v1.backfill_stamp_v2(t.scope->>'start');
  end_stamp:=astra_ingestion_v1.backfill_stamp_v2(t.scope->>'end');
  IF start_stamp IS NULL OR end_stamp IS NULL OR start_stamp>end_stamp
   OR start_stamp<'2025-09-01T04:00:00Z'::timestamptz OR end_stamp>='2026-08-01T04:00:00Z'::timestamptz THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='News relay publication window must lie within the fixed New York target'; END IF;
 ELSIF t.kind IN('massive_short_volume','massive_short_interest') THEN
  start_date:=astra_ingestion_v1.backfill_date_v2(t.scope->>'start');
  end_date:=astra_ingestion_v1.backfill_date_v2(t.scope->>'end');
  IF COALESCE(t.scope->>'start','') !~ '^\d{4}-\d{2}-\d{2}$' OR COALESCE(t.scope->>'end','') !~ '^\d{4}-\d{2}-\d{2}$'
   OR start_date IS NULL OR end_date IS NULL OR start_date>end_date OR start_date<r.target_start OR end_date>r.target_end THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Short-data relay reporting or settlement dates must lie within the fixed target'; END IF;
 ELSE
  IF t.scope->>'archive_date_filter' IS DISTINCT FROM 'UNBOUNDED_PROVIDER_EVENT_HISTORY'
   OR t.scope->'retain_boundary_crossing_events' IS DISTINCT FROM 'true'::jsonb
   OR t.scope->>'target_start' IS DISTINCT FROM r.target_start::text
   OR t.scope->>'target_end' IS DISTINCT FROM r.target_end::text THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='All-history action relay needs the explicit boundary-crossing mission policy'; END IF;
 END IF;
 SELECT string_agg(value,',' ORDER BY ord) INTO symbols
  FROM jsonb_array_elements_text(scope_symbols) WITH ORDINALITY s(value,ord);
 IF symbols IS NULL OR length(symbols)>6500 THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Relay scope lacks bounded provider anchors'; END IF;
 limit_value:=COALESCE(t.page_limit,astra_ingestion_v1.backfill_page_limit_cap_v2(t.kind));
 CASE t.kind
 WHEN 'massive_reference' THEN
  path:='/v3/reference/tickers/'||replace(split_part(symbols,',',1),'/','%2F');
  params:=jsonb_build_object('date',t.scope->>'asof');
 WHEN 'massive_news' THEN
  path:='/v2/reference/news';
  params:=jsonb_build_object('ticker',symbols,'published_utc.gte',t.scope->>'start','published_utc.lte',t.scope->>'end',
   'limit',limit_value,'sort','published_utc','order','asc');
 WHEN 'massive_dividends','massive_splits' THEN
  path:='/stocks/v1/'||CASE WHEN t.kind='massive_dividends' THEN 'dividends' ELSE 'splits' END;
  params:=jsonb_build_object('ticker.any_of',symbols,'limit',limit_value,'sort','ticker.asc');
 WHEN 'massive_short_volume' THEN
  path:='/stocks/v1/short-volume';
  params:=jsonb_build_object('ticker.any_of',symbols,'date.gte',t.scope->>'start','date.lte',t.scope->>'end','limit',limit_value,'sort','ticker.asc');
 WHEN 'massive_short_interest' THEN
  path:='/stocks/v1/short-interest';
  params:=jsonb_build_object('ticker.any_of',symbols,'settlement_date.gte',t.scope->>'start','settlement_date.lte',t.scope->>'end','limit',limit_value,'sort','ticker.asc');
 END CASE;
 IF t.cursor IS NOT NULL AND t.cursor<>'null'::jsonb THEN params:=params||jsonb_build_object('cursor',t.cursor#>>'{}'); END IF;
 expected:=jsonb_build_object('provider','Massive','host','api.massive.com','path',path,'method','GET','params',params);
 request:=p_payload->'request';
 IF request IS DISTINCT FROM expected OR NOT astra_ingestion_v1.backfill_request_valid_v2(t,request) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Relay request differs from the current immutable task and execution page limit';
 END IF;
 dispatch:=(p_payload->>'dispatch_id')::uuid;
 INSERT INTO astra_ingestion_v1.backfill_relay_dispatches_v2
  (task_id,generation,page_no,run_id,run_fence,claim_owner,reserved_at,dispatch_id,request_sha256,request,not_after)
 VALUES(t.id,t.generation,t.page_no,t.run_id,t.run_fence,t.owner,t.reserved_at,dispatch,
  encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(request),'UTF8')),'hex'),request,
  LEAST(t.lease_until,t.attempt_deadline,clock_timestamp()+interval '25 seconds'))
 ON CONFLICT(task_id,generation,page_no) DO NOTHING;
 GET DIAGNOSTICS inserted=ROW_COUNT;
 IF inserted=0 THEN RETURN jsonb_build_object('state','ALREADY_DISPATCHED','provider_requested',false); END IF;
 SELECT * INTO STRICT ticket FROM astra_ingestion_v1.backfill_relay_dispatches_v2 WHERE dispatch_id=dispatch;
 RETURN jsonb_build_object('state','DISPATCH_AUTHORIZED','protocol','astra-massive-relay-v2',
  'dispatch_id',ticket.dispatch_id,'task_id',t.id,'run_id',t.run_id,'generation',t.generation,'page_no',t.page_no,
  'request_sha256',ticket.request_sha256,'not_after',ticket.not_after);
END $$;

DO $acl$
DECLARE g record; obj oid;
BEGIN
 REVOKE ALL ON astra_ingestion_v1.backfill_relay_dispatches_v2 FROM PUBLIC;
 FOR g IN SELECT DISTINCT r.rolname FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a
  JOIN pg_roles r ON r.oid=a.grantee WHERE c.oid='astra_ingestion_v1.backfill_relay_dispatches_v2'::regclass AND a.grantee<>c.relowner
 LOOP EXECUTE format('REVOKE ALL ON astra_ingestion_v1.backfill_relay_dispatches_v2 FROM %I',g.rolname); END LOOP;
 REVOKE ALL ON FUNCTION astra_ingestion_v1.backfill_relay_v2(text,jsonb) FROM PUBLIC;
 FOR g IN SELECT DISTINCT r.rolname FROM pg_proc p CROSS JOIN LATERAL aclexplode(p.proacl) a
  JOIN pg_roles r ON r.oid=a.grantee WHERE p.oid='astra_ingestion_v1.backfill_relay_v2(text,jsonb)'::regprocedure AND a.grantee<>p.proowner
 LOOP EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.backfill_relay_v2(text,jsonb) FROM %I',g.rolname); END LOOP;
END $acl$;
GRANT SELECT,INSERT ON astra_ingestion_v1.backfill_relay_dispatches_v2 TO astra_ingestion_rpc_owner_v1;
CREATE POLICY relay_dispatch_read ON astra_ingestion_v1.backfill_relay_dispatches_v2 FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true);
CREATE POLICY relay_dispatch_insert ON astra_ingestion_v1.backfill_relay_dispatches_v2 FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true);
GRANT EXECUTE ON FUNCTION astra_ingestion_v1.backfill_relay_v2(text,jsonb) TO astra_ingestion_rpc_owner_v1;

DO $wire$
DECLARE d text; marker text:='''backfill_work'''; hook text:='    IF p_operation LIKE ''backfill_%'' THEN';
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_managed_relay_hook_v2')>0
  OR (length(d)-length(replace(d,marker,'')))/length(marker)<>1
  OR (length(d)-length(replace(d,hook,'')))/length(hook)<>1
  OR strpos(d,'v_actor=''worker'' AND p_operation IN')=0 THEN
  RAISE EXCEPTION 'Existing authenticated worker capability dispatch differs; reconcile before relay extension';
 END IF;
 d:=replace(d,marker,marker||',''backfill_relay_probe'',''backfill_relay_dispatch''');
 d:=replace(d,hook,$dispatch$
    -- backfill_managed_relay_hook_v2: after worker-only capability checks and existing global lock.
    IF p_operation IN ('backfill_relay_probe','backfill_relay_dispatch') THEN
      RETURN jsonb_build_object('ok',true,'result',astra_ingestion_v1.backfill_relay_v2(p_operation,p_payload));
    END IF;
$dispatch$||hook);
 EXECUTE d;
END $wire$;

-- Consume this exact reviewed migration once, while preserving the hold record's
-- scope/authority/history. The existing audit and run counters stay separate.
INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,action,evidence)
 SELECT id,'MANAGED_MASSIVE_RELAY_REVIEW_APPLIED',metadata->'massive_relay_security_confirmation'||
  jsonb_build_object('applied_migration_sha256',metadata#>>'{massive_relay_security_confirmation,approved_migration_sha256}',
   'applied_at',clock_timestamp(),'new_worker_operations',jsonb_build_array('backfill_relay_probe','backfill_relay_dispatch'))
 FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030';
UPDATE astra_ingestion_v1.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{massive_relay_security_confirmation}',
 metadata->'massive_relay_security_confirmation'||jsonb_build_object('candidate_applied',true,'applied_at',clock_timestamp(),
  'applied_migration_sha256',metadata#>>'{massive_relay_security_confirmation,approved_migration_sha256}'))
 WHERE id='fixed3000-20250901-20260731-v1-20261030';
COMMIT;
-- ASTRA_RELAY_REVIEW_SQL_END_V2
