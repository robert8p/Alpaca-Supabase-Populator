-- One new option-bar request window per provider contract symbol. Retained
-- duplicate children keep their scopes, states, leases and executable work.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $preflight$ BEGIN
 IF to_regclass('astra_ingestion_v1.backfill_shared_records_v2') IS NULL THEN RAISE EXCEPTION 'Contract registry requires shared-record delivery first';END IF;
END $preflight$;
-- Drain any pre-hook task insertion before installing the new admission path.
LOCK TABLE astra_ingestion_v1.backfill_tasks_v2 IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE astra_ingestion_v1.backfill_contract_state_v2 (
 run_id text PRIMARY KEY REFERENCES astra_ingestion_v1.backfill_runs_v2(id),
 child_created_at timestamptz NOT NULL DEFAULT '-infinity',child_id text NOT NULL DEFAULT '',seed_complete boolean NOT NULL DEFAULT false,
 registered_windows bigint NOT NULL DEFAULT 0,registered_child_links bigint NOT NULL DEFAULT 0,parent_contract_links bigint NOT NULL DEFAULT 0,
 new_children_created bigint NOT NULL DEFAULT 0,enumeration_pages_processed bigint NOT NULL DEFAULT 0,unlinked_source_contracts bigint NOT NULL DEFAULT 0
);
INSERT INTO astra_ingestion_v1.backfill_contract_state_v2(run_id) SELECT id FROM astra_ingestion_v1.backfill_runs_v2;
CREATE TABLE astra_ingestion_v1.backfill_contract_work_v2 (
 run_id text NOT NULL,work_key text NOT NULL,provider text NOT NULL CHECK(provider='Alpaca'),contract_symbol text NOT NULL,
 start_at timestamptz NOT NULL,end_at timestamptz NOT NULL,feed text NOT NULL,timeframe text NOT NULL,
 canonical_task_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),
 PRIMARY KEY(run_id,work_key),UNIQUE(run_id,provider,contract_symbol,start_at,end_at,feed,timeframe)
);
CREATE TABLE astra_ingestion_v1.backfill_contract_child_links_v2 (
 run_id text NOT NULL,work_key text NOT NULL,task_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(run_id,work_key,task_id),
 FOREIGN KEY(run_id,work_key) REFERENCES astra_ingestion_v1.backfill_contract_work_v2(run_id,work_key)
);
CREATE INDEX backfill_contract_child_link_task_v2 ON astra_ingestion_v1.backfill_contract_child_links_v2(task_id);
CREATE TABLE astra_ingestion_v1.backfill_contract_registered_children_v2 (
 task_id text PRIMARY KEY REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),run_id text NOT NULL,scope_sha256 text NOT NULL,
 registered_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE astra_ingestion_v1.backfill_contract_child_proofs_v2 (
 task_id text PRIMARY KEY REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),run_id text NOT NULL,
 task_pages integer NOT NULL,verified_pages bigint NOT NULL,verified_records bigint NOT NULL,query_complete boolean NOT NULL,
 proof_basis text NOT NULL DEFAULT 'ALL_COMMITTED_PAGES_INDEPENDENTLY_VERIFIED_AND_SOURCE_CURSOR_EXHAUSTED',checked_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE astra_ingestion_v1.backfill_contract_enumeration_v2 (
 task_id text NOT NULL,page_no integer NOT NULL,run_id text NOT NULL,processed_at timestamptz,linked_contracts integer,unlinked_source_contracts integer,
 PRIMARY KEY(task_id,page_no),FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_pages_v2(task_id,page_no)
);
CREATE INDEX backfill_contract_enumeration_pending_v2 ON astra_ingestion_v1.backfill_contract_enumeration_v2(run_id,task_id,page_no) WHERE processed_at IS NULL;
CREATE TABLE astra_ingestion_v1.backfill_contract_parent_links_v2 (
 run_id text NOT NULL,parent_task_id text NOT NULL,page_no integer NOT NULL,record_ordinal bigint NOT NULL,
 contract_symbol text NOT NULL,underlying_symbol text NOT NULL,work_key text NOT NULL,task_at_admission text NOT NULL,
 PRIMARY KEY(parent_task_id,page_no,record_ordinal),
 FOREIGN KEY(parent_task_id,page_no) REFERENCES astra_ingestion_v1.backfill_readbacks_v2(task_id,page_no),
 FOREIGN KEY(run_id,work_key) REFERENCES astra_ingestion_v1.backfill_contract_work_v2(run_id,work_key),
 FOREIGN KEY(task_at_admission) REFERENCES astra_ingestion_v1.backfill_tasks_v2(id)
);
CREATE INDEX backfill_contract_parent_work_index_v2 ON astra_ingestion_v1.backfill_contract_parent_links_v2(run_id,work_key);
CREATE TABLE astra_ingestion_v1.backfill_contract_readback_cursor_v2 (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),verified_at timestamptz NOT NULL,task_id text NOT NULL,page_no integer NOT NULL
);
INSERT INTO astra_ingestion_v1.backfill_contract_readback_cursor_v2 VALUES(true,'-infinity','',-1);
CREATE INDEX backfill_contract_old_child_cursor_v2 ON astra_ingestion_v1.backfill_tasks_v2(run_id,created_at,id) WHERE kind='alpaca_option_bars';
CREATE INDEX backfill_contract_enum_task_v2 ON astra_ingestion_v1.backfill_tasks_v2(run_id,id) WHERE kind='alpaca_option_contracts';
DO $immutable$ DECLARE n text;BEGIN
 FOREACH n IN ARRAY ARRAY['backfill_contract_child_links_v2','backfill_contract_parent_links_v2','backfill_contract_registered_children_v2'] LOOP
  EXECUTE format('CREATE TRIGGER contract_links_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.%I FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2()',n);
 END LOOP;
