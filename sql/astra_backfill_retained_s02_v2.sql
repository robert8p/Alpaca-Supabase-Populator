-- Bounded July S02 source references in the existing replacement queue.
-- No original archive changes, no new provider requests, no closure of the
-- outstanding Massive acquisition or credential dependency.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $preflight$ BEGIN
 IF to_regclass('astra_ingestion_v1.backfill_nonminute_pages_v2') IS NULL
 OR to_regclass('population_top3000_202608_202609_v1.massive_shortinterest_record_v1') IS NULL
 OR to_regclass('population_top3000_202608_202609_v1.source_document') IS NULL THEN
  RAISE EXCEPTION 'Retained S02 requires current identity/non-minute delivery and admitted source archives'; END IF;
END $preflight$;

CREATE TABLE astra_ingestion_v1.backfill_s02_seed_cursor_v2(run_id text PRIMARY KEY REFERENCES astra_ingestion_v1.backfill_runs_v2(id),next_page integer NOT NULL DEFAULT 1 CHECK(next_page BETWEEN 1 AND 46));
CREATE TABLE astra_ingestion_v1.backfill_s02_projection_cursor_v2(singleton boolean PRIMARY KEY CHECK(singleton),verified_at timestamptz NOT NULL,task_id text NOT NULL,page_no integer NOT NULL);
INSERT INTO astra_ingestion_v1.backfill_s02_projection_cursor_v2 VALUES(true,'-infinity','',-1);
CREATE TABLE astra_ingestion_v1.backfill_s02_projection_v2(task_id text NOT NULL,page_no integer NOT NULL,PRIMARY KEY(task_id,page_no),FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_readbacks_v2(task_id,page_no));
CREATE TABLE astra_ingestion_v1.backfill_s02_occurrences_v2(
 run_id text NOT NULL,task_id text NOT NULL,page_no integer NOT NULL,record_ordinal integer NOT NULL,
 source_origin text NOT NULL CHECK(source_origin IN('RETAINED','FRESH')),member_id text NOT NULL,symbol text NOT NULL,settlement_date date NOT NULL,
 business_key text NOT NULL,row_sha256 text NOT NULL,archive_key text,archive_page integer,archive_row integer,source_id text,
 source_observed_at timestamptz NOT NULL,field_states jsonb NOT NULL,verified_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(task_id,page_no,record_ordinal,member_id),FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_readbacks_v2(task_id,page_no),
 FOREIGN KEY(run_id,member_id) REFERENCES astra_ingestion_v1.backfill_members_v2(run_id,member_id)
);
CREATE INDEX backfill_s02_business_v2 ON astra_ingestion_v1.backfill_s02_occurrences_v2(run_id,symbol,settlement_date,row_sha256);
CREATE TRIGGER backfill_s02_occurrences_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_s02_occurrences_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();
ALTER TABLE astra_ingestion_v1.backfill_readbacks_v2 ADD COLUMN retained_s02_verification jsonb;

