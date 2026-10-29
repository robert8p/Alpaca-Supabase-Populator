-- One-time restricted, bounded reader of the immutable retained scope.
-- Neither production worker nor public roles gain table access or provider rights.
-- A NOLOGIN identity has EXECUTE on this single SECURITY DEFINER function only.
-- Installed capture remains immutable and held; D06 is catalogue only.
BEGIN;
SET LOCAL statement_timeout = '20s';
SET LOCAL lock_timeout = '5s';
DO $preflight$
BEGIN
 IF to_regprocedure('astra_ingestion_v1.read_retained_capture_page_v1(text,text,text,integer)') IS NOT NULL
    OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname='astra_bulk_retained_reader_v1') THEN
   RAISE EXCEPTION 'reader already installed or role name claimed; do not reinstall blindly';
 END IF;
 IF to_regclass('astra_ingestion_v1.bulk_scope_evidence_v1') IS NULL
    OR to_regclass('astra_ingestion_v1.bulk_scope_capture_v1') IS NULL THEN
   RAISE EXCEPTION 'immutable capture schema missing';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.bulk_scope_capture_v1
   WHERE capture_key='top3000-augsep2026-retained-scope-v1'
     AND evidence_rows=4136
     AND evidence_sha256='ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
     AND state='CAPTURED_NOT_ADMITTED'
     AND provider_requests=0 AND incremental_cost_microusd=0
     AND historical_coverage='NOT_CERTIFIED') THEN
   RAISE EXCEPTION 'expected immutable scope receipt missing';
 END IF;
 IF (SELECT count(*) FROM astra_ingestion_v1.bulk_scope_evidence_v1
     WHERE capture_key='top3000-augsep2026-retained-scope-v1')<>4136 THEN
   RAISE EXCEPTION 'retained capture incomplete';
 END IF;
 IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='astra_ingestion_v1.bulk_scope_evidence_v1'::regclass)
 OR NOT (SELECT relrowsecurity FROM pg_class WHERE oid='astra_ingestion_v1.bulk_scope_capture_v1'::regclass)
 THEN RAISE EXCEPTION 'retained evidence RLS must remain enabled'; END IF;
END $preflight$;
CREATE ROLE astra_bulk_retained_reader_v1 NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT USAGE ON SCHEMA astra_ingestion_v1 TO astra_bulk_retained_reader_v1;
CREATE FUNCTION astra_ingestion_v1.read_retained_capture_page_v1(
 p_capture_key text, p_after_kind text, p_after_key text, p_limit integer
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET timezone='UTC' AS $function$
DECLARE
 v_row record;
 v_rows jsonb := '[]'::jsonb;
 v_count integer := 0;
 v_more boolean := false;
 v_max_bytes integer := 2000000;
BEGIN
 IF p_capture_key IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
    OR p_limit IS NULL OR p_limit<1 OR p_limit>256 THEN
   RAISE EXCEPTION 'unauthorised capture key or nonbounded page';
 END IF;
 IF (p_after_kind IS NULL)<>(p_after_key IS NULL) OR
    (p_after_kind IS NOT NULL AND (
       p_after_kind NOT IN ('scope','cohort','membership','company','contract','calendar','preservation','acceptance_event')
       OR length(p_after_key) NOT BETWEEN 1 AND 512)) THEN
    RAISE EXCEPTION 'invalid complete keyset cursor';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.bulk_scope_capture_v1
   WHERE capture_key=p_capture_key AND evidence_rows=4136
     AND evidence_sha256='ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
     AND state='CAPTURED_NOT_ADMITTED') THEN
   RAISE EXCEPTION 'retained capture receipt unavailable';
 END IF;
 FOR v_row IN
    SELECT kind,evidence_key,source_text,source_sha256
    FROM astra_ingestion_v1.bulk_scope_evidence_v1
    WHERE capture_key=p_capture_key
      AND (p_after_kind IS NULL
        OR (kind,evidence_key)>(p_after_kind,p_after_key))
    ORDER BY kind,evidence_key
    LIMIT p_limit+1
 LOOP
    v_count:=v_count+1;
    IF v_count>p_limit THEN v_more:=true; EXIT; END IF;
    v_rows:=v_rows || jsonb_build_array(jsonb_build_object(
      'kind',v_row.kind,'evidence_key',v_row.evidence_key,
      'source_text',v_row.source_text,'source_sha256',v_row.source_sha256));
    IF octet_length(v_rows::text)>v_max_bytes THEN
      RAISE EXCEPTION 'retained page exceeds finite byte bound; lower the page limit';
    END IF;
 END LOOP;
 RETURN jsonb_build_object('rows',v_rows,'has_more',v_more);
END $function$;
REVOKE ALL ON FUNCTION astra_ingestion_v1.read_retained_capture_page_v1(text,text,text,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION astra_ingestion_v1.read_retained_capture_page_v1(text,text,text,integer)
 TO astra_bulk_retained_reader_v1;
DO $postflight$
BEGIN
 IF NOT EXISTS (
    SELECT 1 FROM pg_proc p WHERE
      p.oid=to_regprocedure('astra_ingestion_v1.read_retained_capture_page_v1(text,text,text,integer)')
      AND p.prosecdef IS TRUE
      AND NOT EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner)))
        WHERE grantee=0 AND privilege_type='EXECUTE')
 ) THEN RAISE EXCEPTION 'restricted reader privilege verification failed'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='astra_bulk_retained_reader_v1'
   AND rolcanlogin IS FALSE AND rolsuper IS FALSE AND rolbypassrls IS FALSE) THEN
   RAISE EXCEPTION 'reader role unexpectedly privileged';
 END IF;
END $postflight$;
COMMIT;