END $immutable$;

CREATE FUNCTION astra_ingestion_v1.backfill_contract_key_v2(p_symbol text,p_start timestamptz,p_end timestamptz,p_feed text,p_timeframe text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT encode(sha256(convert_to(jsonb_build_array('Alpaca',p_symbol,extract(epoch FROM p_start),extract(epoch FROM p_end),p_feed,p_timeframe)::text,'UTF8')),'hex')
$$;
CREATE FUNCTION astra_ingestion_v1.backfill_contract_prove_child_v2(p_task text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;v record;passed boolean;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task;
 IF t.kind<>'alpaca_option_bars' THEN RETURN false;END IF;
 SELECT count(*) n,COALESCE(sum(actual_records),0) records,min(page_no) first_page,max(page_no) last_page INTO v
  FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE task_id=t.id;
 passed:=t.status IN('INGESTED','NO_DATA_RETURNED','IDENTITY_OR_QUALITY_UNRESOLVED') AND t.cursor IS NULL
  AND t.page_no>0 AND v.n=t.page_no AND v.first_page=0 AND v.last_page=t.page_no-1;
 INSERT INTO astra_ingestion_v1.backfill_contract_child_proofs_v2(task_id,run_id,task_pages,verified_pages,verified_records,query_complete)
 VALUES(t.id,t.run_id,t.page_no,v.n,v.records,COALESCE(passed,false)) ON CONFLICT(task_id) DO UPDATE SET task_pages=EXCLUDED.task_pages,
  verified_pages=EXCLUDED.verified_pages,verified_records=EXCLUDED.verified_records,query_complete=EXCLUDED.query_complete,checked_at=clock_timestamp();
 RETURN COALESCE(passed,false);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_contract_register_child_v2(p_task text) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;s text;k text;a timestamptz;b timestamptz;feed text;frame text;
 n integer:=0;v_added integer;v_windows integer:=0;candidate_complete boolean;prior record;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task;
 IF t.kind<>'alpaca_option_bars' OR t.provider<>'Alpaca' THEN RETURN 0;END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(t.run_id,706314020261099));
 INSERT INTO astra_ingestion_v1.backfill_contract_state_v2(run_id) VALUES(t.run_id) ON CONFLICT DO NOTHING;
 candidate_complete:=astra_ingestion_v1.backfill_contract_prove_child_v2(t.id);
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_contract_registered_children_v2 WHERE task_id=t.id) THEN
  IF candidate_complete THEN
   UPDATE astra_ingestion_v1.backfill_contract_work_v2 w SET canonical_task_id=t.id
    FROM astra_ingestion_v1.backfill_contract_child_links_v2 l
    WHERE l.task_id=t.id AND w.run_id=l.run_id AND w.work_key=l.work_key AND w.canonical_task_id<>t.id
     AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_contract_child_proofs_v2 p WHERE p.task_id=w.canonical_task_id AND p.query_complete);
  END IF;
  RETURN 0;
 END IF;
 a:=astra_ingestion_v1.backfill_stamp_v2(t.scope->>'start');b:=astra_ingestion_v1.backfill_stamp_v2(t.scope->>'end');
 feed:=COALESCE(t.scope->>'feed','opra');frame:=COALESCE(t.scope->>'timeframe','1Day');
 IF a IS NULL OR b IS NULL OR a>=b OR feed<>'opra' OR frame<>'1Day' OR jsonb_typeof(t.scope->'symbols')<>'array' THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Existing option child scope cannot be safely registered';END IF;
 FOR s IN SELECT DISTINCT value FROM jsonb_array_elements_text(t.scope->'symbols') WHERE value ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$' LOOP
  k:=astra_ingestion_v1.backfill_contract_key_v2(s,a,b,feed,frame);
  INSERT INTO astra_ingestion_v1.backfill_contract_work_v2 VALUES(t.run_id,k,'Alpaca',s,a,b,feed,frame,t.id) ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS v_added=ROW_COUNT;v_windows:=v_windows+v_added;
  IF v_added=0 AND candidate_complete THEN
   SELECT w.canonical_task_id,COALESCE(p.query_complete,false) complete INTO prior FROM astra_ingestion_v1.backfill_contract_work_v2 w
    LEFT JOIN astra_ingestion_v1.backfill_contract_child_proofs_v2 p ON p.task_id=w.canonical_task_id WHERE w.run_id=t.run_id AND w.work_key=k;
   -- A better retained receipt can be referenced without cancelling or changing
   -- the previous child, including any running lease or incomplete cursor.
   IF NOT prior.complete THEN UPDATE astra_ingestion_v1.backfill_contract_work_v2 SET canonical_task_id=t.id WHERE run_id=t.run_id AND work_key=k;END IF;
  END IF;
  INSERT INTO astra_ingestion_v1.backfill_contract_child_links_v2(run_id,work_key,task_id) VALUES(t.run_id,k,t.id) ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS v_added=ROW_COUNT;n:=n+v_added;
 END LOOP;
 INSERT INTO astra_ingestion_v1.backfill_contract_registered_children_v2(task_id,run_id,scope_sha256)
  VALUES(t.id,t.run_id,encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(t.scope),'UTF8')),'hex'));
 UPDATE astra_ingestion_v1.backfill_contract_state_v2 SET registered_windows=registered_windows+v_windows,registered_child_links=registered_child_links+n WHERE run_id=t.run_id;
 RETURN n;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_contract_child_trigger_v2() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN IF NEW.kind='alpaca_option_bars' THEN PERFORM astra_ingestion_v1.backfill_contract_register_child_v2(NEW.id);END IF;RETURN NEW;END $$;