CREATE FUNCTION astra_ingestion_v1.backfill_s02_source_check_v2(p_task text) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET TimeZone='UTC' SET statement_timeout='8s' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;r astra_ingestion_v1.backfill_runs_v2;
 p population_top3000_202608_202609_v1.massive_shortinterest_page_v1;
 d population_top3000_202608_202609_v1.source_document;b jsonb;v_candidates jsonb;v_members jsonb;v_digest text;v_bad bigint;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task;
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=t.run_id;
 IF t.kind<>'retained_massive_archive' OR t.family<>'S02' OR lower(t.provider)<>'reuse'
  OR r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR r.target_start<>'2025-09-01'::date OR r.target_end<>'2026-07-31'::date
  OR t.scope->>'archive_key' IS DISTINCT FROM 'massive-archive:S02:c1ed3ed6aa5bad110f122c2459ba27f6daa14a7ac484363d4915c0fc9ddb1f88'
  OR COALESCE(t.scope->>'archive_page','') !~ '^[1-9][0-9]?$' OR (t.scope->>'archive_page')::int NOT BETWEEN 1 AND 45
  OR t.scope->>'settlement_start' IS DISTINCT FROM '2026-07-15' OR t.scope->>'settlement_end' IS DISTINCT FROM '2026-07-31'
  OR t.scope->'preserve_provider_acquisition' IS DISTINCT FROM 'true'::jsonb THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='S02 retained source differs from its fixed admitted overlay scope'; END IF;
 SELECT * INTO STRICT p FROM population_top3000_202608_202609_v1.massive_shortinterest_page_v1
  WHERE archive_key=t.scope->>'archive_key' AND page_number=(t.scope->>'archive_page')::int;
 SELECT * INTO STRICT d FROM population_top3000_202608_202609_v1.source_document WHERE source_id=p.source_id;
 IF p.family_id<>'S02' OR p.source_id IS DISTINCT FROM t.scope->>'source_id' OR p.source_sha256 IS DISTINCT FROM t.scope->>'expected_source_sha256'
  OR p.normalized_at IS NULL OR p.result_count NOT BETWEEN 0 AND 1000 OR p.normalized_source_records IS DISTINCT FROM p.result_count
  OR COALESCE(p.wire_sha256,'')!~'^[0-9a-f]{64}$' OR COALESCE(p.wire_bytes,0) NOT BETWEEN 1 AND 8388608
  OR d.source_provider IS DISTINCT FROM 'Massive' OR d.source_sha256 IS DISTINCT FROM p.source_sha256
  OR d.content_text IS NULL OR d.content_bytes NOT BETWEEN 1 AND 8388608
  OR octet_length(d.content_text)::bigint IS DISTINCT FROM d.content_bytes
  OR encode(sha256(convert_to(d.content_text,'UTF8')),'hex') IS DISTINCT FROM p.source_sha256
  OR d.source_uri IS DISTINCT FROM p.request_url OR d.retrieved_at IS DISTINCT FROM p.retrieved_at
  OR d.source_published_at IS NOT NULL OR d.historical_received_at IS NOT NULL
  OR d.license_policy IS DISTINCT FROM 'EXISTING_MASSIVE_SUBSCRIPTION_API_RESPONSE_INTERNAL_USE'
  OR d.evidence->>'hash_representation' IS DISTINCT FROM 'EXACT_UTF8_RESPONSE_WITH_TOP_LEVEL_NEXT_URL_CREDENTIAL_REDACTION_ONLY'
  OR d.evidence->'wire_bytes_retained' IS DISTINCT FROM 'false'::jsonb
  OR d.evidence->'original_historical_receipt' IS DISTINCT FROM 'false'::jsonb
  OR d.evidence->>'wire_sha256' IS DISTINCT FROM p.wire_sha256
  OR d.evidence->>'wire_bytes' IS DISTINCT FROM p.wire_bytes::text
  OR d.evidence->>'stored_content_bytes' IS DISTINCT FROM d.content_bytes::text THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained S02 stored body, hash, byte count or receipt provenance changed'; END IF;
 IF p.page_number=1 AND p.request_url<>'https://api.massive.com/stocks/v1/short-interest?settlement_date.gte=2026-07-15&settlement_date.lte=2026-09-30&sort=settlement_date.asc,ticker.asc&limit=1000'
  OR p.page_number>1 AND (p.request_url!~'^https://api[.]massive[.]com/stocks/v1/short-interest[?]cursor=[A-Za-z0-9_.~%+\-]+$'
   OR NOT EXISTS(SELECT 1 FROM population_top3000_202608_202609_v1.massive_shortinterest_page_v1 prev WHERE prev.archive_key=p.archive_key AND prev.page_number=p.page_number-1 AND prev.next_url=p.request_url)) THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained S02 page request or preceding cursor edge differs'; END IF;
 PERFORM astra_ingestion_v1.rpc_json_unique(d.content_text::json);b:=d.content_text::jsonb;
 IF b->>'status' IS DISTINCT FROM 'OK' OR jsonb_typeof(b->'results') IS DISTINCT FROM 'array'
  OR jsonb_array_length(b->'results') IS DISTINCT FROM p.result_count OR b->>'next_url' IS DISTINCT FROM p.next_url
  OR (p.next_url IS NOT NULL AND p.next_url!~'^https://api[.]massive[.]com/stocks/v1/short-interest[?]cursor=[A-Za-z0-9_.~%+\-]+$') THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained S02 envelope, count or continuation differs'; END IF;
 SELECT count(*) INTO v_bad FROM jsonb_array_elements(b->'results') WITH ORDINALITY e(value,ord)
  LEFT JOIN population_top3000_202608_202609_v1.massive_shortinterest_record_v1 q ON q.archive_key=p.archive_key AND q.page_number=p.page_number AND q.source_row=e.ord
  WHERE jsonb_typeof(e.value)<>'object' OR q.source_id IS DISTINCT FROM p.source_id OR q.raw_record IS DISTINCT FROM e.value
   OR q.raw_record_sha256 IS DISTINCT FROM encode(sha256(convert_to(e.value::text,'UTF8')),'hex')
   OR q.unit_key IS DISTINCT FROM 'MassiveSI:record:'||q.raw_record_sha256
   OR q.source_record_key IS DISTINCT FROM CASE WHEN jsonb_typeof(e.value->'ticker')='string' AND length(e.value->>'ticker') BETWEEN 1 AND 64
     AND e.value->>'ticker'!~'[[:cntrl:][:space:]]' AND astra_ingestion_v1.backfill_date_v2(e.value->>'settlement_date') IS NOT NULL
    THEN 'MassiveSI:business:'||encode(sha256(convert_to(jsonb_build_array(e.value->>'ticker',astra_ingestion_v1.backfill_date_v2(e.value->>'settlement_date'))::text,'UTF8')),'hex')
    ELSE 'MassiveSI:unidentified:'||q.raw_record_sha256 END;
 IF v_bad<>0 OR (SELECT count(*) FROM population_top3000_202608_202609_v1.massive_shortinterest_record_v1 WHERE archive_key=p.archive_key AND page_number=p.page_number)<>p.result_count THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained S02 normalized row, business key, digest or full-page census differs'; END IF;
 WITH anchors AS(SELECT anchor_ticker,min(member_id) member_id FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=t.run_id GROUP BY anchor_ticker HAVING count(*)=1)
 SELECT COALESCE(jsonb_agg(jsonb_build_array(m.member_id,q.source_row,q.raw_record_sha256) ORDER BY q.source_row,m.member_id),'[]'),
  COALESCE(jsonb_agg(DISTINCT m.member_id ORDER BY m.member_id),'[]') INTO v_candidates,v_members
 FROM population_top3000_202608_202609_v1.massive_shortinterest_record_v1 q JOIN anchors m ON m.anchor_ticker=q.raw_record->>'ticker'
 WHERE q.archive_key=p.archive_key AND q.page_number=p.page_number AND astra_ingestion_v1.backfill_date_v2(q.raw_record->>'settlement_date') BETWEEN '2026-07-15'::date AND '2026-07-31'::date;
 IF v_members IS DISTINCT FROM (SELECT COALESCE(jsonb_agg(value ORDER BY value),'[]') FROM jsonb_array_elements(t.scope->'member_ids')) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='S02 candidate fixed-member set differs from its immutable task scope'; END IF;
 v_digest:=encode(sha256(convert_to(v_candidates::text,'UTF8')),'hex');
 RETURN jsonb_build_object('state','RETAINED_S02_SOURCE_VERIFIED','passed',true,'archive_key',p.archive_key,'archive_page',p.page_number,
  'source_id',p.source_id,'source_sha256',p.source_sha256,'stored_content_bytes',d.content_bytes,'wire_sha256',p.wire_sha256,
  'wire_bytes_retained',false,'hash_representation',d.evidence->>'hash_representation','source_request_url',p.request_url,
  'source_next_url',p.next_url,'source_observed_at',p.retrieved_at,'native_page_records',p.result_count,
  'referenced_candidate_records',jsonb_array_length(v_candidates),'candidate_digest',v_digest,
  'historical_attribution','UNRESOLVED_FROZEN_ANCHOR_CANDIDATE','publication_timestamp_supplied',false,
  'historical_receipt_certified',false,'full_replacement_query_satisfied',false,'original_archive_unchanged',true);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_massive_archive_read_v2(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;
BEGIN t:=astra_ingestion_v1.backfill_owned_v2(p_payload->'claim');RETURN astra_ingestion_v1.backfill_s02_source_check_v2(t.id);END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_massive_archive_commit_v2(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;p astra_ingestion_v1.backfill_pages_v2;proof jsonb;pointer jsonb;raw text;result jsonb;
BEGIN
 SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=p_payload#>>'{claim,id}' AND page_no=(p_payload#>>'{claim,page_no}')::int;
 IF FOUND THEN
  IF p.run_id IS DISTINCT FROM p_payload#>>'{claim,run_id}' OR p.generation::text IS DISTINCT FROM p_payload#>>'{claim,generation}'
   OR p.run_fence::text IS DISTINCT FROM p_payload#>>'{claim,run_fence}' OR p.raw_body::jsonb#>>'{rows,0,record_type}' IS DISTINCT FROM 'RETAINED_MASSIVE_SOURCE_POINTER' THEN
   RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Retained S02 acknowledgment belongs to another claim'; END IF;
  RETURN jsonb_build_object('state','already_committed','task_id',p.task_id,'page_no',p.page_no,'body_sha256',p.body_sha256,'record_count',1,
   'referenced_candidate_records',p.raw_body::jsonb#>'{rows,0,proof,referenced_candidate_records}'); END IF;
 t:=astra_ingestion_v1.backfill_owned_v2(p_payload->'claim');
 IF t.page_no<>0 OR t.cursor IS NOT NULL THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Each retained S02 task references exactly one original page'; END IF;
 proof:=astra_ingestion_v1.backfill_s02_source_check_v2(t.id);
 pointer:=jsonb_build_object('record_type','RETAINED_MASSIVE_SOURCE_POINTER','source_relation','population_top3000_202608_202609_v1.massive_shortinterest_record_v1','proof',proof);
 raw:=astra_ingestion_v1.rpc_canonical(jsonb_build_object('rows',jsonb_build_array(pointer)));
 result:=astra_ingestion_v1.backfill_dispatch_v2('backfill_commit',jsonb_build_object('claim',p_payload->'claim','raw_body',raw,
  'body_sha256',encode(sha256(convert_to(raw,'UTF8')),'hex'),'http_status',200,'fetched_at',clock_timestamp(),
  'request',jsonb_build_object('provider','REUSE','operation','VERIFY_EXISTING_MASSIVE_S02_PAGE','source_id',proof->'source_id'),
  'records',jsonb_build_array(pointer),'next_cursor',NULL,'terminal_state','IDENTITY_OR_QUALITY_UNRESOLVED',
  'quality',jsonb_build_array(jsonb_build_object('state','IDENTITY_OR_QUALITY_UNRESOLVED','reason','FROZEN_ANCHOR_CANDIDATE_ONLY_PUBLICATION_AND_HISTORICAL_ATTRIBUTION_UNRESOLVED',
    'provider_acquisition_remains_open',true,'full_replacement_query_satisfied',false)),
  'headers','{}'::jsonb,'adapter_version','fixed3000-retained-s02-v2.1'));
 RETURN result||jsonb_build_object('referenced_candidate_records',proof->'referenced_candidate_records','new_market_rows_written',0,'provider_requests',0);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_massive_archive_verify_v2(p_task text,p_page integer) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE p astra_ingestion_v1.backfill_pages_v2;proof jsonb;
BEGIN
 SELECT * INTO STRICT p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=p_task AND page_no=p_page;
 IF p_page<>0 OR p.record_count<>1 OR p.cursor_out IS NOT NULL OR lower(p.provider)<>'reuse'
  OR p.committed_at>=transaction_timestamp() OR encode(sha256(convert_to(p.raw_body,'UTF8')),'hex')<>p.body_sha256
  OR p.raw_body::jsonb#>>'{rows,0,record_type}' IS DISTINCT FROM 'RETAINED_MASSIVE_SOURCE_POINTER'
  OR encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(p.raw_body::jsonb->'rows'),'UTF8')),'hex')<>p.records_sha256 THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained S02 pointer envelope or independent-readback boundary differs'; END IF;
 proof:=astra_ingestion_v1.backfill_s02_source_check_v2(p_task);
 IF proof IS DISTINCT FROM p.raw_body::jsonb#>'{rows,0,proof}' THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained S02 source proof changed after commit'; END IF;
 RETURN proof;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_s02_seed_v2(p_run text,p_limit integer DEFAULT 2) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE r astra_ingestion_v1.backfill_runs_v2;c astra_ingestion_v1.backfill_s02_seed_cursor_v2;p record;members jsonb;symbols jsonb;scope jsonb;key text;n integer:=0;
