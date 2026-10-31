-- Fixed-cohort replacement execution in the existing authenticated ingestion runtime.
-- No provider credential, public table access, alternate controller or old-job replay.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $admission$
BEGIN
 IF pg_catalog.to_regclass('astra_ingestion_v1.backfill_runs_v2') IS NOT NULL THEN
   RAISE EXCEPTION 'Backfill runtime already installed; reconcile rather than replay migration';
 END IF;
 IF pg_catalog.strpos(pg_catalog.pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure),
      'replacement_scope_admission_gate_v2')=0 THEN
   RAISE EXCEPTION 'The authenticated old-scope admission gate must be installed first';
 END IF;
END $admission$;
INSERT INTO astra_ingestion_v1.source_limits(id,next_request_at) VALUES('massive',0) ON CONFLICT(id) DO NOTHING;

CREATE TABLE astra_ingestion_v1.backfill_runs_v2 (
 id text PRIMARY KEY CHECK(length(id) BETWEEN 8 AND 160),
 instruction_sha256 text NOT NULL CHECK(instruction_sha256 ~ '^[0-9a-f]{64}$'),
 cohort_sha256 text NOT NULL CHECK(cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'),
 cohort_manifest_sha256 text NOT NULL CHECK(cohort_manifest_sha256='4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'),
 cohort_ref text NOT NULL,
 cohort_policy text NOT NULL DEFAULT 'RETROSPECTIVE_FIXED_COHORT' CHECK(cohort_policy='RETROSPECTIVE_FIXED_COHORT'),
 target_start date NOT NULL DEFAULT '2025-09-01' CHECK(target_start='2025-09-01'),
 target_end date NOT NULL DEFAULT '2026-07-31' CHECK(target_end='2026-07-31'),
 scope jsonb NOT NULL CHECK(jsonb_typeof(scope)='object'),
 status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','PAUSED','SUPERSEDED','COMPLETE','COMPLETE_WITH_DOCUMENTED_GAPS','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL')),
 fence bigint NOT NULL DEFAULT 1 CHECK(fence>0),
 metadata jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 last_progress_at timestamptz,
 requests_reserved bigint NOT NULL DEFAULT 0 CHECK(requests_reserved>=0),
 pages_committed bigint NOT NULL DEFAULT 0 CHECK(pages_committed>=0),
 records_committed bigint NOT NULL DEFAULT 0 CHECK(records_committed>=0),
 source_bytes bigint NOT NULL DEFAULT 0 CHECK(source_bytes>=0)
);
CREATE UNIQUE INDEX backfill_one_active_run_v2 ON astra_ingestion_v1.backfill_runs_v2((true)) WHERE status='ACTIVE';
CREATE TABLE astra_ingestion_v1.backfill_members_v2 (
 run_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_runs_v2(id),
 member_id text NOT NULL,
 selection_order integer NOT NULL CHECK(selection_order BETWEEN 1 AND 3000),
 anchor_ticker text NOT NULL,
 anchor jsonb NOT NULL DEFAULT '{}',
 PRIMARY KEY(run_id,member_id), UNIQUE(run_id,selection_order)
);
CREATE TABLE astra_ingestion_v1.backfill_tasks_v2 (
 id text PRIMARY KEY CHECK(length(id) BETWEEN 8 AND 200),
 run_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_runs_v2(id),
 family text NOT NULL CHECK(family IN ('REF01','REF03','P01','P02','D01','D02','D03','D04','D05','N01','N02','N03','S01','S02','CTX02','CTX06')),
 provider text NOT NULL CHECK(provider IN ('Alpaca','Massive','derived','reuse','DERIVED','REUSE')),
 kind text NOT NULL CHECK(kind IN ('alpaca_reference','alpaca_stock_bars','alpaca_news','alpaca_actions','alpaca_option_contracts','alpaca_option_bars','massive_reference','massive_news','massive_dividends','massive_splits','massive_short_volume','massive_short_interest','derive_daily','derive_intraday','derive_breadth','retained_reuse')),
 scope jsonb NOT NULL CHECK(jsonb_typeof(scope)='object'),
 dependencies text[] NOT NULL DEFAULT '{}',
 priority integer NOT NULL DEFAULT 100,
 status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RUNNING','RETRY_WAIT','INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED','OPERATIONAL_ERROR','BLOCKED_EXTERNAL','SUPERSEDED_BY_SCOPE_CHANGE')),
 cursor jsonb,
 page_no integer NOT NULL DEFAULT 0 CHECK(page_no>=0),
 owner text,
 generation bigint NOT NULL DEFAULT 0 CHECK(generation>=0),
 run_fence bigint NOT NULL DEFAULT 1,
 lease_until timestamptz,
 attempt_deadline timestamptz,
 next_retry_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 attempts bigint NOT NULL DEFAULT 0 CHECK(attempts>=0),
 page_attempts integer NOT NULL DEFAULT 0 CHECK(page_attempts BETWEEN 0 AND 8),
 requests_reserved bigint NOT NULL DEFAULT 0 CHECK(requests_reserved>=0),
 records_committed bigint NOT NULL DEFAULT 0 CHECK(records_committed>=0),
 reserved_generation bigint,
 reserved_page_no integer,
 reserved_at timestamptz,
 last_progress_at timestamptz,
 error_code text,
 error_message text,
 source_revision text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(cursor IS NULL OR jsonb_typeof(cursor) IN ('null','string')),
 CHECK((status='RUNNING' AND owner IS NOT NULL AND lease_until IS NOT NULL) OR
       (status<>'RUNNING' AND owner IS NULL AND lease_until IS NULL))
);
CREATE INDEX backfill_tasks_runnable_v2 ON astra_ingestion_v1.backfill_tasks_v2(run_id,status,priority,next_retry_at,id);
CREATE INDEX backfill_tasks_family_v2 ON astra_ingestion_v1.backfill_tasks_v2(run_id,family,status);
CREATE INDEX backfill_tasks_provider_v2 ON astra_ingestion_v1.backfill_tasks_v2(run_id,provider,status,kind);
CREATE TABLE astra_ingestion_v1.backfill_pages_v2 (
 task_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),
 page_no integer NOT NULL CHECK(page_no>=0),
 run_id text NOT NULL,
 generation bigint NOT NULL,
 run_fence bigint NOT NULL,
 provider text NOT NULL,
 cursor_in jsonb,
 cursor_out jsonb,
 request jsonb NOT NULL,
 http_status integer NOT NULL,
 request_id text,
 fetched_at timestamptz NOT NULL,
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 raw_body text NOT NULL,
 body_sha256 text NOT NULL CHECK(body_sha256 ~ '^[0-9a-f]{64}$'),
 records_sha256 text NOT NULL CHECK(records_sha256 ~ '^[0-9a-f]{64}$'),
 record_count integer NOT NULL CHECK(record_count BETWEEN 0 AND 100000),
 source_bytes integer NOT NULL CHECK(source_bytes>=0),
 quality jsonb NOT NULL DEFAULT '[]',
 headers jsonb NOT NULL DEFAULT '{}',
 adapter_version text NOT NULL,
 PRIMARY KEY(task_id,page_no)
);
CREATE INDEX backfill_pages_run_v2 ON astra_ingestion_v1.backfill_pages_v2(run_id,task_id,page_no);
CREATE TABLE astra_ingestion_v1.backfill_exceptions_v2 (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id text NOT NULL,
 task_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),
 page_no integer NOT NULL,
 generation bigint NOT NULL,
 state text NOT NULL,
 code text NOT NULL,
 message text NOT NULL,
 evidence jsonb NOT NULL DEFAULT '{}',
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 next_retry_at timestamptz
);
CREATE INDEX backfill_exceptions_task_v2 ON astra_ingestion_v1.backfill_exceptions_v2(task_id,id);
CREATE TABLE astra_ingestion_v1.backfill_workers_v2 (
 worker_id text PRIMARY KEY,
 source_revision text NOT NULL,
 supported_kinds jsonb NOT NULL,
 capability_revision text NOT NULL,
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE astra_ingestion_v1.backfill_provider_dependencies_v2 (
 run_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_runs_v2(id),
 provider text NOT NULL CHECK(provider IN ('Alpaca','Massive')),
 dependency text NOT NULL CHECK(dependency IN ('ALPACA_WORKER_CREDENTIAL','MASSIVE_WORKER_CREDENTIAL')),
 state text NOT NULL CHECK(state IN ('BLOCKED_EXTERNAL','AVAILABLE')),
 code text NOT NULL,
 evidence jsonb NOT NULL,
 blocked_worker text,
 blocked_revision text,
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 resolved_at timestamptz,
 PRIMARY KEY(run_id,provider)
);

CREATE FUNCTION astra_ingestion_v1.backfill_run_guard_v2() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF NEW.id IS DISTINCT FROM OLD.id OR NEW.instruction_sha256 IS DISTINCT FROM OLD.instruction_sha256
 OR NEW.cohort_sha256 IS DISTINCT FROM OLD.cohort_sha256 OR NEW.cohort_manifest_sha256 IS DISTINCT FROM OLD.cohort_manifest_sha256
 OR NEW.cohort_ref IS DISTINCT FROM OLD.cohort_ref OR NEW.scope IS DISTINCT FROM OLD.scope
 OR NEW.target_start IS DISTINCT FROM OLD.target_start OR NEW.target_end IS DISTINCT FROM OLD.target_end
 OR NEW.fence<OLD.fence OR NEW.requests_reserved<OLD.requests_reserved OR NEW.pages_committed<OLD.pages_committed
 OR NEW.records_committed<OLD.records_committed OR NEW.source_bytes<OLD.source_bytes
 OR (OLD.status IN ('SUPERSEDED','COMPLETE','COMPLETE_WITH_DOCUMENTED_GAPS') AND NEW.status IS DISTINCT FROM OLD.status)
 THEN RAISE EXCEPTION 'Replacement run scope, cumulative accounting and terminal stop are immutable'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER backfill_run_immutable_v2 BEFORE UPDATE ON astra_ingestion_v1.backfill_runs_v2
FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_run_guard_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_task_guard_v2() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$
DECLARE v_kind text; v_members jsonb; v_member text;
BEGIN
 IF TG_OP='UPDATE' THEN
   IF NEW.id IS DISTINCT FROM OLD.id OR NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.family IS DISTINCT FROM OLD.family
    OR NEW.provider IS DISTINCT FROM OLD.provider OR NEW.kind IS DISTINCT FROM OLD.kind OR NEW.scope IS DISTINCT FROM OLD.scope
    OR NEW.dependencies IS DISTINCT FROM OLD.dependencies OR NEW.generation<OLD.generation
    OR NEW.requests_reserved<OLD.requests_reserved OR NEW.records_committed<OLD.records_committed OR NEW.page_no<OLD.page_no
    OR NEW.attempts<OLD.attempts OR (OLD.status IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED','SUPERSEDED_BY_SCOPE_CHANGE') AND NEW.status IS DISTINCT FROM OLD.status)
   THEN RAISE EXCEPTION 'Task scope, cumulative accounting and terminal result are immutable'; END IF;
   RETURN NEW;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=NEW.run_id AND status='ACTIVE' AND fence=NEW.run_fence) THEN
   RAISE EXCEPTION 'Task requires current active replacement run'; END IF;
 IF (NEW.kind LIKE 'alpaca_%' AND NEW.provider<>'Alpaca') OR (NEW.kind LIKE 'massive_%' AND NEW.provider<>'Massive')
 OR (NEW.kind LIKE 'derive_%' AND lower(NEW.provider)<>'derived') OR (NEW.kind='retained_reuse' AND lower(NEW.provider)<>'reuse') THEN
   RAISE EXCEPTION 'Task kind and permitted provider disagree'; END IF;
 v_members:=NEW.scope->'member_ids';
 IF NEW.family NOT IN ('CTX06','REF03') AND (jsonb_typeof(v_members) IS DISTINCT FROM 'array' OR jsonb_array_length(v_members)=0) THEN
   RAISE EXCEPTION 'Member-scoped work requires frozen member identifiers'; END IF;
 IF v_members IS NOT NULL THEN
   IF jsonb_typeof(v_members) IS DISTINCT FROM 'array' OR jsonb_array_length(v_members)>3000 THEN RAISE EXCEPTION 'Invalid member scope'; END IF;
   FOR v_member IN SELECT jsonb_array_elements_text(v_members) LOOP
     IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=NEW.run_id AND member_id=v_member) THEN
       RAISE EXCEPTION 'Task member is outside the frozen cohort'; END IF;
   END LOOP;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER backfill_task_scope_v2 BEFORE INSERT OR UPDATE ON astra_ingestion_v1.backfill_tasks_v2
FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_task_guard_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$ BEGIN RAISE EXCEPTION 'Backfill source evidence and frozen membership are immutable'; END $$;
CREATE TRIGGER backfill_page_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_pages_v2
FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();
CREATE TRIGGER backfill_member_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_members_v2
FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_owned_v2(p_claim jsonb) RETURNS astra_ingestion_v1.backfill_tasks_v2
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;
BEGIN
 IF jsonb_typeof(p_claim) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Invalid replacement claim'; END IF;
 SELECT * INTO t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_claim->>'id' FOR UPDATE;
 IF NOT FOUND OR t.status<>'RUNNING' OR t.run_id IS DISTINCT FROM p_claim->>'run_id'
 OR t.owner IS DISTINCT FROM p_claim->>'owner' OR t.generation::text IS DISTINCT FROM p_claim->>'generation'
 OR t.run_fence::text IS DISTINCT FROM p_claim->>'run_fence' OR t.lease_until<=clock_timestamp()
 OR NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 r WHERE r.id=t.run_id AND r.fence=t.run_fence AND r.status='ACTIVE')
 THEN RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Replacement lease, run fence or stop changed'; END IF;
 RETURN t;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_request_valid_v2(t astra_ingestion_v1.backfill_tasks_v2,q jsonb)
RETURNS boolean LANGUAGE plpgsql SET search_path='' AS $$
DECLARE p text; syms text; h text; token_key text;
BEGIN
 IF lower(t.provider) IN ('derived','reuse') THEN RETURN jsonb_typeof(q)='object'; END IF;
 IF q->>'method' IS DISTINCT FROM 'GET' OR q->>'provider' IS DISTINCT FROM t.provider OR jsonb_typeof(q->'params') IS DISTINCT FROM 'object' THEN RETURN false; END IF;
 SELECT string_agg(s,',' ORDER BY ord) INTO syms FROM jsonb_array_elements_text(t.scope->'symbols') WITH ORDINALITY AS a(s,ord);
 IF syms IS NULL THEN syms:=t.scope->>'symbol'; END IF;
 h:=q->>'host'; p:=q->>'path';
 IF t.provider='Alpaca' THEN
  IF h NOT IN ('data.alpaca.markets','paper-api.alpaca.markets','api.alpaca.markets') THEN RETURN false; END IF;
  token_key:='page_token';
  IF t.kind='alpaca_reference' THEN
   IF h NOT IN ('paper-api.alpaca.markets','api.alpaca.markets') OR p<>('/v2/assets/'||replace(split_part(syms,',',1),'/','%2F')) THEN RETURN false; END IF;
  ELSIF t.kind='alpaca_option_contracts' THEN
   IF h NOT IN ('paper-api.alpaca.markets','api.alpaca.markets') OR p<>'/v2/options/contracts' OR q#>>'{params,underlying_symbols}' IS DISTINCT FROM syms OR q#>>'{params,status}' IS DISTINCT FROM t.scope->>'status' THEN RETURN false; END IF;
  ELSE
   IF h<>'data.alpaca.markets' OR q#>>'{params,symbols}' IS DISTINCT FROM syms
    OR q#>>'{params,start}' IS DISTINCT FROM t.scope->>'start' OR q#>>'{params,end}' IS DISTINCT FROM t.scope->>'end' THEN RETURN false; END IF;
   IF t.kind='alpaca_stock_bars' AND (p<>'/v2/stocks/bars' OR q#>>'{params,feed}'<>'sip' OR q#>>'{params,timeframe}' IS DISTINCT FROM COALESCE(t.scope->>'timeframe','1Min') OR q#>>'{params,adjustment}' IS DISTINCT FROM COALESCE(t.scope->>'adjustment','raw')) THEN RETURN false; END IF;
   IF t.kind='alpaca_option_bars' AND (p<>'/v1beta1/options/bars' OR q#>>'{params,timeframe}'<>'1Day') THEN RETURN false; END IF;
   IF t.kind='alpaca_news' AND p<>'/v1beta1/news' THEN RETURN false; END IF;
   IF t.kind='alpaca_actions' AND p<>'/v1/corporate-actions' THEN RETURN false; END IF;
  END IF;
 ELSE
  IF h<>'api.massive.com' THEN RETURN false; END IF;
  token_key:='cursor';
  IF t.kind='massive_reference' THEN
   IF p<>('/v3/reference/tickers/'||replace(split_part(syms,',',1),'/','%2F')) OR q#>>'{params,date}' IS DISTINCT FROM t.scope->>'asof' THEN RETURN false; END IF;
  ELSIF t.kind='massive_news' THEN
   IF p<>'/v2/reference/news' OR q#>>'{params,ticker}' IS DISTINCT FROM syms OR q#>>'{params,published_utc.gte}' IS DISTINCT FROM t.scope->>'start' OR q#>>'{params,published_utc.lte}' IS DISTINCT FROM t.scope->>'end' THEN RETURN false; END IF;
  ELSE
   IF q#>>'{params,ticker.any_of}' IS DISTINCT FROM syms THEN RETURN false; END IF;
   IF t.kind='massive_dividends' AND p<>'/stocks/v1/dividends' THEN RETURN false; END IF;
   IF t.kind='massive_splits' AND p<>'/stocks/v1/splits' THEN RETURN false; END IF;
   IF t.kind='massive_short_volume' AND (p<>'/stocks/v1/short-volume' OR q#>>'{params,date.gte}' IS DISTINCT FROM t.scope->>'start' OR q#>>'{params,date.lte}' IS DISTINCT FROM t.scope->>'end') THEN RETURN false; END IF;
   IF t.kind='massive_short_interest' AND (p<>'/stocks/v1/short-interest' OR q#>>'{params,settlement_date.gte}' IS DISTINCT FROM t.scope->>'start' OR q#>>'{params,settlement_date.lte}' IS DISTINCT FROM t.scope->>'end') THEN RETURN false; END IF;
  END IF;
 END IF;
 IF q->'params'->>token_key IS DISTINCT FROM t.cursor#>>'{}' THEN RETURN false; END IF;
 RETURN true;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_uri_component_v2(v text) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
DECLARE i integer:=1; b bytea:=''::bytea; c text;
BEGIN
 WHILE i<=length(v) LOOP
  c:=substr(v,i,1);
  IF c='%' THEN
   IF substr(v,i+1,2)!~'^[0-9A-Fa-f]{2}$' THEN RAISE EXCEPTION 'Invalid source cursor encoding'; END IF;
   b:=b||decode(substr(v,i+1,2),'hex');i:=i+3;
  ELSE b:=b||convert_to(CASE WHEN c='+' THEN ' ' ELSE c END,'UTF8');i:=i+1;
  END IF;
 END LOOP;
 RETURN convert_from(b,'UTF8');
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_dispatch_v2(p_operation text,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; p astra_ingestion_v1.backfill_pages_v2;
 v_now timestamptz:=clock_timestamp(); v_claim jsonb; v_owner text; v_lease int; v_supported jsonb; v_result jsonb;
 v_count int; v_hash text; v_raw text; v_cursor jsonb; v_state text; v_delay double precision; v_retry boolean; v_page int;
 v_parsed jsonb; v_source_rows jsonb; v_submitted_rows jsonb; v_source_cursor text; v_source_url text;
 v_members jsonb; v_contracts jsonb; v_symbols jsonb; v_child_scope jsonb; v_child_id text; v_record jsonb; v_group int; v_kind text;
 v_after_task text; v_after_page int; v_limit int; v_pages jsonb; v_last jsonb; v_more boolean;
 v_dependency record; v_capability_revision text; v_dependency_code text;
 v_not_before double precision; v_epoch double precision;
BEGIN
 IF p_operation='backfill_status' THEN
  SELECT COALESCE(jsonb_agg(x),'[]') INTO v_result FROM (
   SELECT to_jsonb(r) || jsonb_build_object(
    'members',(SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=r.id),
    'tasks',(SELECT COALESCE(jsonb_agg(z),'[]') FROM (SELECT family,kind,provider,status,count(*) tasks,sum(records_committed) records,max(last_progress_at) last_progress_at
       FROM astra_ingestion_v1.backfill_tasks_v2 WHERE run_id=r.id GROUP BY family,kind,provider,status) z),
    'unsupported_pending_kinds',(SELECT COALESCE(jsonb_agg(DISTINCT st.kind),'[]') FROM astra_ingestion_v1.backfill_tasks_v2 st WHERE st.run_id=r.id AND st.status IN ('PENDING','RETRY_WAIT')
       AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_workers_v2 w WHERE w.observed_at>clock_timestamp()-interval '10 minutes' AND w.supported_kinds ? st.kind)),
    'provider_dependencies',(SELECT COALESCE(jsonb_agg(to_jsonb(d)),'[]') FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=r.id),
    'next_retry_at',(SELECT min(next_retry_at) FROM astra_ingestion_v1.backfill_tasks_v2 st WHERE st.run_id=r.id AND status='RETRY_WAIT')) AS x
   FROM astra_ingestion_v1.backfill_runs_v2 r WHERE p_payload->>'run_id' IS NULL OR r.id=p_payload->>'run_id' ORDER BY r.created_at DESC LIMIT 20
  ) q;
  RETURN jsonb_build_object('runs',v_result,'observed_at',v_now);
 ELSIF p_operation='backfill_claim' THEN
  v_owner:=p_payload->>'worker_id'; v_supported:=p_payload->'supported_kinds';
  IF v_owner IS NULL OR v_owner !~ '^[A-Za-z0-9_.:-]{1,160}$' OR jsonb_typeof(v_supported) IS DISTINCT FROM 'array' OR jsonb_array_length(v_supported)>32
   OR COALESCE(length(p_payload->>'source_revision'),0) NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid bounded worker capabilities'; END IF;
  v_lease:=GREATEST(30,LEAST(COALESCE((p_payload->>'lease_seconds')::int,120),300));
  v_capability_revision:=COALESCE(p_payload->>'capability_revision',encode(sha256(convert_to(p_payload->>'source_revision'||':'||astra_ingestion_v1.rpc_canonical(v_supported),'UTF8')),'hex'));
  IF length(v_capability_revision) NOT BETWEEN 1 AND 160 THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid capability revision'; END IF;
  INSERT INTO astra_ingestion_v1.backfill_workers_v2(worker_id,source_revision,supported_kinds,capability_revision,observed_at)
   VALUES(v_owner,p_payload->>'source_revision',v_supported,v_capability_revision,v_now) ON CONFLICT(worker_id) DO UPDATE SET source_revision=EXCLUDED.source_revision,supported_kinds=EXCLUDED.supported_kinds,capability_revision=EXCLUDED.capability_revision,observed_at=v_now;
  -- Missing runtime configuration is one durable provider dependency; it does
  -- not consume attempts or request reservations for every waiting task.
  FOR v_dependency IN
   SELECT rr.id run_id,pp.provider FROM astra_ingestion_v1.backfill_runs_v2 rr CROSS JOIN (VALUES('Alpaca'),('Massive')) pp(provider)
   WHERE rr.status='ACTIVE' AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 st WHERE st.run_id=rr.id AND st.provider=pp.provider AND st.status IN ('PENDING','RETRY_WAIT','BLOCKED_EXTERNAL'))
  LOOP
   IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_workers_v2 w WHERE w.observed_at>v_now-interval '10 minutes'
    AND EXISTS(SELECT 1 FROM jsonb_array_elements_text(w.supported_kinds) k WHERE k LIKE lower(v_dependency.provider)||'_%')) THEN
    INSERT INTO astra_ingestion_v1.backfill_provider_dependencies_v2(run_id,provider,dependency,state,code,evidence)
     VALUES(v_dependency.run_id,v_dependency.provider,upper(v_dependency.provider)||'_WORKER_CREDENTIAL','BLOCKED_EXTERNAL','RUNTIME_CAPABILITY_UNAVAILABLE',jsonb_build_object('observed_at',v_now,'reason','No recently registered worker advertises this provider capability'))
     ON CONFLICT(run_id,provider) DO UPDATE SET state='BLOCKED_EXTERNAL',code=EXCLUDED.code,evidence=EXCLUDED.evidence,observed_at=v_now,resolved_at=NULL
      WHERE astra_ingestion_v1.backfill_provider_dependencies_v2.state='AVAILABLE';
   ELSE
    UPDATE astra_ingestion_v1.backfill_provider_dependencies_v2 d SET state='AVAILABLE',resolved_at=v_now,observed_at=v_now,
      evidence=d.evidence||jsonb_build_object('resolution','Changed configured worker capability observed','resolved_at',v_now)
     WHERE d.run_id=v_dependency.run_id AND d.provider=v_dependency.provider AND d.state='BLOCKED_EXTERNAL'
      AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_workers_v2 w WHERE w.observed_at>v_now-interval '10 minutes'
       AND (d.code='RUNTIME_CAPABILITY_UNAVAILABLE' OR w.worker_id IS DISTINCT FROM d.blocked_worker OR w.capability_revision IS DISTINCT FROM d.blocked_revision)
       AND EXISTS(SELECT 1 FROM jsonb_array_elements_text(w.supported_kinds) k WHERE k LIKE lower(d.provider)||'_%'));
    UPDATE astra_ingestion_v1.backfill_tasks_v2 st SET status='PENDING',next_retry_at=v_now,error_code=NULL,error_message=NULL
     WHERE st.run_id=v_dependency.run_id AND st.provider=v_dependency.provider AND st.status='BLOCKED_EXTERNAL' AND st.error_code='MISSING_PROVIDER_CREDENTIAL'
      AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=st.run_id AND d.provider=st.provider AND d.state='AVAILABLE');
   END IF;
  END LOOP;
  -- Exhaustion stays an operational failure, never a provider-gap terminal result.
  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status='OPERATIONAL_ERROR',owner=NULL,lease_until=NULL,error_code='ATTEMPT_BUDGET_EXHAUSTED',error_message='Eight bounded attempts exhausted; implementation recovery must diagnose before requeue'
   WHERE status='RUNNING' AND lease_until<=v_now AND page_attempts>=8;
  SELECT q.* INTO t FROM astra_ingestion_v1.backfill_tasks_v2 q JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=q.run_id
   WHERE rr.status='ACTIVE' AND rr.fence=q.run_fence AND q.kind IN (SELECT jsonb_array_elements_text(v_supported))
    AND q.next_retry_at<=v_now AND q.page_attempts<8
    AND (q.status IN ('PENDING','RETRY_WAIT') OR (q.status='RUNNING' AND q.lease_until<=v_now))
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=q.run_id AND d.provider=q.provider AND d.state='BLOCKED_EXTERNAL')
    AND NOT EXISTS(SELECT 1 FROM unnest(q.dependencies) dep LEFT JOIN astra_ingestion_v1.backfill_tasks_v2 d ON d.id=dep
      WHERE d.id IS NULL OR d.run_id<>q.run_id OR d.status NOT IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED'))
    AND (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=q.run_id)=3000
   ORDER BY q.priority,q.next_retry_at,q.created_at,q.id LIMIT 1 FOR UPDATE OF q;
  IF NOT FOUND THEN RETURN NULL; END IF;
  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status='RUNNING',owner=v_owner,generation=generation+1,lease_until=v_now+make_interval(secs=>v_lease),attempt_deadline=v_now+interval '5 minutes',
    attempts=attempts+1,page_attempts=page_attempts+1,reserved_generation=NULL,reserved_page_no=NULL,reserved_at=NULL,source_revision=p_payload->>'source_revision'
   WHERE id=t.id RETURNING * INTO t;
  RETURN to_jsonb(t);
 END IF;
 v_claim:=p_payload->'claim';
 -- Readback never replays a mutation or requires a live lease; exact claim/run binding still applies.
 IF p_operation='backfill_verify' THEN
  SELECT * INTO t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=v_claim->>'id' AND run_id=v_claim->>'run_id';
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='AI004',MESSAGE='Replacement task not found'; END IF;
  v_page:=COALESCE((p_payload->>'page_no')::int,t.page_no-1);
  SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=t.id AND page_no=v_page;
  IF NOT FOUND THEN RETURN jsonb_build_object('state','not_committed','task_id',t.id,'page_no',v_page,'task_status',t.status,'next_page_no',t.page_no); END IF;
  RETURN jsonb_build_object('state','committed','task_id',t.id,'page_no',p.page_no,'body_sha256',p.body_sha256,
    'readback_sha256',encode(sha256(convert_to(p.raw_body,'UTF8')),'hex'),'records_sha256',p.records_sha256,'record_count',p.record_count,
    'next_cursor',p.cursor_out,'next_page_no',t.page_no,'task_status',t.status,'raw_body',p.raw_body,'request',p.request,'quality',p.quality,'adapter_version',p.adapter_version);
 END IF;
 -- A duplicate after a lost HTTP acknowledgement is an immutable matching-commit receipt, not a second write.
 IF p_operation='backfill_commit' AND v_claim->>'id' IS NOT NULL THEN
  SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=v_claim->>'id' AND page_no=(v_claim->>'page_no')::int;
  IF FOUND THEN
   IF p.run_id IS DISTINCT FROM v_claim->>'run_id' OR p.generation::text IS DISTINCT FROM v_claim->>'generation'
    OR p.run_fence::text IS DISTINCT FROM v_claim->>'run_fence' OR p.body_sha256 IS DISTINCT FROM p_payload->>'body_sha256' THEN
     RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Existing replacement receipt differs from original commit'; END IF;
   RETURN jsonb_build_object('state','already_committed','task_id',p.task_id,'page_no',p.page_no,'body_sha256',p.body_sha256,'record_count',p.record_count,'next_cursor',p.cursor_out);
  END IF;
 END IF;
 t:=astra_ingestion_v1.backfill_owned_v2(v_claim);
 IF p_operation='backfill_work' THEN RETURN to_jsonb(t);
 ELSIF p_operation='backfill_reserve' THEN
  IF t.reserved_generation=t.generation AND t.reserved_page_no=t.page_no THEN RETURN jsonb_build_object('state','already_reserved','task_id',t.id,'page_no',t.page_no); END IF;
  IF t.provider IN ('Alpaca','Massive') THEN
   v_epoch:=extract(epoch FROM v_now);
   SELECT next_request_at INTO STRICT v_not_before FROM astra_ingestion_v1.source_limits WHERE id=lower(t.provider) FOR UPDATE;
   IF v_not_before>v_epoch THEN
    UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status='RETRY_WAIT',owner=NULL,lease_until=NULL,next_retry_at=to_timestamp(v_not_before),page_attempts=GREATEST(0,page_attempts-1) WHERE id=t.id;
    RETURN jsonb_build_object('state','request_deferred','task_id',t.id,'page_no',t.page_no,'next_retry_at',to_timestamp(v_not_before));
   END IF;
   UPDATE astra_ingestion_v1.source_limits SET next_request_at=v_epoch+CASE WHEN t.provider='Alpaca' THEN 2 ELSE 12 END WHERE id=lower(t.provider);
  END IF;
  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET reserved_generation=generation,reserved_page_no=page_no,reserved_at=v_now,
    requests_reserved=requests_reserved+CASE WHEN provider IN ('Alpaca','Massive') THEN 1 ELSE 0 END WHERE id=t.id;
  UPDATE astra_ingestion_v1.backfill_runs_v2 SET requests_reserved=requests_reserved+CASE WHEN t.provider IN ('Alpaca','Massive') THEN 1 ELSE 0 END WHERE id=t.run_id;
  RETURN jsonb_build_object('state','reserved','task_id',t.id,'page_no',t.page_no,'query_scope',t.scope,'cursor',t.cursor,'lease_until',t.lease_until);
 ELSIF p_operation='backfill_defer' THEN
  v_retry:=COALESCE((p_payload->>'retryable')::boolean,false);
  IF length(COALESCE(p_payload->>'code','')) NOT BETWEEN 1 AND 120 OR octet_length(COALESCE(p_payload->'evidence','{}')::text)>4194304 THEN
    RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid bounded failure evidence'; END IF;
  v_delay:=GREATEST(2,COALESCE((p_payload->>'retry_after')::double precision,0),LEAST(3600,power(2,GREATEST(1,t.page_attempts))));
  IF v_delay IN ('Infinity'::double precision,'-Infinity'::double precision,'NaN'::double precision) OR extract(epoch FROM v_now)+v_delay>253402300799 THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retry-After must be a finite representable interval'; END IF;
  v_state:=CASE WHEN v_retry AND t.page_attempts<8 THEN 'RETRY_WAIT'
    WHEN p_payload->>'code' IN ('BLOCKED_EXTERNAL','AUTHENTICATION_FAILED','MISSING_CREDENTIAL','MISSING_PROVIDER_CREDENTIAL','PROVIDER_FORBIDDEN') THEN 'BLOCKED_EXTERNAL' ELSE 'OPERATIONAL_ERROR' END;
  IF t.provider IN ('Alpaca','Massive') AND (p_payload#>>'{evidence,http_status}'='429' OR p_payload->>'code' IN ('SOURCE_RATE_LIMIT','PROVIDER_RATE_LIMIT')) THEN
   UPDATE astra_ingestion_v1.source_limits SET next_request_at=GREATEST(next_request_at,extract(epoch FROM v_now)+v_delay) WHERE id=lower(t.provider);
  END IF;
  v_dependency_code:=p_payload#>>'{evidence,dependency}';
  IF t.provider IN ('Alpaca','Massive') AND v_dependency_code=upper(t.provider)||'_WORKER_CREDENTIAL' THEN
   v_state:='BLOCKED_EXTERNAL';
   SELECT capability_revision INTO v_capability_revision FROM astra_ingestion_v1.backfill_workers_v2 WHERE worker_id=t.owner;
   INSERT INTO astra_ingestion_v1.backfill_provider_dependencies_v2(run_id,provider,dependency,state,code,evidence,blocked_worker,blocked_revision)
    VALUES(t.run_id,t.provider,v_dependency_code,v_state,'MISSING_PROVIDER_CREDENTIAL',COALESCE(p_payload->'evidence','{}'),t.owner,v_capability_revision)
    ON CONFLICT(run_id,provider) DO UPDATE SET state=EXCLUDED.state,code=EXCLUDED.code,evidence=EXCLUDED.evidence,blocked_worker=EXCLUDED.blocked_worker,blocked_revision=EXCLUDED.blocked_revision,observed_at=v_now,resolved_at=NULL;
  END IF;
  INSERT INTO astra_ingestion_v1.backfill_exceptions_v2(run_id,task_id,page_no,generation,state,code,message,evidence,next_retry_at)
   VALUES(t.run_id,t.id,t.page_no,t.generation,v_state,p_payload->>'code',left(COALESCE(p_payload->>'message','Operation failed'),1000),COALESCE(p_payload->'evidence','{}'),CASE WHEN v_state='RETRY_WAIT' THEN v_now+make_interval(secs=>v_delay) END);
  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status=v_state,owner=NULL,lease_until=NULL,next_retry_at=v_now+make_interval(secs=>v_delay),error_code=CASE WHEN v_dependency_code=upper(t.provider)||'_WORKER_CREDENTIAL' THEN 'MISSING_PROVIDER_CREDENTIAL' ELSE p_payload->>'code' END,error_message=left(p_payload->>'message',1000) WHERE id=t.id;
  RETURN jsonb_build_object('state',v_state,'task_id',t.id,'next_retry_at',CASE WHEN v_state='RETRY_WAIT' THEN v_now+make_interval(secs=>v_delay) END,'page_attempts',t.page_attempts);
 ELSIF p_operation='backfill_material' THEN
  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET lease_until=LEAST(attempt_deadline,v_now+interval '120 seconds') WHERE id=t.id;
  v_after_task:=COALESCE(p_payload#>>'{after,task_id}',''); v_after_page:=COALESCE((p_payload#>>'{after,page_no}')::int,-1); v_limit:=GREATEST(1,LEAST(COALESCE((p_payload->>'limit')::int,2),4));
  SELECT COALESCE(jsonb_agg(x ORDER BY task_id,page_no),'[]') INTO v_pages FROM (
   SELECT pg.task_id,pg.page_no,jsonb_build_object('id',d.id,'kind',d.kind,'family',d.family,'provider',d.provider,'scope',d.scope,'cursor',pg.cursor_in) AS task,
    pg.raw_body,pg.body_sha256,pg.request,pg.record_count,pg.quality,pg.adapter_version
   FROM astra_ingestion_v1.backfill_pages_v2 pg JOIN astra_ingestion_v1.backfill_tasks_v2 d ON d.id=pg.task_id
   WHERE pg.task_id=ANY(t.dependencies) AND pg.run_id=t.run_id AND (pg.task_id,pg.page_no)>(v_after_task,v_after_page)
   ORDER BY pg.task_id,pg.page_no LIMIT v_limit
  ) x;
  IF jsonb_array_length(v_pages)>0 THEN v_last:=v_pages->(jsonb_array_length(v_pages)-1); v_after_task:=v_last->>'task_id';v_after_page:=(v_last->>'page_no')::int; END IF;
  SELECT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_pages_v2 pg WHERE pg.task_id=ANY(t.dependencies) AND pg.run_id=t.run_id AND (pg.task_id,pg.page_no)>(v_after_task,v_after_page)) INTO v_more;
  RETURN jsonb_build_object('pages',v_pages,'next_after',CASE WHEN v_more THEN jsonb_build_object('task_id',v_after_task,'page_no',v_after_page) END,'complete',NOT v_more,
    'dependency_states',(SELECT COALESCE(jsonb_agg(jsonb_build_object('id',id,'status',status,'error_code',error_code)),'[]') FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=ANY(t.dependencies)));
 ELSIF p_operation<>'backfill_commit' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Unsupported replacement operation';
 END IF;
 IF t.provider IN ('Alpaca','Massive') AND (t.reserved_generation IS DISTINCT FROM t.generation OR t.reserved_page_no IS DISTINCT FROM t.page_no) THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Page request must be durably reserved before dispatch'; END IF;
 v_raw:=p_payload->>'raw_body'; v_hash:=encode(sha256(convert_to(v_raw,'UTF8')),'hex');
 IF v_raw IS NULL OR octet_length(v_raw)>4194304 OR v_hash IS DISTINCT FROM p_payload->>'body_sha256'
  OR jsonb_typeof(p_payload->'records') IS DISTINCT FROM 'array' OR jsonb_array_length(p_payload->'records')>100000
  OR (p_payload->>'http_status')::int<>200 OR NOT astra_ingestion_v1.backfill_request_valid_v2(t,p_payload->'request')
  OR length(COALESCE(p_payload->>'adapter_version','')) NOT BETWEEN 1 AND 100
 THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Replacement source digest, request scope or page shape is invalid'; END IF;
 PERFORM astra_ingestion_v1.rpc_json_unique(v_raw::json);
 v_parsed:=v_raw::jsonb;
 IF t.kind IN ('alpaca_stock_bars','alpaca_option_bars') THEN
   SELECT COALESCE(jsonb_agg(b.value ORDER BY b.value::text),'[]') INTO v_source_rows
     FROM jsonb_each(COALESCE(NULLIF(v_parsed->'bars','null'::jsonb),'{}')) s CROSS JOIN LATERAL jsonb_array_elements(s.value) b;
 ELSIF t.kind='alpaca_reference' THEN v_source_rows:=jsonb_build_array(v_parsed);
 ELSIF t.kind='alpaca_option_contracts' THEN
   SELECT COALESCE(jsonb_agg(value ORDER BY value::text),'[]') INTO v_source_rows FROM jsonb_array_elements(COALESCE(NULLIF(v_parsed->'option_contracts','null'::jsonb),'[]'));
 ELSIF t.kind='alpaca_news' THEN
   SELECT COALESCE(jsonb_agg(value ORDER BY value::text),'[]') INTO v_source_rows FROM jsonb_array_elements(COALESCE(NULLIF(v_parsed->'news','null'::jsonb),'[]'));
 ELSIF t.kind='alpaca_actions' THEN
   SELECT COALESCE(jsonb_agg(b.value ORDER BY b.value::text),'[]') INTO v_source_rows
     FROM jsonb_each(COALESCE(NULLIF(v_parsed->'corporate_actions','null'::jsonb),'{}')) s CROSS JOIN LATERAL jsonb_array_elements(s.value) b;
 ELSIF t.provider='Massive' THEN
   SELECT COALESCE(jsonb_agg(value ORDER BY value::text),'[]') INTO v_source_rows FROM jsonb_array_elements(
      CASE WHEN jsonb_typeof(v_parsed->'results')='object' THEN jsonb_build_array(v_parsed->'results') ELSE COALESCE(NULLIF(v_parsed->'results','null'::jsonb),'[]') END);
 ELSE
   v_source_rows:=COALESCE(v_parsed->'rows',v_parsed->'records');
 END IF;
 IF t.provider IN ('Alpaca','Massive') THEN
   SELECT COALESCE(jsonb_agg(value->'source' ORDER BY (value->'source')::text),'[]') INTO v_submitted_rows FROM jsonb_array_elements(p_payload->'records');
 ELSE v_submitted_rows:=p_payload->'records'; END IF;
 IF v_source_rows IS DISTINCT FROM v_submitted_rows THEN
   RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Normalized source rows do not match the original retained page'; END IF;
 v_count:=jsonb_array_length(p_payload->'records'); v_cursor:=NULLIF(p_payload->'next_cursor','null'::jsonb);
 IF t.provider='Alpaca' AND t.kind<>'alpaca_reference' THEN
  IF NOT (v_parsed ? 'next_page_token') THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Original source pagination field is missing'; END IF;
  IF NULLIF(v_parsed->'next_page_token','null'::jsonb) IS DISTINCT FROM v_cursor THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained source continuation differs from the proposed checkpoint'; END IF;
 ELSIF t.provider='Massive' THEN
  v_source_url:=v_parsed->>'next_url';v_source_cursor:=NULL;
  IF v_source_url IS NOT NULL THEN
   IF strpos(v_source_url,'https://api.massive.com'||(p_payload#>>'{request,path}')||'?')<>1
    AND strpos(v_source_url,'https://api.polygon.io'||(p_payload#>>'{request,path}')||'?')<>1 THEN
     RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Untrusted provider pagination origin or path'; END IF;
   SELECT astra_ingestion_v1.backfill_uri_component_v2(substr(kv,strpos(kv,'=')+1)) INTO v_source_cursor
    FROM unnest(string_to_array(split_part(v_source_url,'?',2),'&')) kv WHERE split_part(kv,'=',1)='cursor';
   IF v_source_cursor IS NULL THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Source continuation cursor missing'; END IF;
  END IF;
  IF v_source_cursor IS DISTINCT FROM v_cursor#>>'{}' THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained source continuation differs from the proposed checkpoint'; END IF;
 END IF;
 IF v_cursor IS NOT NULL AND (jsonb_typeof(v_cursor)<>'string' OR length(v_cursor#>>'{}') NOT BETWEEN 1 AND 8192 OR v_cursor IS NOT DISTINCT FROM t.cursor
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=t.id AND cursor_in=v_cursor)) THEN
   RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Replacement source pagination token is invalid or repeated'; END IF;
 v_state:=CASE WHEN v_cursor IS NOT NULL THEN 'PENDING' WHEN t.records_committed+v_count=0 THEN 'NO_DATA_RETURNED' ELSE 'INGESTED' END;
 IF v_cursor IS NULL AND p_payload->>'terminal_state' IN ('IDENTITY_OR_QUALITY_UNRESOLVED','NOT_APPLICABLE','PROVIDER_LIMITATION') THEN
   IF COALESCE(jsonb_array_length(p_payload->'quality'),0)=0 THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='A terminal limitation requires retained evidence'; END IF;
   v_state:=p_payload->>'terminal_state';
 END IF;
 IF v_cursor IS NULL AND jsonb_array_length(COALESCE(p_payload->'quality','[]'))>0 AND v_state='INGESTED' THEN v_state:='IDENTITY_OR_QUALITY_UNRESOLVED'; END IF;
 INSERT INTO astra_ingestion_v1.backfill_pages_v2(task_id,page_no,run_id,generation,run_fence,provider,cursor_in,cursor_out,request,http_status,request_id,fetched_at,raw_body,body_sha256,records_sha256,record_count,source_bytes,quality,headers,adapter_version)
 VALUES(t.id,t.page_no,t.run_id,t.generation,t.run_fence,t.provider,t.cursor,v_cursor,p_payload->'request',200,left(p_payload->>'request_id',256),(p_payload->>'fetched_at')::timestamptz,v_raw,v_hash,
  encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(p_payload->'records'),'UTF8')),'hex'),v_count,octet_length(v_raw),COALESCE(p_payload->'quality','[]'),COALESCE(p_payload->'headers','{}'),p_payload->>'adapter_version');
 -- Historical option enumeration creates executable daily-bar successors atomically.
 IF t.kind='alpaca_option_contracts' THEN
  FOR v_symbols,v_group IN
   SELECT jsonb_agg(symbol ORDER BY symbol),grp FROM (
    SELECT symbol,((row_number() OVER(ORDER BY symbol)-1)/100)::int grp FROM (
     SELECT DISTINCT value->>'symbol' symbol FROM jsonb_array_elements(p_payload->'records')
     WHERE value->>'symbol' ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$'
      AND (t.scope->'symbols') ? (value->>'underlying_symbol')
    ) z
   ) z GROUP BY grp
  LOOP
   v_child_scope:=jsonb_build_object('symbols',v_symbols,'member_ids',t.scope->'member_ids','start','2025-09-01T00:00:00-04:00','end','2026-07-31T23:59:59-04:00','identity_status','PROVIDER_CONTRACT_UNDERLYING_LINK','enumeration_parent',t.id);
   v_child_id:='backfill-options-'||encode(sha256(convert_to(t.run_id||':'||astra_ingestion_v1.rpc_canonical(v_child_scope),'UTF8')),'hex');
   INSERT INTO astra_ingestion_v1.backfill_tasks_v2(id,run_id,family,provider,kind,scope,priority,run_fence)
   VALUES(v_child_id,t.run_id,'CTX02','Alpaca','alpaca_option_bars',v_child_scope,t.priority+1,t.run_fence) ON CONFLICT(id) DO NOTHING;
  END LOOP;
 END IF;
 PERFORM astra_ingestion_v1.backfill_owned_v2(v_claim);
 UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status=v_state,cursor=v_cursor,page_no=page_no+1,records_committed=records_committed+v_count,
  owner=NULL,lease_until=NULL,page_attempts=0,last_progress_at=v_now,next_retry_at=v_now,error_code=NULL,error_message=NULL WHERE id=t.id;
 UPDATE astra_ingestion_v1.backfill_runs_v2 SET pages_committed=pages_committed+1,records_committed=records_committed+v_count,source_bytes=source_bytes+octet_length(v_raw),last_progress_at=v_now WHERE id=t.run_id;
 IF v_state IN ('IDENTITY_OR_QUALITY_UNRESOLVED','NOT_APPLICABLE','PROVIDER_LIMITATION') THEN
  INSERT INTO astra_ingestion_v1.backfill_exceptions_v2(run_id,task_id,page_no,generation,state,code,message,evidence)
   VALUES(t.run_id,t.id,t.page_no,t.generation,v_state,v_state,'Retained source page has documented per-unit limitations',COALESCE(p_payload->'quality','[]'));
 END IF;
 RETURN jsonb_build_object('state','page_committed','task_id',t.id,'page_no',t.page_no,'task_status',v_state,'record_count',v_count,'body_sha256',v_hash,'next_cursor',v_cursor);
END $$;

-- Private role permissions; gateway roles receive no direct table/helper access.
DO $acl$
DECLARE t text; f record; g record;
BEGIN
 FOREACH t IN ARRAY ARRAY['backfill_runs_v2','backfill_members_v2','backfill_tasks_v2','backfill_pages_v2','backfill_exceptions_v2','backfill_workers_v2','backfill_provider_dependencies_v2'] LOOP
  EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON astra_ingestion_v1.%I FROM PUBLIC',t);
  FOR g IN SELECT DISTINCT r.rolname FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles r ON r.oid=a.grantee
   WHERE c.oid=to_regclass('astra_ingestion_v1.'||t) AND a.grantee<>c.relowner LOOP
   EXECUTE format('REVOKE ALL ON astra_ingestion_v1.%I FROM %I',t,g.rolname);
  END LOOP;
  EXECUTE format('CREATE POLICY backfill_runtime_read ON astra_ingestion_v1.%I FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true)',t);
 END LOOP;
 FOR f IN SELECT p.oid,n.nspname,p.proname,pg_get_function_identity_arguments(p.oid) args,p.proowner,p.proacl FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='astra_ingestion_v1' AND p.proname LIKE 'backfill_%_v2' LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %I.%I(%s) FROM PUBLIC',f.nspname,f.proname,f.args);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(f.proacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>f.proowner LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION %I.%I(%s) FROM %I',f.nspname,f.proname,f.args,g.rolname);
  END LOOP;
 END LOOP;
END $acl$;
GRANT SELECT ON astra_ingestion_v1.backfill_runs_v2,astra_ingestion_v1.backfill_members_v2,astra_ingestion_v1.backfill_tasks_v2,astra_ingestion_v1.backfill_pages_v2,astra_ingestion_v1.backfill_exceptions_v2,astra_ingestion_v1.backfill_workers_v2,astra_ingestion_v1.backfill_provider_dependencies_v2 TO astra_ingestion_rpc_owner_v1;
GRANT UPDATE ON astra_ingestion_v1.backfill_runs_v2,astra_ingestion_v1.backfill_tasks_v2 TO astra_ingestion_rpc_owner_v1;
GRANT INSERT ON astra_ingestion_v1.backfill_tasks_v2,astra_ingestion_v1.backfill_pages_v2,astra_ingestion_v1.backfill_exceptions_v2 TO astra_ingestion_rpc_owner_v1;
GRANT INSERT,UPDATE ON astra_ingestion_v1.backfill_workers_v2 TO astra_ingestion_rpc_owner_v1;
GRANT INSERT,UPDATE ON astra_ingestion_v1.backfill_provider_dependencies_v2 TO astra_ingestion_rpc_owner_v1;
GRANT USAGE ON SEQUENCE astra_ingestion_v1.backfill_exceptions_v2_id_seq TO astra_ingestion_rpc_owner_v1;
CREATE POLICY backfill_runtime_update ON astra_ingestion_v1.backfill_runs_v2 FOR UPDATE TO astra_ingestion_rpc_owner_v1 USING(true) WITH CHECK(true);
CREATE POLICY backfill_runtime_update ON astra_ingestion_v1.backfill_tasks_v2 FOR UPDATE TO astra_ingestion_rpc_owner_v1 USING(true) WITH CHECK(true);
CREATE POLICY backfill_runtime_insert ON astra_ingestion_v1.backfill_tasks_v2 FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true);
CREATE POLICY backfill_runtime_insert ON astra_ingestion_v1.backfill_pages_v2 FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true);
CREATE POLICY backfill_runtime_insert ON astra_ingestion_v1.backfill_exceptions_v2 FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true);
CREATE POLICY backfill_runtime_insert ON astra_ingestion_v1.backfill_workers_v2 FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true);
CREATE POLICY backfill_runtime_update ON astra_ingestion_v1.backfill_workers_v2 FOR UPDATE TO astra_ingestion_rpc_owner_v1 USING(true) WITH CHECK(true);
CREATE POLICY backfill_runtime_insert ON astra_ingestion_v1.backfill_provider_dependencies_v2 FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true);
CREATE POLICY backfill_runtime_update ON astra_ingestion_v1.backfill_provider_dependencies_v2 FOR UPDATE TO astra_ingestion_rpc_owner_v1 USING(true) WITH CHECK(true);
GRANT EXECUTE ON FUNCTION astra_ingestion_v1.backfill_dispatch_v2(text,jsonb),astra_ingestion_v1.backfill_owned_v2(jsonb),astra_ingestion_v1.backfill_request_valid_v2(astra_ingestion_v1.backfill_tasks_v2,jsonb),astra_ingestion_v1.backfill_uri_component_v2(text) TO astra_ingestion_rpc_owner_v1;

