-- A private August 4 D02 route. Installing it admits zero batches.
-- The approval owner separately pins an exact manifest, attempt and ten-rank
-- slice. The original pilot owns ranks 1-10 and its objects remain untouched.
BEGIN;
SET LOCAL search_path = pg_catalog;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '20s';

CREATE TABLE astra_ingestion_v1.d02_batch_approvals_v1 (
    attempt uuid PRIMARY KEY,
    manifest_sha text NOT NULL UNIQUE CHECK (manifest_sha ~ '^[0-9a-f]{64}$'),
    session_date date NOT NULL CHECK (session_date = DATE '2026-08-04'),
    first_rank integer NOT NULL CHECK (first_rank BETWEEN 11 AND 2991 AND first_rank % 10 = 1),
    deadline timestamptz NOT NULL,
    approved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    approved_by name NOT NULL DEFAULT current_user,
    CHECK (deadline > approved_at AND deadline <= approved_at + interval '1 hour'),
    UNIQUE (attempt,manifest_sha),
    UNIQUE (session_date,first_rank)
);
CREATE TABLE astra_ingestion_v1.d02_batch_manifests_v1 (
    attempt uuid PRIMARY KEY,
    manifest_sha text NOT NULL,
    manifest_text text NOT NULL CHECK (octet_length(manifest_text) BETWEEN 2 AND 16384
        AND manifest_sha = encode(sha256(convert_to(manifest_text,'UTF8')),'hex')),
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (attempt,manifest_sha) REFERENCES astra_ingestion_v1.d02_batch_approvals_v1(attempt,manifest_sha)
);
CREATE TABLE astra_ingestion_v1.d02_batch_stops_v1 (
    attempt uuid PRIMARY KEY REFERENCES astra_ingestion_v1.d02_batch_approvals_v1(attempt),
    stopped_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE astra_ingestion_v1.d02_batch_rows_v1 (
    attempt uuid NOT NULL REFERENCES astra_ingestion_v1.d02_batch_manifests_v1(attempt),
    payload astra_ingestion_v1.aug_d02_pilot_value_v1 NOT NULL,
    CHECK (payload IS NOT NULL AND (payload).ordinal BETWEEN 11 AND 3000
        AND (payload).session_date = DATE '2026-08-04' AND (payload).raw_close > 0 AND (payload).raw_volume >= 0)
);
CREATE UNIQUE INDEX d02_batch_company_day_v1 ON astra_ingestion_v1.d02_batch_rows_v1
    (((payload).company_id), ((payload).session_date));
CREATE UNIQUE INDEX d02_batch_session_rank_v1 ON astra_ingestion_v1.d02_batch_rows_v1
    (((payload).session_date), ((payload).ordinal));
CREATE INDEX d02_batch_attempt_rows_v1 ON astra_ingestion_v1.d02_batch_rows_v1 (attempt);

CREATE TABLE astra_ingestion_v1.d02_batch_receipts_v1 (
    attempt uuid PRIMARY KEY REFERENCES astra_ingestion_v1.d02_batch_manifests_v1(attempt),
    manifest_sha text NOT NULL UNIQUE,
    inserted_count integer NOT NULL CHECK (inserted_count BETWEEN 0 AND 10),
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    writer_role name NOT NULL DEFAULT current_user,
    caller_role name NOT NULL DEFAULT session_user,
    FOREIGN KEY (attempt,manifest_sha) REFERENCES astra_ingestion_v1.d02_batch_approvals_v1(attempt,manifest_sha)
);

CREATE FUNCTION astra_ingestion_v1.d02_batch_immutable_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
BEGIN
    RAISE EXCEPTION 'Batch evidence is append-only';
END $fn$;

CREATE FUNCTION astra_ingestion_v1.d02_batch_approve_v1(
    p_attempt uuid, p_manifest_sha text, p_session_date date, p_first_rank integer, p_deadline timestamptz)
RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
BEGIN
    INSERT INTO astra_ingestion_v1.d02_batch_approvals_v1(attempt,manifest_sha,session_date,first_rank,deadline)
    VALUES (p_attempt,p_manifest_sha,p_session_date,p_first_rank,p_deadline);
    RETURN p_attempt;
END $fn$;

-- Private fixed projection. It only returns pre-registered exact member keys.
-- The installer owns this projection to avoid granting either job actor access
-- to the large original archive or to unrelated retained/production evidence.
CREATE FUNCTION astra_ingestion_v1.d02_batch_source_v1(p_attempt uuid)
RETURNS SETOF astra_ingestion_v1.aug_d02_pilot_value_v1
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $fn$
 WITH m AS MATERIALIZED (
   SELECT x.* FROM astra_ingestion_v1.d02_batch_manifests_v1 p
   CROSS JOIN LATERAL jsonb_to_recordset(p.manifest_text::jsonb->'members') x(
    ordinal integer,company_id text,ticker text,composite_figi text,share_class_figi text,
    exchange_mic text,issue_type text,source_row integer,raw_record_sha256 text,
    identity_source_sha256 text,identity_record_sha256 text)
   WHERE p.attempt=p_attempt
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
 ), pairs AS (
 SELECT ROW(m.ordinal,m.company_id,m.ticker,m.composite_figi,m.share_class_figi,m.exchange_mic,m.issue_type,
   DATE '2026-08-04',(b.rec->>'c')::numeric,(b.rec->>'v')::numeric,b.sha,m.source_row,
   m.raw_record_sha256,m.identity_source_sha256,m.identity_record_sha256)::astra_ingestion_v1.aug_d02_pilot_value_v1 AS payload,
   count(*) OVER (PARTITION BY m.ordinal) AS witness_count
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
 )
 SELECT (p.payload).* FROM pairs p WHERE p.witness_count=1 ORDER BY (p.payload).ordinal
$fn$;

CREATE FUNCTION astra_ingestion_v1.d02_batch_register_v1(p_manifest_text text,p_manifest_sha text,p_attempt uuid)
RETURNS text LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
DECLARE
    a astra_ingestion_v1.d02_batch_approvals_v1;
    m jsonb;
    members jsonb;
    valid boolean;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('astra-d02-batch/'||p_attempt::text,0));
    SELECT * INTO STRICT a FROM astra_ingestion_v1.d02_batch_approvals_v1
    WHERE attempt=p_attempt AND manifest_sha=p_manifest_sha;
    IF a.deadline<=clock_timestamp() OR EXISTS (SELECT 1 FROM astra_ingestion_v1.d02_batch_stops_v1 WHERE attempt=p_attempt)
        OR octet_length(p_manifest_text) NOT BETWEEN 2 AND 16384
        OR p_manifest_sha IS DISTINCT FROM encode(sha256(convert_to(p_manifest_text,'UTF8')),'hex')
        OR NOT (p_manifest_text IS JSON OBJECT WITH UNIQUE KEYS) THEN
        RAISE EXCEPTION 'Batch stopped, expired or manifest differs from approval';
    END IF;
    m:=p_manifest_text::jsonb;
    members:=m->'members';
    IF (m-'members') IS DISTINCT FROM jsonb_build_object('schema','astra-d02-batch/v1','date','2026-08-04',
        'cohort_sha256','2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec',
        'source_sha256','81e74427cd1365680d18cdaa31e5950bf601087e3bb0c11a13b2bfd14f4c93ae')
        OR jsonb_typeof(members) IS DISTINCT FROM 'array' OR jsonb_array_length(members)<>10 THEN
        RAISE EXCEPTION 'Invalid batch date, source, cohort or count';
    END IF;

    SELECT bool_and((
        v->'ordinal'=to_jsonb(a.first_rank+n-1) AND jsonb_typeof(v->'source_row')='number'
        AND v->>'source_row' ~ '^[1-9][0-9]{0,5}$' AND v->>'company_id' ~ '^CIK:[0-9]{10}$'
        AND (SELECT count(*) FROM jsonb_object_keys(v))=11
        AND NOT EXISTS (SELECT 1 FROM jsonb_each(v) j WHERE j.key NOT IN ('ordinal','source_row')
                        AND jsonb_typeof(j.value)<>'string')
        AND v ?& ARRAY['ordinal','company_id','ticker','composite_figi','share_class_figi','exchange_mic','issue_type',
                        'source_row','raw_record_sha256','identity_source_sha256','identity_record_sha256']
        AND v->>'raw_record_sha256' ~ '^[0-9a-f]{64}$' AND v->>'identity_source_sha256' ~ '^[0-9a-f]{64}$'
        AND v->>'identity_record_sha256' ~ '^[0-9a-f]{64}$') IS TRUE)
        AND count(DISTINCT v->>'company_id')=10 AND count(DISTINCT v->>'ticker')=10
        AND count(DISTINCT v->>'composite_figi')=10 AND count(DISTINCT v->>'share_class_figi')=10
        AND count(DISTINCT v->>'source_row')=10
    INTO valid FROM jsonb_array_elements(members) WITH ORDINALITY x(v,n);
    IF valid IS DISTINCT FROM true THEN RAISE EXCEPTION 'Invalid rank slice, identities or evidence'; END IF;
    IF EXISTS (SELECT 1 FROM astra_ingestion_v1.aug_d02_pilot_rows_v1 r
        JOIN jsonb_array_elements(members) x(v) ON (r.payload).company_id=v->>'company_id'
        WHERE (r.payload).session_date=a.session_date) THEN RAISE EXCEPTION 'Completed pilot overlap'; END IF;
    INSERT INTO astra_ingestion_v1.d02_batch_manifests_v1(attempt,manifest_sha,manifest_text)
    VALUES(p_attempt,p_manifest_sha,p_manifest_text);
    IF (SELECT count(*) FROM astra_ingestion_v1.d02_batch_source_v1(p_attempt))<>10 OR a.deadline<=clock_timestamp() THEN
        RAISE EXCEPTION 'Ten unique dated source pairs required within deadline';
    END IF;
    RETURN p_manifest_sha;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.d02_batch_commit_v1(p_manifest_sha text,p_attempt uuid)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE
    a astra_ingestion_v1.d02_batch_approvals_v1;
    pairs integer;
    collisions integer;
    inserted integer;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('astra-d02-batch/'||p_attempt::text,0));
    SELECT * INTO STRICT a FROM astra_ingestion_v1.d02_batch_approvals_v1
    WHERE attempt=p_attempt AND manifest_sha=p_manifest_sha;
    IF current_user<>'astra_ingestion_rpc_owner_v1' OR a.deadline<=clock_timestamp()
        OR NOT EXISTS (SELECT 1 FROM astra_ingestion_v1.d02_batch_manifests_v1 WHERE attempt=p_attempt)
        OR EXISTS (SELECT 1 FROM astra_ingestion_v1.d02_batch_stops_v1 WHERE attempt=p_attempt) THEN
        RAISE EXCEPTION 'Batch actor, registration, deadline or stop fence rejected';
    END IF;
    IF EXISTS (SELECT 1 FROM astra_ingestion_v1.d02_batch_receipts_v1 WHERE attempt=p_attempt) THEN
        RAISE EXCEPTION 'Batch already committed; reconcile its receipt';
    END IF;
    WITH expected AS MATERIALIZED (SELECT s FROM astra_ingestion_v1.d02_batch_source_v1(p_attempt) s),
    pending AS (SELECT e.s FROM expected e WHERE NOT EXISTS (
        SELECT 1 FROM astra_ingestion_v1.d02_batch_rows_v1 r
        WHERE (r.payload).session_date=(e.s).session_date AND (r.payload).company_id=(e.s).company_id)),
    added AS (INSERT INTO astra_ingestion_v1.d02_batch_rows_v1(attempt,payload)
        SELECT p_attempt,p.s FROM pending p RETURNING 1)
    SELECT (SELECT count(*) FROM expected),(SELECT count(*) FROM added),
        (SELECT count(*) FROM astra_ingestion_v1.d02_batch_rows_v1 r
         WHERE (r.attempt=p_attempt AND NOT EXISTS (SELECT 1 FROM expected e WHERE e.s=r.payload))
            OR (r.attempt<>p_attempt AND EXISTS (SELECT 1 FROM expected e
                WHERE (r.payload).session_date=(e.s).session_date AND (r.payload).company_id=(e.s).company_id)))
    INTO pairs,inserted,collisions;
    IF pairs<>10 OR collisions<>0 OR a.deadline<=clock_timestamp() THEN
        RAISE EXCEPTION 'Source missing or destination conflict or deadline expired';
    END IF;
    INSERT INTO astra_ingestion_v1.d02_batch_receipts_v1(attempt,manifest_sha,inserted_count) VALUES(p_attempt,p_manifest_sha,inserted);
    RETURN inserted;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.d02_batch_read_v1(p_attempt uuid)
