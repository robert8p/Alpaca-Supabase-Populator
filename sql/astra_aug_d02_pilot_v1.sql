-- One private, one-shot D02 job. No legacy mutations, scheduling, provider calls,
-- new login, public RPC, or changes to the separate replacement-run dispatcher.
BEGIN;
SET LOCAL search_path = pg_catalog;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '20s';

CREATE TABLE astra_ingestion_v1.aug_d02_pilot_v1 (
 singleton boolean PRIMARY KEY CHECK (singleton),
 manifest_text text NOT NULL CHECK (octet_length(manifest_text) BETWEEN 2 AND 16384),
 manifest_sha text UNIQUE NOT NULL CHECK (manifest_sha = encode(sha256(convert_to(manifest_text,'UTF8')),'hex')),
 attempt uuid NOT NULL UNIQUE,
 deadline timestamptz NOT NULL,
 registered_by name NOT NULL DEFAULT session_user
);
CREATE TABLE astra_ingestion_v1.aug_d02_pilot_stop_v1 (
 singleton boolean PRIMARY KEY REFERENCES astra_ingestion_v1.aug_d02_pilot_v1(singleton),
 stopped_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TYPE astra_ingestion_v1.aug_d02_pilot_value_v1 AS (
 ordinal integer, company_id text, ticker text, composite_figi text, share_class_figi text,
 exchange_mic text, issue_type text, session_date date, raw_close numeric, raw_volume numeric,
 source_sha256 text, source_row integer, raw_record_sha256 text,
 identity_source_sha256 text, identity_record_sha256 text
);
CREATE TABLE astra_ingestion_v1.aug_d02_pilot_rows_v1 (
 manifest_sha text NOT NULL REFERENCES astra_ingestion_v1.aug_d02_pilot_v1(manifest_sha),
 payload astra_ingestion_v1.aug_d02_pilot_value_v1 NOT NULL,
 
 CHECK (payload IS NOT NULL AND (payload).ordinal BETWEEN 1 AND 10
   AND (payload).session_date=DATE '2026-08-04' AND (payload).raw_close>0 AND (payload).raw_volume>=0)
);
CREATE UNIQUE INDEX aug_d02_pilot_company_day ON astra_ingestion_v1.aug_d02_pilot_rows_v1
 ( ((payload).company_id), ((payload).session_date) );
CREATE UNIQUE INDEX aug_d02_pilot_ordinal ON astra_ingestion_v1.aug_d02_pilot_rows_v1 ( ((payload).ordinal) );
CREATE TABLE astra_ingestion_v1.aug_d02_pilot_receipt_v1 (
 attempt uuid PRIMARY KEY REFERENCES astra_ingestion_v1.aug_d02_pilot_v1(attempt),
 manifest_sha text NOT NULL UNIQUE REFERENCES astra_ingestion_v1.aug_d02_pilot_v1(manifest_sha),
 inserted_count integer NOT NULL CHECK (inserted_count BETWEEN 0 AND 10),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 writer_role name NOT NULL DEFAULT current_user, caller_role name NOT NULL DEFAULT session_user
);

-- Private fixed projection. It only returns pre-registered exact member keys.
-- The installer owns this projection to avoid granting either job actor access
-- to the large original archive or to unrelated retained/production evidence.
CREATE FUNCTION astra_ingestion_v1.aug_d02_pilot_source_v1()
RETURNS SETOF astra_ingestion_v1.aug_d02_pilot_value_v1
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $fn$
 WITH m AS MATERIALIZED (
   SELECT x.* FROM astra_ingestion_v1.aug_d02_pilot_v1 p
   CROSS JOIN LATERAL jsonb_to_recordset(p.manifest_text::jsonb->'members') x(
    ordinal integer,company_id text,ticker text,composite_figi text,share_class_figi text,
    exchange_mic text,issue_type text,source_row integer,raw_record_sha256 text,
    identity_source_sha256 text,identity_record_sha256 text)
 ), archive AS MATERIALIZED (
   SELECT d.content_text::jsonb AS doc, d.source_sha256 AS sha
   FROM population_top3000_202608_202609_v1.source_document d
   WHERE d.source_id='d02-daily-v2:7d9ac7ffe6757bdf8c19748275d87dc9b26d32cac5334a6deae52dc5c54b0d43:source'
     AND d.source_sha256='81e74427cd1365680d18cdaa31e5950bf601087e3bb0c11a13b2bfd14f4c93ae'
     AND d.source_provider='Massive' AND d.content_bytes=octet_length(d.content_text)
     AND d.source_sha256=encode(sha256(convert_to(d.content_text,'UTF8')),'hex')
     AND d.source_uri='https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/2026-08-04?adjusted=false&include_otc=false'
 ), price AS MATERIALIZED (
   SELECT a.sha,j.rec,j.idx,count(*) OVER(PARTITION BY j.rec->>'T') AS n
   FROM archive a CROSS JOIN LATERAL jsonb_array_elements(a.doc->'results') WITH ORDINALITY AS j(rec,idx)
   WHERE j.rec->>'T' IN (SELECT ticker FROM m)
 ), reference AS MATERIALIZED (
   SELECT d.source_sha256 AS sha,d.content_text::jsonb AS doc FROM population_top3000_202608_202609_v1.source_document d
   WHERE d.source_sha256 IN (SELECT identity_source_sha256 FROM m)
     AND d.source_provider='Massive' AND d.evidence->>'as_of'='2026-08-04'
     AND d.content_bytes=octet_length(d.content_text)
     AND d.source_sha256=encode(sha256(convert_to(d.content_text,'UTF8')),'hex')
 ), identities AS MATERIALIZED (
   SELECT r.sha,j.rec,j.idx,count(*) OVER(PARTITION BY j.rec->>'ticker') AS n
   FROM reference r CROSS JOIN LATERAL jsonb_array_elements(r.doc->'results') WITH ORDINALITY j(rec,idx)
   WHERE j.rec->>'ticker' IN (SELECT ticker FROM m)
 )
 SELECT m.ordinal,m.company_id,m.ticker,m.composite_figi,m.share_class_figi,m.exchange_mic,m.issue_type,
   DATE '2026-08-04',(b.rec->>'c')::numeric,(b.rec->>'v')::numeric,b.sha,m.source_row,
   m.raw_record_sha256,m.identity_source_sha256,m.identity_record_sha256
 FROM m JOIN price b ON b.rec->>'T'=m.ticker AND b.idx=m.source_row AND b.n=1
 JOIN astra_ingestion_v1.bulk_scope_evidence_v1 cm ON cm.capture_key='top3000-augsep2026-retained-scope-v1'
   AND cm.kind='company' AND cm.evidence_key=m.company_id AND cm.source_sha256=encode(sha256(convert_to(cm.source_text,'UTF8')),'hex')
   AND cm.source_text::jsonb @> jsonb_build_object('cohort_sha256','2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec',
       'membership_accepted',true,'membership_acceptance_sha256','20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9',
       'company_id',m.company_id,'selection_order',m.ordinal,'anchor_ticker',m.ticker,'anchor_exchange',m.exchange_mic,
       'anchor_composite_figi',m.composite_figi,'anchor_share_class_figi',m.share_class_figi,'anchor_security_type',m.issue_type)
 JOIN population_top3000_202608_202609_v1.ref01_date_record_v4 r ON r.company_id=m.company_id AND r.point_date=DATE '2026-08-04'
   AND r.record_sha256=m.identity_record_sha256 AND r.record_sha256=encode(sha256(convert_to(r.content::text,'UTF8')),'hex')
   AND r.identity_state='FROZEN_ANCHOR_TICKER_AND_TWO_FIGI_MATCH'
 JOIN population_top3000_202608_202609_v1.ref01_practical_dated_instrument_v3 x ON x.point_date=r.point_date AND x.company_id=m.company_id
   AND x.cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec' AND x.ticker=m.ticker
   AND x.record_sha256=encode(sha256(convert_to(x.content::text,'UTF8')),'hex') AND x.content->>'source_record_sha256'=r.record_sha256
 JOIN identities i ON i.rec->>'ticker'=m.ticker AND i.sha=m.identity_source_sha256 AND i.n=1
 WHERE i.rec->>'market'='stocks' AND i.rec->>'locale'='us' AND i.rec->'active'='true'::jsonb
   AND i.rec->>'cik'=substring(m.company_id FROM 5) AND i.rec->>'composite_figi'=m.composite_figi
   AND i.rec->>'share_class_figi'=m.share_class_figi AND i.rec->>'type'=m.issue_type AND i.rec->>'primary_exchange'=m.exchange_mic
   AND r.ordinal=i.idx AND r.content->'source_record'=i.rec AND r.content->>'source_sha256'=i.sha AND i.rec->>'currency_name'='usd'
   AND m.raw_record_sha256=encode(sha256(convert_to(b.rec::text,'UTF8')),'hex')
   AND jsonb_typeof(b.rec->'c')='number' AND (b.rec->>'c')::numeric>0
   AND jsonb_typeof(b.rec->'v')='number' AND (b.rec->>'v')::numeric>=0
   AND jsonb_typeof(b.rec->'t')='number' AND (to_timestamp((b.rec->>'t')::numeric/1000) AT TIME ZONE 'America/New_York')::date=DATE '2026-08-04'
 ORDER BY m.ordinal
$fn$;

CREATE FUNCTION astra_ingestion_v1.aug_d02_pilot_register_v1(p_manifest_text text,p_manifest_sha text,p_attempt uuid,p_deadline timestamptz)
RETURNS text LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
DECLARE m jsonb; anchors text; valid boolean; arr jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock(7603608040010);
 IF octet_length(p_manifest_text) NOT BETWEEN 2 AND 16384 OR p_manifest_sha IS DISTINCT FROM encode(sha256(convert_to(p_manifest_text,'UTF8')),'hex')
    OR p_manifest_sha IS DISTINCT FROM '61860ca4d4829f4f33459e9ebc0bad1c220a4552bfd5d9097d3a46af527717e4'
    OR p_attempt IS DISTINCT FROM 'e3d0a2e8-ee58-5e31-ac5a-cd1dbe34f54a'::uuid OR p_deadline IS NULL OR NOT (p_deadline>clock_timestamp() AND p_deadline<=clock_timestamp()+interval '1 hour') THEN
  RAISE EXCEPTION 'Invalid pilot pin, attempt or deadline';
 END IF;
 m:=p_manifest_text::jsonb; arr:=m->'members';
 IF NOT (p_manifest_text IS JSON OBJECT WITH UNIQUE KEYS) OR
   (m-'members') IS DISTINCT FROM jsonb_build_object('schema','astra-aug-d02-pilot/v1','date','2026-08-04',
    'cohort_sha256','2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec',
    'source_sha256','81e74427cd1365680d18cdaa31e5950bf601087e3bb0c11a13b2bfd14f4c93ae')
    OR jsonb_typeof(arr) IS DISTINCT FROM 'array' OR jsonb_array_length(arr)<>10 THEN RAISE EXCEPTION 'Invalid pilot scope'; END IF;
 SELECT encode(sha256(convert_to(string_agg(concat_ws('|',n,v->>'company_id',v->>'ticker',v->>'composite_figi',v->>'share_class_figi',v->>'exchange_mic',v->>'issue_type'),E'\n' ORDER BY n),'UTF8')),'hex'),
  bool_and((v->'ordinal'=to_jsonb(n) AND jsonb_typeof(v->'source_row')='number' AND v->>'source_row' ~ '^[1-9][0-9]{0,5}$'
   AND (SELECT count(*) FROM jsonb_object_keys(v))=11 AND v ?& ARRAY['ordinal','company_id','ticker','composite_figi','share_class_figi','exchange_mic','issue_type','source_row','raw_record_sha256','identity_source_sha256','identity_record_sha256']
   AND v->>'raw_record_sha256' ~ '^[0-9a-f]{64}$' AND v->>'identity_source_sha256' ~ '^[0-9a-f]{64}$'
   AND v->>'identity_record_sha256' ~ '^[0-9a-f]{64}$') IS TRUE)
 INTO anchors,valid FROM jsonb_array_elements(arr) WITH ORDINALITY x(v,n);
 IF NOT valid OR anchors IS DISTINCT FROM 'f48b5796245916e46580dbf0c5e5c9e81338a0861f8d0a3004024c78c2215667' THEN RAISE EXCEPTION 'Frozen ordered ten identities or evidence differ'; END IF;
 INSERT INTO astra_ingestion_v1.aug_d02_pilot_v1(singleton,manifest_text,manifest_sha,attempt,deadline)
 VALUES(true,p_manifest_text,p_manifest_sha,p_attempt,p_deadline);
 IF (SELECT count(*) FROM astra_ingestion_v1.aug_d02_pilot_source_v1()) <> 10 THEN RAISE EXCEPTION 'Ten independently resolvable dated source pairs required'; END IF;
 RETURN p_manifest_sha;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.aug_d02_pilot_commit_v1(p_manifest_sha text,p_attempt uuid)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE m astra_ingestion_v1.aug_d02_pilot_v1; pairs integer; collisions integer; inserted integer;
BEGIN
 PERFORM pg_advisory_xact_lock(7603608040010);
 SELECT * INTO STRICT m FROM astra_ingestion_v1.aug_d02_pilot_v1 WHERE singleton;
 IF current_user<>'astra_ingestion_rpc_owner_v1' OR p_manifest_sha IS DISTINCT FROM m.manifest_sha OR p_attempt IS DISTINCT FROM m.attempt
    OR EXISTS(SELECT 1 FROM astra_ingestion_v1.aug_d02_pilot_stop_v1)
    OR m.deadline<=clock_timestamp() THEN RAISE EXCEPTION 'Pilot scope, actor, deadline or fence rejected'; END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.aug_d02_pilot_receipt_v1) THEN RAISE EXCEPTION 'Pilot already committed; independent readback required'; END IF;
 WITH expected AS MATERIALIZED (SELECT s FROM astra_ingestion_v1.aug_d02_pilot_source_v1() s),
   pending AS (SELECT e.s FROM expected e WHERE NOT EXISTS (SELECT 1 FROM astra_ingestion_v1.aug_d02_pilot_rows_v1 r WHERE (r.payload).company_id=(e.s).company_id)),
   add_rows AS (INSERT INTO astra_ingestion_v1.aug_d02_pilot_rows_v1(manifest_sha,payload) SELECT m.manifest_sha,p.s FROM pending p RETURNING 1)
 SELECT (SELECT count(*) FROM expected),(SELECT count(*) FROM add_rows),
    (SELECT count(*) FROM astra_ingestion_v1.aug_d02_pilot_rows_v1 r WHERE r.manifest_sha<>m.manifest_sha OR NOT EXISTS (SELECT 1 FROM expected e WHERE e.s=r.payload))
 INTO pairs,inserted,collisions;
 IF pairs<>10 OR collisions<>0 OR m.deadline<=clock_timestamp() THEN RAISE EXCEPTION 'Source missing or destination conflict'; END IF;
 INSERT INTO astra_ingestion_v1.aug_d02_pilot_receipt_v1(attempt,manifest_sha,inserted_count) VALUES(m.attempt,m.manifest_sha,inserted);
 RETURN inserted;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.aug_d02_pilot_read_v1()
