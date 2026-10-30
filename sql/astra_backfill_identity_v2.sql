-- Progressive dated identity proof in the existing fixed-cohort queue.
-- Original source bytes, frozen membership, task scopes and completed pages stay immutable.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $preflight$ BEGIN
 IF to_regclass('astra_ingestion_v1.backfill_breadth_inputs_v2') IS NULL
 OR to_regclass('market_governance.remediation_source_response_v1') IS NULL
 OR to_regclass('market_governance.remediation_source_batch_v1') IS NULL
 OR to_regclass('reference.massive_security_master_observation_v1') IS NULL
 OR to_regclass('astra_ingestion_v1.backfill_identity_evidence_v2') IS NOT NULL THEN
  RAISE EXCEPTION 'Identity extension requires the current runtime and retained source estate; reconcile before replay'; END IF;
END $preflight$;

CREATE TABLE astra_ingestion_v1.backfill_identity_sources_v2 (
 run_id text NOT NULL,source_ref text NOT NULL,source_kind text NOT NULL CHECK(source_kind IN('RETAINED','CURRENT_PAGE')),
 source_id uuid,task_id text NOT NULL,page_no integer NOT NULL,market_date date NOT NULL,
 source_sha256 text NOT NULL,compressed_sha256 text,native_records integer NOT NULL,
 verified boolean NOT NULL DEFAULT false,invalidated boolean NOT NULL DEFAULT false,
 invalidation_reason text,verified_at timestamptz,PRIMARY KEY(run_id,source_ref),
 FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_pages_v2(task_id,page_no)
);
CREATE TABLE astra_ingestion_v1.backfill_identity_evidence_v2 (
 evidence_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id text NOT NULL,member_id text NOT NULL,market_date date NOT NULL,source_ref text NOT NULL,native_ordinal integer NOT NULL,
 symbol text NOT NULL,historical_symbol text,cik text,composite_figi text,share_class_figi text,security_type text,primary_exchange text,
 identity_anchor text,state text NOT NULL,reason text,eligible boolean,native_row_sha256 text NOT NULL,
 source_sha256 text NOT NULL,recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(run_id,member_id,market_date,source_ref,native_ordinal),
 FOREIGN KEY(run_id,member_id) REFERENCES astra_ingestion_v1.backfill_members_v2(run_id,member_id),
 FOREIGN KEY(run_id,source_ref) REFERENCES astra_ingestion_v1.backfill_identity_sources_v2(run_id,source_ref)
);
CREATE INDEX backfill_identity_evidence_member_day_v2 ON astra_ingestion_v1.backfill_identity_evidence_v2(run_id,member_id,market_date);
CREATE INDEX backfill_identity_evidence_source_v2 ON astra_ingestion_v1.backfill_identity_evidence_v2(run_id,source_ref);
CREATE TRIGGER backfill_identity_evidence_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_identity_evidence_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();

CREATE TABLE astra_ingestion_v1.backfill_identity_discovered_members_v2 (
 run_id text NOT NULL,member_id text NOT NULL,discovered_sources integer NOT NULL,observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 complete boolean NOT NULL DEFAULT false,after_day date NOT NULL DEFAULT '2025-06-04',after_source_id text NOT NULL DEFAULT '',
 PRIMARY KEY(run_id,member_id),FOREIGN KEY(run_id,member_id) REFERENCES astra_ingestion_v1.backfill_members_v2(run_id,member_id)
);
CREATE TABLE astra_ingestion_v1.backfill_identity_discovery_gaps_v2 (
 run_id text NOT NULL,member_id text NOT NULL,market_date date NOT NULL,source_id uuid NOT NULL,reason text NOT NULL,evidence jsonb NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(run_id,member_id,market_date,source_id)
);
CREATE TRIGGER backfill_identity_discovery_gap_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_identity_discovery_gaps_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();
CREATE TABLE astra_ingestion_v1.backfill_identity_source_members_v2 (
 run_id text NOT NULL,member_id text NOT NULL,task_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),
 PRIMARY KEY(run_id,member_id,task_id)
);
CREATE TABLE astra_ingestion_v1.backfill_identity_roots_v2 (
 root_task_id text PRIMARY KEY REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),run_id text NOT NULL,member_id text,
 input_start date NOT NULL,target_end date NOT NULL,identity_material_sha256 text NOT NULL,invalidated boolean NOT NULL DEFAULT false,
 checked_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX backfill_identity_roots_member_v2 ON astra_ingestion_v1.backfill_identity_roots_v2(run_id,member_id,input_start,target_end);
