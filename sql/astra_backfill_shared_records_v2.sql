-- Verified shared provider records, immutable versions and receipt references.
-- Source pages stay unchanged. Logical records and links are not page counts.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $preflight$ BEGIN
 IF to_regclass('astra_ingestion_v1.backfill_nonminute_pages_v2') IS NULL THEN
  RAISE EXCEPTION 'Shared records require the installed non-minute projection';END IF;
END $preflight$;

CREATE TABLE astra_ingestion_v1.backfill_shared_versions_v2 (
 run_id text NOT NULL,record_key text NOT NULL,row_sha256 text NOT NULL,
 provider text NOT NULL,record_type text NOT NULL,kind text NOT NULL,record_group text NOT NULL,
 provider_record_id text,identity_basis text NOT NULL,symbol text,market_date date,date_axes jsonb NOT NULL,primary_date_field text NOT NULL,
 version_timestamp timestamptz,field_states jsonb NOT NULL,delivery_families text[] NOT NULL,
 task_id text NOT NULL,page_no integer NOT NULL,record_ordinal bigint NOT NULL,
 PRIMARY KEY(run_id,record_key,row_sha256),
 FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_readbacks_v2(task_id,page_no)
);
CREATE TABLE astra_ingestion_v1.backfill_shared_occurrences_v2 (
 run_id text NOT NULL,record_key text NOT NULL,row_sha256 text NOT NULL,
 task_id text NOT NULL,page_no integer NOT NULL,record_ordinal bigint NOT NULL,
 PRIMARY KEY(task_id,page_no,record_ordinal),
 FOREIGN KEY(run_id,record_key,row_sha256) REFERENCES astra_ingestion_v1.backfill_shared_versions_v2(run_id,record_key,row_sha256),
 FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_readbacks_v2(task_id,page_no)
);
CREATE INDEX backfill_shared_occurrence_key_v2 ON astra_ingestion_v1.backfill_shared_occurrences_v2(run_id,record_key);
CREATE TABLE astra_ingestion_v1.backfill_shared_version_links_v2 (
 run_id text NOT NULL,record_key text NOT NULL,row_sha256 text NOT NULL,security_symbol text NOT NULL,link_role text NOT NULL,
 PRIMARY KEY(run_id,record_key,row_sha256,security_symbol,link_role),
 FOREIGN KEY(run_id,record_key,row_sha256) REFERENCES astra_ingestion_v1.backfill_shared_versions_v2(run_id,record_key,row_sha256)
);
CREATE TABLE astra_ingestion_v1.backfill_shared_records_v2 (
 run_id text NOT NULL,record_key text NOT NULL,row_sha256 text NOT NULL,
 provider text NOT NULL,record_type text NOT NULL,kind text NOT NULL,record_group text NOT NULL,
 provider_record_id text,identity_basis text NOT NULL,symbol text,market_date date,date_axes jsonb NOT NULL,primary_date_field text NOT NULL,
 period text NOT NULL,boundary_crossing boolean NOT NULL,boundary_support boolean NOT NULL,
 source_versions bigint NOT NULL,current_candidate_versions bigint NOT NULL,ordered_versions boolean NOT NULL,
 source_occurrences bigint NOT NULL,conflict_fields jsonb NOT NULL,field_states jsonb NOT NULL,delivery_families text[] NOT NULL,
 task_id text NOT NULL,page_no integer NOT NULL,record_ordinal bigint NOT NULL,
 PRIMARY KEY(run_id,record_key),
 FOREIGN KEY(run_id,record_key,row_sha256) REFERENCES astra_ingestion_v1.backfill_shared_versions_v2(run_id,record_key,row_sha256)
);
CREATE INDEX backfill_shared_record_page_v2 ON astra_ingestion_v1.backfill_shared_records_v2(task_id,page_no,record_ordinal);
CREATE INDEX backfill_shared_contract_symbol_v2 ON astra_ingestion_v1.backfill_shared_records_v2(run_id,provider,symbol,record_key) WHERE record_type='CONTRACT_REFERENCE';
CREATE TABLE astra_ingestion_v1.backfill_shared_links_v2 (
 run_id text NOT NULL,record_key text NOT NULL,security_symbol text NOT NULL,link_role text NOT NULL,
 observed_versions bigint NOT NULL,current_candidate_versions bigint NOT NULL,link_state text NOT NULL,
 candidate_member_ids jsonb NOT NULL,identity_state text NOT NULL,
 PRIMARY KEY(run_id,record_key,security_symbol,link_role),
 FOREIGN KEY(run_id,record_key) REFERENCES astra_ingestion_v1.backfill_shared_records_v2(run_id,record_key)
);
CREATE INDEX backfill_shared_member_anchor_v2 ON astra_ingestion_v1.backfill_members_v2(run_id,anchor_ticker,member_id);
CREATE INDEX backfill_shared_action_tasks_v2 ON astra_ingestion_v1.backfill_tasks_v2(run_id,status,id) WHERE kind='alpaca_actions';
CREATE TABLE astra_ingestion_v1.backfill_shared_pages_v2 (
 task_id text NOT NULL,page_no integer NOT NULL,run_id text NOT NULL,delivery_families text[] NOT NULL,
 source_records integer NOT NULL,projected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(task_id,page_no),FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_readbacks_v2(task_id,page_no)
);
CREATE INDEX backfill_shared_pages_run_v2 ON astra_ingestion_v1.backfill_shared_pages_v2(run_id,task_id,page_no);
CREATE TABLE astra_ingestion_v1.backfill_shared_cursor_v2 (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),verified_at timestamptz NOT NULL,task_id text NOT NULL,page_no integer NOT NULL
);
INSERT INTO astra_ingestion_v1.backfill_shared_cursor_v2 VALUES(true,'-infinity','',-1);

-- Report counters are updated from the before/after state of touched keys.
-- Routine status never scans or parses the growing source/record archive.
CREATE TABLE astra_ingestion_v1.backfill_shared_counts_v2 (
 run_id text NOT NULL,family text NOT NULL,record_type text NOT NULL,kind text NOT NULL,period text NOT NULL,
 records bigint NOT NULL,occurrences bigint NOT NULL,versions bigint NOT NULL,conflicts bigint NOT NULL,fallback_keys bigint NOT NULL,
 boundary_crossing bigint NOT NULL,boundary_support bigint NOT NULL,links bigint NOT NULL,cohort_links bigint NOT NULL,
 PRIMARY KEY(run_id,family,record_type,kind,period)
);
CREATE TABLE astra_ingestion_v1.backfill_shared_fields_v2 (
 run_id text NOT NULL,family text NOT NULL,record_type text NOT NULL,kind text NOT NULL,period text NOT NULL,
 field text NOT NULL,datatype text NOT NULL,nonnull boolean NOT NULL,reason text NOT NULL,records bigint NOT NULL,
 PRIMARY KEY(run_id,family,record_type,kind,period,field,datatype,nonnull,reason)
);
CREATE TABLE astra_ingestion_v1.backfill_shared_dates_v2 (
 run_id text NOT NULL,family text NOT NULL,record_type text NOT NULL,date_axis text NOT NULL,period text NOT NULL,records bigint NOT NULL,
 PRIMARY KEY(run_id,family,record_type,date_axis,period)
);
DO $immutable$ DECLARE n text;BEGIN
 FOREACH n IN ARRAY ARRAY['backfill_shared_versions_v2','backfill_shared_occurrences_v2','backfill_shared_version_links_v2','backfill_shared_pages_v2'] LOOP
  EXECUTE format('CREATE TRIGGER shared_evidence_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.%I FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2()',n);
 END LOOP;