RETURNS TABLE(ordinal integer,company_id text,ticker text,composite_figi text,share_class_figi text,exchange_mic text,issue_type text,
 session_date date,raw_close numeric,raw_volume numeric,source_sha256 text,source_row integer,raw_record_sha256 text,identity_source_sha256 text,
 identity_record_sha256 text,manifest_sha text,attempt uuid,verified boolean,caller_role name,effective_role name)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $fn$
 WITH expected AS MATERIALIZED (SELECT s FROM astra_ingestion_v1.aug_d02_pilot_source_v1() s)
 SELECT (r.payload).*,r.manifest_sha,receipt.attempt,
  (current_user='astra_ingestion_verifier_owner_v1' AND e.s IS NOT NULL AND e.s=r.payload
   AND receipt.attempt IS NOT NULL AND receipt.writer_role='astra_ingestion_rpc_owner_v1'
   AND (SELECT count(*) FROM expected)=10 AND (SELECT count(*) FROM astra_ingestion_v1.aug_d02_pilot_rows_v1)=10) IS TRUE,
  session_user,current_user
 FROM astra_ingestion_v1.aug_d02_pilot_rows_v1 r
 LEFT JOIN expected e ON (e.s).company_id=(r.payload).company_id
 LEFT JOIN astra_ingestion_v1.aug_d02_pilot_receipt_v1 receipt ON receipt.manifest_sha=r.manifest_sha
 ORDER BY (r.payload).ordinal;