CREATE TRIGGER backfill_contract_child_insert_v2 AFTER INSERT ON astra_ingestion_v1.backfill_tasks_v2 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_contract_child_trigger_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_contract_enqueue_v2(p_task text,p_page integer) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' AS $$
BEGIN
 INSERT INTO astra_ingestion_v1.backfill_contract_enumeration_v2(task_id,page_no,run_id)
 SELECT t.id,p_page,t.run_id FROM astra_ingestion_v1.backfill_tasks_v2 t JOIN astra_ingestion_v1.backfill_pages_v2 p ON p.task_id=t.id AND p.page_no=p_page
 WHERE t.id=p_task AND t.kind='alpaca_option_contracts' ON CONFLICT DO NOTHING;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_contract_seed_v2(p_run text,p_limit integer DEFAULT 8) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='12s' AS $$
DECLARE c astra_ingestion_v1.backfill_contract_state_v2;t record;n integer:=0;
BEGIN
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_run,706314020261099));
 INSERT INTO astra_ingestion_v1.backfill_contract_state_v2(run_id) VALUES(p_run) ON CONFLICT DO NOTHING;
 SELECT * INTO STRICT c FROM astra_ingestion_v1.backfill_contract_state_v2 WHERE run_id=p_run FOR UPDATE;
 IF c.seed_complete THEN RETURN 0;END IF;
 FOR t IN SELECT id,created_at FROM astra_ingestion_v1.backfill_tasks_v2 WHERE run_id=p_run AND kind='alpaca_option_bars'
  AND (created_at,id)>(c.child_created_at,c.child_id) ORDER BY created_at,id LIMIT GREATEST(1,LEAST(p_limit,16)) LOOP
  PERFORM astra_ingestion_v1.backfill_contract_register_child_v2(t.id);n:=n+1;
  UPDATE astra_ingestion_v1.backfill_contract_state_v2 SET child_created_at=t.created_at,child_id=t.id WHERE run_id=p_run;
 END LOOP;
 UPDATE astra_ingestion_v1.backfill_contract_state_v2 st SET seed_complete=true WHERE st.run_id=p_run
  AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 pending WHERE pending.run_id=p_run AND pending.kind='alpaca_option_bars' AND (pending.created_at,pending.id)>(st.child_created_at,st.child_id));
 RETURN n;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_contract_admit_page_v2(p_task text,p_page integer) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='12s' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;r astra_ingestion_v1.backfill_runs_v2;e astra_ingestion_v1.backfill_contract_enumeration_v2;
 rows jsonb;syms jsonb;scope jsonb;child_id text;grp integer;children integer:=0;linked integer;unlinked integer;
 a timestamptz:='2025-09-01T00:00:00-04:00';b timestamptz:='2026-07-31T23:59:59-04:00';
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(t.run_id,706314020261099));
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=t.run_id;
 IF r.status<>'ACTIVE' OR r.fence<>t.run_fence THEN RETURN jsonb_build_object('state','RUN_FENCE_NOT_ACTIVE');END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_contract_state_v2 WHERE run_id=t.run_id AND seed_complete) THEN RETURN jsonb_build_object('state','RETAINED_CHILD_RECONCILIATION_PENDING');END IF;
 SELECT * INTO STRICT e FROM astra_ingestion_v1.backfill_contract_enumeration_v2 WHERE task_id=p_task AND page_no=p_page FOR UPDATE;
 IF e.processed_at IS NOT NULL THEN RETURN jsonb_build_object('state','ALREADY_LINKED');END IF;
 IF t.kind<>'alpaca_option_contracts' OR NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE task_id=p_task AND page_no=p_page) THEN RETURN jsonb_build_object('state','INDEPENDENT_READBACK_PENDING');END IF;
 SELECT COALESCE(jsonb_agg(jsonb_build_object('ordinal',x.record_ordinal,'symbol',x.source_row->>'symbol','underlying',x.source_row->>'underlying_symbol',
  'eligible',COALESCE(x.source_row->>'symbol' ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$' AND (t.scope->'symbols') ? (x.source_row->>'underlying_symbol'),false))),'[]') INTO rows
 FROM astra_ingestion_v1.backfill_page_rows_v2(t.id,p_page) x;
 FOR syms,grp IN
  SELECT jsonb_agg(symbol ORDER BY symbol),g FROM(SELECT symbol,((row_number() OVER(ORDER BY symbol)-1)/100)::int g FROM(
   SELECT DISTINCT x->>'symbol' symbol FROM jsonb_array_elements(rows) x WHERE x->'eligible'='true'::jsonb
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_contract_work_v2 w WHERE w.run_id=t.run_id AND w.work_key=astra_ingestion_v1.backfill_contract_key_v2(x->>'symbol',a,b,'opra','1Day'))
  ) unique_symbols) numbered GROUP BY g
 LOOP
  scope:=jsonb_build_object('symbols',syms,'member_ids',t.scope->'member_ids','start','2025-09-01T00:00:00-04:00','end','2026-07-31T23:59:59-04:00',
   'identity_status','PROVIDER_CONTRACT_UNDERLYING_LINK','enumeration_parent',t.id,'contract_registry_version','fixed3000-contract-work-v2');
  child_id:='backfill-contract-'||encode(sha256(convert_to(jsonb_build_array(t.run_id,syms,extract(epoch FROM a),extract(epoch FROM b),'opra','1Day')::text,'UTF8')),'hex');
  INSERT INTO astra_ingestion_v1.backfill_tasks_v2(id,run_id,family,provider,kind,scope,priority,run_fence)
  VALUES(child_id,t.run_id,'CTX02','Alpaca','alpaca_option_bars',scope,t.priority+1,t.run_fence);
  children:=children+1;
 END LOOP;
 INSERT INTO astra_ingestion_v1.backfill_contract_parent_links_v2(run_id,parent_task_id,page_no,record_ordinal,contract_symbol,underlying_symbol,work_key,task_at_admission)
 SELECT t.run_id,t.id,p_page,(x->>'ordinal')::bigint,x->>'symbol',x->>'underlying',w.work_key,w.canonical_task_id
 FROM jsonb_array_elements(rows) x JOIN astra_ingestion_v1.backfill_contract_work_v2 w
  ON w.run_id=t.run_id AND w.work_key=astra_ingestion_v1.backfill_contract_key_v2(x->>'symbol',a,b,'opra','1Day') WHERE x->'eligible'='true'::jsonb ON CONFLICT DO NOTHING;
 GET DIAGNOSTICS linked=ROW_COUNT;
 SELECT count(*) INTO unlinked FROM jsonb_array_elements(rows) x WHERE x->'eligible'<>'true'::jsonb;
 UPDATE astra_ingestion_v1.backfill_contract_enumeration_v2 SET processed_at=clock_timestamp(),linked_contracts=linked,unlinked_source_contracts=unlinked WHERE task_id=t.id AND page_no=p_page;
 UPDATE astra_ingestion_v1.backfill_contract_state_v2 SET parent_contract_links=parent_contract_links+linked,new_children_created=new_children_created+children,
  enumeration_pages_processed=enumeration_pages_processed+1,unlinked_source_contracts=unlinked_source_contracts+unlinked WHERE run_id=t.run_id;
 RETURN jsonb_build_object('state','CONTRACT_WORK_LINKED','new_children',children,'linked_source_contracts',linked,'unlinked_source_contracts',unlinked,
  'preexisting_children_preserved',true,'historical_enumeration_completeness_certified',false);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_contract_readback_v2(p_task text,p_page integer) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task;
 IF t.kind NOT IN('alpaca_option_bars','alpaca_option_contracts') THEN RETURN;END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(t.run_id,706314020261099));
 IF t.kind='alpaca_option_bars' THEN PERFORM astra_ingestion_v1.backfill_contract_register_child_v2(t.id);
 ELSE PERFORM astra_ingestion_v1.backfill_contract_enqueue_v2(t.id,p_page);
  PERFORM astra_ingestion_v1.backfill_contract_admit_page_v2(t.id,p_page);END IF;
END $$;
CREATE FUNCTION astra_ingestion_v1.backfill_contract_readback_trigger_v2() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN PERFORM astra_ingestion_v1.backfill_contract_readback_v2(NEW.task_id,NEW.page_no);RETURN NEW;END $$;
CREATE TRIGGER backfill_contract_readback_v2 AFTER INSERT ON astra_ingestion_v1.backfill_readbacks_v2 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_contract_readback_trigger_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_contract_maintain_v2() RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='20s' AS $$
DECLARE r record;x record;c astra_ingestion_v1.backfill_contract_readback_cursor_v2;n integer:=0;
BEGIN
 FOR r IN SELECT id FROM astra_ingestion_v1.backfill_runs_v2 WHERE status='ACTIVE' ORDER BY created_at LIMIT 1 LOOP
  PERFORM astra_ingestion_v1.backfill_contract_seed_v2(r.id,8);
  FOR x IN SELECT e.task_id,e.page_no FROM astra_ingestion_v1.backfill_contract_enumeration_v2 e JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no)
   WHERE e.run_id=r.id AND e.processed_at IS NULL ORDER BY e.task_id,e.page_no LIMIT 1 LOOP PERFORM astra_ingestion_v1.backfill_contract_admit_page_v2(x.task_id,x.page_no);n:=n+1;END LOOP;
 END LOOP;
 SELECT * INTO STRICT c FROM astra_ingestion_v1.backfill_contract_readback_cursor_v2 WHERE singleton FOR UPDATE;
 FOR x IN SELECT b.verified_at,b.task_id,b.page_no,t.kind FROM astra_ingestion_v1.backfill_readbacks_v2 b JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=b.task_id
  WHERE (b.verified_at,b.task_id,b.page_no)>(c.verified_at,c.task_id,c.page_no) ORDER BY b.verified_at,b.task_id,b.page_no LIMIT 32 LOOP
  -- Catchup only queues retained enumeration pointers. Heavy source parsing and
  -- admission stays at one page per maintenance call, never32 provider pages.
  IF x.kind='alpaca_option_contracts' THEN PERFORM astra_ingestion_v1.backfill_contract_enqueue_v2(x.task_id,x.page_no);
  ELSIF x.kind='alpaca_option_bars' THEN PERFORM astra_ingestion_v1.backfill_contract_register_child_v2(x.task_id);END IF;
  UPDATE astra_ingestion_v1.backfill_contract_readback_cursor_v2 SET verified_at=x.verified_at,task_id=x.task_id,page_no=x.page_no WHERE singleton;
 END LOOP;RETURN n;
END $$;

CREATE VIEW astra_ingestion_v1.backfill_contract_parent_work_v2 WITH(security_invoker=true) AS
 SELECT l.run_id,l.parent_task_id,l.page_no,l.record_ordinal,l.contract_symbol,l.underlying_symbol,l.work_key,l.task_at_admission,
  w.canonical_task_id,t.status canonical_task_status,COALESCE(p.query_complete,false) canonical_query_complete,
  COALESCE(p.verified_pages,0) independently_verified_pages,COALESCE(p.verified_records,0) independently_verified_records,
  parent.scope->'member_ids' parent_member_ids,t.scope->'member_ids' canonical_task_member_ids,
  'SOURCE_QUERY_AND_PROVIDER_CONTRACT_UNDERLYING_LINK_NOT_HISTORICAL_IDENTITY_CERTIFICATION'::text attribution_basis,
  'ENTIRE_CANONICAL_CHILD_REQUEST_NOT_THIS_CONTRACT'::text verification_count_scope,false counts_additive_across_parent_links,
  false historical_enumeration_completeness_certified
 FROM astra_ingestion_v1.backfill_contract_parent_links_v2 l JOIN astra_ingestion_v1.backfill_contract_work_v2 w USING(run_id,work_key)
 JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=w.canonical_task_id JOIN astra_ingestion_v1.backfill_tasks_v2 parent ON parent.id=l.parent_task_id
 LEFT JOIN astra_ingestion_v1.backfill_contract_child_proofs_v2 p ON p.task_id=w.canonical_task_id;
CREATE VIEW astra_ingestion_v1.backfill_contract_work_status_v2 WITH(security_invoker=true) AS
 SELECT s.run_id,jsonb_build_object('registry_seed_complete',s.seed_complete,'registered_contract_windows',s.registered_windows,
  'registered_child_contract_links',s.registered_child_links,'parent_contract_links',s.parent_contract_links,
  'new_children_created',s.new_children_created,'enumeration_pages_processed',s.enumeration_pages_processed,
  'unlinked_source_contracts',s.unlinked_source_contracts,'pending_enumeration_pages',COALESCE(e.pending,0),
  'unverified_pending_enumeration_pages',COALESCE(e.unverified,0),'unreconciled_verified_enumeration_pages',COALESCE(u.missing,0),'preexisting_children_preserved',true,
  'existing_overlap_contract_links',GREATEST(0,s.registered_child_links-s.registered_windows),
  'existing_overlaps_remain_executable',true,'historical_enumeration_completeness_certified',false,
  'parent_link_count_basis','VERIFIED_ENUMERATION_SOURCE_OCCURRENCES_NOT_DISTINCT_PARENT_CONTRACT_PAIRS',
  'expected_contract_population',NULL,'coverage_fraction',NULL) contract_work
 FROM astra_ingestion_v1.backfill_contract_state_v2 s LEFT JOIN LATERAL(
  SELECT count(*) pending,count(*) FILTER(WHERE NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 b WHERE b.task_id=q.task_id AND b.page_no=q.page_no)) unverified
  FROM astra_ingestion_v1.backfill_contract_enumeration_v2 q WHERE q.run_id=s.run_id AND q.processed_at IS NULL
 ) e ON true LEFT JOIN LATERAL(
  SELECT sum(x.missing) missing FROM astra_ingestion_v1.backfill_tasks_v2 t CROSS JOIN LATERAL(
   SELECT count(*) missing FROM astra_ingestion_v1.backfill_readbacks_v2 b WHERE b.task_id=t.id AND NOT EXISTS(
    SELECT 1 FROM astra_ingestion_v1.backfill_contract_enumeration_v2 q WHERE q.task_id=b.task_id AND q.page_no=b.page_no AND q.processed_at IS NOT NULL)
  ) x WHERE t.run_id=s.run_id AND t.kind='alpaca_option_contracts'
 ) u ON true;