RETURNS TABLE(ordinal integer,company_id text,ticker text,composite_figi text,share_class_figi text,exchange_mic text,issue_type text,
    session_date date,raw_close numeric,raw_volume numeric,source_sha256 text,source_row integer,raw_record_sha256 text,
    identity_source_sha256 text,identity_record_sha256 text,manifest_sha text,attempt uuid,verified boolean,caller_role name,effective_role name)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $fn$
    WITH expected AS MATERIALIZED (SELECT s FROM astra_ingestion_v1.d02_batch_source_v1(p_attempt) s)
    SELECT (r.payload).*,receipt.manifest_sha,r.attempt,
        (current_user='astra_ingestion_verifier_owner_v1' AND e.s IS NOT NULL AND e.s=r.payload
         AND receipt.writer_role='astra_ingestion_rpc_owner_v1'
         AND (SELECT count(*) FROM expected)=10
         AND (SELECT count(*) FROM astra_ingestion_v1.d02_batch_rows_v1 v WHERE v.attempt=p_attempt)=10) IS TRUE,
        session_user,current_user
    FROM astra_ingestion_v1.d02_batch_rows_v1 r
    LEFT JOIN expected e ON (e.s).company_id=(r.payload).company_id
    LEFT JOIN astra_ingestion_v1.d02_batch_receipts_v1 receipt ON receipt.attempt=r.attempt
    WHERE r.attempt=p_attempt ORDER BY (r.payload).ordinal