$fn$;

CREATE FUNCTION astra_ingestion_v1.aug_d02_pilot_stop_job_v1() RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
BEGIN
 PERFORM pg_advisory_xact_lock(7603608040010);
 INSERT INTO astra_ingestion_v1.aug_d02_pilot_stop_v1 VALUES(true,clock_timestamp()) ON CONFLICT DO NOTHING;
END $fn$;

-- Fixed privilege boundary: clear inherited object defaults on new objects,
-- including Supabase custom defaults. No global role or default changes.
DO $acl$
DECLARE r record; cmd text;
BEGIN
 FOR r IN
   SELECT 'TABLE' AS obj,c.oid::regclass::text AS ident,x.grantee,c.relowner AS owner
     FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x
     WHERE c.relnamespace='astra_ingestion_v1'::regnamespace AND c.relname IN
      ('aug_d02_pilot_v1','aug_d02_pilot_stop_v1','aug_d02_pilot_rows_v1','aug_d02_pilot_receipt_v1')
   UNION ALL
   SELECT 'FUNCTION',p.oid::regprocedure::text,x.grantee,p.proowner FROM pg_proc p
     CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x
     WHERE p.pronamespace='astra_ingestion_v1'::regnamespace AND p.proname IN
      ('aug_d02_pilot_source_v1','aug_d02_pilot_register_v1','aug_d02_pilot_commit_v1','aug_d02_pilot_read_v1','aug_d02_pilot_stop_job_v1')
 LOOP
  IF r.grantee<>r.owner THEN
   cmd:=CASE WHEN r.grantee=0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(r.grantee)) END;
   EXECUTE format('REVOKE ALL ON %s %s FROM %s',r.obj,r.ident,cmd);
  END IF;
 END LOOP;
