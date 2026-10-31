-- Keep canonical hashes byte-identical while making long article strings linear.
-- The former per-character concatenation was quadratic and timed out real news pages.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $preflight$
DECLARE d text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_ascii_string(text)'::regprocedure) INTO STRICT d;
 IF strpos(d,'rpc_ascii_linear_v2')>0 OR strpos(d,'FOR v_i IN 1..')=0 THEN
  RAISE EXCEPTION 'Canonical performance requires the original string serializer; reconcile before applying';
 END IF;
END $preflight$;

CREATE OR REPLACE FUNCTION astra_ingestion_v1.rpc_ascii_string(p_value text)
RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT SET search_path='' AS $fn$
DECLARE v_text text:=pg_catalog.to_jsonb(p_value)::text; v_result text;
BEGIN
 -- rpc_ascii_linear_v2: PostgreSQL performs JSON escaping once. Preserve its
 -- ASCII runs intact, escaping only individual non-ASCII codepoints (including DEL).
 IF (v_text COLLATE "C") !~ '[^ -~]' THEN RETURN v_text; END IF;
 SELECT pg_catalog.string_agg(
  CASE WHEN cp>=65536 THEN
    E'\\u'||pg_catalog.lpad(pg_catalog.to_hex(55296+(cp-65536)/1024),4,'0')||
    E'\\u'||pg_catalog.lpad(pg_catalog.to_hex(56320+(cp-65536)%1024),4,'0')
   WHEN cp>=127 THEN E'\\u'||pg_catalog.lpad(pg_catalog.to_hex(cp),4,'0')
   ELSE piece END,'' ORDER BY ordinal)
 INTO v_result
 FROM (SELECT m[1] piece,pg_catalog.ascii(m[1]) cp,ordinal
   FROM pg_catalog.regexp_matches(v_text COLLATE "C",'([ -~]+|[^ -~])','g') WITH ORDINALITY r(m,ordinal)) x;
 RETURN v_result;
END $fn$;
-- CREATE OR REPLACE retains the original owner and EXECUTE grants. No privilege,
-- scope, receipt, record hash, provider request, deadline or attempt is reset.
COMMIT;
