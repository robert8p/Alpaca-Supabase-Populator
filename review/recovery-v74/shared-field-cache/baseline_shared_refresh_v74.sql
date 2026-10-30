CREATE OR REPLACE FUNCTION astra_ingestion_v1.backfill_shared_refresh_v2(p_run text, p_keys jsonb)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
BEGIN
 -- backfill_shared_refresh_bounded_keys_v2: bind each immutable archive lookup
 -- to one supplied key before joining compact intermediates. OFFSET0 keeps the
 -- parameterized key restriction from being flattened into a run-wide join.
 WITH keys AS MATERIALIZED(SELECT value record_key FROM jsonb_array_elements_text(p_keys)),
 versions AS MATERIALIZED(SELECT v.* FROM keys k CROSS JOIN LATERAL(
  SELECT v.* FROM astra_ingestion_v1.backfill_shared_versions_v2 v
  WHERE v.run_id=p_run AND v.record_key=k.record_key OFFSET 0) v),
 stats AS MATERIALIZED(SELECT record_key,count(*) versions,bool_and(version_timestamp IS NOT NULL) ordered,max(version_timestamp) latest FROM versions GROUP BY record_key),
 candidates AS MATERIALIZED(SELECT v.*,s.versions,s.ordered FROM versions v JOIN stats s USING(record_key) WHERE NOT s.ordered OR v.version_timestamp=s.latest),
 candidate_counts AS MATERIALIZED(SELECT record_key,count(*) n FROM candidates GROUP BY record_key),
 chosen AS MATERIALIZED(SELECT DISTINCT ON(record_key) * FROM candidates ORDER BY record_key,row_sha256,task_id,page_no,record_ordinal),
 votes AS MATERIALIZED(SELECT c.record_key,f.key field,count(*) n,count(DISTINCT f.value->>'value_sha256') values,
  bool_or((f.value->>'nonnull')::boolean) nonnull,min(f.value->>'datatype') datatype
  FROM candidates c CROSS JOIN LATERAL jsonb_each(c.field_states) f GROUP BY c.record_key,f.key),
 fields AS MATERIALIZED(SELECT c.record_key,jsonb_object_agg(v.field,COALESCE(c.field_states->v.field,jsonb_build_object('datatype',v.datatype,'nonnull',v.nonnull))||
  CASE WHEN v.n<n.n OR v.values>1 THEN jsonb_build_object('nonnull',v.nonnull,'reason','CONFLICTING_PROVIDER_RECORD_VERSIONS') ELSE '{}'::jsonb END) states,
  COALESCE(jsonb_agg(v.field ORDER BY v.field) FILTER(WHERE v.n<n.n OR v.values>1),'[]') conflicts
  FROM chosen c JOIN votes v USING(record_key) JOIN candidate_counts n USING(record_key) GROUP BY c.record_key),
 clean AS MATERIALIZED(SELECT c.*,n.n candidates,f.states,f.conflicts,
  (SELECT COALESCE(jsonb_object_agg(d.key,CASE WHEN f.conflicts ? CASE d.key WHEN 'publication_date_new_york' THEN c.primary_date_field WHEN 'market_session_new_york' THEN 't' ELSE d.key END THEN 'null'::jsonb ELSE d.value END),'{}') FROM jsonb_each(c.date_axes) d) clean_axes
  FROM chosen c JOIN fields f USING(record_key) JOIN candidate_counts n USING(record_key)),
 dated AS MATERIALIZED(SELECT c.*,a.first_date,a.last_date,COALESCE(a.in_target,false) in_target
  FROM clean c LEFT JOIN LATERAL(SELECT min((value#>>'{}')::date) first_date,max((value#>>'{}')::date) last_date,
   bool_or((value#>>'{}')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date) in_target FROM jsonb_each(c.clean_axes) WHERE value<>'null'::jsonb) a ON true),
 occurrences AS MATERIALIZED(SELECT k.record_key,count(*) n FROM keys k CROSS JOIN LATERAL(
  SELECT 1 FROM astra_ingestion_v1.backfill_shared_occurrences_v2 o
  WHERE o.run_id=p_run AND o.record_key=k.record_key OFFSET 0) o GROUP BY k.record_key)
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
 WITH keys AS MATERIALIZED(SELECT DISTINCT value record_key FROM jsonb_array_elements_text(p_keys)),
 scoped_versions AS MATERIALIZED(SELECT v.* FROM keys k CROSS JOIN LATERAL(
  SELECT v.record_key,v.row_sha256,v.version_timestamp FROM astra_ingestion_v1.backfill_shared_versions_v2 v
  WHERE v.run_id=p_run AND v.record_key=k.record_key OFFSET 0) v),
 scoped_records AS MATERIALIZED(SELECT r.* FROM keys k CROSS JOIN LATERAL(
  SELECT r.record_key,r.ordered_versions,r.current_candidate_versions FROM astra_ingestion_v1.backfill_shared_records_v2 r
  WHERE r.run_id=p_run AND r.record_key=k.record_key OFFSET 0) r),
 scoped_links AS MATERIALIZED(SELECT l.* FROM keys k CROSS JOIN LATERAL(
  SELECT l.record_key,l.row_sha256,l.security_symbol,l.link_role FROM astra_ingestion_v1.backfill_shared_version_links_v2 l
  WHERE l.run_id=p_run AND l.record_key=k.record_key OFFSET 0) l),
 vstat AS MATERIALIZED(SELECT record_key,max(version_timestamp) latest FROM scoped_versions GROUP BY record_key),
 links AS MATERIALIZED(SELECT l.record_key,l.security_symbol,l.link_role,count(*) observed_versions,
  count(*) FILTER(WHERE NOT r.ordered_versions OR v.version_timestamp=s.latest) current_versions
  FROM scoped_links l JOIN scoped_records r USING(record_key)
  JOIN scoped_versions v ON v.record_key=l.record_key AND v.row_sha256=l.row_sha256
  JOIN vstat s ON s.record_key=l.record_key
  GROUP BY l.record_key,l.security_symbol,l.link_role)
 INSERT INTO astra_ingestion_v1.backfill_shared_links_v2
 SELECT p_run,l.record_key,l.security_symbol,l.link_role,l.observed_versions,l.current_versions,
  CASE WHEN l.current_versions=r.current_candidate_versions THEN 'PRESENT_IN_ALL_CURRENT_PROVIDER_VERSIONS'
   WHEN l.current_versions=0 THEN 'RETAINED_OLDER_PROVIDER_VERSION_LINK' ELSE 'CONFLICTING_PROVIDER_RECORD_LINK_VERSIONS' END,
  COALESCE(m.members,'[]'),CASE WHEN m.n=1 THEN 'UNRESOLVED_FROZEN_ANCHOR_CANDIDATE' WHEN m.n>1 THEN 'AMBIGUOUS_FROZEN_ANCHOR_CANDIDATES' ELSE 'OUTSIDE_FROZEN_ANCHOR_SET' END
 FROM links l JOIN scoped_records r ON r.record_key=l.record_key
 LEFT JOIN LATERAL(SELECT count(*) n,jsonb_agg(member_id ORDER BY member_id) members FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=p_run AND m.anchor_ticker=l.security_symbol) m ON true;
END $function$
