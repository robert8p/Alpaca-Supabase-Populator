-- Forward-only repair for Supabase's provider-owned auth schema.
-- Historical astra_ingestion_rpc_v1.sql is intentionally unchanged.
-- This changes only the pinned private dispatcher's anonymous-context predicate.
-- It grants no schema access, issues no credential, and preserves owner/ACL/config.
BEGIN;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '3s';
SET LOCAL search_path = pg_catalog;
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $auth_context$
DECLARE
  v_oid oid := pg_catalog.to_regprocedure('astra_ingestion_v1.rpc_dispatch(text,jsonb)');
  v_before jsonb;
  v_after jsonb;
  v_source text;
  v_new_source text;
  v_definition text;
  v_old_check text := $old_check$OR v_claims->>'role' IS DISTINCT FROM 'anon' OR auth.uid() IS NOT NULL$old_check$;
  v_new_check text := $new_check$OR v_claims->>'role' IS DISTINCT FROM 'anon'
     OR (v_claims->>'sub') IS NOT NULL
     OR NULLIF(pg_catalog.current_setting('request.jwt.claim.sub',true),'') IS NOT NULL$new_check$;
BEGIN
  IF v_oid IS NULL THEN
    RAISE EXCEPTION 'Auth-context repair refused: ingestion dispatcher is absent';
  END IF;
  SELECT pg_catalog.to_jsonb(p)-'prosrc',p.prosrc INTO STRICT v_before,v_source
    FROM pg_catalog.pg_proc p WHERE p.oid=v_oid;
  IF (v_before->>'proowner')::oid IS DISTINCT FROM (SELECT oid FROM pg_catalog.pg_roles WHERE rolname='astra_ingestion_rpc_owner_v1')
    OR v_before->>'prosecdef' IS DISTINCT FROM 'true'
    OR pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_source,'UTF8')),'hex') <> '3866c86c65b0f50cc932cfb300219918cd78a2d630d8bc7d028976beaa0e8a4c'
    OR pg_catalog.length(v_source)-pg_catalog.length(pg_catalog.replace(v_source,v_old_check,'')) <> pg_catalog.length(v_old_check) THEN
    RAISE EXCEPTION 'Auth-context repair refused: dispatcher does not match the reviewed baseline';
  END IF;
  v_new_source := pg_catalog.replace(v_source,v_old_check,v_new_check);
  IF pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_new_source,'UTF8')),'hex') <> 'b293ce9c6216e77bc80713d8c1955b05b82644cf8e21f4871aea0491a51151a4' THEN
    RAISE EXCEPTION 'Auth-context repair refused: replacement hash mismatch';
  END IF;
  v_definition := pg_catalog.pg_get_functiondef(v_oid);
  IF pg_catalog.length(v_definition)-pg_catalog.length(pg_catalog.replace(v_definition,v_source,'')) <> pg_catalog.length(v_source) THEN
    RAISE EXCEPTION 'Auth-context repair refused: unexpected function definition';
  END IF;
  -- pg_get_functiondef supplies CREATE OR REPLACE with the exact existing
  -- signature and function attributes. Only its hash-bound body is replaced.
  EXECUTE pg_catalog.replace(v_definition,v_source,v_new_source);
  SELECT pg_catalog.to_jsonb(p)-'prosrc',p.prosrc INTO STRICT v_after,v_source
    FROM pg_catalog.pg_proc p WHERE p.oid=v_oid;
  IF v_after IS DISTINCT FROM v_before
     OR pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_source,'UTF8')),'hex') <> 'b293ce9c6216e77bc80713d8c1955b05b82644cf8e21f4871aea0491a51151a4' THEN
    RAISE EXCEPTION 'Auth-context repair refused: metadata or final body changed unexpectedly';
  END IF;
END
$auth_context$;
COMMIT;