DO $wire$
DECLARE d text;old_block text;start_at integer;end_at integer;cols text;b text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT d;
 start_at:=strpos(d,' -- Historical option enumeration creates executable daily-bar successors atomically.');
 end_at:=strpos(d,E' PERFORM astra_ingestion_v1.backfill_owned_v2(v_claim);\n UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status=v_state');
 IF start_at=0 OR end_at<=start_at OR strpos(substr(d,start_at,end_at-start_at),'backfill-options-')=0 THEN
  RAISE EXCEPTION 'Existing inline contract successor block differs; reconcile before registry installation';END IF;
 old_block:=substr(d,start_at,end_at-start_at);
 d:=replace(d,old_block,E' -- Durable contract enumeration admission is independently verified and reconciled by the same controller.\n IF t.kind=''alpaca_option_contracts'' THEN PERFORM astra_ingestion_v1.backfill_contract_enqueue_v2(t.id,t.page_no);END IF;\n');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_contract_maintain_v2')>0 OR strpos(d,' FOR p IN SELECT pg.task_id')=0 THEN RAISE EXCEPTION 'Contract registry monitor baseline differs';END IF;
 d:=replace(d,' FOR p IN SELECT pg.task_id',E' PERFORM astra_ingestion_v1.backfill_contract_maintain_v2();\n FOR p IN SELECT pg.task_id');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_try_finalize_v2(text)'::regprocedure) INTO STRICT d;
 IF strpos(d,'  v_coverage_unknown:=')=0 THEN RAISE EXCEPTION 'Contract registry finalizer baseline differs';END IF;
 d:=replace(d,'  v_coverage_unknown:=',E'  IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 b JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=b.task_id WHERE b.run_id=r.id AND t.kind=''alpaca_option_contracts'' AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_contract_enumeration_v2 e WHERE e.task_id=b.task_id AND e.page_no=b.page_no AND e.processed_at IS NOT NULL)) THEN RETURN jsonb_build_object(''state'',''CONTRACT_WORK_ADMISSION_PENDING'');END IF;\n  v_coverage_unknown:=');EXECUTE d;
 SELECT pg_get_viewdef('astra_ingestion_v1.backfill_family_status_v2'::regclass,true) INTO STRICT b;
 SELECT string_agg(CASE WHEN a.attname='nonminute_coverage' THEN
  'CASE WHEN old.family=''CTX02'' THEN jsonb_set(old.nonminute_coverage,''{shared_records}'',COALESCE(old.nonminute_coverage->''shared_records'',''{}''::jsonb)||jsonb_build_object(''contract_work'',c.contract_work)) ELSE old.nonminute_coverage END nonminute_coverage'
  WHEN a.attname='work_completion' THEN
   'CASE WHEN old.family=''CTX02'' AND old.work_completion IN(''COMPLETE'',''COMPLETE_WITH_DOCUMENTED_GAPS'') AND (COALESCE((c.contract_work->>''pending_enumeration_pages'')::bigint,0)>0 OR COALESCE((c.contract_work->>''unreconciled_verified_enumeration_pages'')::bigint,0)>0 OR c.contract_work->''registry_seed_complete''=''false''::jsonb) THEN ''IN_PROGRESS'' ELSE old.work_completion END work_completion'
  ELSE format('old.%I',a.attname) END,',' ORDER BY a.attnum) INTO cols FROM pg_attribute a WHERE a.attrelid='astra_ingestion_v1.backfill_family_status_v2'::regclass AND a.attnum>0 AND NOT a.attisdropped;
 EXECUTE 'CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_status_v2 WITH(security_invoker=true) AS WITH old AS ('||rtrim(b,';')||') SELECT '||cols||' FROM old LEFT JOIN astra_ingestion_v1.backfill_contract_work_status_v2 c ON c.run_id=old.run_id';
END $wire$;

DO $acl$
DECLARE o record;f record;g record;
BEGIN
 FOR o IN SELECT c.* FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='astra_ingestion_v1' AND c.relname LIKE 'backfill_contract_%_v2' AND c.relkind IN('r','v') LOOP
  EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM PUBLIC',o.relname);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(o.relacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>o.relowner LOOP EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM %I',o.relname,g.rolname);END LOOP;
  IF o.relkind='r' THEN EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',o.relname);EXECUTE format('CREATE POLICY contract_read_v2 ON astra_ingestion_v1.%I FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true)',o.relname);END IF;
  EXECUTE format('GRANT SELECT ON TABLE astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',o.relname);
 END LOOP;
 FOR f IN SELECT p.*,pg_get_function_identity_arguments(p.oid) args FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='astra_ingestion_v1' AND p.proname LIKE 'backfill_contract_%_v2' LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM PUBLIC',f.proname,f.args);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(f.proacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>f.proowner LOOP EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM %I',f.proname,f.args,g.rolname);END LOOP;
  EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.%I(%s) TO astra_ingestion_rpc_owner_v1',f.proname,f.args);
 END LOOP;
END $acl$;
COMMIT;
