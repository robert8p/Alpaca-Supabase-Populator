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
 chosen_fields AS MATERIALIZED(SELECT c.record_key,f.key field,f.value field_state FROM chosen c CROSS JOIN LATERAL jsonb_each(c.field_states) f),
 fields AS MATERIALIZED(SELECT c.record_key,jsonb_object_agg(v.field,COALESCE(cf.field_state,jsonb_build_object('datatype',v.datatype,'nonnull',v.nonnull))||
  CASE WHEN v.n<n.n OR v.values>1 THEN jsonb_build_object('nonnull',v.nonnull,'reason','CONFLICTING_PROVIDER_RECORD_VERSIONS') ELSE '{}'::jsonb END) states,
  COALESCE(jsonb_agg(v.field ORDER BY v.field) FILTER(WHERE v.n<n.n OR v.values>1),'[]') conflicts
  FROM chosen c JOIN votes v USING(record_key) JOIN candidate_counts n USING(record_key)
  LEFT JOIN chosen_fields cf ON cf.record_key=c.record_key AND cf.field=v.field GROUP BY c.record_key),
 clean AS MATERIALIZED(SELECT c.*,n.n candidates,f.states,f.conflicts,
  (SELECT COALESCE(jsonb_object_agg(d.key,CASE WHEN f.conflicts ? CASE d.key WHEN 'publication_date_new_york' THEN c.primary_date_field WHEN 'market_session_new_york' THEN 't' ELSE d.key END THEN 'null'::jsonb ELSE d.value END),'{}') FROM jsonb_each(c.date_axes) d) clean_axes
  FROM chosen c JOIN fields f USING(record_key) JOIN candidate_counts n USING(record_key)),
 dated AS MATERIALIZED(SELECT c.*,a.first_date,a.last_date,COALESCE(a.in_target,false) in_target
  FROM clean c LEFT JOIN LATERAL(SELECT min((value#>>'{}')::date) first_date,max((value#>>'{}')::date) last_date,
   bool_or((value#>>'{}')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date) in_target FROM jsonb_each(c.clean_axes) WHERE value<>'null'::jsonb) a ON true),
 occurrences AS MATERIALIZED(SELECT k.record_key,count(*) n FROM keys k CROSS JOIN LATERAL(
  SELECT 1 FROM astra_ingestion_v1.backfill_shared_occurrences_v2 o
  WHERE o.run_id=p_run AND o.record_key=k.record_key OFFSET 0) o GROUP BY k.record_key)

 SELECT p_run,c.record_key,c.row_sha256,c.provider,c.record_type,c.kind,c.record_group,c.provider_record_id,c.identity_basis,
  CASE WHEN c.record_type='ACTION' AND c.conflicts ?| ARRAY['ticker','symbol','initiating_symbol'] THEN NULL ELSE c.symbol END,
  CASE WHEN c.conflicts ? c.primary_date_field THEN NULL ELSE c.market_date END,c.clean_axes,c.primary_date_field,
  CASE WHEN c.in_target THEN 'TARGET' WHEN c.last_date<'2025-09-01'::date THEN 'SUPPORT' WHEN c.first_date>'2026-07-31'::date THEN 'AFTER_TARGET'
   WHEN c.first_date IS NOT NULL THEN 'BOUNDARY_SUPPORT' ELSE 'UNKNOWN_DATE' END,
  COALESCE(c.first_date<'2025-09-01'::date AND c.last_date>='2025-09-01'::date OR c.first_date<='2026-07-31'::date AND c.last_date>'2026-07-31'::date,false),
  COALESCE(NOT c.in_target AND c.first_date<'2025-09-01'::date AND c.last_date>'2026-07-31'::date,false),
  c.versions,c.candidates,c.ordered,o.n,c.conflicts,c.states,c.delivery_families,c.task_id,c.page_no,c.record_ordinal
 FROM dated c JOIN occurrences o USING(record_key)