BEGIN
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=p_run;
 IF r.status<>'ACTIVE' OR r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec' OR r.target_start<>'2025-09-01'::date OR r.target_end<>'2026-07-31'::date THEN RETURN 0; END IF;
 INSERT INTO astra_ingestion_v1.backfill_s02_seed_cursor_v2(run_id) VALUES(r.id) ON CONFLICT DO NOTHING;
 SELECT * INTO c FROM astra_ingestion_v1.backfill_s02_seed_cursor_v2 WHERE run_id=r.id FOR UPDATE;
 FOR p IN SELECT * FROM population_top3000_202608_202609_v1.massive_shortinterest_page_v1
  WHERE archive_key='massive-archive:S02:c1ed3ed6aa5bad110f122c2459ba27f6daa14a7ac484363d4915c0fc9ddb1f88'
   AND page_number>=c.next_page AND page_number<=45 ORDER BY page_number LIMIT GREATEST(1,LEAST(p_limit,8)) LOOP
  WITH anchors AS(SELECT anchor_ticker,min(member_id) member_id FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id GROUP BY anchor_ticker HAVING count(*)=1)
  SELECT COALESCE(jsonb_agg(DISTINCT m.member_id ORDER BY m.member_id),'[]'),COALESCE(jsonb_agg(DISTINCT m.anchor_ticker ORDER BY m.anchor_ticker),'[]') INTO members,symbols
   FROM population_top3000_202608_202609_v1.massive_shortinterest_record_v1 q JOIN anchors m ON m.anchor_ticker=q.raw_record->>'ticker'
   WHERE q.archive_key=p.archive_key AND q.page_number=p.page_number AND astra_ingestion_v1.backfill_date_v2(q.raw_record->>'settlement_date') BETWEEN '2026-07-15'::date AND '2026-07-31'::date;
  IF jsonb_array_length(members)>0 THEN
   scope:=jsonb_build_object('archive_key',p.archive_key,'archive_page',p.page_number,'source_id',p.source_id,'expected_source_sha256',p.source_sha256,
    'settlement_start','2026-07-15','settlement_end','2026-07-31','member_ids',members,'symbols',symbols,'preserve_provider_acquisition',true,'retained_overlay',true);
   key:='backfill-retained-s02-'||encode(sha256(convert_to(r.id||':'||p.archive_key||':'||p.page_number::text||':'||p.source_sha256,'UTF8')),'hex');
   INSERT INTO astra_ingestion_v1.backfill_tasks_v2(id,run_id,family,provider,kind,scope,priority,run_fence)
    VALUES(key,r.id,'S02','REUSE','retained_massive_archive',scope,80,r.fence) ON CONFLICT DO NOTHING;n:=n+1;
  END IF;
  UPDATE astra_ingestion_v1.backfill_s02_seed_cursor_v2 SET next_page=p.page_number+1 WHERE run_id=r.id;
 END LOOP;
 RETURN n;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_s02_project_v2(p_task text,p_page integer) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;p astra_ingestion_v1.backfill_pages_v2;proof jsonb;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task;
 IF t.family<>'S02' OR t.kind NOT IN('retained_massive_archive','massive_short_interest') OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_s02_projection_v2 WHERE task_id=p_task AND page_no=p_page) THEN RETURN; END IF;
 SELECT pg.* INTO STRICT p FROM astra_ingestion_v1.backfill_pages_v2 pg JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no) WHERE pg.task_id=p_task AND pg.page_no=p_page;
 IF t.kind='retained_massive_archive' THEN
  SELECT retained_s02_verification INTO proof FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE task_id=p_task AND page_no=p_page;
  IF proof->'passed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='S02 reference projection requires independent source readback'; END IF;
 END IF;
 WITH anchors AS(SELECT anchor_ticker,min(member_id) member_id FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=t.run_id GROUP BY anchor_ticker HAVING count(*)=1),
 rows AS MATERIALIZED(
  SELECT q.source_row ordinal,q.raw_record row,q.raw_record_sha256 row_sha,q.source_record_key business_key,q.source_id,
   (proof->>'source_observed_at')::timestamptz observed,q.archive_key,q.page_number archive_page,q.source_row archive_row
  FROM population_top3000_202608_202609_v1.massive_shortinterest_record_v1 q
  WHERE t.kind='retained_massive_archive' AND q.archive_key=t.scope->>'archive_key' AND q.page_number=(t.scope->>'archive_page')::int
  UNION ALL
  SELECT x.record_ordinal::int,x.source_row,encode(sha256(convert_to(x.source_row::text,'UTF8')),'hex'),
   'MassiveSI:business:'||encode(sha256(convert_to(jsonb_build_array(x.source_row->>'ticker',x.market_date)::text,'UTF8')),'hex'),NULL,p.fetched_at,NULL,NULL,NULL
  FROM astra_ingestion_v1.backfill_page_rows_v2(t.id,p_page) x WHERE t.kind='massive_short_interest'
 ), selected AS(
  SELECT q.*,m.member_id,m.anchor_ticker,astra_ingestion_v1.backfill_date_v2(q.row->>'settlement_date') settled FROM rows q JOIN anchors m ON m.anchor_ticker=q.row->>'ticker'
  WHERE (t.scope->'member_ids')?m.member_id AND astra_ingestion_v1.backfill_date_v2(q.row->>'settlement_date') BETWEEN '2025-09-01'::date AND '2026-07-31'::date
   AND (t.kind<>'retained_massive_archive' OR astra_ingestion_v1.backfill_date_v2(q.row->>'settlement_date')>='2026-07-15'::date)
 )
 INSERT INTO astra_ingestion_v1.backfill_s02_occurrences_v2(run_id,task_id,page_no,record_ordinal,source_origin,member_id,symbol,settlement_date,business_key,row_sha256,archive_key,archive_page,archive_row,source_id,source_observed_at,field_states)
 SELECT t.run_id,t.id,p_page,q.ordinal,CASE WHEN t.kind='retained_massive_archive' THEN 'RETAINED' ELSE 'FRESH' END,q.member_id,q.anchor_ticker,q.settled,q.business_key,q.row_sha,q.archive_key,q.archive_page,q.archive_row,q.source_id,q.observed,
  (SELECT jsonb_object_agg(f.key,jsonb_build_object('nonnull',v.value IS NOT NULL AND v.value<>'null'::jsonb,'reason',
    astra_ingestion_v1.backfill_nonminute_field_reason_v2(v.value,f.value,CASE WHEN f.key='publication_time' AND (v.value IS NULL OR v.value='null'::jsonb) THEN 'PUBLICATION_TIMESTAMP_NOT_SUPPLIED' END)))
   FROM jsonb_each_text(astra_ingestion_v1.backfill_nonminute_field_spec_v2('S02','massive_short_interest')) f
   CROSS JOIN LATERAL(SELECT astra_ingestion_v1.backfill_nonminute_field_value_v2(q.row,'SOURCE',f.key) value) v)
 FROM selected q ON CONFLICT DO NOTHING;
 INSERT INTO astra_ingestion_v1.backfill_s02_projection_v2 VALUES(t.id,p_page) ON CONFLICT DO NOTHING;
