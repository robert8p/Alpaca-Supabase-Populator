-- Compact D03 inputs for bounded, one-company-per-vote cohort breadth.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $preflight$ BEGIN
 IF to_regclass('astra_ingestion_v1.backfill_plan_manifests_v2') IS NULL OR to_regclass('astra_ingestion_v1.backfill_breadth_inputs_v2') IS NOT NULL THEN
  RAISE EXCEPTION 'Breadth material requires the installed delivery runtime and applies once'; END IF;
END $preflight$;

CREATE TABLE astra_ingestion_v1.backfill_breadth_inputs_v2 (
 run_id text NOT NULL,
 member_id text NOT NULL,
 market_date date NOT NULL,
 source_month date NOT NULL,
 symbol text NOT NULL,
 task_id text NOT NULL,
 page_no integer NOT NULL,
 record_ordinal integer NOT NULL,
 raw_ret_1d numeric,
 adjusted_ret_1d numeric,
 raw_null_reason text,
 adjusted_null_reason text,
 formula_version text,
 body_sha256 text NOT NULL,
 source_committed_at timestamptz NOT NULL,
 PRIMARY KEY(run_id,member_id,market_date,task_id,page_no),
 FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_pages_v2(task_id,page_no),
 FOREIGN KEY(run_id,member_id) REFERENCES astra_ingestion_v1.backfill_members_v2(run_id,member_id)
);
CREATE INDEX backfill_breadth_inputs_day_v2 ON astra_ingestion_v1.backfill_breadth_inputs_v2(run_id,source_month,market_date,member_id,source_committed_at DESC);
CREATE TABLE astra_ingestion_v1.backfill_breadth_projected_pages_v2 (
 task_id text NOT NULL,
 page_no integer NOT NULL,
 run_id text NOT NULL,
 source_month date,
 body_sha256 text NOT NULL,
 projected_records integer NOT NULL,
 projected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(task_id,page_no),
 FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_pages_v2(task_id,page_no)
);
CREATE INDEX backfill_daily_month_units_v2 ON astra_ingestion_v1.backfill_tasks_v2(run_id,(scope->>'source_month'),(scope#>>'{member_ids,0}'),status) WHERE family='D03';
CREATE TRIGGER backfill_breadth_input_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_breadth_inputs_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();
CREATE TRIGGER backfill_breadth_projection_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_breadth_projected_pages_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_breadth_project_page_v2(p_task_id text,p_page_no integer) RETURNS integer
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; p astra_ingestion_v1.backfill_pages_v2;
 v_row jsonb; v_day date; v_month date; v_member text; v_symbol text; v_ordinal integer:=0; v_raw numeric; v_adjusted numeric;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task_id;
 IF t.family<>'D03' OR lower(t.provider)<>'derived' THEN RETURN 0; END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_breadth_projected_pages_v2 WHERE task_id=t.id AND page_no=p_page_no) THEN RETURN 0; END IF;
 SELECT * INTO STRICT p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=t.id AND page_no=p_page_no;
 IF jsonb_array_length(t.scope->'member_ids')<>1 THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Daily return projection requires one frozen company'; END IF;
 v_member:=t.scope#>>'{member_ids,0}';v_month:=astra_ingestion_v1.backfill_date_v2(t.scope->>'source_month');
 FOR v_row IN SELECT value FROM jsonb_array_elements(COALESCE(p.raw_body::jsonb->'rows','[]')) LOOP
  v_ordinal:=v_ordinal+1;v_day:=astra_ingestion_v1.backfill_date_v2(v_row->>'market_date');v_symbol:=v_row->>'symbol';
  IF v_row->>'member_id' IS DISTINCT FROM v_member OR v_day IS NULL OR length(COALESCE(v_symbol,''))=0
   OR v_day<'2025-09-01'::date OR v_day>'2026-07-31'::date
   OR (v_month IS NOT NULL AND date_trunc('month',v_day)::date<>v_month) THEN
   RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='D03 projection member/date differs from its immutable workflow scope'; END IF;
  v_raw:=CASE WHEN jsonb_typeof(v_row#>'{values,raw_ret_1d}')='number' THEN (v_row#>>'{values,raw_ret_1d}')::numeric END;
  v_adjusted:=CASE WHEN jsonb_typeof(v_row#>'{values,adjusted_ret_1d}')='number' THEN (v_row#>>'{values,adjusted_ret_1d}')::numeric END;
  INSERT INTO astra_ingestion_v1.backfill_breadth_inputs_v2(run_id,member_id,market_date,source_month,symbol,task_id,page_no,record_ordinal,
   raw_ret_1d,adjusted_ret_1d,raw_null_reason,adjusted_null_reason,formula_version,body_sha256,source_committed_at)
  VALUES(t.run_id,v_member,v_day,date_trunc('month',v_day)::date,v_symbol,t.id,p.page_no,v_ordinal,v_raw,v_adjusted,
   CASE WHEN v_raw IS NULL THEN COALESCE(v_row#>>'{null_reasons,raw_ret_1d}','MISSING_OR_NON_NUMERIC_D03_INPUT') END,
   CASE WHEN v_adjusted IS NULL THEN COALESCE(v_row#>>'{null_reasons,adjusted_ret_1d}','MISSING_OR_NON_NUMERIC_D03_INPUT') END,
   COALESCE(v_row->>'formula_version',p.adapter_version),p.body_sha256,p.committed_at);
 END LOOP;
 IF v_ordinal<>p.record_count THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='D03 compact projection count differs from retained receipt'; END IF;
 INSERT INTO astra_ingestion_v1.backfill_breadth_projected_pages_v2(task_id,page_no,run_id,source_month,body_sha256,projected_records)
 VALUES(t.id,p.page_no,t.run_id,v_month,p.body_sha256,v_ordinal);
 RETURN v_ordinal;
END $$;
CREATE FUNCTION astra_ingestion_v1.backfill_breadth_projection_trigger_v2() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$ BEGIN PERFORM astra_ingestion_v1.backfill_breadth_project_page_v2(NEW.task_id,NEW.page_no);RETURN NEW;END $$;
CREATE TRIGGER backfill_breadth_project_on_commit_v2 AFTER INSERT ON astra_ingestion_v1.backfill_pages_v2
 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_breadth_projection_trigger_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_breadth_project_pending_v2(p_limit integer DEFAULT 2) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE p record; v_pages integer:=0;v_rows bigint:=0;v_errors integer:=0;
BEGIN
 FOR p IN SELECT pg.task_id,pg.page_no,pg.run_id FROM astra_ingestion_v1.backfill_pages_v2 pg JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=pg.task_id
  WHERE t.family='D03' AND lower(t.provider)='derived'
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_breadth_projected_pages_v2 q WHERE q.task_id=pg.task_id AND q.page_no=pg.page_no)
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=pg.task_id AND a.action='D03_PROJECTION_FAILURE' AND a.evidence->>'page_no'=pg.page_no::text)
  ORDER BY pg.committed_at,pg.task_id,pg.page_no LIMIT GREATEST(1,LEAST(p_limit,8))
 LOOP
  BEGIN v_rows:=v_rows+astra_ingestion_v1.backfill_breadth_project_page_v2(p.task_id,p.page_no);v_pages:=v_pages+1;
  EXCEPTION WHEN OTHERS THEN
   v_errors:=v_errors+1;
   INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,task_id,action,evidence) VALUES(p.run_id,p.task_id,'D03_PROJECTION_FAILURE',
    jsonb_build_object('page_no',p.page_no,'sqlstate',SQLSTATE,'reason',left(SQLERRM,500),'next_action','Repair the projection and execute backfill_breadth_project_page_v2 for this exact task/page'));
  END;
 END LOOP;
 RETURN jsonb_build_object('projected_pages',v_pages,'projected_records',v_rows,'projection_errors',v_errors);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_breadth_ready_v2(p_task_id text) RETURNS boolean
LANGUAGE plpgsql STABLE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; v_month text; v_count integer;
BEGIN
 SELECT * INTO t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task_id;
 IF NOT FOUND OR t.kind<>'derive_breadth' OR t.family<>'CTX06' THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_manifests_v2 WHERE run_id=t.run_id)
  OR NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=t.run_id AND metadata->'planning_complete'='true'::jsonb) THEN RETURN false; END IF;
 v_month:=t.scope->>'source_month';
 IF v_month IS NULL OR v_month !~ '^\d{4}-\d{2}-01$' OR t.scope->>'target_start' IS DISTINCT FROM t.scope->>'target_end' THEN RETURN false; END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 d WHERE d.run_id=t.run_id AND d.family='D03' AND d.scope->>'source_month'=v_month
  AND d.status NOT IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED')) THEN RETURN false; END IF;
 SELECT count(DISTINCT d.scope#>>'{member_ids,0}') INTO v_count FROM astra_ingestion_v1.backfill_tasks_v2 d
  WHERE d.run_id=t.run_id AND d.family='D03' AND d.scope->>'source_month'=v_month AND jsonb_array_length(d.scope->'member_ids')=1;
 IF v_count<>3000 THEN RETURN false; END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 d JOIN astra_ingestion_v1.backfill_pages_v2 p ON p.task_id=d.id
  WHERE d.run_id=t.run_id AND d.family='D03' AND d.scope->>'source_month'=v_month
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_breadth_projected_pages_v2 b WHERE b.task_id=p.task_id AND b.page_no=p.page_no AND b.body_sha256=p.body_sha256)) THEN RETURN false; END IF;
 RETURN true;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_breadth_material_v2(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; v_after integer:=COALESCE((p_payload->>'after')::integer,0); v_limit integer:=GREATEST(1,LEAST(COALESCE((p_payload->>'limit')::integer,500),1000));
 v_date date;v_month date;v_rows jsonb;v_lineage jsonb;v_last integer;v_more boolean;
BEGIN
 t:=astra_ingestion_v1.backfill_owned_v2(p_payload->'claim');
 IF t.kind<>'derive_breadth' OR t.family<>'CTX06' OR v_after<0 OR v_after>3000 THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid fixed-cohort breadth read'; END IF;
 IF NOT astra_ingestion_v1.backfill_breadth_ready_v2(t.id) THEN RETURN jsonb_build_object('ready',false,'reason','SEALED_PLAN_OR_MONTHLY_D03_WORK_NOT_READY','rows','[]'::jsonb); END IF;
 v_date:=(t.scope->>'target_start')::date;v_month:=(t.scope->>'source_month')::date;
 IF jsonb_typeof(t.scope->'representative_security') IS DISTINCT FROM 'object' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Breadth requires the explicit company representative map'; END IF;
 UPDATE astra_ingestion_v1.backfill_tasks_v2 SET lease_until=LEAST(attempt_deadline,clock_timestamp()+interval '120 seconds') WHERE id=t.id;
 WITH members AS MATERIALIZED (
  SELECT m.* FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=t.run_id AND m.selection_order>v_after ORDER BY m.selection_order LIMIT v_limit
 ), selected AS MATERIALIZED (
  SELECT m.member_id,m.selection_order,COALESCE(t.scope->'representative_security'->m.member_id->>'symbol',m.anchor_ticker) representative,b.*
  FROM members m LEFT JOIN LATERAL (
   SELECT q.task_id,q.page_no,q.symbol,q.raw_ret_1d,q.adjusted_ret_1d,q.raw_null_reason,q.adjusted_null_reason,q.formula_version,q.body_sha256
   FROM astra_ingestion_v1.backfill_breadth_inputs_v2 q WHERE q.run_id=t.run_id AND q.source_month=v_month AND q.market_date=v_date AND q.member_id=m.member_id
    AND q.symbol=t.scope->'representative_security'->m.member_id->>'symbol'
   ORDER BY q.source_committed_at DESC,q.task_id,q.page_no DESC LIMIT 1
  ) b ON true
 )
 SELECT COALESCE(jsonb_agg(jsonb_build_object('member_id',member_id,'symbol',representative,'market_date',v_date,
   'values',jsonb_build_object('raw_ret_1d',raw_ret_1d,'adjusted_ret_1d',adjusted_ret_1d),
   'null_reasons',jsonb_strip_nulls(jsonb_build_object('raw_ret_1d',CASE WHEN raw_ret_1d IS NULL THEN COALESCE(raw_null_reason,'NO_PROJECTED_D03_OBSERVATION') END,'adjusted_ret_1d',CASE WHEN adjusted_ret_1d IS NULL THEN COALESCE(adjusted_null_reason,'NO_PROJECTED_D03_OBSERVATION') END)),
   'formula_version',formula_version,'source_lineage',CASE WHEN task_id IS NOT NULL THEN jsonb_build_object('task_id',task_id,'page_no',page_no,'body_sha256',body_sha256) END)
  ORDER BY selection_order),'[]'),
  COALESCE(jsonb_agg(DISTINCT jsonb_build_object('task_id',task_id,'page_no',page_no,'body_sha256',body_sha256)) FILTER(WHERE task_id IS NOT NULL),'[]'),max(selection_order)
 INTO v_rows,v_lineage,v_last FROM selected;
 SELECT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=t.run_id AND selection_order>COALESCE(v_last,v_after)) INTO v_more;
 RETURN jsonb_build_object('ready',true,'rows',v_rows,'input_lineage',v_lineage,'next_after',CASE WHEN v_more THEN v_last END,'complete',NOT v_more,'source_month',v_month,'target_date',v_date);