$fn$;

CREATE FUNCTION astra_ingestion_v1.d02_batch_stop_v1(p_attempt uuid)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('astra-d02-batch/'||p_attempt::text,0));
    INSERT INTO astra_ingestion_v1.d02_batch_stops_v1(attempt) VALUES(p_attempt) ON CONFLICT DO NOTHING;
END $fn$;

-- Clear custom/default grants on these exact new objects. Neither actor gains
-- general archive access, table ownership or ongoing schema CREATE.
DO $acl$
DECLARE r record; grantee_name text;
BEGIN
    FOR r IN
        SELECT 'TABLE' AS kind,c.oid::regclass::text AS ident,x.grantee,c.relowner AS owner
        FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x
        WHERE c.relnamespace='astra_ingestion_v1'::regnamespace AND c.relname IN
            ('d02_batch_approvals_v1','d02_batch_manifests_v1','d02_batch_rows_v1','d02_batch_receipts_v1','d02_batch_stops_v1')
        UNION ALL
        SELECT 'FUNCTION',p.oid::regprocedure::text,x.grantee,p.proowner
        FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x
        WHERE p.pronamespace='astra_ingestion_v1'::regnamespace AND p.proname IN
            ('d02_batch_approve_v1','d02_batch_source_v1','d02_batch_register_v1','d02_batch_commit_v1','d02_batch_read_v1','d02_batch_stop_v1','d02_batch_immutable_v1')
    LOOP
        IF r.grantee<>r.owner THEN
            grantee_name:=CASE WHEN r.grantee=0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(r.grantee)) END;
            EXECUTE format('REVOKE ALL ON %s %s FROM %s',r.kind,r.ident,grantee_name);
        END IF;
    END LOOP;
