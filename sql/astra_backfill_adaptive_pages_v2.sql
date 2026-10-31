-- Bounded adaptive source pages. Execution size is separate from frozen scope.
-- No cursor, source receipt, successful page or cumulative attempt is reset.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

CREATE FUNCTION astra_ingestion_v1.backfill_page_limit_cap_v2(p_kind text) RETURNS integer
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT CASE WHEN p_kind IN('alpaca_stock_bars','alpaca_option_bars') THEN 10000
  WHEN p_kind='alpaca_news' THEN 50
  WHEN p_kind IN('alpaca_option_contracts','alpaca_actions','massive_news','massive_dividends','massive_splits','massive_short_volume','massive_short_interest') THEN 1000
  ELSE 1 END
$$;
-- Existing tasks are initialized lazily on claim, avoiding a million-row rewrite.
ALTER TABLE astra_ingestion_v1.backfill_tasks_v2 ADD COLUMN page_limit integer;
ALTER TABLE astra_ingestion_v1.backfill_tasks_v2 ADD CONSTRAINT backfill_page_limit_bounded_v2
 CHECK(page_limit IS NULL OR page_limit BETWEEN 1 AND astra_ingestion_v1.backfill_page_limit_cap_v2(kind)) NOT VALID;

CREATE FUNCTION astra_ingestion_v1.backfill_page_limit_guard_v2() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 NEW.page_limit:=LEAST(COALESCE(NEW.page_limit,CASE WHEN NEW.kind='massive_news' AND (NEW.cursor IS NULL OR NEW.cursor='null'::jsonb) THEN 100 ELSE astra_ingestion_v1.backfill_page_limit_cap_v2(NEW.kind) END),astra_ingestion_v1.backfill_page_limit_cap_v2(NEW.kind));
 IF NEW.page_limit<1 OR (TG_OP='UPDATE' AND OLD.page_limit IS NOT NULL AND NEW.page_limit>OLD.page_limit) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Execution page limit must remain positive and cannot silently increase'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER backfill_execution_page_limit_v2 BEFORE INSERT OR UPDATE OF page_limit,kind ON astra_ingestion_v1.backfill_tasks_v2
 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_page_limit_guard_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_adapt_page_v2(t astra_ingestion_v1.backfill_tasks_v2,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE e jsonb:=COALESCE(p_payload->'evidence','{}'); old_limit integer; new_limit integer;
 partial bytea; observed integer; can_reduce boolean; cursor_locked boolean;
BEGIN
 t:=astra_ingestion_v1.backfill_owned_v2(p_payload->'claim');
 old_limit:=COALESCE(t.page_limit,astra_ingestion_v1.backfill_page_limit_cap_v2(t.kind));
 IF t.provider NOT IN('Alpaca','Massive') OR t.reserved_generation IS DISTINCT FROM t.generation
  OR t.reserved_page_no IS DISTINCT FROM t.page_no THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Adaptive source sizing requires the actual reserved source attempt'; END IF;
 IF e->'response_complete' IS DISTINCT FROM 'false'::jsonb
  OR e->>'http_status' IS DISTINCT FROM '200'
  OR e->>'read_limit_bytes' IS DISTINCT FROM '3145728'
  OR COALESCE(e->>'observed_prefix_bytes','') !~ '^[0-9]{1,8}$'
  OR COALESCE(e->>'partial_body_bytes','') !~ '^[0-9]{1,5}$'
  OR COALESCE(e->>'observed_prefix_sha256','') !~ '^[0-9a-f]{64}$'
  OR COALESCE(e->>'partial_body_sha256','') !~ '^[0-9a-f]{64}$'
  OR length(COALESCE(e->>'partial_body_base64','')) NOT BETWEEN 1 AND 22000
  OR NOT astra_ingestion_v1.backfill_request_valid_v2(t,e->'request') THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Adaptive page failure needs a scoped incomplete-response receipt'; END IF;
 partial:=decode(e->>'partial_body_base64','base64');observed:=(e->>'observed_prefix_bytes')::int;
 IF observed<>3145729 OR octet_length(partial) NOT BETWEEN 1 AND 16384
  OR octet_length(partial)<>(e->>'partial_body_bytes')::int
  OR encode(sha256(partial),'hex')<>e->>'partial_body_sha256' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Adaptive response prefix length or digest differs'; END IF;
 -- Massive embeds query settings in its opaque cursor. Its documented cursor
 -- requests ignore every query argument except apiKey; changing limit there
 -- would repeat the same failure rather than perform a smaller request.
 cursor_locked:=t.provider='Massive' AND t.cursor IS NOT NULL AND t.cursor<>'null'::jsonb;
 can_reduce:=NOT cursor_locked AND astra_ingestion_v1.backfill_page_limit_cap_v2(t.kind)>1 AND old_limit>1 AND t.page_attempts<8;
 new_limit:=CASE WHEN can_reduce THEN GREATEST(1,old_limit/10) ELSE old_limit END;
 IF can_reduce THEN
  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET page_limit=new_limit WHERE id=t.id;
 END IF;
 e:=e||jsonb_build_object('adaptive_page_policy','REDUCE_TENFOLD_KEEP_CURSOR_V2',
  'previous_page_limit',old_limit,'next_page_limit',new_limit,'page_no_preserved',t.page_no,
  'cursor_preserved',t.cursor,'cumulative_attempts_preserved',t.attempts,
  'minimum_page_size_exhausted',old_limit=1,'attempt_budget_exhausted',t.page_attempts>=8,
  'cursor_controls_page_size',cursor_locked,
  'operational_dependency',CASE WHEN cursor_locked THEN 'MASSIVE_OPAQUE_CURSOR_PAGE_TOO_LARGE' ELSE NULL END,
  'source_response_incomplete',true,'not_provider_absence',true,
  'execution_action',CASE WHEN can_reduce THEN 'RETRY_SAME_CURSOR_SMALLER_PAGE' ELSE 'OPERATIONAL_REPAIR_REQUIRED' END);
 RETURN p_payload||jsonb_build_object('retryable',can_reduce,'evidence',e,
  'message',CASE WHEN can_reduce THEN 'Oversized source response; same cursor queued with smaller durable page limit'
   WHEN cursor_locked THEN 'Oversized Massive cursor page requires operational repair; provider ignores smaller limits on opaque cursor requests'
   ELSE 'Oversized source response remains an operational failure; bounded automatic reduction is exhausted' END);
END $$;

DO $wire$
DECLARE d text; v text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_request_valid_v2(astra_ingestion_v1.backfill_tasks_v2,jsonb)'::regprocedure) INTO STRICT v;
 IF strpos(v,'backfill_adaptive_page_request_v2')>0 OR strpos(v,' IF q->''params''->>token_key IS DISTINCT FROM t.cursor#>>''{}'' THEN')=0 THEN
  RAISE EXCEPTION 'Request validator changed or adaptive sizing is already installed'; END IF;
 v:=replace(v,' IF q->''params''->>token_key IS DISTINCT FROM t.cursor#>>''{}'' THEN',
  $limit$
 -- backfill_adaptive_page_request_v2: a caller cannot enlarge or omit its claimed limit.
 IF astra_ingestion_v1.backfill_page_limit_cap_v2(t.kind)>1 AND (
  jsonb_typeof(q#>'{params,limit}') IS DISTINCT FROM 'number'
  OR COALESCE(q#>>'{params,limit}','') !~ '^[0-9]{1,5}$'
  OR q#>>'{params,limit}' IS DISTINCT FROM COALESCE(t.page_limit,astra_ingestion_v1.backfill_page_limit_cap_v2(t.kind))::text) THEN RETURN false;END IF;
 IF q->'params'->>token_key IS DISTINCT FROM t.cursor#>>'{}' THEN$limit$);
 EXECUTE v;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_adaptive_page_dispatch_v2')>0
  OR strpos(d,'    attempts=attempts+1,page_attempts=page_attempts+1')=0
  OR strpos(d,' ELSIF p_operation=''backfill_defer'' THEN')=0 THEN
  RAISE EXCEPTION 'Runtime claim/defer baseline changed; reconcile adaptive sizing before applying'; END IF;
 d:=replace(d,'    attempts=attempts+1,page_attempts=page_attempts+1',
  '    page_limit=COALESCE(page_limit,CASE WHEN kind=''massive_news'' AND (cursor IS NULL OR cursor=''null''::jsonb) THEN 100 ELSE astra_ingestion_v1.backfill_page_limit_cap_v2(kind) END),attempts=attempts+1,page_attempts=page_attempts+1');
 d:=replace(d,' ELSIF p_operation=''backfill_defer'' THEN',$defer$
 ELSIF p_operation='backfill_defer' THEN
  -- backfill_adaptive_page_dispatch_v2: already authenticated, locked and fenced.
  IF p_payload->>'code'='SOURCE_PAGE_TOO_LARGE' THEN
   p_payload:=astra_ingestion_v1.backfill_adapt_page_v2(t,p_payload);
   t:=astra_ingestion_v1.backfill_owned_v2(v_claim);
  END IF;$defer$);
 EXECUTE d;
END $wire$;

DO $acl$
DECLARE f record; g record;
BEGIN
 FOR f IN SELECT p.oid,p.proname,p.proowner,p.proacl,pg_get_function_identity_arguments(p.oid) args FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='astra_ingestion_v1' AND p.proname IN('backfill_page_limit_cap_v2','backfill_page_limit_guard_v2','backfill_adapt_page_v2') LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM PUBLIC',f.proname,f.args);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(f.proacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>f.proowner LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM %I',f.proname,f.args,g.rolname);END LOOP;
  EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.%I(%s) TO astra_ingestion_rpc_owner_v1',f.proname,f.args);
 END LOOP;
END $acl$;

UPDATE astra_ingestion_v1.backfill_runs_v2 SET metadata=metadata||jsonb_build_object(
 'adaptive_page_policy',jsonb_build_object('version','fixed3000-adaptive-pages-v2.1',
  'execution_column','page_limit','immutable_scope_unchanged',true,'reduction_factor',10,
  'minimum_limit',1,'maximum_attempts_per_page',8,'retained_prefix_bytes',16384,
  'initial_massive_news_limit',100,'massive_cursor_policy','Operational repair; cursor query parameters are immutable',
  'massive_cursor_source','https://www.massive.com/blog/api-pagination-patterns',
  'source_verified_date','2026-10-30','source_verified_by','Controlling engineering owner',
  'provider_absence_inferred',false,'applied_at',clock_timestamp()))
 WHERE id='fixed3000-20250901-20260731-v1-20261030';
COMMIT;