END $$;

DO $acl$
DECLARE o record;g record;f record;
BEGIN
 FOR o IN SELECT c.* FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='astra_ingestion_v1' AND c.relname IN ('backfill_breadth_inputs_v2','backfill_breadth_projected_pages_v2') LOOP
  EXECUTE format('REVOKE ALL ON astra_ingestion_v1.%I FROM PUBLIC',o.relname);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(o.relacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>o.relowner LOOP EXECUTE format('REVOKE ALL ON astra_ingestion_v1.%I FROM %I',o.relname,g.rolname);END LOOP;
  EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',o.relname);
  EXECUTE format('GRANT SELECT,INSERT ON astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',o.relname);
  EXECUTE format('CREATE POLICY breadth_material_read ON astra_ingestion_v1.%I FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true)',o.relname);
  EXECUTE format('CREATE POLICY breadth_material_insert ON astra_ingestion_v1.%I FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true)',o.relname);
 END LOOP;
 FOR f IN SELECT p.*,pg_get_function_identity_arguments(p.oid) args FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='astra_ingestion_v1' AND p.proname IN ('backfill_breadth_project_page_v2','backfill_breadth_projection_trigger_v2','backfill_breadth_project_pending_v2','backfill_breadth_ready_v2','backfill_breadth_material_v2') LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM PUBLIC',f.proname,f.args);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(f.proacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>f.proowner LOOP EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM %I',f.proname,f.args,g.rolname);END LOOP;
  EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.%I(%s) TO astra_ingestion_rpc_owner_v1',f.proname,f.args);
 END LOOP;