END $acl$;
REVOKE ALL ON TYPE astra_ingestion_v1.aug_d02_pilot_value_v1 FROM PUBLIC;
GRANT USAGE ON TYPE astra_ingestion_v1.aug_d02_pilot_value_v1 TO astra_ingestion_rpc_owner_v1,astra_ingestion_verifier_owner_v1;
ALTER TABLE astra_ingestion_v1.aug_d02_pilot_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.aug_d02_pilot_stop_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.aug_d02_pilot_rows_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.aug_d02_pilot_receipt_v1 ENABLE ROW LEVEL SECURITY;
DO $roles$
DECLARE role_name text; table_name text;
BEGIN
 FOREACH role_name IN ARRAY ARRAY['astra_ingestion_rpc_owner_v1','astra_ingestion_verifier_owner_v1'] LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name AND NOT rolcanlogin AND NOT rolbypassrls AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb)
    OR has_schema_privilege(role_name,'astra_ingestion_v1','CREATE') THEN RAISE EXCEPTION 'Unexpected pilot role privilege'; END IF;
  IF role_name='astra_ingestion_verifier_owner_v1' AND pg_has_role(role_name,'astra_ingestion_rpc_owner_v1','MEMBER') THEN RAISE EXCEPTION 'Verifier may not assume the pilot writer'; END IF;
  FOREACH table_name IN ARRAY ARRAY['aug_d02_pilot_rows_v1','aug_d02_pilot_receipt_v1','aug_d02_pilot_v1','aug_d02_pilot_stop_v1'] LOOP
   EXECUTE format('GRANT SELECT ON astra_ingestion_v1.%I TO %I',table_name,role_name);
   EXECUTE format('CREATE POLICY %I ON astra_ingestion_v1.%I FOR SELECT TO %I USING(true)',role_name,table_name,role_name);
  END LOOP;
 END LOOP;