END $$;
CREATE FUNCTION astra_ingestion_v1.backfill_s02_readback_trigger_v2() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN PERFORM astra_ingestion_v1.backfill_s02_project_v2(NEW.task_id,NEW.page_no);RETURN NEW;END $$;
CREATE TRIGGER backfill_s02_readback_v2 AFTER INSERT ON astra_ingestion_v1.backfill_readbacks_v2 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_s02_readback_trigger_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_s02_maintain_v2() RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE r record;x record;c astra_ingestion_v1.backfill_s02_projection_cursor_v2;n integer:=0;
BEGIN
 FOR r IN SELECT id FROM astra_ingestion_v1.backfill_runs_v2 WHERE status='ACTIVE' ORDER BY created_at LIMIT 1 LOOP PERFORM astra_ingestion_v1.backfill_s02_seed_v2(r.id,2);END LOOP;
 SELECT * INTO STRICT c FROM astra_ingestion_v1.backfill_s02_projection_cursor_v2 WHERE singleton FOR UPDATE;
 FOR x IN SELECT verified_at,task_id,page_no FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE (verified_at,task_id,page_no)>(c.verified_at,c.task_id,c.page_no)
  ORDER BY verified_at,task_id,page_no LIMIT 8 LOOP
  PERFORM astra_ingestion_v1.backfill_s02_project_v2(x.task_id,x.page_no);
  UPDATE astra_ingestion_v1.backfill_s02_projection_cursor_v2 SET verified_at=x.verified_at,task_id=x.task_id,page_no=x.page_no WHERE singleton;n:=n+1;
 END LOOP;RETURN n;