END $acl$;
DO $wire$
DECLARE d text;b text;m text;needle text:='    AND (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=q.run_id)=3000';
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'''backfill_breadth_material''')>0 OR strpos(d,'''backfill_work''')=0 THEN RAISE EXCEPTION 'Unexpected breadth capability wiring baseline';END IF;
 d:=replace(d,'''backfill_work''','''backfill_work'',''backfill_breadth_material'',''backfill_breadth_project''');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT b;
 IF strpos(b,needle)=0 OR strpos(b,' IF p_operation=''backfill_status'' THEN')=0 THEN RAISE EXCEPTION 'Unexpected breadth runtime baseline';END IF;
 b:=replace(b,needle,'    AND (q.kind<>''derive_breadth'' OR astra_ingestion_v1.backfill_breadth_ready_v2(q.id))'||chr(10)||needle);
 b:=replace(b,' IF p_operation=''backfill_status'' THEN',
  ' IF p_operation=''backfill_breadth_material'' THEN RETURN astra_ingestion_v1.backfill_breadth_material_v2(p_payload); END IF;'||chr(10)||
  ' IF p_operation=''backfill_breadth_project'' THEN RETURN astra_ingestion_v1.backfill_breadth_project_pending_v2(COALESCE((p_payload->>''limit'')::integer,2)); END IF;'||chr(10)||' IF p_operation=''backfill_status'' THEN');EXECUTE b;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) INTO STRICT m;
 IF strpos(m,' FOR p IN SELECT pg.task_id,pg.page_no,pg.run_id')=0 THEN RAISE EXCEPTION 'Unexpected existing maintenance baseline';END IF;
 m:=replace(m,' FOR p IN SELECT pg.task_id,pg.page_no,pg.run_id',' PERFORM astra_ingestion_v1.backfill_breadth_project_pending_v2(2);'||chr(10)||' FOR p IN SELECT pg.task_id,pg.page_no,pg.run_id');EXECUTE m;
END $wire$;
COMMIT;