END $roles$;
GRANT INSERT ON astra_ingestion_v1.aug_d02_pilot_rows_v1,astra_ingestion_v1.aug_d02_pilot_receipt_v1 TO astra_ingestion_rpc_owner_v1;
CREATE POLICY pilot_worker_insert ON astra_ingestion_v1.aug_d02_pilot_rows_v1 FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true);
CREATE POLICY pilot_worker_receipt ON astra_ingestion_v1.aug_d02_pilot_receipt_v1 FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true);
GRANT EXECUTE ON FUNCTION astra_ingestion_v1.aug_d02_pilot_source_v1() TO astra_ingestion_rpc_owner_v1,astra_ingestion_verifier_owner_v1;
GRANT CREATE ON SCHEMA astra_ingestion_v1 TO astra_ingestion_rpc_owner_v1,astra_ingestion_verifier_owner_v1;
ALTER FUNCTION astra_ingestion_v1.aug_d02_pilot_commit_v1(text,uuid) OWNER TO astra_ingestion_rpc_owner_v1;
ALTER FUNCTION astra_ingestion_v1.aug_d02_pilot_read_v1() OWNER TO astra_ingestion_verifier_owner_v1;
REVOKE CREATE ON SCHEMA astra_ingestion_v1 FROM astra_ingestion_rpc_owner_v1,astra_ingestion_verifier_owner_v1;
DO $grant$ BEGIN
 EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.aug_d02_pilot_commit_v1(text,uuid),astra_ingestion_v1.aug_d02_pilot_read_v1() TO %I',current_user);
END $grant$;
COMMIT;