-- Extend, rather than fork, the already authenticated dispatcher and its lock.
DO $wire$
DECLARE d text; f text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_runtime_dispatch_v2')>0 THEN RAISE EXCEPTION 'Runtime dispatcher already extended'; END IF;
 IF strpos(d,$oldapi$p_operation IN ('list_jobs','get_job','submit_job','control_job')$oldapi$)=0
 OR strpos(d,$oldworker$p_operation IN ('claim_next','reserve_request','commit_page','verification_material','finish_verification','fail_claim')$oldworker$)=0 THEN
  RAISE EXCEPTION 'Existing capability allowlists differ; reconcile before extension'; END IF;
 d:=replace(d,$oldapi$p_operation IN ('list_jobs','get_job','submit_job','control_job')$oldapi$,$newapi$p_operation IN ('list_jobs','get_job','submit_job','control_job','backfill_status')$newapi$);
 d:=replace(d,$oldworker$p_operation IN ('claim_next','reserve_request','commit_page','verification_material','finish_verification','fail_claim')$oldworker$,$newworker$p_operation IN ('claim_next','reserve_request','commit_page','verification_material','finish_verification','fail_claim','backfill_status','backfill_claim','backfill_reserve','backfill_commit','backfill_defer','backfill_verify','backfill_material','backfill_work')$newworker$);
 d:=replace(d,'    CASE p_operation',$dispatch$
    -- backfill_runtime_dispatch_v2: follows capability authentication and shared transaction lock.
    IF p_operation LIKE 'backfill_%' THEN
      RETURN pg_catalog.jsonb_build_object('ok',true,'result',astra_ingestion_v1.backfill_dispatch_v2(p_operation,p_payload));
    END IF;
    CASE p_operation$dispatch$);
 EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_refresh(text,double precision)'::regprocedure) INTO STRICT f;
 f:=replace(f,$oldrefresh$IN ('paused','cancelled') THEN RETURN;$oldrefresh$,$newrefresh$IN ('paused','cancelled','SUPERSEDED_BY_SCOPE_CHANGE') THEN RETURN;$newrefresh$);
 EXECUTE f;
END $wire$;
-- Clear inherited default privileges on the only new identity sequence.
REVOKE ALL ON SEQUENCE astra_ingestion_v1.backfill_exceptions_v2_id_seq FROM PUBLIC;
DO $sequence_acl$
DECLARE g record;
BEGIN
 FOR g IN SELECT DISTINCT r.rolname FROM pg_class c
  CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles r ON r.oid=a.grantee
  WHERE c.oid='astra_ingestion_v1.backfill_exceptions_v2_id_seq'::regclass
   AND a.grantee<>c.relowner AND r.rolname<>'astra_ingestion_rpc_owner_v1'
 LOOP
  EXECUTE format('REVOKE ALL ON SEQUENCE astra_ingestion_v1.backfill_exceptions_v2_id_seq FROM %I',g.rolname);
 END LOOP;
END $sequence_acl$;
COMMIT;