END $$;

CREATE VIEW astra_ingestion_v1.backfill_s02_canonical_v2 WITH(security_invoker=true) AS
 WITH versions AS(SELECT run_id,symbol,settlement_date,count(DISTINCT row_sha256) versions,count(*) occurrences FROM astra_ingestion_v1.backfill_s02_occurrences_v2 GROUP BY run_id,symbol,settlement_date),
 ranked AS(SELECT o.*,row_number() OVER(PARTITION BY run_id,symbol,settlement_date ORDER BY (source_origin='FRESH') DESC,source_observed_at DESC,task_id,page_no,record_ordinal) rank FROM astra_ingestion_v1.backfill_s02_occurrences_v2 o)
 SELECT r.*,v.versions,v.occurrences FROM ranked r JOIN versions v USING(run_id,symbol,settlement_date) WHERE r.rank=1;
CREATE VIEW astra_ingestion_v1.backfill_s02_field_coverage_v2 WITH(security_invoker=true) AS
 WITH cells AS(SELECT c.run_id,f.key field,(f.value->>'nonnull')::boolean nonnull,
  CASE WHEN c.versions>1 AND f.key IN('short_interest','avg_daily_volume','days_to_cover') THEN 'CONFLICTING_RETAINED_OR_FRESH_SOURCE_VERSIONS' ELSE f.value->>'reason' END reason
  FROM astra_ingestion_v1.backfill_s02_canonical_v2 c CROSS JOIN LATERAL jsonb_each(c.field_states) f),
 reasons AS(SELECT run_id,field,reason,count(*) records FROM cells WHERE reason IS NOT NULL GROUP BY run_id,field,reason)
 SELECT c.run_id,c.field,count(*) observed_field_slots,count(*) FILTER(WHERE c.nonnull) nonnull_values,count(*) FILTER(WHERE reason IS NULL) usable_values,
  count(*) FILTER(WHERE NOT c.nonnull) missing_values,count(*) FILTER(WHERE c.nonnull AND reason IS NOT NULL) unusable_present_values,
  (SELECT COALESCE(jsonb_object_agg(r.reason,r.records),'{}') FROM reasons r WHERE r.run_id=c.run_id AND r.field=c.field) null_or_unusable_reasons,
  NULL::bigint expected_applicable_field_slots,NULL::numeric coverage_fraction,
  'SOURCE_VALUE_ONLY_UNRESOLVED_HISTORICAL_TICKER_ATTRIBUTION'::text usability_basis
 FROM cells c GROUP BY c.run_id,c.field;