CREATE TABLE astra_ingestion_v1.backfill_identity_calculation_receipts_v2 (
 task_id text PRIMARY KEY REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),root_task_id text NOT NULL,
 identity_material_sha256 text,body_sha256 text NOT NULL,page_no integer NOT NULL,
 FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_pages_v2(task_id,page_no)
);
CREATE TABLE astra_ingestion_v1.backfill_identity_refresh_v2 (
 run_id text NOT NULL,member_id text NOT NULL,earliest_date date NOT NULL,latest_date date NOT NULL,
 after_task_id text NOT NULL DEFAULT '',ready_after timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(run_id,member_id)
);
ALTER TABLE astra_ingestion_v1.backfill_readbacks_v2 ADD COLUMN retained_identity_verification jsonb;
ALTER TABLE astra_ingestion_v1.backfill_breadth_inputs_v2 ADD COLUMN identity_input_attribution jsonb;
CREATE INDEX backfill_identity_derived_member_v2 ON astra_ingestion_v1.backfill_tasks_v2(run_id,(scope#>>'{member_ids,0}'),id)
 WHERE kind IN('derive_daily','derive_intraday') AND NOT(scope ? 'identity_refresh_of');
CREATE INDEX backfill_identity_refresh_tasks_v2 ON astra_ingestion_v1.backfill_tasks_v2(run_id,status)
 WHERE scope ? 'identity_refresh_of';
CREATE INDEX backfill_identity_member_symbol_v2 ON astra_ingestion_v1.backfill_members_v2(run_id,anchor_ticker);
CREATE INDEX backfill_identity_member_composite_v2 ON astra_ingestion_v1.backfill_members_v2(run_id,(anchor->>'anchor_composite_figi'));
CREATE INDEX backfill_identity_member_class_v2 ON astra_ingestion_v1.backfill_members_v2(run_id,(anchor->>'anchor_share_class_figi'));

CREATE FUNCTION astra_ingestion_v1.backfill_identity_mark_changed_v2(p_run text,p_member text,p_day date) RETURNS void
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$ BEGIN
 UPDATE astra_ingestion_v1.backfill_identity_roots_v2 SET invalidated=true
  WHERE run_id=p_run AND (member_id=p_member OR member_id IS NULL) AND p_day BETWEEN input_start AND target_end;
 INSERT INTO astra_ingestion_v1.backfill_identity_refresh_v2(run_id,member_id,earliest_date,latest_date,ready_after)
 VALUES(p_run,p_member,p_day,p_day,clock_timestamp()+interval '30 seconds')
 ON CONFLICT(run_id,member_id) DO UPDATE SET earliest_date=LEAST(astra_ingestion_v1.backfill_identity_refresh_v2.earliest_date,EXCLUDED.earliest_date),
  latest_date=GREATEST(astra_ingestion_v1.backfill_identity_refresh_v2.latest_date,EXCLUDED.latest_date),after_task_id='',ready_after=EXCLUDED.ready_after;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_source_meta_v2(p_source uuid,p_day date,p_body boolean DEFAULT false) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE s market_governance.remediation_source_response_v1;b market_governance.remediation_source_batch_v1;
BEGIN
 IF p_day NOT BETWEEN '2025-06-05'::date AND '2026-07-31'::date THEN RETURN jsonb_build_object('state','SOURCE_UNAVAILABLE','reason','REFERENCE_DATE_OUTSIDE_TARGET_AND_SUPPORT'); END IF;
 SELECT * INTO s FROM market_governance.remediation_source_response_v1 WHERE source_id=p_source;
 IF NOT FOUND THEN RETURN jsonb_build_object('state','SOURCE_UNAVAILABLE','reason','ORIGINAL_SOURCE_RECEIPT_NOT_FOUND'); END IF;
 SELECT * INTO b FROM market_governance.remediation_source_batch_v1 WHERE batch_id=s.batch_id;
 IF NOT FOUND OR b.provider<>'massive' OR b.source_type<>'massive_reference_tickers' OR b.status<>'COMPLETE'
 OR b.request_json->>'reference_date' IS DISTINCT FROM p_day::text
 OR (b.start_ts AT TIME ZONE 'UTC')::date IS DISTINCT FROM p_day
 OR s.http_status<>200 OR s.storage_encoding<>'gzip' OR s.credential_redactions<>0
 OR s.original_bytes NOT BETWEEN 1 AND 4194304 OR octet_length(s.compressed_body)>2097152
 OR s.source_sha256 IS DISTINCT FROM s.stored_body_sha256
 OR sha256(s.compressed_body) IS DISTINCT FROM s.compressed_sha256
 OR (s.source_url NOT LIKE 'https://api.massive.com/v3/reference/tickers?%' AND s.source_url NOT LIKE 'https://api.polygon.io/v3/reference/tickers?%')
 THEN RETURN jsonb_build_object('state','SOURCE_UNAVAILABLE','reason','ORIGINAL_SOURCE_PROFILE_OR_COMPRESSED_HASH_DIFFERS'); END IF;
 RETURN jsonb_build_object('state','RETAINED_SOURCE_READY','source_id',s.source_id,'batch_id',s.batch_id,'market_date',p_day,
  'source_sha256',encode(s.source_sha256,'hex'),'compressed_sha256',encode(s.compressed_sha256,'hex'),
  'original_bytes',s.original_bytes,'storage_encoding',s.storage_encoding,'received_at',s.received_at,
  'source_endpoint','/v3/reference/tickers','retrospective_only',true,
  'compressed_body_base64',CASE WHEN p_body THEN replace(encode(s.compressed_body,'base64'),E'\n','') END);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_discover_member_v2(p_run text,p_member text) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE m astra_ingestion_v1.backfill_members_v2;r astra_ingestion_v1.backfill_runs_v2;x record;meta jsonb;v_id text;n integer:=0;
 state astra_ingestion_v1.backfill_identity_discovered_members_v2;seen integer:=0;last_day date;last_source text;more boolean;
BEGIN
 SELECT * INTO STRICT m FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=p_run AND member_id=p_member;
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=p_run FOR UPDATE;
 IF r.status<>'ACTIVE' THEN RETURN 0; END IF;
 INSERT INTO astra_ingestion_v1.backfill_identity_discovered_members_v2(run_id,member_id,discovered_sources) VALUES(p_run,p_member,0) ON CONFLICT DO NOTHING;
 SELECT * INTO STRICT state FROM astra_ingestion_v1.backfill_identity_discovered_members_v2 WHERE run_id=p_run AND member_id=p_member FOR UPDATE;
 IF state.complete THEN RETURN 0; END IF;
 last_day:=state.after_day;last_source:=state.after_source_id;
 FOR x IN SELECT DISTINCT o.requested_as_of,lower(o.raw_payload#>>'{_remediation_acquisition,source_id}') source_id
  FROM reference.massive_security_master_observation_v1 o
  WHERE o.requested_as_of BETWEEN '2025-06-05'::date AND '2026-07-31'::date
   AND o.source_route='market_data_remediation_20261008_v1.massive_native_listing_pages_v1'
   AND (o.ticker=m.anchor_ticker OR (o.composite_figi=m.anchor->>'anchor_composite_figi' AND o.share_class_figi=m.anchor->>'anchor_share_class_figi'))
   AND o.raw_payload#>>'{_remediation_acquisition,source_id}' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
   AND (o.requested_as_of,lower(o.raw_payload#>>'{_remediation_acquisition,source_id}'))>(state.after_day,state.after_source_id)
  ORDER BY o.requested_as_of,source_id LIMIT 128
 LOOP
  seen:=seen+1;last_day:=x.requested_as_of;last_source:=x.source_id;
  meta:=astra_ingestion_v1.backfill_identity_source_meta_v2(x.source_id::uuid,x.requested_as_of,false);
  IF meta->>'state'<>'RETAINED_SOURCE_READY' THEN
   INSERT INTO astra_ingestion_v1.backfill_identity_discovery_gaps_v2(run_id,member_id,market_date,source_id,reason,evidence)
   VALUES(p_run,p_member,x.requested_as_of,x.source_id::uuid,COALESCE(meta->>'reason','RETAINED_SOURCE_UNVERIFIABLE'),meta) ON CONFLICT DO NOTHING;
   CONTINUE; END IF;
  v_id:='backfill-identity-source-'||encode(sha256(convert_to(p_run||':'||x.source_id,'UTF8')),'hex');
  INSERT INTO astra_ingestion_v1.backfill_tasks_v2(id,run_id,family,provider,kind,scope,priority,run_fence)
  VALUES(v_id,p_run,'REF01','REUSE','retained_identity',jsonb_build_object('identity_source_id',x.source_id,
   'expected_source_sha256',meta->>'source_sha256','reference_date',x.requested_as_of,'cohort_sha256',r.cohort_sha256,
   'shared_cohort_reference',true,'member_ids','[]'::jsonb,'plan_static',false,'governing_date','REFERENCE_AS_OF'),15,r.fence)
  ON CONFLICT(id) DO NOTHING;
  INSERT INTO astra_ingestion_v1.backfill_identity_source_members_v2 VALUES(p_run,p_member,v_id) ON CONFLICT DO NOTHING;
  n:=n+1;
 END LOOP;
 SELECT EXISTS(SELECT 1 FROM reference.massive_security_master_observation_v1 o
  WHERE o.requested_as_of BETWEEN '2025-06-05'::date AND '2026-07-31'::date
   AND o.source_route='market_data_remediation_20261008_v1.massive_native_listing_pages_v1'
   AND (o.ticker=m.anchor_ticker OR (o.composite_figi=m.anchor->>'anchor_composite_figi' AND o.share_class_figi=m.anchor->>'anchor_share_class_figi'))
   AND o.raw_payload#>>'{_remediation_acquisition,source_id}' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
   AND (o.requested_as_of,lower(o.raw_payload#>>'{_remediation_acquisition,source_id}'))>(last_day,last_source)) INTO more;
 UPDATE astra_ingestion_v1.backfill_identity_discovered_members_v2 SET discovered_sources=discovered_sources+n,observed_at=clock_timestamp(),
  complete=NOT more,after_day=last_day,after_source_id=last_source WHERE run_id=p_run AND member_id=p_member;
 RETURN n;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_discover_pending_v2() RETURNS integer
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE x record;
BEGIN
 SELECT d.run_id,d.member_id INTO x FROM astra_ingestion_v1.backfill_identity_discovered_members_v2 d
 JOIN astra_ingestion_v1.backfill_runs_v2 r ON r.id=d.run_id WHERE NOT d.complete AND r.status='ACTIVE'
 ORDER BY d.observed_at,d.run_id,d.member_id LIMIT 1;
 IF NOT FOUND THEN RETURN 0; END IF;
 RETURN astra_ingestion_v1.backfill_identity_discover_member_v2(x.run_id,x.member_id);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_project_v2(p_run text,p_day date,p_ref text,p_sha text,p_rows jsonb) RETURNS integer
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE x record;v_cik text;v_state text;v_reason text;v_anchor text;n integer:=0;added integer;
BEGIN
 IF jsonb_typeof(p_rows)<>'array' OR jsonb_array_length(p_rows)>1000 THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Bounded native reference rows required'; END IF;
 FOR x IN SELECT m.member_id,m.anchor_ticker,m.anchor,n.row,n.ordinality::integer ord
  FROM jsonb_array_elements(p_rows) WITH ORDINALITY n(row,ordinality)
  JOIN astra_ingestion_v1.backfill_members_v2 m ON m.run_id=p_run AND
   (n.row->>'ticker'=m.anchor_ticker OR n.row->>'composite_figi'=m.anchor->>'anchor_composite_figi'
     OR n.row->>'share_class_figi'=m.anchor->>'anchor_share_class_figi')
 LOOP
  v_cik:=CASE WHEN x.row->>'cik' ~ '^\d{1,10}$' THEN lpad(x.row->>'cik',10,'0') END;
  v_state:='IDENTITY_OR_QUALITY_UNRESOLVED';v_reason:='STABLE_COHORT_IDENTIFIERS_DIFFER';v_anchor:=NULL;
  IF v_cik IS NOT NULL AND x.member_id='CIK:'||v_cik
   AND x.row->>'composite_figi' ~ '^[A-Z0-9]{12}$' AND x.row->>'share_class_figi' ~ '^[A-Z0-9]{12}$'
   AND x.row->>'composite_figi'=x.anchor->>'anchor_composite_figi'
   AND x.row->>'share_class_figi'=x.anchor->>'anchor_share_class_figi'
   AND x.row->>'type'=x.anchor->>'anchor_security_type'
   AND length(COALESCE(x.row->>'primary_exchange',''))>0
   AND x.row->>'market'='stocks' AND x.row->>'locale'='us'
  THEN v_state:='RETROSPECTIVE_DATED_IDENTIFIERS_MATCHED';v_reason:=NULL;
   v_anchor:='CIK:'||v_cik||'|FIGI:'||(x.row->>'composite_figi')||'|CLASS:'||(x.row->>'share_class_figi');
  ELSIF v_cik IS NULL OR x.row->>'composite_figi' IS NULL OR x.row->>'share_class_figi' IS NULL THEN v_reason:='STABLE_PROVIDER_IDENTIFIERS_MISSING'; END IF;
  INSERT INTO astra_ingestion_v1.backfill_identity_evidence_v2(run_id,member_id,market_date,source_ref,native_ordinal,symbol,historical_symbol,
   cik,composite_figi,share_class_figi,security_type,primary_exchange,identity_anchor,state,reason,eligible,native_row_sha256,source_sha256)
  VALUES(p_run,x.member_id,p_day,p_ref,x.ord,x.anchor_ticker,x.row->>'ticker',v_cik,x.row->>'composite_figi',x.row->>'share_class_figi',
   x.row->>'type',x.row->>'primary_exchange',v_anchor,v_state,v_reason,
   CASE WHEN v_state='RETROSPECTIVE_DATED_IDENTIFIERS_MATCHED' AND x.row->'active'='true'::jsonb THEN true END,
   encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(x.row),'UTF8')),'hex'),p_sha) ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS added=ROW_COUNT;n:=n+added;
  IF added>0 THEN PERFORM astra_ingestion_v1.backfill_identity_mark_changed_v2(p_run,x.member_id,p_day); END IF;
 END LOOP;
 RETURN n;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_source_read_v2(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;v jsonb;
BEGIN
 t:=astra_ingestion_v1.backfill_owned_v2(p_payload->'claim');
 IF t.kind<>'retained_identity' OR t.family<>'REF01' OR lower(t.provider)<>'reuse' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained identity source claim required'; END IF;
 v:=astra_ingestion_v1.backfill_identity_source_meta_v2((t.scope->>'identity_source_id')::uuid,(t.scope->>'reference_date')::date,true);
 IF v->>'source_sha256' IS DISTINCT FROM t.scope->>'expected_source_sha256' THEN
  RETURN jsonb_build_object('state','SOURCE_UNAVAILABLE','reason','PINNED_ORIGINAL_REFERENCE_SOURCE_CHANGED','run_id',t.run_id,'task_id',t.id); END IF;
 RETURN v||jsonb_build_object('run_id',t.run_id,'task_id',t.id);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_source_commit_v2(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;p astra_ingestion_v1.backfill_pages_v2;v jsonb;b jsonb;pointer jsonb;raw text;result jsonb;
 ref text;n integer;v_day date;v_source uuid;v_sha text;
BEGIN
 SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=p_payload#>>'{claim,id}' AND page_no=(p_payload#>>'{claim,page_no}')::int;
 IF FOUND THEN
  IF p.run_id IS DISTINCT FROM p_payload#>>'{claim,run_id}' OR p.generation::text IS DISTINCT FROM p_payload#>>'{claim,generation}'
   OR p.run_fence::text IS DISTINCT FROM p_payload#>>'{claim,run_fence}'
   OR p.raw_body::jsonb#>>'{rows,0,source_sha256}' IS DISTINCT FROM p_payload->>'source_sha256' THEN
   RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Existing retained identity commit differs'; END IF;
  RETURN jsonb_build_object('state','already_committed','task_id',p.task_id,'body_sha256',p.body_sha256,'record_count',p.record_count); END IF;
 t:=astra_ingestion_v1.backfill_owned_v2(p_payload->'claim');
 IF t.kind<>'retained_identity' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained identity claim required'; END IF;
 v_source:=(t.scope->>'identity_source_id')::uuid;v_day:=(t.scope->>'reference_date')::date;ref:='retained:'||v_source;
 v:=astra_ingestion_v1.backfill_identity_source_meta_v2(v_source,v_day,false);v_sha:=v->>'source_sha256';
 IF v->>'state'<>'RETAINED_SOURCE_READY' OR v_sha IS DISTINCT FROM t.scope->>'expected_source_sha256'
 OR v_sha IS DISTINCT FROM p_payload->>'source_sha256' OR v->>'compressed_sha256' IS DISTINCT FROM p_payload->>'compressed_sha256'
 OR octet_length(p_payload->>'raw_body') IS DISTINCT FROM (v->>'original_bytes')::integer
 OR encode(sha256(convert_to(p_payload->>'raw_body','UTF8')),'hex') IS DISTINCT FROM v_sha THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Original identity source bytes or retained receipt differs'; END IF;
 PERFORM astra_ingestion_v1.rpc_json_unique((p_payload->>'raw_body')::json);b:=(p_payload->>'raw_body')::jsonb;
 IF jsonb_typeof(b->'results') IS DISTINCT FROM 'array' OR jsonb_array_length(b->'results')>1000 OR b->>'status' NOT IN('OK','DELAYED') THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Native retained listing envelope differs'; END IF;
 n:=jsonb_array_length(b->'results');
 pointer:=jsonb_build_object('record_type','RETAINED_REFERENCE_SOURCE_POINTER','source_id',v_source,'source_sha256',v_sha,
  'compressed_sha256',v->>'compressed_sha256','reference_date',v_day,'referenced_reference_records',n,
  'source_relation','market_governance.remediation_source_response_v1','original_received_at',v->'received_at',
  'original_page_readback','ORIGINAL_BYTES_HASH_VERIFIED','retrospective_only',true,'strict_historical_availability_certified',false);
 raw:=astra_ingestion_v1.rpc_canonical(jsonb_build_object('rows',jsonb_build_array(pointer)));
 result:=astra_ingestion_v1.backfill_dispatch_v2('backfill_commit',jsonb_build_object('claim',p_payload->'claim','raw_body',raw,
  'body_sha256',encode(sha256(convert_to(raw,'UTF8')),'hex'),'http_status',200,'fetched_at',clock_timestamp(),
  'request',jsonb_build_object('provider','REUSE','operation','HASH_VERIFY_RETAINED_NATIVE_REFERENCE','source_id',v_source),
  'records',jsonb_build_array(pointer),'next_cursor',NULL,'terminal_state','INGESTED','quality','[]'::jsonb,'headers','{}'::jsonb,
  'adapter_version','fixed3000-retrospective-identity-v2.1'));
 INSERT INTO astra_ingestion_v1.backfill_identity_sources_v2(run_id,source_ref,source_kind,source_id,task_id,page_no,market_date,source_sha256,compressed_sha256,native_records)
 VALUES(t.run_id,ref,'RETAINED',v_source,t.id,t.page_no,v_day,v_sha,v->>'compressed_sha256',n);
 n:=astra_ingestion_v1.backfill_identity_project_v2(t.run_id,v_day,ref,v_sha,b->'results');
 RETURN result||jsonb_build_object('matched_or_held_member_observations',n,'original_source_sha256',v_sha);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_source_verify_v2(p_task text,p_page integer) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE s astra_ingestion_v1.backfill_identity_sources_v2;v jsonb;ok boolean;x record;
BEGIN
 SELECT * INTO s FROM astra_ingestion_v1.backfill_identity_sources_v2 WHERE task_id=p_task AND page_no=p_page AND source_kind='RETAINED';
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='AI004',MESSAGE='Retained identity proof does not exist'; END IF;
 v:=astra_ingestion_v1.backfill_identity_source_meta_v2(s.source_id,s.market_date,false);
 ok:=v->>'state'='RETAINED_SOURCE_READY' AND v->>'source_sha256'=s.source_sha256 AND v->>'compressed_sha256'=s.compressed_sha256;
 UPDATE astra_ingestion_v1.backfill_identity_sources_v2 SET verified=COALESCE(ok,false),invalidated=NOT COALESCE(ok,false),
  invalidation_reason=CASE WHEN NOT COALESCE(ok,false) THEN 'ORIGINAL_REFERENCE_SOURCE_CHANGED' END,verified_at=clock_timestamp()
  WHERE run_id=s.run_id AND source_ref=s.source_ref;
 RETURN jsonb_build_object('passed',COALESCE(ok,false),'state',CASE WHEN ok THEN 'RETAINED_IDENTITY_SOURCE_VERIFIED' ELSE 'RETAINED_IDENTITY_SOURCE_CHANGED' END,
  'source_id',s.source_id,'source_sha256',s.source_sha256,'native_records',s.native_records,'market_date',s.market_date);
END $$;

CREATE VIEW astra_ingestion_v1.backfill_identity_current_v2 WITH(security_invoker=true) AS
 WITH grouped AS (
  SELECT e.run_id,e.member_id,e.market_date,min(e.evidence_id) FILTER(WHERE e.state='RETROSPECTIVE_DATED_IDENTIFIERS_MATCHED') first_evidence,
   count(DISTINCT e.identity_anchor) FILTER(WHERE s.verified AND NOT s.invalidated) identities,
   (bool_or(e.state<>'RETROSPECTIVE_DATED_IDENTIFIERS_MATCHED' OR NOT s.verified OR s.invalidated)
    OR count(DISTINCT jsonb_build_array(e.historical_symbol,e.primary_exchange,e.security_type))>1) held,
   CASE WHEN bool_and(e.eligible IS TRUE) THEN true END eligible,
   count(*) evidence_records
  FROM astra_ingestion_v1.backfill_identity_evidence_v2 e JOIN astra_ingestion_v1.backfill_identity_sources_v2 s USING(run_id,source_ref)
  GROUP BY e.run_id,e.member_id,e.market_date
 )
 SELECT g.run_id,g.member_id,g.market_date,e.symbol,e.historical_symbol,e.cik,e.composite_figi,e.share_class_figi,e.security_type,e.primary_exchange,
  CASE WHEN NOT g.held AND g.identities=1 THEN e.identity_anchor END identity_anchor,
  CASE WHEN NOT g.held AND g.identities=1 THEN 'RETROSPECTIVE_DATED_IDENTIFIERS_MATCHED' ELSE 'IDENTITY_OR_QUALITY_UNRESOLVED' END state,
  CASE WHEN g.held OR g.identities<>1 THEN 'CONFLICTING_OR_UNVERIFIED_DATED_IDENTITY_EVIDENCE' END reason,
  CASE WHEN NOT g.held AND g.identities=1 THEN g.eligible END eligible,
  encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(jsonb_build_object('source_ref',e.source_ref,'source_sha256',e.source_sha256,
   'native_row_sha256',e.native_row_sha256,'member_id',g.member_id,'market_date',g.market_date,'held',g.held,'identities',g.identities,'eligible',g.eligible)),'UTF8')),'hex') evidence_sha256,
  e.source_ref,g.evidence_records,true retrospective_only,false strict_historical_availability_certified
 FROM grouped g LEFT JOIN astra_ingestion_v1.backfill_identity_evidence_v2 e ON e.evidence_id=g.first_evidence;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_price_attribution_v2(p_row jsonb,p_current jsonb,p_anchor jsonb,p_symbol text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
DECLARE proof jsonb:=p_row->'identity_input_attribution';mapping jsonb:=proof->'provider_symbol_mapping';
BEGIN
 IF p_current->>'state' IS DISTINCT FROM 'RETROSPECTIVE_DATED_IDENTIFIERS_MATCHED' THEN RETURN false;END IF;
 IF jsonb_typeof(mapping) IS DISTINCT FROM 'object' THEN RETURN p_symbol=p_current->>'historical_symbol';END IF;
 IF proof->'all_input_provider_symbol_mappings_consistent' IS DISTINCT FROM 'true'::jsonb
 OR proof->>'member_id' IS DISTINCT FROM p_current->>'member_id' OR proof->>'market_date' IS DISTINCT FROM p_current->>'market_date'
 OR proof->>'symbol' IS DISTINCT FROM p_symbol OR mapping->>'requested_symbol' IS DISTINCT FROM p_symbol
 OR mapping->>'provider' IS DISTINCT FROM 'Alpaca' OR mapping->>'host' IS DISTINCT FROM 'data.alpaca.markets'
 OR mapping->>'path' IS DISTINCT FROM '/v2/stocks/bars' OR mapping->>'method' IS DISTINCT FROM 'GET'
 OR COALESCE(mapping->>'source_body_sha256','') !~ '^[0-9a-f]{64}$' OR COALESCE(mapping->>'request_sha256','') !~ '^[0-9a-f]{64}$'
 THEN RETURN false;END IF;
 IF mapping->>'asof'='-' THEN RETURN p_symbol=p_current->>'historical_symbol';END IF;
 RETURN COALESCE(p_symbol=p_current->>'symbol' AND mapping->>'asof'=p_anchor->>'anchor_observation_date'
  AND mapping->>'asof' ~ '^\d{4}-\d{2}-\d{2}$'
  AND p_anchor->'membership_accepted'='true'::jsonb
  AND p_anchor->>'cohort_sha256'='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  AND p_current->>'member_id'='CIK:'||(p_current->>'cik')
  AND p_current->>'composite_figi'=p_anchor->>'anchor_composite_figi'
  AND p_current->>'share_class_figi'=p_anchor->>'anchor_share_class_figi'
  AND p_current->>'security_type'=p_anchor->>'anchor_security_type',false);
END $$;

-- Intraday raw calculations remain numerically reusable when only attribution
-- improves. Overlay current dated identity instead of copying their minute grid.
ALTER VIEW astra_ingestion_v1.backfill_family_d01_v2 RENAME TO backfill_family_d01_receipt_v2;
DO $intraday_overlay$
DECLARE columns text;
BEGIN
 SELECT string_agg(CASE
  WHEN a.attname='identity_status' THEN 'CASE WHEN iq.qualified THEN ic.state ELSE ''IDENTITY_OR_QUALITY_UNRESOLVED'' END AS identity_status'
  WHEN a.attname='source_row' THEN 'b.source_row||jsonb_build_object(''current_identity_resolution'',jsonb_build_object(''state'',CASE WHEN iq.qualified THEN ic.state ELSE ''IDENTITY_OR_QUALITY_UNRESOLVED'' END,''reference_state'',ic.state,''identity_anchor'',CASE WHEN iq.qualified THEN ic.identity_anchor END,''historical_symbol'',ic.historical_symbol,''evidence_sha256'',ic.evidence_sha256,''reason'',CASE WHEN ic.state=''RETROSPECTIVE_DATED_IDENTIFIERS_MATCHED'' AND NOT iq.qualified THEN CASE WHEN jsonb_typeof(b.source_row#>''{identity_input_attribution,provider_symbol_mapping}'')=''object'' THEN ''PROVIDER_ASOF_ANCHOR_UNVERIFIED'' ELSE ''HISTORICAL_SYMBOL_REQUIRES_ALIAS_ACQUISITION'' END ELSE COALESCE(ic.reason,CASE WHEN ic.state IS NULL THEN ''DATED_IDENTITY_EVIDENCE_UNAVAILABLE'' END) END,''retrospective_only'',true,''strict_historical_availability_certified'',false)) AS source_row'
  ELSE format('b.%I',a.attname) END,',' ORDER BY a.attnum) INTO columns
 FROM pg_attribute a WHERE a.attrelid='astra_ingestion_v1.backfill_family_d01_receipt_v2'::regclass AND a.attnum>0 AND NOT a.attisdropped;
 EXECUTE 'CREATE VIEW astra_ingestion_v1.backfill_family_d01_v2 WITH(security_invoker=true) AS SELECT '||columns||
  ' FROM astra_ingestion_v1.backfill_family_d01_receipt_v2 b LEFT JOIN LATERAL(SELECT i.* FROM astra_ingestion_v1.backfill_identity_current_v2 i WHERE i.run_id=b.run_id AND i.member_id=b.member_ids->>0 AND i.market_date=b.market_date OFFSET 0) ic ON true'||
  ' LEFT JOIN astra_ingestion_v1.backfill_members_v2 m ON m.run_id=b.run_id AND m.member_id=b.member_ids->>0'||
  ' CROSS JOIN LATERAL(SELECT astra_ingestion_v1.backfill_identity_price_attribution_v2(b.source_row,to_jsonb(ic),m.anchor,b.symbol) qualified OFFSET 0) iq';
END $intraday_overlay$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_validate_sources_v2(p_run text,p_member text,p_start date,p_end date) RETURNS integer
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE s astra_ingestion_v1.backfill_identity_sources_v2;v jsonb;ok boolean;x record;n integer:=0;
BEGIN
 FOR s IN SELECT DISTINCT sr.* FROM astra_ingestion_v1.backfill_identity_sources_v2 sr
  JOIN astra_ingestion_v1.backfill_identity_evidence_v2 e USING(run_id,source_ref)
  WHERE sr.run_id=p_run AND (p_member IS NULL OR e.member_id=p_member) AND e.market_date BETWEEN p_start AND p_end
   AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 rb WHERE rb.task_id=sr.task_id AND rb.page_no=sr.page_no)
 LOOP
  IF s.source_kind='RETAINED' THEN
   v:=astra_ingestion_v1.backfill_identity_source_meta_v2(s.source_id,s.market_date,false);
   ok:=v->>'state'='RETAINED_SOURCE_READY' AND v->>'source_sha256'=s.source_sha256 AND v->>'compressed_sha256'=s.compressed_sha256;
  ELSE SELECT encode(sha256(convert_to(p.raw_body,'UTF8')),'hex')=s.source_sha256 AND p.body_sha256=s.source_sha256 INTO ok
   FROM astra_ingestion_v1.backfill_pages_v2 p WHERE p.task_id=s.task_id AND p.page_no=s.page_no; END IF;
  ok:=COALESCE(ok,false);
  IF s.verified IS DISTINCT FROM ok OR s.invalidated IS DISTINCT FROM NOT ok THEN
   INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,task_id,action,evidence)
   VALUES(s.run_id,s.task_id,CASE WHEN ok THEN 'IDENTITY_SOURCE_REVALIDATED' ELSE 'IDENTITY_SOURCE_INVALIDATED' END,
    jsonb_build_object('source_ref',s.source_ref,'source_sha256',s.source_sha256,'market_date',s.market_date,
     'previously_verified',s.verified,'verified_now',ok,'reason',CASE WHEN NOT ok THEN 'ORIGINAL_REFERENCE_SOURCE_CHANGED' END));
   UPDATE astra_ingestion_v1.backfill_identity_sources_v2 SET verified=ok,invalidated=NOT ok,
    invalidation_reason=CASE WHEN NOT ok THEN 'ORIGINAL_REFERENCE_SOURCE_CHANGED' END,verified_at=clock_timestamp()
    WHERE run_id=s.run_id AND source_ref=s.source_ref;
   FOR x IN SELECT DISTINCT member_id,market_date FROM astra_ingestion_v1.backfill_identity_evidence_v2 WHERE run_id=s.run_id AND source_ref=s.source_ref LOOP
    PERFORM astra_ingestion_v1.backfill_identity_mark_changed_v2(s.run_id,x.member_id,x.market_date);END LOOP;
  END IF;
  n:=n+1;
 END LOOP;
 RETURN n;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_build_material_v2(t astra_ingestion_v1.backfill_tasks_v2) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path='' AS $$
DECLARE rows jsonb;digest text;
BEGIN
 WITH requested AS (
  SELECT m.member_id,m.anchor_ticker symbol,m.anchor,(d->>'date')::date AS requested_date
  FROM astra_ingestion_v1.backfill_members_v2 m CROSS JOIN LATERAL jsonb_array_elements(COALESCE(t.scope->'calendar','[]')) d
  WHERE m.run_id=t.run_id AND (t.kind='derive_breadth' OR (t.scope->'member_ids') ? m.member_id)
 )
 SELECT COALESCE(jsonb_agg(jsonb_build_object('member_id',q.member_id,'symbol',q.symbol,'market_date',q.requested_date,
  'state',COALESCE(c.state,'IDENTITY_OR_QUALITY_UNRESOLVED'),'reason',COALESCE(c.reason,CASE WHEN c.state IS NULL THEN 'DATED_IDENTITY_EVIDENCE_UNAVAILABLE' END),
  'identity_anchor',c.identity_anchor,'cik',c.cik,'composite_figi',c.composite_figi,'share_class_figi',c.share_class_figi,
  'historical_symbol',c.historical_symbol,'security_type',c.security_type,'primary_exchange',c.primary_exchange,'eligible',c.eligible,
  'anchor_identity',jsonb_build_object('member_id',q.member_id,'symbol',q.symbol,'reference_date',q.anchor->>'anchor_observation_date',
   'cik',substring(q.member_id from 5),'composite_figi',q.anchor->>'anchor_composite_figi','share_class_figi',q.anchor->>'anchor_share_class_figi',
   'security_type',q.anchor->>'anchor_security_type','primary_exchange',q.anchor->>'anchor_exchange',
   'membership_accepted',q.anchor->'membership_accepted','cohort_sha256',q.anchor->>'cohort_sha256',
   'anchor_sha256',encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(q.anchor),'UTF8')),'hex')),
  'evidence_sha256',c.evidence_sha256,'retrospective_only',true,'strict_historical_availability_certified',false,
  'input_body_sha256',CASE WHEN t.kind='derive_breadth' THEN b.body_sha256 END) ORDER BY q.member_id,q.requested_date),'[]') INTO rows
 FROM requested q LEFT JOIN LATERAL(SELECT ic.* FROM astra_ingestion_v1.backfill_identity_current_v2 ic
  WHERE ic.run_id=t.run_id AND ic.member_id=q.member_id AND ic.market_date=q.requested_date OFFSET 0) c ON true
 LEFT JOIN LATERAL(SELECT bi.body_sha256 FROM astra_ingestion_v1.backfill_breadth_inputs_v2 bi
   JOIN astra_ingestion_v1.backfill_readbacks_v2 rb ON rb.task_id=bi.task_id AND rb.page_no=bi.page_no
   WHERE t.kind='derive_breadth' AND bi.run_id=t.run_id AND bi.member_id=q.member_id AND bi.market_date=q.requested_date
   ORDER BY bi.source_committed_at DESC,bi.task_id,bi.page_no DESC LIMIT 1) b ON true;
 IF jsonb_array_length(rows)>3000 THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Identity material exceeds fixed bounded unit'; END IF;
 digest:=encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(rows),'UTF8')),'hex');
 RETURN jsonb_build_object('version','fixed3000-retrospective-identity-v2.2','run_id',t.run_id,'task_id',t.id,
  'mappings',rows,'identity_material_sha256',digest,'evidence_revision',digest);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_material_v2(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;result jsonb;root text;member text;
BEGIN
 t:=astra_ingestion_v1.backfill_owned_v2(p_payload->'claim');
 IF t.kind NOT IN('derive_daily','derive_intraday','derive_breadth') THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Identity material is scoped to a calculation claim'; END IF;
 member:=CASE WHEN t.kind<>'derive_breadth' THEN t.scope#>>'{member_ids,0}' END;
 IF member IS NOT NULL THEN PERFORM astra_ingestion_v1.backfill_identity_discover_member_v2(t.run_id,member); END IF;
 PERFORM astra_ingestion_v1.backfill_identity_validate_sources_v2(t.run_id,member,
  (SELECT min((e->>'date')::date) FROM jsonb_array_elements(t.scope->'calendar') e),
  (SELECT max((e->>'date')::date) FROM jsonb_array_elements(t.scope->'calendar') e));
 result:=astra_ingestion_v1.backfill_identity_build_material_v2(t);root:=COALESCE(t.scope->>'identity_refresh_of',t.id);
 INSERT INTO astra_ingestion_v1.backfill_identity_roots_v2(root_task_id,run_id,member_id,input_start,target_end,identity_material_sha256)
 VALUES(root,t.run_id,member,(SELECT min((e->>'date')::date) FROM jsonb_array_elements(t.scope->'calendar') e),
  (SELECT max((e->>'date')::date) FROM jsonb_array_elements(t.scope->'calendar') e),result->>'identity_material_sha256')
 ON CONFLICT(root_task_id) DO UPDATE SET identity_material_sha256=EXCLUDED.identity_material_sha256,invalidated=false,checked_at=clock_timestamp();
 RETURN result;
END $$;

CREATE VIEW astra_ingestion_v1.backfill_identity_output_validity_v2 WITH(security_invoker=true) AS
 SELECT t.id task_id,
  CASE WHEN c.identity_material_sha256 IS NOT NULL THEN NOT COALESCE(r.invalidated,true) AND c.identity_material_sha256=r.identity_material_sha256 END identity_material_current,
  c.identity_material_sha256 IS NOT NULL AND (COALESCE(r.invalidated,true) OR c.identity_material_sha256 IS DISTINCT FROM r.identity_material_sha256) identity_invalidated,
  CASE WHEN c.identity_material_sha256 IS NOT NULL AND (COALESCE(r.invalidated,true) OR c.identity_material_sha256 IS DISTINCT FROM r.identity_material_sha256)
   THEN 'CURRENT_IDENTITY_EVIDENCE_CHANGED_RECOMPUTE_PENDING' END invalidation_reason
 FROM astra_ingestion_v1.backfill_tasks_v2 t LEFT JOIN astra_ingestion_v1.backfill_identity_calculation_receipts_v2 c ON c.task_id=t.id
 LEFT JOIN astra_ingestion_v1.backfill_identity_roots_v2 r ON r.root_task_id=COALESCE(t.scope->>'identity_refresh_of',t.id)
 WHERE t.kind IN('derive_daily','derive_intraday','derive_breadth');

CREATE FUNCTION astra_ingestion_v1.backfill_identity_readback_trigger_v2() RETURNS trigger
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;p astra_ingestion_v1.backfill_pages_v2;ref text;b jsonb;day date;x record;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=NEW.task_id;
 SELECT * INTO STRICT p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=NEW.task_id AND page_no=NEW.page_no;
 IF t.kind='massive_reference' THEN
  b:=p.raw_body::jsonb;day:=(t.scope->>'asof')::date;ref:='page:'||t.id||':'||p.page_no;
  INSERT INTO astra_ingestion_v1.backfill_identity_sources_v2(run_id,source_ref,source_kind,task_id,page_no,market_date,source_sha256,native_records,verified,verified_at)
  VALUES(t.run_id,ref,'CURRENT_PAGE',t.id,p.page_no,day,p.body_sha256,p.record_count,true,clock_timestamp()) ON CONFLICT DO NOTHING;
  PERFORM astra_ingestion_v1.backfill_identity_project_v2(t.run_id,day,ref,p.body_sha256,
   CASE WHEN jsonb_typeof(b->'results')='object' THEN jsonb_build_array(b->'results') ELSE COALESCE(b->'results','[]') END);
 ELSIF t.kind IN('derive_daily','derive_intraday','derive_breadth') THEN
  INSERT INTO astra_ingestion_v1.backfill_identity_calculation_receipts_v2(task_id,root_task_id,identity_material_sha256,body_sha256,page_no)
  VALUES(t.id,COALESCE(t.scope->>'identity_refresh_of',t.id),p.raw_body::jsonb->>'identity_material_sha256',p.body_sha256,p.page_no) ON CONFLICT DO NOTHING;
  IF t.family='D03' THEN
   FOR x IN SELECT DISTINCT (value->>'market_date')::date AS session_date FROM jsonb_array_elements(COALESCE(p.raw_body::jsonb->'rows','[]')) LOOP
    IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_identity_roots_v2 ir WHERE ir.run_id=t.run_id AND ir.member_id IS NULL
      AND x.session_date BETWEEN ir.input_start AND ir.target_end) THEN
     PERFORM astra_ingestion_v1.backfill_identity_mark_changed_v2(t.run_id,'__COHORT__',x.session_date); END IF;
   END LOOP;
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER backfill_identity_readback_v2 AFTER INSERT ON astra_ingestion_v1.backfill_readbacks_v2
 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_identity_readback_trigger_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_identity_refresh_pending_v2(p_limit integer DEFAULT 2) RETURNS integer