END $immutable$;

CREATE FUNCTION astra_ingestion_v1.backfill_shared_meta_v2(p_provider text,p_kind text,p_group text,p_symbol text,p_row jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
DECLARE typ text;grp text;pid text;basis text;key_value jsonb;row_hash text;d date;stamp timestamptz;axes jsonb;spec jsonb;fields jsonb;
 links jsonb:='[]';families text[];item jsonb;token text;role text;v jsonb;dt text;primary_date_field text;
BEGIN
 typ:=CASE WHEN p_kind IN('massive_news','alpaca_news') THEN 'ARTICLE' WHEN p_kind='alpaca_option_contracts' THEN 'CONTRACT_REFERENCE'
  WHEN p_kind='alpaca_option_bars' THEN 'OPTION_DAILY_BAR' ELSE 'ACTION' END;
 grp:=CASE WHEN p_kind='massive_dividends' THEN 'DIVIDEND' WHEN p_kind='massive_splits' THEN 'SPLIT' ELSE p_group END;
 families:=CASE WHEN typ='ARTICLE' THEN ARRAY['N01'] WHEN typ IN('CONTRACT_REFERENCE','OPTION_DAILY_BAR') THEN ARRAY['CTX02']
  WHEN p_kind='massive_splits' THEN ARRAY['N03'] WHEN p_kind='alpaca_actions' AND p_group IN('forward_splits','reverse_splits','unit_splits') THEN ARRAY['N02','N03'] ELSE ARRAY['N02'] END;
 row_hash:=encode(sha256(convert_to(p_row::text,'UTF8')),'hex');
 pid:=CASE WHEN jsonb_typeof(p_row->'id') IN('string','number') AND length(p_row->>'id') BETWEEN 1 AND 512 THEN p_row->>'id' END;
 basis:='PROVIDER_RECORD_ID';key_value:=jsonb_build_array(typ,CASE WHEN typ='ACTION' THEN grp ELSE '' END,pid);
 IF typ='OPTION_DAILY_BAR' THEN
  stamp:=astra_ingestion_v1.backfill_stamp_v2(p_row->>'t');d:=(stamp AT TIME ZONE 'America/New_York')::date;
  IF p_symbol ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$' AND d IS NOT NULL THEN basis:='PROVIDER_CONTRACT_SYMBOL_SESSION_OPRA';key_value:=jsonb_build_array(typ,p_symbol,d,'opra','1Day');
  ELSE basis:='EXACT_CONTENT_FALLBACK_SEMANTIC_IDENTITY_UNKNOWN';key_value:=jsonb_build_array(typ,p_symbol,'opra','1Day',row_hash);END IF;
 ELSIF typ='CONTRACT_REFERENCE' AND p_row->>'symbol' ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$' THEN
  basis:='PROVIDER_CONTRACT_SYMBOL';key_value:=jsonb_build_array(typ,p_row->>'symbol');
 ELSIF pid IS NULL THEN
  basis:='EXACT_CONTENT_FALLBACK_SEMANTIC_IDENTITY_UNKNOWN';key_value:=jsonb_build_array(typ,grp,row_hash);
 END IF;
 axes:='{}';
 IF typ='ARTICLE' THEN
  primary_date_field:=CASE WHEN p_kind='massive_news' THEN 'published_utc' ELSE 'created_at' END;
  stamp:=astra_ingestion_v1.backfill_stamp_v2(p_row->>primary_date_field);d:=(stamp AT TIME ZONE 'America/New_York')::date;
  axes:=jsonb_build_object('publication_date_new_york',d);
  v:=CASE WHEN p_kind='massive_news' THEN p_row->'tickers' ELSE p_row->'symbols' END;
  FOR item IN SELECT value FROM jsonb_array_elements(CASE WHEN jsonb_typeof(v)='array' THEN v ELSE '[]' END) LOOP
   token:=item#>>'{}';IF jsonb_typeof(item)='string' AND token ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$' THEN links:=links||jsonb_build_array(jsonb_build_object('symbol',upper(token),'role','ARTICLE_SECURITY'));END IF;
  END LOOP;
 ELSIF typ='ACTION' THEN
  SELECT COALESCE(jsonb_object_agg(key,astra_ingestion_v1.backfill_date_v2(value#>>'{}')),'{}') INTO axes FROM jsonb_each(p_row)
   WHERE key IN('announcement_date','declaration_date','ex_date','ex_dividend_date','record_date','pay_date','payable_date','payment_date','execution_date','effective_date','process_date');
  primary_date_field:=CASE WHEN p_kind='massive_dividends' THEN 'ex_dividend_date' WHEN p_kind='massive_splits' THEN 'execution_date'
   WHEN p_row ? 'effective_date' THEN 'effective_date' WHEN p_row ? 'ex_date' THEN 'ex_date' ELSE 'process_date' END;
  d:=astra_ingestion_v1.backfill_date_v2(p_row->>primary_date_field);
  FOR token,role IN SELECT p_row->>'ticker','SECURITY' UNION ALL SELECT p_row->>'symbol','SECURITY'
   UNION ALL SELECT p_row->>'initiating_symbol','INITIATING_SECURITY' UNION ALL SELECT p_row->>'target_symbol','TARGET_SECURITY' LOOP
   IF token ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$' THEN links:=links||jsonb_build_array(jsonb_build_object('symbol',upper(token),'role',role));END IF;
  END LOOP;
 ELSIF typ='CONTRACT_REFERENCE' THEN
  primary_date_field:='expiration_date';d:=astra_ingestion_v1.backfill_date_v2(p_row->>'expiration_date');axes:=jsonb_build_object('expiration_date',d);
  token:=p_row->>'underlying_symbol';IF token ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$' THEN links:=jsonb_build_array(jsonb_build_object('symbol',upper(token),'role','CONTRACT_UNDERLYING'));END IF;
 ELSE primary_date_field:='t';axes:=jsonb_build_object('market_session_new_york',d);END IF;
 spec:=astra_ingestion_v1.backfill_nonminute_field_spec_v2(families[1],p_kind);
 IF p_kind='massive_news' THEN spec:=spec||'{"updated_utc":"timestamp"}'::jsonb;END IF;
 IF p_kind='alpaca_actions' AND families @> ARRAY['N03'] THEN spec:=spec||'{"ex_date":"date","old_rate":"positive","new_rate":"positive"}'::jsonb;END IF;
 -- Preserve hashes for every supplied field so unmodelled conflicts are not
 -- silently selected. Unknown field semantics are not called usable.
 SELECT COALESCE(jsonb_object_agg(f.key,jsonb_build_object('datatype',COALESCE(spec->>f.key,'undeclared'),
  'nonnull',p_row->f.key IS NOT NULL AND p_row->f.key<>'null'::jsonb,
  'value_sha256',CASE WHEN p_row ? f.key THEN encode(sha256(convert_to((p_row->f.key)::text,'UTF8')),'hex') ELSE 'ABSENT' END,
  'reason',astra_ingestion_v1.backfill_nonminute_field_reason_v2(p_row->f.key,COALESCE(spec->>f.key,'undeclared'),NULL))),'{}') INTO fields
 FROM(SELECT jsonb_object_keys(spec||p_row) key) f;
 RETURN jsonb_build_object('record_key',p_provider||':'||typ||':'||encode(sha256(convert_to(key_value::text,'UTF8')),'hex'),'row_sha256',row_hash,
  'provider',p_provider,'record_type',typ,'kind',p_kind,'record_group',grp,'provider_record_id',pid,'identity_basis',basis,
  'symbol',CASE WHEN typ='ARTICLE' THEN NULL WHEN typ='OPTION_DAILY_BAR' THEN p_symbol ELSE COALESCE(p_row->>'ticker',p_row->>'symbol',p_row->>'initiating_symbol') END,
  'market_date',d,'date_axes',axes,'primary_date_field',primary_date_field,
  'version_timestamp',astra_ingestion_v1.backfill_stamp_v2(COALESCE(p_row->>'updated_utc',p_row->>'updated_at')),
  'field_states',fields,'delivery_families',to_jsonb(families),'links',links);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_shared_refresh_v2(p_run text,p_keys jsonb) RETURNS void
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
BEGIN
 WITH versions AS MATERIALIZED(SELECT v.* FROM astra_ingestion_v1.backfill_shared_versions_v2 v
  JOIN jsonb_array_elements_text(p_keys) k ON v.record_key=k.value WHERE v.run_id=p_run),
 stats AS(SELECT record_key,count(*) versions,bool_and(version_timestamp IS NOT NULL) ordered,max(version_timestamp) latest FROM versions GROUP BY record_key),
 candidates AS MATERIALIZED(SELECT v.*,s.versions,s.ordered FROM versions v JOIN stats s USING(record_key) WHERE NOT s.ordered OR v.version_timestamp=s.latest),
 candidate_counts AS(SELECT record_key,count(*) n FROM candidates GROUP BY record_key),
 chosen AS(SELECT DISTINCT ON(record_key) * FROM candidates ORDER BY record_key,row_sha256,task_id,page_no,record_ordinal),
 votes AS(SELECT c.record_key,f.key field,count(*) n,count(DISTINCT f.value->>'value_sha256') values,
  bool_or((f.value->>'nonnull')::boolean) nonnull,min(f.value->>'datatype') datatype
  FROM candidates c CROSS JOIN LATERAL jsonb_each(c.field_states) f GROUP BY c.record_key,f.key),
 fields AS(SELECT c.record_key,jsonb_object_agg(v.field,COALESCE(c.field_states->v.field,jsonb_build_object('datatype',v.datatype,'nonnull',v.nonnull))||
  CASE WHEN v.n<n.n OR v.values>1 THEN jsonb_build_object('nonnull',v.nonnull,'reason','CONFLICTING_PROVIDER_RECORD_VERSIONS') ELSE '{}'::jsonb END) states,
  COALESCE(jsonb_agg(v.field ORDER BY v.field) FILTER(WHERE v.n<n.n OR v.values>1),'[]') conflicts
  FROM chosen c JOIN votes v USING(record_key) JOIN candidate_counts n USING(record_key) GROUP BY c.record_key),
 clean AS(SELECT c.*,n.n candidates,f.states,f.conflicts,
  (SELECT COALESCE(jsonb_object_agg(d.key,CASE WHEN f.conflicts ? CASE d.key WHEN 'publication_date_new_york' THEN c.primary_date_field WHEN 'market_session_new_york' THEN 't' ELSE d.key END THEN 'null'::jsonb ELSE d.value END),'{}') FROM jsonb_each(c.date_axes) d) clean_axes
  FROM chosen c JOIN fields f USING(record_key) JOIN candidate_counts n USING(record_key)),
 dated AS(SELECT c.*,a.first_date,a.last_date,COALESCE(a.in_target,false) in_target
  FROM clean c LEFT JOIN LATERAL(SELECT min((value#>>'{}')::date) first_date,max((value#>>'{}')::date) last_date,
   bool_or((value#>>'{}')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date) in_target FROM jsonb_each(c.clean_axes) WHERE value<>'null'::jsonb) a ON true),
 occurrences AS(SELECT o.record_key,count(*) n FROM astra_ingestion_v1.backfill_shared_occurrences_v2 o
  JOIN jsonb_array_elements_text(p_keys) k ON o.record_key=k.value WHERE o.run_id=p_run GROUP BY o.record_key)
 INSERT INTO astra_ingestion_v1.backfill_shared_records_v2
 SELECT p_run,c.record_key,c.row_sha256,c.provider,c.record_type,c.kind,c.record_group,c.provider_record_id,c.identity_basis,
  CASE WHEN c.record_type='ACTION' AND c.conflicts ?| ARRAY['ticker','symbol','initiating_symbol'] THEN NULL ELSE c.symbol END,
  CASE WHEN c.conflicts ? c.primary_date_field THEN NULL ELSE c.market_date END,c.clean_axes,c.primary_date_field,
  CASE WHEN c.in_target THEN 'TARGET' WHEN c.last_date<'2025-09-01'::date THEN 'SUPPORT' WHEN c.first_date>'2026-07-31'::date THEN 'AFTER_TARGET'
   WHEN c.first_date IS NOT NULL THEN 'BOUNDARY_SUPPORT' ELSE 'UNKNOWN_DATE' END,
  COALESCE(c.first_date<'2025-09-01'::date AND c.last_date>='2025-09-01'::date OR c.first_date<='2026-07-31'::date AND c.last_date>'2026-07-31'::date,false),
  COALESCE(NOT c.in_target AND c.first_date<'2025-09-01'::date AND c.last_date>'2026-07-31'::date,false),
  c.versions,c.candidates,c.ordered,o.n,c.conflicts,c.states,c.delivery_families,c.task_id,c.page_no,c.record_ordinal
 FROM dated c JOIN occurrences o USING(record_key)
 ON CONFLICT(run_id,record_key) DO UPDATE SET row_sha256=EXCLUDED.row_sha256,kind=EXCLUDED.kind,record_group=EXCLUDED.record_group,
  provider_record_id=EXCLUDED.provider_record_id,identity_basis=EXCLUDED.identity_basis,symbol=EXCLUDED.symbol,market_date=EXCLUDED.market_date,
  date_axes=EXCLUDED.date_axes,primary_date_field=EXCLUDED.primary_date_field,period=EXCLUDED.period,boundary_crossing=EXCLUDED.boundary_crossing,boundary_support=EXCLUDED.boundary_support,
  source_versions=EXCLUDED.source_versions,current_candidate_versions=EXCLUDED.current_candidate_versions,ordered_versions=EXCLUDED.ordered_versions,
  source_occurrences=EXCLUDED.source_occurrences,conflict_fields=EXCLUDED.conflict_fields,field_states=EXCLUDED.field_states,delivery_families=EXCLUDED.delivery_families,
  task_id=EXCLUDED.task_id,page_no=EXCLUDED.page_no,record_ordinal=EXCLUDED.record_ordinal;

 DELETE FROM astra_ingestion_v1.backfill_shared_links_v2 l USING jsonb_array_elements_text(p_keys) k WHERE l.run_id=p_run AND l.record_key=k.value;
 WITH vstat AS(SELECT v.record_key,max(version_timestamp) latest FROM astra_ingestion_v1.backfill_shared_versions_v2 v
  JOIN jsonb_array_elements_text(p_keys) k ON v.record_key=k.value WHERE v.run_id=p_run GROUP BY v.record_key),
 links AS(SELECT l.record_key,l.security_symbol,l.link_role,count(*) observed_versions,
  count(*) FILTER(WHERE NOT r.ordered_versions OR v.version_timestamp=s.latest) current_versions
  FROM astra_ingestion_v1.backfill_shared_version_links_v2 l JOIN astra_ingestion_v1.backfill_shared_records_v2 r USING(run_id,record_key)
  JOIN astra_ingestion_v1.backfill_shared_versions_v2 v ON v.run_id=l.run_id AND v.record_key=l.record_key AND v.row_sha256=l.row_sha256
  JOIN vstat s ON s.record_key=l.record_key
  WHERE l.run_id=p_run GROUP BY l.record_key,l.security_symbol,l.link_role)
 INSERT INTO astra_ingestion_v1.backfill_shared_links_v2
 SELECT p_run,l.record_key,l.security_symbol,l.link_role,l.observed_versions,l.current_versions,
  CASE WHEN l.current_versions=r.current_candidate_versions THEN 'PRESENT_IN_ALL_CURRENT_PROVIDER_VERSIONS'
   WHEN l.current_versions=0 THEN 'RETAINED_OLDER_PROVIDER_VERSION_LINK' ELSE 'CONFLICTING_PROVIDER_RECORD_LINK_VERSIONS' END,
  COALESCE(m.members,'[]'),CASE WHEN m.n=1 THEN 'UNRESOLVED_FROZEN_ANCHOR_CANDIDATE' WHEN m.n>1 THEN 'AMBIGUOUS_FROZEN_ANCHOR_CANDIDATES' ELSE 'OUTSIDE_FROZEN_ANCHOR_SET' END
 FROM links l JOIN astra_ingestion_v1.backfill_shared_records_v2 r ON r.run_id=p_run AND r.record_key=l.record_key
 LEFT JOIN LATERAL(SELECT count(*) n,jsonb_agg(member_id ORDER BY member_id) members FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=p_run AND m.anchor_ticker=l.security_symbol) m ON true;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_shared_project_v2(p_task text,p_page integer) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='12s' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;p astra_ingestion_v1.backfill_pages_v2;keys jsonb;old_summary jsonb;families text[];
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task;
 IF t.kind NOT IN('alpaca_news','massive_news','alpaca_actions','massive_dividends','massive_splits','alpaca_option_contracts','alpaca_option_bars') THEN RETURN jsonb_build_object('state','SEPARATE_FAMILY');END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(t.run_id,706314020261099));
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_shared_pages_v2 WHERE task_id=p_task AND page_no=p_page) THEN RETURN jsonb_build_object('state','ALREADY_PROJECTED');END IF;
 SELECT pg.* INTO STRICT p FROM astra_ingestion_v1.backfill_pages_v2 pg JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no)
  WHERE pg.task_id=p_task AND pg.page_no=p_page AND pg.body_sha256=b.body_sha256 AND b.body_sha256=b.readback_sha256 AND pg.record_count=b.actual_records;
 WITH rows AS MATERIALIZED(SELECT x.record_ordinal,astra_ingestion_v1.backfill_shared_meta_v2(t.provider,t.kind,x.record_group,x.symbol,x.source_row) m
  FROM astra_ingestion_v1.backfill_page_rows_v2(p_task,p_page) x),
 versions AS(INSERT INTO astra_ingestion_v1.backfill_shared_versions_v2
  SELECT DISTINCT ON(m->>'record_key',m->>'row_sha256') t.run_id,m->>'record_key',m->>'row_sha256',m->>'provider',m->>'record_type',m->>'kind',m->>'record_group',
   m->>'provider_record_id',m->>'identity_basis',m->>'symbol',(m->>'market_date')::date,m->'date_axes',m->>'primary_date_field',
   (m->>'version_timestamp')::timestamptz,m->'field_states',ARRAY(SELECT jsonb_array_elements_text(m->'delivery_families')),t.id,p_page,record_ordinal
  FROM rows ORDER BY m->>'record_key',m->>'row_sha256',record_ordinal ON CONFLICT DO NOTHING RETURNING record_key),
 occurrences AS(INSERT INTO astra_ingestion_v1.backfill_shared_occurrences_v2
  SELECT t.run_id,m->>'record_key',m->>'row_sha256',t.id,p_page,record_ordinal FROM rows ON CONFLICT DO NOTHING RETURNING record_key),
 links AS(INSERT INTO astra_ingestion_v1.backfill_shared_version_links_v2
  SELECT DISTINCT t.run_id,m->>'record_key',m->>'row_sha256',l->>'symbol',l->>'role' FROM rows CROSS JOIN LATERAL jsonb_array_elements(m->'links') l
  ON CONFLICT DO NOTHING RETURNING record_key)
 SELECT COALESCE(jsonb_agg(DISTINCT m->>'record_key'),'[]') INTO keys FROM rows;
 old_summary:=astra_ingestion_v1.backfill_shared_summary_v2(t.run_id,keys);
 PERFORM astra_ingestion_v1.backfill_shared_refresh_v2(t.run_id,keys);
 PERFORM astra_ingestion_v1.backfill_shared_apply_delta_v2(t.run_id,old_summary,astra_ingestion_v1.backfill_shared_summary_v2(t.run_id,keys));
 families:=CASE WHEN t.kind='alpaca_actions' THEN ARRAY['N02','N03'] ELSE ARRAY[t.family] END;
 INSERT INTO astra_ingestion_v1.backfill_shared_pages_v2(task_id,page_no,run_id,delivery_families,source_records) VALUES(t.id,p_page,t.run_id,families,p.record_count);
 RETURN jsonb_build_object('state','SHARED_RECORDS_PROJECTED','record_keys_touched',jsonb_array_length(keys),'source_occurrences',p.record_count);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_shared_readback_trigger_v2() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN PERFORM astra_ingestion_v1.backfill_shared_project_v2(NEW.task_id,NEW.page_no);RETURN NEW;END $$;
CREATE TRIGGER backfill_shared_readback_v2 AFTER INSERT ON astra_ingestion_v1.backfill_readbacks_v2
 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_shared_readback_trigger_v2();
CREATE FUNCTION astra_ingestion_v1.backfill_shared_maintain_v2(p_limit integer DEFAULT 4) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='15s' AS $$
DECLARE c astra_ingestion_v1.backfill_shared_cursor_v2;x record;n integer:=0;
BEGIN
 SELECT * INTO STRICT c FROM astra_ingestion_v1.backfill_shared_cursor_v2 WHERE singleton FOR UPDATE;
 FOR x IN SELECT verified_at,task_id,page_no FROM astra_ingestion_v1.backfill_readbacks_v2
  WHERE (verified_at,task_id,page_no)>(c.verified_at,c.task_id,c.page_no) ORDER BY verified_at,task_id,page_no LIMIT GREATEST(1,LEAST(p_limit,8)) LOOP
  PERFORM astra_ingestion_v1.backfill_shared_project_v2(x.task_id,x.page_no);
  UPDATE astra_ingestion_v1.backfill_shared_cursor_v2 SET verified_at=x.verified_at,task_id=x.task_id,page_no=x.page_no WHERE singleton;n:=n+1;
 END LOOP;RETURN n;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_shared_summary_v2(p_run text,p_keys jsonb) RETURNS jsonb
LANGUAGE sql STABLE SET search_path='' AS $$
 WITH touched AS MATERIALIZED(SELECT r.*,f.family,COALESCE(l.links,0) links,COALESCE(l.cohort_links,0) cohort_links
  FROM astra_ingestion_v1.backfill_shared_records_v2 r JOIN jsonb_array_elements_text(p_keys) k ON r.record_key=k.value
  CROSS JOIN LATERAL unnest(r.delivery_families) f(family)
  LEFT JOIN LATERAL(SELECT count(*) links,count(*) FILTER(WHERE jsonb_array_length(candidate_member_ids)>0) cohort_links
   FROM astra_ingestion_v1.backfill_shared_links_v2 l WHERE l.run_id=r.run_id AND l.record_key=r.record_key AND l.link_role='ARTICLE_SECURITY') l ON true
  WHERE r.run_id=p_run),
 counts AS(SELECT family,record_type,kind,period,count(*) records,sum(source_occurrences) occurrences,sum(source_versions) versions,
  count(*) FILTER(WHERE jsonb_array_length(conflict_fields)>0) conflicts,count(*) FILTER(WHERE identity_basis LIKE 'EXACT_CONTENT_FALLBACK%') fallback_keys,
  count(*) FILTER(WHERE boundary_crossing) boundary_crossing,count(*) FILTER(WHERE boundary_support) boundary_support,sum(links) links,sum(cohort_links) cohort_links
  FROM touched GROUP BY family,record_type,kind,period),
 fields AS(SELECT family,record_type,kind,period,f.key field,f.value->>'datatype' datatype,(f.value->>'nonnull')::boolean nonnull,
  COALESCE(f.value->>'reason','') reason,count(*) records FROM touched CROSS JOIN LATERAL jsonb_each(field_states) f
  GROUP BY family,record_type,kind,period,f.key,f.value->>'datatype',(f.value->>'nonnull')::boolean,COALESCE(f.value->>'reason','')),
 dates AS(SELECT family,record_type,f.key date_axis,CASE WHEN f.value='null'::jsonb THEN 'UNKNOWN_DATE'
  WHEN (f.value#>>'{}')::date<'2025-09-01'::date THEN 'SUPPORT' WHEN (f.value#>>'{}')::date>'2026-07-31'::date THEN 'AFTER_TARGET' ELSE 'TARGET' END period,count(*) records
  FROM touched CROSS JOIN LATERAL jsonb_each(date_axes) f GROUP BY family,record_type,f.key,4)
 SELECT jsonb_build_object('counts',(SELECT COALESCE(jsonb_agg(to_jsonb(c)),'[]') FROM counts c),
  'fields',(SELECT COALESCE(jsonb_agg(to_jsonb(f)),'[]') FROM fields f),'dates',(SELECT COALESCE(jsonb_agg(to_jsonb(d)),'[]') FROM dates d))
$$;

CREATE FUNCTION astra_ingestion_v1.backfill_shared_apply_delta_v2(p_run text,p_old jsonb,p_new jsonb) RETURNS void
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
BEGIN
 WITH delta AS(SELECT -1 sign,x.* FROM jsonb_to_recordset(p_old->'counts') x(family text,record_type text,kind text,period text,records bigint,occurrences bigint,versions bigint,conflicts bigint,fallback_keys bigint,boundary_crossing bigint,boundary_support bigint,links bigint,cohort_links bigint)
  UNION ALL SELECT 1,x.* FROM jsonb_to_recordset(p_new->'counts') x(family text,record_type text,kind text,period text,records bigint,occurrences bigint,versions bigint,conflicts bigint,fallback_keys bigint,boundary_crossing bigint,boundary_support bigint,links bigint,cohort_links bigint))
 INSERT INTO astra_ingestion_v1.backfill_shared_counts_v2
 SELECT p_run,family,record_type,kind,period,sum(sign*records),sum(sign*occurrences),sum(sign*versions),sum(sign*conflicts),sum(sign*fallback_keys),sum(sign*boundary_crossing),sum(sign*boundary_support),sum(sign*links),sum(sign*cohort_links)
 FROM delta GROUP BY family,record_type,kind,period
 ON CONFLICT(run_id,family,record_type,kind,period) DO UPDATE SET records=backfill_shared_counts_v2.records+EXCLUDED.records,
  occurrences=backfill_shared_counts_v2.occurrences+EXCLUDED.occurrences,versions=backfill_shared_counts_v2.versions+EXCLUDED.versions,
  conflicts=backfill_shared_counts_v2.conflicts+EXCLUDED.conflicts,fallback_keys=backfill_shared_counts_v2.fallback_keys+EXCLUDED.fallback_keys,
  boundary_crossing=backfill_shared_counts_v2.boundary_crossing+EXCLUDED.boundary_crossing,boundary_support=backfill_shared_counts_v2.boundary_support+EXCLUDED.boundary_support,
  links=backfill_shared_counts_v2.links+EXCLUDED.links,cohort_links=backfill_shared_counts_v2.cohort_links+EXCLUDED.cohort_links;
 WITH delta AS(SELECT -1 sign,x.* FROM jsonb_to_recordset(p_old->'fields') x(family text,record_type text,kind text,period text,field text,datatype text,nonnull boolean,reason text,records bigint)
  UNION ALL SELECT 1,x.* FROM jsonb_to_recordset(p_new->'fields') x(family text,record_type text,kind text,period text,field text,datatype text,nonnull boolean,reason text,records bigint))
 INSERT INTO astra_ingestion_v1.backfill_shared_fields_v2
 SELECT p_run,family,record_type,kind,period,field,datatype,nonnull,reason,sum(sign*records) FROM delta GROUP BY family,record_type,kind,period,field,datatype,nonnull,reason
 ON CONFLICT(run_id,family,record_type,kind,period,field,datatype,nonnull,reason) DO UPDATE SET records=backfill_shared_fields_v2.records+EXCLUDED.records;
 WITH delta AS(SELECT -1 sign,x.* FROM jsonb_to_recordset(p_old->'dates') x(family text,record_type text,date_axis text,period text,records bigint)
  UNION ALL SELECT 1,x.* FROM jsonb_to_recordset(p_new->'dates') x(family text,record_type text,date_axis text,period text,records bigint))
 INSERT INTO astra_ingestion_v1.backfill_shared_dates_v2
 SELECT p_run,family,record_type,date_axis,period,sum(sign*records) FROM delta GROUP BY family,record_type,date_axis,period
 ON CONFLICT(run_id,family,record_type,date_axis,period) DO UPDATE SET records=backfill_shared_dates_v2.records+EXCLUDED.records;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_shared_counts_v2 WHERE run_id=p_run AND LEAST(records,occurrences,versions,conflicts,fallback_keys,boundary_crossing,boundary_support,links,cohort_links)<0)
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_shared_fields_v2 WHERE run_id=p_run AND records<0)
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_shared_dates_v2 WHERE run_id=p_run AND records<0) THEN RAISE EXCEPTION 'Shared logical counters became negative';END IF;
END $$;

CREATE VIEW astra_ingestion_v1.backfill_shared_field_coverage_v2 WITH(security_invoker=true) AS
 WITH cells AS(SELECT * FROM astra_ingestion_v1.backfill_shared_fields_v2 WHERE records>0),
 reasons AS(SELECT run_id,family,record_type,kind,period,field,reason,sum(records) records FROM cells WHERE reason<>'' GROUP BY run_id,family,record_type,kind,period,field,reason)
 SELECT c.run_id,c.family,c.record_type,'SOURCE'::text observation_role,c.kind source_variant,c.period,c.field,c.datatype,
  'DATA'::text field_role,sum(c.records) observed_field_slots,sum(c.records) FILTER(WHERE nonnull) nonnull_values,
  COALESCE(sum(c.records) FILTER(WHERE reason=''),0) usable_values,COALESCE(sum(c.records) FILTER(WHERE NOT nonnull),0) missing_values,
  COALESCE(sum(c.records) FILTER(WHERE nonnull AND reason<>''),0) unusable_present_values,
  (SELECT COALESCE(jsonb_object_agg(r.reason,r.records),'{}') FROM reasons r WHERE (r.run_id,r.family,r.record_type,r.kind,r.period,r.field)=(c.run_id,c.family,c.record_type,c.kind,c.period,c.field)) null_or_unusable_reasons,
  NULL::bigint expected_applicable_field_slots,NULL::numeric coverage_fraction,
  'ONE_CURRENT_PROVIDER_RECORD_KEY_VALUE_LEVEL_ONLY_NOT_HISTORICAL_IDENTITY_OR_AVAILABILITY_CERTIFIED'::text usability_basis
 FROM cells c GROUP BY c.run_id,c.family,c.record_type,c.kind,c.period,c.field,c.datatype;

-- The original is parsed once per explicit page read, not once per article.
-- Its bytes and every source version remain available through the old receipt.
CREATE FUNCTION astra_ingestion_v1.backfill_shared_read_page_v2(p_task text,p_page integer,p_family text)
RETURNS SETOF astra_ingestion_v1.backfill_source_records_v2
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT r.run_id,p_family,r.kind,r.provider,r.task_id,r.page_no,r.record_ordinal,
  COALESCE(m.members,CASE WHEN r.record_type='OPTION_DAILY_BAR' THEN t.scope->'member_ids' END,'[]'::jsonb) member_ids,r.symbol,r.market_date,CASE WHEN r.record_type='OPTION_DAILY_BAR' THEN 'DAILY' ELSE NULL END session,
  r.period='TARGET' target_window,'UNRESOLVED_FROZEN_ANCHOR_CANDIDATE'::text identity_status,
  CASE WHEN r.record_type='OPTION_DAILY_BAR' THEN 'PROVIDER_OPTION_CONTRACT' ELSE NULL END price_basis,r.record_group,
  x.source_row||COALESCE((SELECT jsonb_object_agg(value,'null'::jsonb) FROM jsonb_array_elements_text(r.conflict_fields)),'{}')||
   jsonb_build_object('_shared_record',jsonb_build_object('record_key',r.record_key,'record_type',r.record_type,'identity_basis',r.identity_basis,
    'conflict_fields',r.conflict_fields,'date_axes',r.date_axes,'period',r.period,'boundary_crossing',r.boundary_crossing,'boundary_support',r.boundary_support)) source_row,
  p.body_sha256,p.fetched_at,p.committed_at,p.quality||CASE WHEN jsonb_array_length(r.conflict_fields)>0 THEN '["CONFLICTING_PROVIDER_RECORD_VERSIONS"]'::jsonb ELSE '[]'::jsonb END quality,
  jsonb_build_object('task_id',r.task_id,'page_no',r.page_no,'record_ordinal',r.record_ordinal,'body_sha256',p.body_sha256,
   'record_key',r.record_key,'source_row_sha256',r.row_sha256,'source_versions',r.source_versions,'current_candidate_versions',r.current_candidate_versions,
   'source_occurrences',r.source_occurrences,'ordered_provider_update_versions',r.ordered_versions,
   'member_ids_basis',CASE WHEN m.members IS NULL AND r.record_type='OPTION_DAILY_BAR' THEN 'SOURCE_QUERY_MEMBER_SCOPE_NOT_HISTORICAL_ATTRIBUTION' ELSE 'PROVIDER_REPORTED_SECURITY_LINK_FROZEN_ANCHOR_CANDIDATES_NOT_HISTORICAL_ATTRIBUTION' END,
   'cross_provider_matching','NOT_ASSERTED') lineage
 FROM astra_ingestion_v1.backfill_pages_v2 p JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=p.task_id
 CROSS JOIN LATERAL astra_ingestion_v1.backfill_page_rows_v2(p.task_id,p.page_no) x
 JOIN astra_ingestion_v1.backfill_shared_records_v2 r ON r.task_id=p.task_id AND r.page_no=p.page_no AND r.record_ordinal=x.record_ordinal
 LEFT JOIN LATERAL(SELECT jsonb_agg(DISTINCT member ORDER BY member) members FROM(
  SELECT l.candidate_member_ids FROM astra_ingestion_v1.backfill_shared_links_v2 l WHERE l.run_id=r.run_id AND l.record_key=r.record_key
  UNION ALL SELECT l.candidate_member_ids FROM astra_ingestion_v1.backfill_shared_records_v2 cr
   JOIN astra_ingestion_v1.backfill_shared_links_v2 l ON l.run_id=cr.run_id AND l.record_key=cr.record_key AND l.link_role='CONTRACT_UNDERLYING'
   WHERE r.record_type='OPTION_DAILY_BAR' AND cr.run_id=r.run_id AND cr.provider=r.provider AND cr.symbol=r.symbol AND cr.record_type='CONTRACT_REFERENCE'
  ) links CROSS JOIN LATERAL jsonb_array_elements_text(links.candidate_member_ids) member) m ON true
 WHERE p.task_id=p_task AND p.page_no=p_page AND p_family=ANY(r.delivery_families)
$$;
DO $views$ DECLARE f text;BEGIN
 FOREACH f IN ARRAY ARRAY['N01','N02','N03','CTX02'] LOOP
  EXECUTE format('CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_%s_v2 WITH(security_invoker=true) AS SELECT x.* FROM astra_ingestion_v1.backfill_shared_pages_v2 p CROSS JOIN LATERAL astra_ingestion_v1.backfill_shared_read_page_v2(p.task_id,p.page_no,%L) x WHERE %L=ANY(p.delivery_families)',lower(f),f,f);
 END LOOP;
END $views$;
CREATE VIEW astra_ingestion_v1.backfill_article_security_links_v2 WITH(security_invoker=true) AS
 SELECT l.run_id,r.provider,r.provider_record_id article_provider_id,r.record_key article_key,l.security_symbol,l.link_role,
  l.observed_versions,l.current_candidate_versions,l.link_state,l.candidate_member_ids,l.identity_state,
  false historical_attribution_certified,false strict_historical_availability_certified
 FROM astra_ingestion_v1.backfill_shared_links_v2 l JOIN astra_ingestion_v1.backfill_shared_records_v2 r USING(run_id,record_key)
 WHERE r.record_type='ARTICLE' AND l.link_role='ARTICLE_SECURITY';
CREATE VIEW astra_ingestion_v1.backfill_contract_underlying_links_v2 WITH(security_invoker=true) AS
 SELECT l.run_id,r.provider,CASE WHEN r.conflict_fields ? 'id' THEN NULL ELSE r.provider_record_id END contract_provider_id,r.symbol contract_symbol,r.record_key contract_key,
  l.security_symbol underlying_symbol,l.observed_versions,l.current_candidate_versions,l.link_state,l.candidate_member_ids,l.identity_state,
  false historical_enumeration_completeness_certified
 FROM astra_ingestion_v1.backfill_shared_links_v2 l JOIN astra_ingestion_v1.backfill_shared_records_v2 r USING(run_id,record_key)
 WHERE r.record_type='CONTRACT_REFERENCE' AND l.link_role='CONTRACT_UNDERLYING';
CREATE VIEW astra_ingestion_v1.backfill_option_bar_underlying_links_v2 WITH(security_invoker=true) AS
 SELECT b.run_id,b.provider,b.record_key option_bar_key,b.symbol contract_symbol,b.market_date,
  c.contract_key,c.contract_provider_id,c.underlying_symbol,c.link_state,c.candidate_member_ids,c.identity_state,
  false historical_attribution_certified
 FROM astra_ingestion_v1.backfill_shared_records_v2 b JOIN astra_ingestion_v1.backfill_contract_underlying_links_v2 c
  ON c.run_id=b.run_id AND c.provider=b.provider AND c.contract_symbol=b.symbol WHERE b.record_type='OPTION_DAILY_BAR';

CREATE VIEW astra_ingestion_v1.backfill_shared_family_summary_v2 WITH(security_invoker=true) AS
 SELECT run_id,family,sum(records) unique_provider_record_keys,
  COALESCE(sum(records) FILTER(WHERE record_type='ARTICLE'),0) unique_articles,
  COALESCE(sum(records) FILTER(WHERE record_type='CONTRACT_REFERENCE'),0) unique_contract_references,
  COALESCE(sum(records-fallback_keys) FILTER(WHERE record_type='OPTION_DAILY_BAR' AND period<>'UNKNOWN_DATE'),0) unique_contract_session_bars,
  COALESCE(sum(CASE WHEN period='UNKNOWN_DATE' THEN records ELSE fallback_keys END) FILTER(WHERE record_type='OPTION_DAILY_BAR'),0) non_session_option_bar_records,
  COALESCE(sum(records) FILTER(WHERE record_type<>'CONTRACT_REFERENCE'),0) primary_records,
  COALESCE(sum(records) FILTER(WHERE record_type<>'CONTRACT_REFERENCE' AND period='TARGET'),0) target_records,
  COALESCE(sum(records) FILTER(WHERE record_type<>'CONTRACT_REFERENCE' AND period IN('SUPPORT','BOUNDARY_SUPPORT')),0) support_records,
  COALESCE(sum(records) FILTER(WHERE record_type<>'CONTRACT_REFERENCE' AND period='AFTER_TARGET'),0) after_target_records,
  COALESCE(sum(records) FILTER(WHERE record_type<>'CONTRACT_REFERENCE' AND period='UNKNOWN_DATE'),0) unknown_date_records,
  sum(occurrences) verified_source_occurrences,sum(versions) source_versions,sum(conflicts) conflicting_records,sum(fallback_keys) fallback_content_keys,
  sum(links) article_security_links,sum(cohort_links) cohort_candidate_article_links,
  sum(boundary_crossing) boundary_crossing_events,sum(boundary_support) boundary_support_events
 FROM astra_ingestion_v1.backfill_shared_counts_v2 GROUP BY run_id,family;
CREATE VIEW astra_ingestion_v1.backfill_shared_action_work_v2 WITH(security_invoker=true) AS
 SELECT run_id,count(*) planned_units,count(*) FILTER(WHERE status IN('PENDING','RUNNING','RETRY_WAIT')) open_units,
  count(*) FILTER(WHERE status='OPERATIONAL_ERROR') operational_error_units,count(*) FILTER(WHERE status='BLOCKED_EXTERNAL') blocked_units,
  count(*) FILTER(WHERE status IN('NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED')) documented_gap_units
 FROM astra_ingestion_v1.backfill_tasks_v2 WHERE kind='alpaca_actions' GROUP BY run_id;

DO $wire$
DECLARE d text;cols text;b text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_shared_maintain_v2')>0 OR strpos(d,' FOR p IN SELECT pg.task_id')=0 THEN RAISE EXCEPTION 'Shared projection monitor baseline differs';END IF;
 d:=replace(d,' FOR p IN SELECT pg.task_id',E' PERFORM astra_ingestion_v1.backfill_shared_maintain_v2(4);\n FOR p IN SELECT pg.task_id');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_try_finalize_v2(text)'::regprocedure) INTO STRICT d;
 IF strpos(d,'  v_coverage_unknown:=')=0 THEN RAISE EXCEPTION 'Shared projection finalizer baseline differs';END IF;
 d:=replace(d,'  v_coverage_unknown:=',E'  IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_nonminute_pages_v2 n WHERE n.run_id=r.id AND n.kind IN(''alpaca_news'',''massive_news'',''alpaca_actions'',''massive_dividends'',''massive_splits'',''alpaca_option_contracts'',''alpaca_option_bars'') AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_shared_pages_v2 s WHERE s.task_id=n.task_id AND s.page_no=n.page_no)) THEN RETURN jsonb_build_object(''state'',''SHARED_RECORD_PROJECTION_PENDING'');END IF;\n  v_coverage_unknown:=');
 d:=replace(d,'  v_state:=CASE WHEN v_gaps OR v_coverage_unknown',E'  v_gaps:=v_gaps OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_shared_counts_v2 WHERE run_id=r.id AND (conflicts>0 OR fallback_keys>0));\n  v_state:=CASE WHEN v_gaps OR v_coverage_unknown');EXECUTE d;
 SELECT pg_get_viewdef('astra_ingestion_v1.backfill_family_status_v2'::regclass,true) INTO STRICT b;
 SELECT string_agg(CASE
  WHEN a.attname IN('committed_records','dated_target_records','support_records','unknown_date_records') THEN
   format('CASE WHEN old.family IN(''N01'',''N02'',''N03'',''CTX02'') THEN COALESCE(s.%I,0)::%s ELSE old.%I END AS %I',CASE a.attname WHEN 'committed_records' THEN 'primary_records' WHEN 'dated_target_records' THEN 'target_records' ELSE a.attname END,format_type(a.atttypid,a.atttypmod),a.attname,a.attname)
  WHEN a.attname='work_completion' THEN
   'CASE WHEN old.family=''N03'' AND COALESCE(a.operational_error_units,0)>0 THEN ''PARTIAL_OPERATIONAL_FAILURE'' WHEN old.family=''N03'' AND old.work_completion<>''PARTIAL_OPERATIONAL_FAILURE'' AND COALESCE(a.blocked_units,0)>0 THEN ''BLOCKED_EXTERNAL'' WHEN old.work_completion IN(''COMPLETE'',''COMPLETE_WITH_DOCUMENTED_GAPS'') AND old.family=''N03'' AND COALESCE(a.open_units,0)>0 THEN ''IN_PROGRESS'' WHEN old.work_completion IN(''COMPLETE'',''COMPLETE_WITH_DOCUMENTED_GAPS'') AND COALESCE(p.pending_pages,0)>0 THEN ''READBACK_PENDING'' WHEN old.work_completion=''COMPLETE'' AND old.family=''N03'' AND COALESCE(a.documented_gap_units,0)>0 THEN ''COMPLETE_WITH_DOCUMENTED_GAPS'' ELSE old.work_completion END work_completion'
  WHEN a.attname='nonminute_coverage' THEN
   'CASE WHEN old.family IN(''N01'',''N02'',''N03'',''CTX02'') THEN old.nonminute_coverage||jsonb_build_object(''logical_output_records'',COALESCE(s.primary_records,0),''target_records'',COALESCE(s.target_records,0),''support_records'',COALESCE(s.support_records,0),''after_target_records'',COALESCE(s.after_target_records,0),''unknown_date_records'',COALESCE(s.unknown_date_records,0),''source_count_basis'',''PROVIDER_RECORD_KEYS_DEDUPLICATED_WITH_EXPLICIT_CONTENT_FALLBACKS_NO_CROSS_PROVIDER_MATCHING'',''variant_count_basis'',''PHYSICAL_PROVIDER_RECORD_OCCURRENCES'',''source_occurrence_fields'',old.nonminute_coverage->''fields'',''fields'',COALESCE(f.fields,''[]''::jsonb),''shared_records'',COALESCE(to_jsonb(s)-''run_id''-''family'',''{}''::jsonb)||jsonb_build_object(''historically_attributed_article_links'',0,''cross_provider_matching'',''NOT_ASSERTED'',''date_axes'',COALESCE(d.axes,''[]''::jsonb),''projection_pending_verified_pages'',COALESCE(p.pending_pages,0),''shared_action_workflows'',CASE WHEN old.family=''N03'' THEN to_jsonb(a)-''run_id'' ELSE NULL END,''expected_applicable_records'',NULL,''coverage_fraction'',NULL,''counts_additive_across_record_types'',false,''all_original_versions_retained'',true)) ELSE old.nonminute_coverage END nonminute_coverage'
  ELSE format('old.%I',a.attname) END,',' ORDER BY a.attnum) INTO cols
 FROM pg_attribute a WHERE a.attrelid='astra_ingestion_v1.backfill_family_status_v2'::regclass AND a.attnum>0 AND NOT a.attisdropped;
 EXECUTE 'CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_status_v2 WITH(security_invoker=true) AS WITH old AS ('||rtrim(b,';')||'), f AS ('||
  'SELECT run_id,family,jsonb_agg(to_jsonb(x)-''run_id''-''family'' ORDER BY record_type,source_variant,period,field) fields FROM astra_ingestion_v1.backfill_shared_field_coverage_v2 x GROUP BY run_id,family), d AS ('||
  'SELECT run_id,family,jsonb_agg(to_jsonb(x)-''run_id''-''family'' ORDER BY record_type,date_axis,period) axes FROM astra_ingestion_v1.backfill_shared_dates_v2 x WHERE records>0 GROUP BY run_id,family), p AS ('||
  'SELECT n.run_id,df.family,count(*) pending_pages FROM astra_ingestion_v1.backfill_nonminute_pages_v2 n CROSS JOIN LATERAL(SELECT n.family UNION ALL SELECT ''N03'' WHERE n.kind=''alpaca_actions'') df(family) WHERE n.kind IN(''alpaca_news'',''massive_news'',''alpaca_actions'',''massive_dividends'',''massive_splits'',''alpaca_option_contracts'',''alpaca_option_bars'') AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_shared_pages_v2 s WHERE s.task_id=n.task_id AND s.page_no=n.page_no) GROUP BY n.run_id,df.family)'||
  ' SELECT '||cols||' FROM old LEFT JOIN astra_ingestion_v1.backfill_shared_family_summary_v2 s ON s.run_id=old.run_id AND s.family=old.family LEFT JOIN f ON f.run_id=old.run_id AND f.family=old.family LEFT JOIN d ON d.run_id=old.run_id AND d.family=old.family LEFT JOIN p ON p.run_id=old.run_id AND p.family=old.family LEFT JOIN astra_ingestion_v1.backfill_shared_action_work_v2 a ON a.run_id=old.run_id';
END $wire$;

DO $acl$
DECLARE o record;f record;g record;
BEGIN
 FOR o IN SELECT c.* FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='astra_ingestion_v1'
  AND (c.relname LIKE 'backfill_shared_%_v2' OR c.relname IN('backfill_article_security_links_v2','backfill_contract_underlying_links_v2','backfill_option_bar_underlying_links_v2')) AND c.relkind IN('r','v') LOOP
  EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM PUBLIC',o.relname);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(o.relacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>o.relowner LOOP EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM %I',o.relname,g.rolname);END LOOP;
  IF o.relkind='r' THEN EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',o.relname);EXECUTE format('CREATE POLICY shared_read_v2 ON astra_ingestion_v1.%I FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true)',o.relname);END IF;
  EXECUTE format('GRANT SELECT ON TABLE astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',o.relname);
 END LOOP;
 FOR f IN SELECT p.*,pg_get_function_identity_arguments(p.oid) args FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='astra_ingestion_v1' AND p.proname LIKE 'backfill_shared_%_v2' LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM PUBLIC',f.proname,f.args);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(f.proacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>f.proowner LOOP EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM %I',f.proname,f.args,g.rolname);END LOOP;
  EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.%I(%s) TO astra_ingestion_rpc_owner_v1',f.proname,f.args);
 END LOOP;
END $acl$;
COMMIT;