CREATE FUNCTION astra_ingestion_v1.backfill_s02_retained_rows_v2(p_task text)
RETURNS TABLE(source_row integer,member_id text,symbol text,settlement_date date,raw_record jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE proof jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE task_id=p_task AND page_no=0 AND retained_s02_verification->'passed'='true'::jsonb) THEN RETURN;END IF;
 proof:=astra_ingestion_v1.backfill_massive_archive_verify_v2(p_task,0);
 RETURN QUERY SELECT o.archive_row,o.member_id,o.symbol,o.settlement_date,q.raw_record
  FROM astra_ingestion_v1.backfill_s02_occurrences_v2 o JOIN population_top3000_202608_202609_v1.massive_shortinterest_record_v1 q
   ON q.archive_key=o.archive_key AND q.page_number=o.archive_page AND q.source_row=o.archive_row
  WHERE o.task_id=p_task AND o.page_no=0 AND o.source_origin='RETAINED';
END $$;
CREATE VIEW astra_ingestion_v1.backfill_s02_all_records_v2 WITH(security_invoker=true) AS
 SELECT p.run_id,'S02'::text family,'retained_massive_archive'::text kind,'Massive'::text provider,p.task_id,p.page_no,x.source_row::bigint record_ordinal,
  jsonb_build_array(x.member_id) member_ids,x.symbol,x.settlement_date market_date,NULL::text session,true target_window,
  'UNRESOLVED_FROZEN_ANCHOR_CANDIDATE'::text identity_status,NULL::text price_basis,'RETAINED_MASSIVE_S02'::text record_group,x.raw_record source_row,
  p.body_sha256,p.fetched_at,p.committed_at,p.quality,
  jsonb_build_object('task_id',p.task_id,'page_no',0,'original_source_id',p.raw_body::jsonb#>'{rows,0,proof,source_id}',
   'original_source_sha256',p.raw_body::jsonb#>'{rows,0,proof,source_sha256}','original_source_row',x.source_row,'wire_bytes_retained',false,
   'historical_attribution','UNRESOLVED_FROZEN_ANCHOR_CANDIDATE','full_replacement_query_satisfied',false) lineage
 FROM astra_ingestion_v1.backfill_pages_v2 p JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=p.task_id AND t.kind='retained_massive_archive'
 CROSS JOIN LATERAL astra_ingestion_v1.backfill_s02_retained_rows_v2(t.id) x
 UNION ALL SELECT * FROM astra_ingestion_v1.backfill_source_records_v2 WHERE family='S02' AND kind='massive_short_interest';
CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_s02_v2 WITH(security_invoker=true) AS
 SELECT x.run_id,x.family,x.kind,x.provider,x.task_id,x.page_no,x.record_ordinal,x.member_ids,x.symbol,x.market_date,x.session,x.target_window,
  x.identity_status,x.price_basis,x.record_group,
  CASE WHEN c.versions>1 THEN x.source_row||jsonb_build_object('short_interest',NULL,'avg_daily_volume',NULL,'days_to_cover',NULL,'null_reason','CONFLICTING_RETAINED_OR_FRESH_SOURCE_VERSIONS') ELSE x.source_row END source_row,
  x.body_sha256,x.fetched_at,x.committed_at,x.quality,x.lineage||jsonb_build_object('distinct_source_value_versions',c.versions,'verified_occurrences',c.occurrences) lineage
 FROM astra_ingestion_v1.backfill_s02_all_records_v2 x JOIN astra_ingestion_v1.backfill_s02_canonical_v2 c
  ON c.task_id=x.task_id AND c.page_no=x.page_no AND c.record_ordinal=x.record_ordinal AND c.symbol=x.symbol AND c.settlement_date=x.market_date;

DO $wire$
DECLARE c record;d text;b text;v text;cols text;old_branch text:=' IF lower(p.provider)=''reuse'' AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 it WHERE it.id=p.task_id AND it.kind=''retained_identity'') THEN';
BEGIN
 FOR c IN SELECT conname,pg_get_constraintdef(oid) def FROM pg_constraint WHERE conrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%retained_reuse%' LOOP
  EXECUTE format('ALTER TABLE astra_ingestion_v1.backfill_tasks_v2 DROP CONSTRAINT %I',c.conname);
  EXECUTE 'ALTER TABLE astra_ingestion_v1.backfill_tasks_v2 ADD CONSTRAINT '||quote_ident(c.conname)||' '||replace(regexp_replace(c.def,' NOT VALID$',''),'''retained_reuse''::text','''retained_reuse''::text, ''retained_massive_archive''::text')||' NOT VALID';
 END LOOP;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_task_guard_v2()'::regprocedure) INTO d;
 d:=replace(d,' v_members:=NEW.scope->''member_ids'';',E' IF NEW.kind=''retained_massive_archive'' AND (NEW.family<>''S02'' OR lower(NEW.provider)<>''reuse'' OR NEW.scope->''preserve_provider_acquisition'' IS DISTINCT FROM ''true''::jsonb) THEN RAISE EXCEPTION ''Invalid retained S02 overlay'';END IF;\n v_members:=NEW.scope->''member_ids'';');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_snapshot_task_v2(text)'::regprocedure) INTO d;
 d:=replace(d,'OR t.kind=''retained_identity'' THEN RETURN false;','OR t.kind IN(''retained_identity'',''retained_massive_archive'') THEN RETURN false;');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO d;
 d:=replace(d,'''backfill_work''','''backfill_work'',''backfill_massive_archive_read'',''backfill_massive_archive_commit'',''backfill_massive_archive_verify''');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO d;
 d:=replace(d,' IF p_operation=''backfill_status'' THEN',E' IF p_operation=''backfill_massive_archive_read'' THEN RETURN astra_ingestion_v1.backfill_massive_archive_read_v2(p_payload);END IF;\n IF p_operation=''backfill_massive_archive_commit'' THEN RETURN astra_ingestion_v1.backfill_massive_archive_commit_v2(p_payload);END IF;\n IF p_operation=''backfill_massive_archive_verify'' THEN RETURN astra_ingestion_v1.backfill_massive_archive_verify_v2(p_payload->>''task_id'',(p_payload->>''page_no'')::int);END IF;\n IF p_operation=''backfill_status'' THEN');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_recheck_page_v2(text,integer)'::regprocedure) INTO d;
 IF strpos(d,old_branch)=0 OR strpos(d,'v_identity jsonb;')=0 OR strpos(d,'retained_identity_verification)')=0 OR strpos(d,',v_identity)')=0 THEN RAISE EXCEPTION 'Retained S02 verifier requires the current identity readback baseline';END IF;
 d:=replace(d,old_branch,' IF lower(p.provider)=''reuse'' AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 it WHERE it.id=p.task_id AND it.kind=''retained_reuse'') THEN');
 d:=replace(d,'v_identity jsonb;','v_identity jsonb;v_s02 jsonb;');
 d:=replace(d,' v_hash:=encode(sha256(convert_to(p.raw_body,''UTF8'')),''hex'');',E' v_hash:=encode(sha256(convert_to(p.raw_body,''UTF8'')),''hex'');\n IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 st WHERE st.id=p.task_id AND st.kind=''retained_massive_archive'') THEN v_s02:=astra_ingestion_v1.backfill_massive_archive_verify_v2(p.task_id,p.page_no);END IF;');
 d:=replace(d,'retained_identity_verification)','retained_identity_verification,retained_s02_verification)');d:=replace(d,',v_identity)',',v_identity,v_s02)');EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) INTO d;
 d:=replace(d,' FOR p IN SELECT pg.task_id',E' PERFORM astra_ingestion_v1.backfill_s02_maintain_v2();\n FOR p IN SELECT pg.task_id');EXECUTE d;
 SELECT pg_get_viewdef('astra_ingestion_v1.backfill_family_status_v2'::regclass,true) INTO b;
 SELECT string_agg(CASE WHEN a.attname IN('committed_records','dated_target_records','referenced_existing_records','referenced_qualifying_records') THEN
   format('CASE WHEN old.family=''S02'' THEN COALESCE(s.%I,0)::%s ELSE old.%I END AS %I',CASE WHEN a.attname IN('committed_records','dated_target_records') THEN 'records' ELSE 'retained_records' END,format_type(a.atttypid,a.atttypmod),a.attname,a.attname)
  WHEN a.attname='nonminute_coverage' THEN 'CASE WHEN old.family=''S02'' THEN old.nonminute_coverage||jsonb_build_object(''logical_output_records'',COALESCE(s.records,0),''target_records'',COALESCE(s.records,0),''referenced_source_observations'',COALESCE(s.retained_records,0),''verified_source_occurrences'',COALESCE(s.occurrences,0),''conflicting_source_records'',COALESCE(s.conflicts,0),''historically_attributed_records'',0,''historical_attribution'',''UNRESOLVED_FROZEN_ANCHOR_CANDIDATE'',''full_replacement_query_satisfied'',false,''fields'',COALESCE(f.fields,''[]''::jsonb)) ELSE old.nonminute_coverage END nonminute_coverage'
  ELSE format('old.%I',a.attname) END,',' ORDER BY a.attnum) INTO cols FROM pg_attribute a WHERE a.attrelid='astra_ingestion_v1.backfill_family_status_v2'::regclass AND a.attnum>0 AND NOT a.attisdropped;
 EXECUTE 'CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_status_v2 WITH(security_invoker=true) AS WITH old AS ('||rtrim(b,';')||'), s AS (SELECT run_id,count(*) records,count(*) FILTER(WHERE source_origin=''RETAINED'') retained_records,sum(occurrences) occurrences,count(*) FILTER(WHERE versions>1) conflicts FROM astra_ingestion_v1.backfill_s02_canonical_v2 GROUP BY run_id), f AS (SELECT run_id,jsonb_agg(to_jsonb(x)-''run_id'' ORDER BY field) fields FROM astra_ingestion_v1.backfill_s02_field_coverage_v2 x GROUP BY run_id) SELECT '||cols||' FROM old LEFT JOIN s ON s.run_id=old.run_id LEFT JOIN f ON f.run_id=old.run_id';
END $wire$;

DO $acl$
DECLARE o record;f record;g record;
BEGIN
 FOR o IN SELECT c.* FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='astra_ingestion_v1' AND c.relname LIKE 'backfill_s02_%_v2' AND c.relkind IN('r','v') LOOP
  EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM PUBLIC',o.relname);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(o.relacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>o.relowner LOOP EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM %I',o.relname,g.rolname);END LOOP;
  IF o.relkind='r' THEN EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',o.relname);EXECUTE format('CREATE POLICY s02_read_v2 ON astra_ingestion_v1.%I FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true)',o.relname);END IF;
  EXECUTE format('GRANT SELECT ON TABLE astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',o.relname);
 END LOOP;
 FOR f IN SELECT p.*,pg_get_function_identity_arguments(p.oid) args FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='astra_ingestion_v1' AND (p.proname LIKE 'backfill_s02_%_v2' OR p.proname LIKE 'backfill_massive_archive_%_v2') LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM PUBLIC',f.proname,f.args);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(f.proacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>f.proowner LOOP EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM %I',f.proname,f.args,g.rolname);END LOOP;
  EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.%I(%s) TO astra_ingestion_rpc_owner_v1',f.proname,f.args);
 END LOOP;
END $acl$;
COMMIT;