LANGUAGE plpgsql VOLATILE SET search_path='' SET statement_timeout='8s' AS $$
DECLARE q astra_ingestion_v1.backfill_identity_refresh_v2;t astra_ingestion_v1.backfill_tasks_v2;v jsonb;v_id text;n integer:=0;seen integer:=0;last_id text;
BEGIN
 SELECT x.* INTO q FROM astra_ingestion_v1.backfill_identity_refresh_v2 x JOIN astra_ingestion_v1.backfill_runs_v2 r ON r.id=x.run_id
  WHERE r.status='ACTIVE' AND x.ready_after<=clock_timestamp()
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_identity_source_members_v2 sm JOIN astra_ingestion_v1.backfill_tasks_v2 st ON st.id=sm.task_id
    WHERE sm.run_id=x.run_id AND sm.member_id=x.member_id AND st.status IN('PENDING','RUNNING','RETRY_WAIT'))
  ORDER BY x.ready_after,x.run_id,x.member_id LIMIT 1 FOR UPDATE OF x;
 IF NOT FOUND THEN RETURN 0; END IF;
 PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=q.run_id AND status='ACTIVE' FOR UPDATE;
 IF NOT FOUND THEN RETURN 0; END IF;
 last_id:=q.after_task_id;
 FOR t IN SELECT * FROM astra_ingestion_v1.backfill_tasks_v2 z WHERE z.run_id=q.run_id AND z.id>q.after_task_id AND NOT(z.scope ? 'identity_refresh_of')
  AND ((q.member_id='__COHORT__' AND z.kind='derive_breadth') OR (z.kind='derive_daily' AND z.scope#>>'{member_ids,0}'=q.member_id))
  AND z.status IN('INGESTED','NO_DATA_RETURNED','IDENTITY_OR_QUALITY_UNRESOLVED')
  AND COALESCE((z.scope->>'input_start')::date,(z.scope->>'target_start')::date)<=q.latest_date
  AND (z.scope->>'target_end')::date>=q.earliest_date ORDER BY z.id LIMIT GREATEST(1,LEAST(p_limit,8))
 LOOP
  seen:=seen+1;last_id:=t.id;v:=astra_ingestion_v1.backfill_identity_build_material_v2(t);
  INSERT INTO astra_ingestion_v1.backfill_identity_roots_v2(root_task_id,run_id,member_id,input_start,target_end,identity_material_sha256)
  VALUES(t.id,t.run_id,CASE WHEN t.kind<>'derive_breadth' THEN q.member_id END,COALESCE((t.scope->>'input_start')::date,(t.scope->>'target_start')::date),(t.scope->>'target_end')::date,v->>'identity_material_sha256')
  ON CONFLICT(root_task_id) DO UPDATE SET identity_material_sha256=EXCLUDED.identity_material_sha256,invalidated=false,checked_at=clock_timestamp();
  IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_identity_calculation_receipts_v2 c
    WHERE c.root_task_id=t.id AND c.identity_material_sha256=v->>'identity_material_sha256') THEN CONTINUE; END IF;
  v_id:='backfill-identity-refresh-'||encode(sha256(convert_to(t.id||':'||(v->>'identity_material_sha256'),'UTF8')),'hex');
  INSERT INTO astra_ingestion_v1.backfill_tasks_v2(id,run_id,family,provider,kind,scope,dependencies,priority,run_fence)
  VALUES(v_id,t.run_id,t.family,t.provider,t.kind,t.scope||jsonb_build_object('identity_refresh_of',t.id,
    'identity_material_sha256',v->>'identity_material_sha256','plan_static',false,'prefer_retained_formula_cache',false),t.dependencies,GREATEST(t.priority,150),t.run_fence)
  ON CONFLICT(id) DO NOTHING;
  n:=n+1;
 END LOOP;
 IF seen<GREATEST(1,LEAST(p_limit,8)) THEN DELETE FROM astra_ingestion_v1.backfill_identity_refresh_v2 WHERE run_id=q.run_id AND member_id=q.member_id;
 ELSE UPDATE astra_ingestion_v1.backfill_identity_refresh_v2 SET after_task_id=last_id WHERE run_id=q.run_id AND member_id=q.member_id; END IF;
 RETURN n;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_identity_progress_v2(p_run text) RETURNS jsonb
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT jsonb_build_object(
  'identity_discovery_pending_count',(SELECT count(*) FROM astra_ingestion_v1.backfill_identity_discovered_members_v2 WHERE run_id=p_run AND NOT complete),
  'identity_refresh_pending_count',(SELECT count(*) FROM astra_ingestion_v1.backfill_identity_refresh_v2 WHERE run_id=p_run),
  'identity_refresh_next_retry_at',(SELECT min(ready_after) FROM astra_ingestion_v1.backfill_identity_refresh_v2 WHERE run_id=p_run),
  'identity_recalculation_pending_tasks',(SELECT count(*) FROM astra_ingestion_v1.backfill_tasks_v2 WHERE run_id=p_run AND scope ? 'identity_refresh_of' AND status IN('PENDING','RUNNING','RETRY_WAIT')),
  'identity_sources_verified',(SELECT count(*) FROM astra_ingestion_v1.backfill_identity_sources_v2 WHERE run_id=p_run AND verified AND NOT invalidated),
  'identity_sources_invalidated',(SELECT count(*) FROM astra_ingestion_v1.backfill_identity_sources_v2 WHERE run_id=p_run AND invalidated),
  'identity_source_last_verified_at',(SELECT max(verified_at) FROM astra_ingestion_v1.backfill_identity_sources_v2 WHERE run_id=p_run AND verified AND NOT invalidated))
$$;

-- Extend only the existing authenticated capability and queue. No public source access.
DO $wire$
DECLARE c record;d text;b text;v text;
BEGIN
 FOR c IN SELECT conname,pg_get_constraintdef(oid) def FROM pg_constraint WHERE conrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass AND contype='c'
  AND pg_get_constraintdef(oid) LIKE '%retained_reuse%' LOOP
  EXECUTE format('ALTER TABLE astra_ingestion_v1.backfill_tasks_v2 DROP CONSTRAINT %I',c.conname);
  EXECUTE 'ALTER TABLE astra_ingestion_v1.backfill_tasks_v2 ADD CONSTRAINT '||quote_ident(c.conname)||' '||replace(c.def,'''retained_reuse''::text','''retained_reuse''::text, ''retained_identity''::text');
 END LOOP;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_task_guard_v2()'::regprocedure) INTO d;
 d:=replace(d,'NEW.family NOT IN (''CTX06'',''REF03'') AND','NEW.family NOT IN (''CTX06'',''REF03'') AND NEW.kind<>''retained_identity'' AND');
 d:=replace(d,' v_members:=NEW.scope->''member_ids'';',E' IF NEW.kind=''retained_identity'' AND (lower(NEW.provider)<>''reuse'' OR NEW.family<>''REF01'' OR NEW.scope->''shared_cohort_reference'' IS DISTINCT FROM ''true''::jsonb OR NEW.scope->>''cohort_sha256'' IS DISTINCT FROM ''2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'') THEN RAISE EXCEPTION ''Invalid shared fixed-cohort identity source''; END IF;\n v_members:=NEW.scope->''member_ids'';');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_snapshot_task_v2(text)'::regprocedure) INTO d;
 d:=replace(d,'OR t.scope ? ''reuse_parent'' THEN RETURN false;','OR t.scope ? ''reuse_parent'' OR t.scope ? ''identity_refresh_of'' OR t.kind=''retained_identity'' THEN RETURN false;');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO d;
 d:=replace(d,'''backfill_work''','''backfill_work'',''backfill_identity_material'',''backfill_identity_source_read'',''backfill_identity_source_commit'',''backfill_identity_refresh''');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO b;
 b:=replace(b,' IF p_operation=''backfill_status'' THEN',E' IF p_operation=''backfill_identity_material'' THEN RETURN astra_ingestion_v1.backfill_identity_material_v2(p_payload); END IF;\n IF p_operation=''backfill_identity_source_read'' THEN RETURN astra_ingestion_v1.backfill_identity_source_read_v2(p_payload); END IF;\n IF p_operation=''backfill_identity_source_commit'' THEN RETURN astra_ingestion_v1.backfill_identity_source_commit_v2(p_payload); END IF;\n IF p_operation=''backfill_identity_refresh'' THEN RETURN jsonb_build_object(''queued'',astra_ingestion_v1.backfill_identity_refresh_pending_v2(COALESCE((p_payload->>''limit'')::int,2))); END IF;\n IF p_operation=''backfill_status'' THEN');
 IF strpos(b,' ELSIF p_operation=''backfill_claim'' THEN')=0 THEN RAISE EXCEPTION 'Identity refresh claim hook baseline changed'; END IF;
 b:=replace(b,' ELSIF p_operation=''backfill_claim'' THEN',E' ELSIF p_operation=''backfill_claim'' THEN\n  PERFORM astra_ingestion_v1.backfill_identity_discover_pending_v2();\n  PERFORM astra_ingestion_v1.backfill_identity_refresh_pending_v2(2);\n  v_now:=clock_timestamp();');
 IF strpos(b,'SELECT to_jsonb(r) || jsonb_build_object(')=0 THEN RAISE EXCEPTION 'Identity status projection baseline changed';END IF;
 b:=replace(b,'SELECT to_jsonb(r) || jsonb_build_object(','SELECT to_jsonb(r) || astra_ingestion_v1.backfill_identity_progress_v2(r.id) || jsonb_build_object(');EXECUTE b;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_breadth_project_page_v2(text,integer)'::regprocedure) INTO d;
 IF strpos(d,'formula_version,body_sha256,source_committed_at)')=0 OR strpos(d,'p.body_sha256,p.committed_at);')=0 THEN
  RAISE EXCEPTION 'Identity breadth projection baseline changed';END IF;
 d:=replace(d,'formula_version,body_sha256,source_committed_at)','formula_version,body_sha256,source_committed_at,identity_input_attribution)');
 d:=replace(d,'p.body_sha256,p.committed_at);','p.body_sha256,p.committed_at,v_row->''identity_input_attribution'');');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_breadth_material_v2(jsonb)'::regprocedure) INTO d;
 IF strpos(d,'q.formula_version,q.body_sha256')=0 OR strpos(d,'''formula_version'',formula_version,''source_lineage''')=0 THEN
  RAISE EXCEPTION 'Identity breadth reader baseline changed';END IF;
 d:=replace(d,'q.formula_version,q.body_sha256','q.formula_version,q.body_sha256,q.identity_input_attribution');
 d:=replace(d,'''formula_version'',formula_version,''source_lineage''','''formula_version'',formula_version,''identity_input_attribution'',identity_input_attribution,''source_lineage''');
 d:=replace(d,'   FROM astra_ingestion_v1.backfill_breadth_inputs_v2 q WHERE',E'   FROM astra_ingestion_v1.backfill_breadth_inputs_v2 q JOIN astra_ingestion_v1.backfill_readbacks_v2 qr ON qr.task_id=q.task_id AND qr.page_no=q.page_no WHERE');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_recheck_page_v2(text,integer)'::regprocedure) INTO d;
 IF strpos(d,'v_feature jsonb;')=0 OR strpos(d,'retained_feature_verification)')=0 OR strpos(d,',v_feature)')=0 THEN
  RAISE EXCEPTION 'Identity readback requires the qualified feature-reuse baseline'; END IF;
 d:=replace(d,'v_feature jsonb;','v_feature jsonb; v_identity jsonb;');
 d:=replace(d,' IF lower(p.provider)=''reuse'' THEN',' IF lower(p.provider)=''reuse'' AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 it WHERE it.id=p.task_id AND it.kind=''retained_identity'') THEN');
 d:=replace(d,' v_hash:=encode(sha256(convert_to(p.raw_body,''UTF8'')),''hex'');',E' v_hash:=encode(sha256(convert_to(p.raw_body,''UTF8'')),''hex'');\n IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 it WHERE it.id=p.task_id AND it.kind=''retained_identity'') THEN\n  v_identity:=astra_ingestion_v1.backfill_identity_source_verify_v2(p.task_id,p.page_no);\n  IF v_identity->''passed'' IS DISTINCT FROM ''true''::jsonb THEN RAISE EXCEPTION USING ERRCODE=''AI002'',MESSAGE=''Retained identity source readback differs''; END IF;\n END IF;');
 d:=replace(d,'retained_feature_verification)','retained_feature_verification,retained_identity_verification)');
 d:=replace(d,',v_feature)',',v_feature,v_identity)');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) INTO d;
 d:=replace(d,' FOR p IN SELECT pg.task_id',E' PERFORM astra_ingestion_v1.backfill_identity_discover_pending_v2();\n PERFORM astra_ingestion_v1.backfill_identity_refresh_pending_v2(2);\n FOR p IN SELECT pg.task_id');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_try_finalize_v2(text)'::regprocedure) INTO d;
 d:=replace(d,' IF r.metadata->''planning_complete''',E' IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_identity_discovered_members_v2 WHERE run_id=r.id AND NOT complete) THEN RETURN jsonb_build_object(''state'',''IDENTITY_SOURCE_DISCOVERY_PENDING''); END IF;\n IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_identity_refresh_v2 WHERE run_id=r.id) THEN RETURN jsonb_build_object(''state'',''IDENTITY_RECOMPUTATION_PENDING''); END IF;\n IF r.metadata->''planning_complete''');EXECUTE d;
END $wire$;

DO $acl$
DECLARE o record;g record;f record;
BEGIN
 FOR o IN SELECT c.* FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='astra_ingestion_v1'
  AND (c.relname LIKE 'backfill_identity_%' OR c.relname='backfill_family_d01_v2') AND c.relkind IN('r','v','S') LOOP
  EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM PUBLIC',o.relname);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(o.relacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>o.relowner LOOP
   EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM %I',o.relname,g.rolname);END LOOP;
  IF o.relkind='r' THEN
   EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',o.relname);
   EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',o.relname);
   EXECUTE format('CREATE POLICY identity_internal_v2 ON astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1 USING(true) WITH CHECK(true)',o.relname);
  ELSIF o.relkind='v' THEN EXECUTE format('GRANT SELECT ON astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',o.relname);
  ELSIF o.relkind='S' THEN EXECUTE format('GRANT USAGE,SELECT ON SEQUENCE astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',o.relname); END IF;
 END LOOP;
 FOR f IN SELECT p.*,pg_get_function_identity_arguments(p.oid) args FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='astra_ingestion_v1' AND p.proname LIKE 'backfill_identity_%_v2' LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM PUBLIC',f.proname,f.args);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(f.proacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>f.proowner LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM %I',f.proname,f.args,g.rolname);END LOOP;
  EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.%I(%s) TO astra_ingestion_rpc_owner_v1',f.proname,f.args);
 END LOOP;
END $acl$;
COMMIT;