END $acl$;
DO $roles$
DECLARE role_name text; table_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['astra_ingestion_rpc_owner_v1','astra_ingestion_verifier_owner_v1'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name AND NOT rolcanlogin AND NOT rolbypassrls
             AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb)
             OR has_schema_privilege(role_name,'astra_ingestion_v1','CREATE') THEN RAISE EXCEPTION 'Unexpected batch role privilege'; END IF;
    END LOOP;
    IF pg_has_role('astra_ingestion_verifier_owner_v1','astra_ingestion_rpc_owner_v1','MEMBER')
        OR pg_has_role('astra_ingestion_rpc_owner_v1','astra_ingestion_verifier_owner_v1','MEMBER') THEN
        RAISE EXCEPTION 'Distinct batch roles required';
    END IF;
    FOREACH table_name IN ARRAY ARRAY['d02_batch_approvals_v1','d02_batch_manifests_v1','d02_batch_rows_v1','d02_batch_receipts_v1','d02_batch_stops_v1'] LOOP
        EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format('CREATE TRIGGER immutable_batch BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.%I
            FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.d02_batch_immutable_v1()',table_name);
        EXECUTE format('GRANT SELECT ON astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',table_name);
        EXECUTE format('CREATE POLICY writer_read ON astra_ingestion_v1.%I FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true)',table_name);
    END LOOP;
    FOREACH table_name IN ARRAY ARRAY['d02_batch_rows_v1','d02_batch_receipts_v1'] LOOP
        EXECUTE format('GRANT INSERT ON astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',table_name);
        EXECUTE format('CREATE POLICY writer_insert ON astra_ingestion_v1.%I FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true)',table_name);
        EXECUTE format('GRANT SELECT ON astra_ingestion_v1.%I TO astra_ingestion_verifier_owner_v1',table_name);
        EXECUTE format('CREATE POLICY verifier_read ON astra_ingestion_v1.%I FOR SELECT TO astra_ingestion_verifier_owner_v1 USING(true)',table_name);
    END LOOP;
END $roles$;
GRANT EXECUTE ON FUNCTION astra_ingestion_v1.d02_batch_source_v1(uuid) TO astra_ingestion_rpc_owner_v1,astra_ingestion_verifier_owner_v1;
GRANT CREATE ON SCHEMA astra_ingestion_v1 TO astra_ingestion_rpc_owner_v1,astra_ingestion_verifier_owner_v1;
ALTER FUNCTION astra_ingestion_v1.d02_batch_commit_v1(text,uuid) OWNER TO astra_ingestion_rpc_owner_v1;
ALTER FUNCTION astra_ingestion_v1.d02_batch_read_v1(uuid) OWNER TO astra_ingestion_verifier_owner_v1;
REVOKE CREATE ON SCHEMA astra_ingestion_v1 FROM astra_ingestion_rpc_owner_v1,astra_ingestion_verifier_owner_v1;
DO $grant$ BEGIN
    EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.d02_batch_commit_v1(text,uuid),astra_ingestion_v1.d02_batch_read_v1(uuid) TO %I',current_user);
END $grant$;
COMMIT;
