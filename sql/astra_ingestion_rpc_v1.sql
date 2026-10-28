-- Restricted ingestion Data API. One-time migration; no credentials or LOGIN roles.
-- Requires the already installed private schema v1. Never expose that schema in
-- pgrst.db_schemas. The only public endpoint is a fixed-operation invoker wrapper.
BEGIN;
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '3s';
SET LOCAL search_path = pg_catalog;
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $admission$
BEGIN
  IF pg_catalog.to_regnamespace('astra_ingestion_v1') IS NULL
     OR (SELECT version FROM astra_ingestion_v1.schema_info WHERE id=1) IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'RPC admission requires the existing ingestion schema v1';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='astra_ingestion_rpc_owner_v1')
     OR EXISTS(SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
               WHERE n.nspname='public' AND p.proname='astra_ingestion_rpc_v1')
     OR pg_catalog.to_regclass('astra_ingestion_v1.runtime_credentials') IS NOT NULL
     OR EXISTS (SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='astra_ingestion_v1' AND p.proname LIKE 'rpc_%') THEN
    RAISE EXCEPTION 'RPC admission refuses existing role, endpoint or credential objects';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='anon')
     OR pg_catalog.to_regprocedure('auth.uid()') IS NULL THEN
    RAISE EXCEPTION 'RPC admission requires the Supabase anonymous gateway context';
  END IF;
  IF (SELECT pg_catalog.count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='astra_ingestion_v1' AND c.relkind='r')<>9
    OR EXISTS(SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a
        WHERE n.nspname='astra_ingestion_v1' AND c.relkind='r' AND a.grantee<>c.relowner) THEN
    RAISE EXCEPTION 'RPC admission requires the unchanged private nine-table schema with owner-only table grants';
  END IF;
  CREATE ROLE astra_ingestion_rpc_owner_v1 NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  EXECUTE pg_catalog.format('GRANT astra_ingestion_rpc_owner_v1 TO %I', current_user);
END
$admission$;

CREATE TABLE astra_ingestion_v1.runtime_credentials (
  token_sha256 text PRIMARY KEY CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
  actor text NOT NULL CHECK (actor IN ('api','worker')),
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  CHECK (expires_at > created_at)
);
ALTER TABLE astra_ingestion_v1.runtime_credentials ENABLE ROW LEVEL SECURITY;
-- Deliberately empty. Provision only digests through a separately authorised
-- administrative action; the runtime can neither create nor rotate credentials.

CREATE FUNCTION astra_ingestion_v1.rpc_ascii_string(p_value text)
RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT SET search_path = '' AS $fn$
DECLARE v_text text := pg_catalog.to_jsonb(p_value)::text; v_result text := ''; v_char text; v_n integer; v_i integer;
BEGIN
  FOR v_i IN 1..pg_catalog.char_length(v_text) LOOP
    v_char := pg_catalog.substr(v_text,v_i,1); v_n := pg_catalog.ascii(v_char);
    IF v_n >= 65536 THEN
      v_n := v_n-65536;
      v_result := v_result || E'\\u' || pg_catalog.lpad(pg_catalog.to_hex(55296+v_n/1024),4,'0')
                    || E'\\u' || pg_catalog.lpad(pg_catalog.to_hex(56320+v_n%1024),4,'0');
    ELSIF v_n >= 127 THEN
      v_result := v_result || E'\\u' || pg_catalog.lpad(pg_catalog.to_hex(v_n),4,'0');
    ELSE v_result := v_result || v_char;
    END IF;
  END LOOP;
  RETURN v_result;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_canonical(p_value jsonb)
RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT SET search_path = '' AS $fn$
DECLARE v_result text;
BEGIN
  CASE pg_catalog.jsonb_typeof(p_value)
  WHEN 'object' THEN
    SELECT '{' || COALESCE(pg_catalog.string_agg(astra_ingestion_v1.rpc_ascii_string(k) || ':' || astra_ingestion_v1.rpc_canonical(v),',' ORDER BY k COLLATE "C"),'') || '}'
      INTO v_result FROM pg_catalog.jsonb_each(p_value) e(k,v);
  WHEN 'array' THEN
    SELECT '[' || COALESCE(pg_catalog.string_agg(astra_ingestion_v1.rpc_canonical(v),',' ORDER BY i),'') || ']'
      INTO v_result FROM pg_catalog.jsonb_array_elements(p_value) WITH ORDINALITY e(v,i);
  WHEN 'string' THEN v_result := astra_ingestion_v1.rpc_ascii_string(p_value #>> '{}');
  ELSE v_result := p_value::text;
  END CASE;
  RETURN v_result;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_time(p_value timestamptz)
RETURNS text LANGUAGE sql IMMUTABLE STRICT SET search_path = '' AS $fn$
SELECT pg_catalog.to_char(p_value AT TIME ZONE 'UTC',
  CASE WHEN pg_catalog.date_part('microseconds',p_value)::bigint % 1000000=0
  THEN 'YYYY-MM-DD"T"HH24:MI:SS"Z"' ELSE 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"' END)
$fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_timestamp(p_value text)
RETURNS timestamptz LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $fn$
BEGIN
  IF p_value IS NULL OR p_value !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$' THEN
    RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='A canonical UTC timestamp is required';
  END IF;
  RETURN p_value::timestamptz;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_keys(p_value jsonb,p_keys text[])
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = '' AS $fn$
SELECT CASE WHEN pg_catalog.jsonb_typeof(p_value)='object' THEN
 (SELECT pg_catalog.count(*)=pg_catalog.cardinality(p_keys) AND COALESCE(pg_catalog.bool_and(k=ANY(p_keys)),true)
  FROM pg_catalog.jsonb_object_keys(p_value) e(k)) ELSE false END
$fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_spec(p_value jsonb)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $fn$
DECLARE v_start timestamptz; v_end timestamptz; v_field text; v_n bigint; v_name text;
BEGIN
  IF NOT astra_ingestion_v1.rpc_keys(p_value,ARRAY['symbols','start','end','name','timeframe','feed','adjustment','max_requests','max_records','deadline_seconds']) THEN
    RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Supply the complete bounded ingestion specification';
  END IF;
  IF pg_catalog.jsonb_typeof(p_value->'symbols') IS DISTINCT FROM 'array'
     OR pg_catalog.jsonb_array_length(p_value->'symbols') NOT BETWEEN 1 AND 10 THEN
    RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Select between one and ten explicit symbols';
  END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(p_value->'symbols') e(v)
            WHERE pg_catalog.jsonb_typeof(v)<>'string' OR (v#>>'{}') !~ '^[A-Z][A-Z0-9.\-]{0,19}$')
     OR (SELECT pg_catalog.count(*)<>pg_catalog.count(DISTINCT v) FROM pg_catalog.jsonb_array_elements(p_value->'symbols') e(v)) THEN
    RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Symbols must be unique valid uppercase text';
  END IF;
  FOREACH v_field IN ARRAY ARRAY['start','end','name','timeframe','feed','adjustment'] LOOP
    IF pg_catalog.jsonb_typeof(p_value->v_field) IS DISTINCT FROM 'string' THEN
      RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Specification text fields must be strings';
    END IF;
  END LOOP;
  v_start:=astra_ingestion_v1.rpc_timestamp(p_value->>'start'); v_end:=astra_ingestion_v1.rpc_timestamp(p_value->>'end');
  IF NOT (v_start >= '2025-09-01T00:00:00Z'::timestamptz AND v_start<v_end
          AND v_end<='2026-08-01T00:00:00Z'::timestamptz AND v_end-v_start<=INTERVAL '7 days') THEN
    RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Scope exceeds the admitted historical window or seven-day bound';
  END IF;
  v_name:=p_value->>'name';
  IF pg_catalog.char_length(pg_catalog.btrim(v_name)) NOT BETWEEN 1 AND 120 OR pg_catalog.char_length(v_name)>120 OR v_name~'[[:cntrl:]]'
     OR (p_value->>'timeframe') NOT IN ('1Min','5Min','15Min','1Hour')
     OR p_value->>'feed'<>'sip' OR p_value->>'adjustment'<>'raw' THEN
    RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid name, timeframe, feed or adjustment';
  END IF;
  FOREACH v_field IN ARRAY ARRAY['max_requests','max_records','deadline_seconds'] LOOP
    IF pg_catalog.jsonb_typeof(p_value->v_field) IS DISTINCT FROM 'number' OR (p_value->>v_field)!~'^[0-9]{1,6}$' THEN
      RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Budgets must be bounded integers';
    END IF;
    v_n:=(p_value->>v_field)::bigint;
    IF (v_field='max_requests' AND v_n NOT BETWEEN 1 AND 200)
       OR (v_field='max_records' AND v_n NOT BETWEEN 1 AND 100000)
       OR (v_field='deadline_seconds' AND v_n NOT BETWEEN 30 AND 7200) THEN
      RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Budget exceeds the admitted bound';
    END IF;
  END LOOP;
  RETURN p_value || pg_catalog.jsonb_build_object('start',astra_ingestion_v1.rpc_time(v_start),'end',astra_ingestion_v1.rpc_time(v_end));
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_public_row(p_value jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE STRICT SET search_path = '' AS $fn$
DECLARE v_result jsonb:=p_value-'owner'; v_key text;
BEGIN
  FOREACH v_key IN ARRAY ARRAY['created_at','updated_at','last_progress_at','deadline_at','next_attempt_at','lease_until','timestamp','checked_at'] LOOP
    IF v_result ? v_key AND v_result->v_key<>'null'::jsonb THEN
      v_result:=pg_catalog.jsonb_set(v_result,ARRAY[v_key],pg_catalog.to_jsonb(astra_ingestion_v1.rpc_time(pg_catalog.to_timestamp((v_result->>v_key)::double precision))));
    END IF;
  END LOOP;
  FOREACH v_key IN ARRAY ARRAY['spec','detail','result'] LOOP
    IF pg_catalog.jsonb_typeof(v_result->v_key)='string' THEN
      v_result:=pg_catalog.jsonb_set(v_result,ARRAY[v_key],(v_result->>v_key)::jsonb);
    END IF;
  END LOOP;
  RETURN v_result;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_job(p_id text)
RETURNS jsonb LANGUAGE sql STABLE SET search_path = '' AS $fn$
SELECT astra_ingestion_v1.rpc_public_row(pg_catalog.to_jsonb(j)) || pg_catalog.jsonb_build_object(
 'partitions',COALESCE((SELECT pg_catalog.jsonb_agg(astra_ingestion_v1.rpc_public_row(pg_catalog.to_jsonb(p)) || pg_catalog.jsonb_build_object(
     'verification',(SELECT astra_ingestion_v1.rpc_public_row(pg_catalog.to_jsonb(v)) FROM astra_ingestion_v1.verifications v WHERE v.partition_id=p.id)) ORDER BY p.symbol,p.start_at)
     FROM astra_ingestion_v1.partitions p WHERE p.job_id=j.id),'[]'::jsonb),
 'events',COALESCE((SELECT pg_catalog.jsonb_agg(astra_ingestion_v1.rpc_public_row(pg_catalog.to_jsonb(e)) ORDER BY e.timestamp DESC)
     FROM (SELECT timestamp,event,detail FROM astra_ingestion_v1.events WHERE job_id=j.id ORDER BY timestamp DESC LIMIT 30) e),'[]'::jsonb),
 'coverage_certification','NOT_CERTIFIED','verification_meaning','Exact retained source response to stored record comparison')
FROM astra_ingestion_v1.jobs j WHERE j.id=p_id
$fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_event(p_job text,p_event text,p_detail jsonb,p_now double precision)
RETURNS void LANGUAGE sql VOLATILE SET search_path = '' AS $fn$
INSERT INTO astra_ingestion_v1.events(id,job_id,timestamp,event,detail)
VALUES(pg_catalog.gen_random_uuid()::text,p_job,p_now,p_event,astra_ingestion_v1.rpc_canonical(p_detail))
$fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_refresh(p_job text,p_now double precision)
RETURNS void LANGUAGE plpgsql VOLATILE SET search_path = '' AS $fn$
DECLARE v_status text; v_verification text; v_statuses text[];
BEGIN
  IF (SELECT status FROM astra_ingestion_v1.jobs WHERE id=p_job) IN ('paused','cancelled') THEN RETURN; END IF;
  SELECT pg_catalog.array_agg(status) INTO v_statuses FROM astra_ingestion_v1.partitions WHERE job_id=p_job;
  IF v_statuses && ARRAY['pending','running','loaded','verifying'] THEN v_status:='running'; v_verification:='pending';
  ELSIF pg_catalog.cardinality(v_statuses)>0 AND 'verified'=ALL(v_statuses) THEN v_status:='completed';v_verification:='passed';
  ELSIF 'blocked'=ANY(v_statuses) THEN v_status:='blocked';v_verification:='blocked';
  ELSIF 'failed'=ANY(v_statuses) THEN v_status:='failed';v_verification:='failed';
  ELSE v_status:='cancelled';v_verification:='cancelled'; END IF;
  UPDATE astra_ingestion_v1.jobs SET status=v_status,verification_status=v_verification,updated_at=p_now WHERE id=p_job;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_owned(p_claim jsonb,p_allow_deadline boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SET search_path = '' AS $fn$
DECLARE v_p astra_ingestion_v1.partitions%ROWTYPE; v_j astra_ingestion_v1.jobs%ROWTYPE; v_now double precision:=EXTRACT(EPOCH FROM pg_catalog.clock_timestamp());
BEGIN
  IF pg_catalog.jsonb_typeof(p_claim) IS DISTINCT FROM 'object'
     OR pg_catalog.jsonb_typeof(p_claim->'id') IS DISTINCT FROM 'string'
     OR pg_catalog.jsonb_typeof(p_claim->'owner') IS DISTINCT FROM 'string'
     OR pg_catalog.jsonb_typeof(p_claim->'generation') IS DISTINCT FROM 'number'
     OR (p_claim->>'generation')!~'^[0-9]{1,10}$' THEN
    RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Invalid ownership claim';
  END IF;
  SELECT * INTO v_p FROM astra_ingestion_v1.partitions WHERE id=p_claim->>'id';
  IF NOT FOUND OR v_p.owner IS DISTINCT FROM p_claim->>'owner' OR v_p.generation::bigint<>(p_claim->>'generation')::bigint
     OR v_p.lease_until IS NULL OR v_p.lease_until<=v_now THEN
    RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Worker ownership is no longer valid';
  END IF;
  SELECT * INTO STRICT v_j FROM astra_ingestion_v1.jobs WHERE id=v_p.job_id;
  IF v_j.status<>'running' OR (NOT p_allow_deadline AND v_j.deadline_at<=v_now) THEN
    RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Job is stopped or its deadline has expired';
  END IF;
  RETURN pg_catalog.jsonb_build_object('partition',pg_catalog.to_jsonb(v_p),'job',pg_catalog.to_jsonb(v_j),'now',v_now);
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_json_unique(p_value json)
RETURNS void LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $fn$
DECLARE v_item json;
BEGIN
  IF pg_catalog.json_typeof(p_value)='object' THEN
    IF (SELECT pg_catalog.count(*)<>pg_catalog.count(DISTINCT key) FROM pg_catalog.json_each(p_value)) THEN
      RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Duplicate source JSON object key';
    END IF;
    FOR v_item IN SELECT value FROM pg_catalog.json_each(p_value) LOOP PERFORM astra_ingestion_v1.rpc_json_unique(v_item); END LOOP;
  ELSIF pg_catalog.json_typeof(p_value)='array' THEN
    FOR v_item IN SELECT value FROM pg_catalog.json_array_elements(p_value) LOOP PERFORM astra_ingestion_v1.rpc_json_unique(v_item); END LOOP;
  END IF;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_number(p_value jsonb,p_positive boolean,p_integer boolean)
RETURNS text LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $fn$
DECLARE v_n numeric; v_digits text;
BEGIN
  IF pg_catalog.jsonb_typeof(p_value) IS DISTINCT FROM 'number' OR pg_catalog.length(p_value::text)>128 THEN
    RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Source value must be a bounded JSON number';
  END IF;
  v_n:=(p_value::text)::numeric; v_digits:=pg_catalog.regexp_replace(pg_catalog.replace(p_value::text,'.',''),'^0+','');
  IF (CASE WHEN p_positive THEN v_n<=0 ELSE v_n<0 END)
     OR (v_n<>0 AND (v_n<1e-30::numeric OR v_n>=1e31::numeric OR pg_catalog.length(v_digits)>40))
     OR (p_integer AND (v_n<>pg_catalog.trunc(v_n) OR v_n>9223372036854775807::numeric)) THEN
    RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Source value exceeds its numeric contract';
  END IF;
  RETURN CASE WHEN v_n=0 THEN '0' ELSE pg_catalog.trim_scale(v_n)::text END;
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_source_timestamp(p_value text)
RETURNS timestamptz LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $fn$
DECLARE v_value text:=p_value; v_extra text;
BEGIN
  IF v_value IS NULL OR v_value !~ '^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}([.,][0-9]+)?(Z|[+-]\d{2}:\d{2})$' THEN
    RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Source timestamp must include an explicit RFC3339 offset';
  END IF;
  v_extra:=pg_catalog.substring(v_value,'[.,][0-9]{6}([0-9]+)(Z|[+-]\d{2}:\d{2})$');
  IF v_extra ~ '[1-9]' THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Timestamp has unsupported sub-microsecond precision'; END IF;
  v_value:=pg_catalog.regexp_replace(v_value,'([.,][0-9]{6})[0-9]+(Z|[+-]\d{2}:\d{2})$','\1\2');
  RETURN pg_catalog.replace(v_value,',','.')::timestamptz;
EXCEPTION WHEN invalid_text_representation OR datetime_field_overflow OR invalid_datetime_format THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Invalid source timestamp';
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_parse_source(p_raw text,p_symbol text,p_start text,p_end text)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $fn$
DECLARE v_json json; v_body jsonb; v_row jsonb; v_record jsonb; v_records jsonb:='{}'; v_token jsonb; v_time timestamptz; v_timestamp text; v_key text;
BEGIN
  IF p_raw IS NULL OR pg_catalog.octet_length(p_raw)>2097152 THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Response exceeds two MiB receipt limit'; END IF;
  v_json:=p_raw::json; PERFORM astra_ingestion_v1.rpc_json_unique(v_json); v_body:=v_json::jsonb;
  IF pg_catalog.jsonb_typeof(v_body) IS DISTINCT FROM 'object' OR pg_catalog.jsonb_typeof(v_body->'bars') IS DISTINCT FROM 'object'
     OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_object_keys(v_body->'bars') k WHERE k<>p_symbol) THEN
    RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Source response contains invalid or out-of-scope symbols';
  END IF;
  IF NOT (v_body->'bars' ? p_symbol) THEN v_body:=pg_catalog.jsonb_set(v_body,ARRAY['bars',p_symbol],'[]'::jsonb); END IF;
  IF pg_catalog.jsonb_typeof(v_body->'bars'->p_symbol) IS DISTINCT FROM 'array' OR pg_catalog.jsonb_array_length(v_body->'bars'->p_symbol)>1000 THEN
    RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Source bars must be a list of at most 1000 rows';
  END IF;
  v_token:=COALESCE(v_body->'next_page_token','null'::jsonb);
  IF v_token<>'null'::jsonb AND (pg_catalog.jsonb_typeof(v_token)<>'string' OR pg_catalog.char_length(v_token#>>'{}') NOT BETWEEN 1 AND 4096) THEN
    RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Invalid source pagination token';
  END IF;
  FOR v_row IN SELECT value FROM pg_catalog.jsonb_array_elements(v_body->'bars'->p_symbol) LOOP
    IF pg_catalog.jsonb_typeof(v_row) IS DISTINCT FROM 'object' OR NOT (v_row ?& ARRAY['t','o','h','l','c','v','n','vw']) OR pg_catalog.jsonb_typeof(v_row->'t') IS DISTINCT FROM 'string' THEN
      RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Bar is missing a required field';
    END IF;
    -- Source RFC3339 offsets normalize to UTC; precision beyond microseconds
    -- must be zero. Admission timestamps remain canonical UTC text.
    v_time:=astra_ingestion_v1.rpc_source_timestamp(v_row->>'t');
    IF v_time<astra_ingestion_v1.rpc_timestamp(p_start) OR v_time>=astra_ingestion_v1.rpc_timestamp(p_end) THEN
      RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Bar timestamp lies outside its admitted interval';
    END IF;
    v_record:=pg_catalog.jsonb_build_object('symbol',p_symbol,'timestamp',astra_ingestion_v1.rpc_time(v_time),
      'open',astra_ingestion_v1.rpc_number(v_row->'o',true,false),'high',astra_ingestion_v1.rpc_number(v_row->'h',true,false),
      'low',astra_ingestion_v1.rpc_number(v_row->'l',true,false),'close',astra_ingestion_v1.rpc_number(v_row->'c',true,false),
      'volume',astra_ingestion_v1.rpc_number(v_row->'v',false,false),'trade_count',astra_ingestion_v1.rpc_number(v_row->'n',false,true),
      'vwap',astra_ingestion_v1.rpc_number(v_row->'vw',true,false));
    IF NOT ((v_record->>'low')::numeric<=(v_record->>'open')::numeric AND (v_record->>'open')::numeric<=(v_record->>'high')::numeric
      AND (v_record->>'low')::numeric<=(v_record->>'close')::numeric AND (v_record->>'close')::numeric<=(v_record->>'high')::numeric) THEN
      RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Bar violates OHLC ordering';
    END IF;
    v_key:=p_symbol||'|'||(v_record->>'timestamp');
    IF v_records ? v_key AND v_records->v_key<>v_record THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Source contains conflicting duplicate bars'; END IF;
    v_records:=v_records||pg_catalog.jsonb_build_object(v_key,v_record);
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('next_page_token',v_token,'records',COALESCE((SELECT pg_catalog.jsonb_agg(value ORDER BY key COLLATE "C") FROM pg_catalog.jsonb_each(v_records)),'[]'::jsonb));
END $fn$;

CREATE FUNCTION astra_ingestion_v1.rpc_dispatch(p_operation text,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' SET statement_timeout='10s' SET lock_timeout='3s' AS $fn$
DECLARE
 v_headers jsonb; v_claims jsonb; v_token text; v_actor text; v_credential text; v_now double precision;
 v_result jsonb; v_spec jsonb; v_hash text; v_id text; v_key text; v_action text; v_claim jsonb; v_owned jsonb;
 v_job astra_ingestion_v1.jobs%ROWTYPE; v_part astra_ingestion_v1.partitions%ROWTYPE;
 v_start timestamptz; v_end timestamptz; v_cursor timestamptz; v_until timestamptz; v_symbol text;
 v_worker text; v_lease integer; v_phase text; v_status text; v_verification text; v_next double precision;
 v_raw text; v_parsed jsonb; v_record jsonb; v_payload_text text; v_previous text; v_count integer; v_bytes integer; v_page_token text;
 v_failures integer; v_delay double precision; v_proposed double precision; v_retry boolean; v_reason text; v_errcode text; v_errmessage text;
BEGIN
  -- A machine endpoint: an anonymous gateway context is necessary, but never
  -- sufficient. Independent scoped capability authentication happens here, so
  -- calling this private function directly cannot bypass the check.
  v_headers:=NULLIF(pg_catalog.current_setting('request.headers',true),'')::jsonb;
  v_claims:=NULLIF(pg_catalog.current_setting('request.jwt.claims',true),'')::jsonb;
  v_token:=v_headers->>'x-astra-ingestion-token';
  IF pg_catalog.current_setting('role',true) IS DISTINCT FROM 'anon'
     OR v_claims->>'role' IS DISTINCT FROM 'anon' OR auth.uid() IS NOT NULL
     OR pg_catalog.current_setting('request.method',true) IS DISTINCT FROM 'POST'
     OR pg_catalog.jsonb_typeof(v_headers->'x-astra-ingestion-token') IS DISTINCT FROM 'string'
     OR v_token !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE='PT401',MESSAGE='Ingestion capability authentication required';
  END IF;
  v_credential:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_token,'UTF8')),'hex');
  SELECT actor INTO v_actor FROM astra_ingestion_v1.runtime_credentials
    WHERE token_sha256=v_credential AND revoked_at IS NULL AND expires_at>pg_catalog.clock_timestamp();
  IF v_actor IS NULL THEN RAISE EXCEPTION USING ERRCODE='PT401',MESSAGE='Ingestion capability authentication required'; END IF;
  IF p_operation IS NULL OR NOT (p_operation='health' OR (v_actor='api' AND p_operation IN ('list_jobs','get_job','submit_job','control_job'))
     OR (v_actor='worker' AND p_operation IN ('claim_next','reserve_request','commit_page','verification_material','finish_verification','fail_claim'))) THEN
    RAISE EXCEPTION USING ERRCODE='PT403',MESSAGE='Operation is outside this capability';
  END IF;
  IF pg_catalog.jsonb_typeof(p_payload) IS DISTINCT FROM 'object' OR pg_catalog.octet_length(p_payload::text)>8388608 THEN
    RAISE EXCEPTION USING ERRCODE='PT400',MESSAGE='A bounded operation object is required';
  END IF;
  -- Authentication precedes the global lock. Never accept SQL, identifiers,
  -- function names, destinations or schema choices from the caller.
  PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
  IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.runtime_credentials WHERE token_sha256=v_credential AND actor=v_actor AND revoked_at IS NULL AND expires_at>pg_catalog.clock_timestamp()) THEN
    RAISE EXCEPTION USING ERRCODE='PT401',MESSAGE='Ingestion capability authentication required';
  END IF;
  -- All mutating operations are in this exception subtransaction. An expected
  -- error rolls back its effects before the safe error envelope is returned.
  BEGIN
    v_now:=EXTRACT(EPOCH FROM pg_catalog.clock_timestamp());
    CASE p_operation
    WHEN 'health' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY[]::text[]) THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Unexpected health parameters'; END IF;
      IF (SELECT version FROM astra_ingestion_v1.schema_info WHERE id=1) IS DISTINCT FROM 1 THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Schema migration required'; END IF;
      v_result:=pg_catalog.jsonb_build_object('ready',true,'schema_version',1,'rpc_version',1);
    WHEN 'list_jobs' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['limit']) OR pg_catalog.jsonb_typeof(p_payload->'limit')<>'number' OR (p_payload->>'limit')!~'^[0-9]{1,3}$' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid list bound'; END IF;
      SELECT COALESCE(pg_catalog.jsonb_agg(astra_ingestion_v1.rpc_public_row(pg_catalog.to_jsonb(q)) ORDER BY q.created_at DESC),'[]'::jsonb)
        INTO v_result FROM (SELECT * FROM astra_ingestion_v1.jobs ORDER BY created_at DESC LIMIT GREATEST(1,LEAST((p_payload->>'limit')::integer,100))) q;
    WHEN 'get_job' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['job_id']) OR pg_catalog.jsonb_typeof(p_payload->'job_id')<>'string' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid job identifier'; END IF;
      v_result:=astra_ingestion_v1.rpc_job(p_payload->>'job_id');
    WHEN 'submit_job' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['spec','request_key']) OR pg_catalog.jsonb_typeof(p_payload->'request_key')<>'string'
        OR (p_payload->>'request_key')!~'^[A-Za-z0-9._:-]{8,128}$' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='A stable 8-128 character idempotency key is required'; END IF;
      v_spec:=astra_ingestion_v1.rpc_spec(p_payload->'spec');
      v_hash:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(astra_ingestion_v1.rpc_canonical(v_spec),'UTF8')),'hex');
      SELECT * INTO v_job FROM astra_ingestion_v1.jobs WHERE request_key=p_payload->>'request_key';
      IF FOUND THEN
        IF v_job.scope_hash<>v_hash THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Idempotency key already belongs to another scope'; END IF;
        v_id:=v_job.id;
      ELSE
        v_id:=pg_catalog.gen_random_uuid()::text;
        INSERT INTO astra_ingestion_v1.jobs(id,request_key,scope_hash,name,spec,status,created_at,updated_at,deadline_at)
          VALUES(v_id,p_payload->>'request_key',v_hash,v_spec->>'name',astra_ingestion_v1.rpc_canonical(v_spec),'queued',v_now,v_now,v_now+(v_spec->>'deadline_seconds')::integer);
        v_start:=astra_ingestion_v1.rpc_timestamp(v_spec->>'start');v_end:=astra_ingestion_v1.rpc_timestamp(v_spec->>'end');
        FOR v_symbol IN SELECT value FROM pg_catalog.jsonb_array_elements_text(v_spec->'symbols') LOOP
          v_cursor:=v_start;
          WHILE v_cursor<v_end LOOP
            v_until:=LEAST(v_cursor+INTERVAL '24 hours',v_end);
            INSERT INTO astra_ingestion_v1.partitions(id,job_id,symbol,start_at,end_at,status)
              VALUES(pg_catalog.gen_random_uuid()::text,v_id,v_symbol,astra_ingestion_v1.rpc_time(v_cursor),astra_ingestion_v1.rpc_time(v_until),'pending');
            v_cursor:=v_until;
          END LOOP;
        END LOOP;
        PERFORM astra_ingestion_v1.rpc_event(v_id,'job_admitted',pg_catalog.jsonb_build_object('scope_hash',v_hash,'symbols',v_spec->'symbols'),v_now);
      END IF;
      v_result:=astra_ingestion_v1.rpc_job(v_id);
    WHEN 'control_job' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['job_id','action']) THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid control payload'; END IF;
      v_action:=p_payload->>'action';v_id:=p_payload->>'job_id';
      IF v_action NOT IN ('pause','resume','cancel') OR v_action IS NULL THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Unsupported control'; END IF;
      SELECT * INTO v_job FROM astra_ingestion_v1.jobs WHERE id=v_id;
      IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='AI004',MESSAGE='Job does not exist'; END IF;
      IF v_action='resume' THEN
        IF v_job.status<>'paused' OR v_job.deadline_at<=v_now THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Only an unexpired paused job can resume; quality holds remain in force'; END IF;
        UPDATE astra_ingestion_v1.jobs SET status='running',updated_at=v_now WHERE id=v_id;
        PERFORM astra_ingestion_v1.rpc_refresh(v_id,v_now);
      ELSIF v_action='pause' THEN
        IF v_job.status NOT IN ('queued','running','paused') THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Only queued or running jobs can pause'; END IF;
        UPDATE astra_ingestion_v1.jobs SET status='paused',updated_at=v_now WHERE id=v_id;
        UPDATE astra_ingestion_v1.partitions SET status=CASE WHEN status='verifying' THEN 'loaded' ELSE 'pending' END,
          owner=NULL,lease_until=NULL,generation=generation+1 WHERE job_id=v_id AND status IN ('running','verifying');
      ELSE
        IF v_job.status='completed' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='A completed job cannot be cancelled'; END IF;
        UPDATE astra_ingestion_v1.jobs SET status='cancelled',verification_status='cancelled',updated_at=v_now WHERE id=v_id;
        UPDATE astra_ingestion_v1.partitions SET status='cancelled',verification_status='cancelled',owner=NULL,lease_until=NULL,generation=generation+1
          WHERE job_id=v_id AND status IN ('pending','running','loaded','verifying');
      END IF;
      PERFORM astra_ingestion_v1.rpc_event(v_id,'job_'||v_action,'{}',v_now);v_result:=astra_ingestion_v1.rpc_job(v_id);
    WHEN 'claim_next' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['worker_id','lease_seconds']) OR pg_catalog.jsonb_typeof(p_payload->'worker_id') IS DISTINCT FROM 'string'
        OR (p_payload->>'worker_id')!~'^[A-Za-z0-9._:-]{1,128}$' OR pg_catalog.jsonb_typeof(p_payload->'lease_seconds') IS DISTINCT FROM 'number'
        OR (p_payload->>'lease_seconds')!~'^[0-9]{1,3}$' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid bounded worker claim'; END IF;
      v_worker:=p_payload->>'worker_id';v_lease:=GREATEST(30,LEAST((p_payload->>'lease_seconds')::integer,300));
      FOR v_job IN SELECT * FROM astra_ingestion_v1.jobs WHERE status IN ('queued','running') AND deadline_at<=v_now LOOP
        UPDATE astra_ingestion_v1.partitions SET status='failed',verification_status='failed',owner=NULL,lease_until=NULL,generation=generation+1,error='Whole-job deadline exceeded'
          WHERE job_id=v_job.id AND status IN ('pending','running','loaded','verifying');
        UPDATE astra_ingestion_v1.jobs SET status='failed',verification_status='failed',error='Whole-job deadline exceeded',updated_at=v_now WHERE id=v_job.id;
        PERFORM astra_ingestion_v1.rpc_event(v_job.id,'deadline_exceeded','{}',v_now);
      END LOOP;
      SELECT p.* INTO v_part FROM astra_ingestion_v1.partitions p JOIN astra_ingestion_v1.jobs j ON j.id=p.job_id
        WHERE j.status IN ('queued','running') AND j.deadline_at>v_now AND p.next_attempt_at<=v_now
        AND (p.status IN ('pending','loaded') OR (p.status IN ('running','verifying') AND p.lease_until<=v_now))
        ORDER BY j.created_at,p.symbol,p.start_at LIMIT 1;
      IF NOT FOUND THEN v_result:='null';
      ELSE
        SELECT * INTO STRICT v_job FROM astra_ingestion_v1.jobs WHERE id=v_part.job_id;
        v_phase:=CASE WHEN v_part.status IN ('loaded','verifying') THEN 'verify' ELSE 'fetch' END;
        v_status:=CASE WHEN v_phase='verify' THEN 'verifying' ELSE 'running' END;
        UPDATE astra_ingestion_v1.partitions SET status=v_status,owner=v_worker,generation=generation+1,lease_until=v_now+v_lease WHERE id=v_part.id RETURNING * INTO v_part;
        UPDATE astra_ingestion_v1.jobs SET status='running',updated_at=v_now WHERE id=v_job.id;
        PERFORM astra_ingestion_v1.rpc_event(v_job.id,'partition_claimed',pg_catalog.jsonb_build_object('partition_id',v_part.id,'generation',v_part.generation,'phase',v_phase),v_now);
        v_result:=pg_catalog.to_jsonb(v_part)||pg_catalog.jsonb_build_object('phase',v_phase,'spec',v_job.spec::jsonb,'start',v_part.start_at,'end',v_part.end_at);
      END IF;
    WHEN 'reserve_request' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['claim']) THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid reservation payload'; END IF;
      v_claim:=p_payload->'claim';v_owned:=astra_ingestion_v1.rpc_owned(v_claim);
      SELECT * INTO v_part FROM pg_catalog.jsonb_populate_record(NULL::astra_ingestion_v1.partitions,v_owned->'partition');
      SELECT * INTO v_job FROM pg_catalog.jsonb_populate_record(NULL::astra_ingestion_v1.jobs,v_owned->'job');v_now:=(v_owned->>'now')::double precision;
      IF v_part.status<>'running' THEN RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Not a fetch claim'; END IF;
      IF v_job.request_count>=(v_job.spec::jsonb->>'max_requests')::integer THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Whole-job provider request budget exhausted'; END IF;
      SELECT next_request_at INTO STRICT v_next FROM astra_ingestion_v1.source_limits WHERE id='alpaca';
      IF v_next>=v_job.deadline_at THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Provider not-before time exceeds this job deadline'; END IF;
      IF v_next>v_now THEN
        UPDATE astra_ingestion_v1.partitions SET status='pending',owner=NULL,lease_until=NULL,next_attempt_at=v_next WHERE id=v_part.id;
        -- Deliberately return, do not raise: pacing-release effects must commit.
        RETURN pg_catalog.jsonb_build_object('ok',false,'error',pg_catalog.jsonb_build_object('code','request_deferred','message','Shared provider pacing'));
      END IF;
      UPDATE astra_ingestion_v1.source_limits SET next_request_at=v_now+2 WHERE id='alpaca';
      UPDATE astra_ingestion_v1.jobs SET request_count=request_count+1,updated_at=v_now WHERE id=v_job.id;
      UPDATE astra_ingestion_v1.partitions SET request_count=request_count+1 WHERE id=v_part.id;
      PERFORM astra_ingestion_v1.rpc_owned(v_claim);v_result:='null';
    WHEN 'commit_page' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['claim','raw_body','request_id','records','next_page_token','response_sha256'])
        OR pg_catalog.jsonb_typeof(p_payload->'raw_body') IS DISTINCT FROM 'string'
        OR pg_catalog.jsonb_typeof(p_payload->'records') IS DISTINCT FROM 'array'
        OR pg_catalog.jsonb_typeof(p_payload->'response_sha256') IS DISTINCT FROM 'string'
        OR (p_payload->'request_id'<>'null'::jsonb AND (pg_catalog.jsonb_typeof(p_payload->'request_id')<>'string' OR pg_catalog.char_length(p_payload->>'request_id')>256)) THEN
        RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Invalid source page payload';
      END IF;
      v_claim:=p_payload->'claim';v_owned:=astra_ingestion_v1.rpc_owned(v_claim);
      SELECT * INTO v_part FROM pg_catalog.jsonb_populate_record(NULL::astra_ingestion_v1.partitions,v_owned->'partition');
      SELECT * INTO v_job FROM pg_catalog.jsonb_populate_record(NULL::astra_ingestion_v1.jobs,v_owned->'job');v_now:=(v_owned->>'now')::double precision;
      IF v_part.status<>'running' OR v_part.next_page_token IS DISTINCT FROM v_claim->>'next_page_token' THEN RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Page checkpoint moved'; END IF;
      IF v_part.request_count<=v_part.page_count THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Provider request was not reserved'; END IF;
      v_raw:=p_payload->>'raw_body';v_hash:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_raw,'UTF8')),'hex');
      IF v_hash<>p_payload->>'response_sha256' THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Source receipt hash does not match'; END IF;
      v_parsed:=astra_ingestion_v1.rpc_parse_source(v_raw,v_part.symbol,v_part.start_at,v_part.end_at);
      IF v_parsed->'records'<>p_payload->'records' OR v_parsed->'next_page_token'<>p_payload->'next_page_token' THEN
        RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Normalized records do not match the retained source response';
      END IF;
      v_page_token:=v_parsed->>'next_page_token';
      IF v_page_token IS NOT NULL AND (v_page_token IS NOT DISTINCT FROM v_part.next_page_token
          OR EXISTS(SELECT 1 FROM astra_ingestion_v1.receipts WHERE partition_id=v_part.id AND token_in=v_page_token)) THEN
        RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Provider repeated a pagination token';
      END IF;
      v_count:=0;
      FOR v_record IN SELECT value FROM pg_catalog.jsonb_array_elements(v_parsed->'records') LOOP
        v_key:=(v_record->>'symbol')||'|'||(v_record->>'timestamp');v_payload_text:=astra_ingestion_v1.rpc_canonical(v_record);
        SELECT payload INTO v_previous FROM astra_ingestion_v1.records WHERE partition_id=v_part.id AND record_key=v_key;
        IF FOUND THEN
          IF v_previous::jsonb<>v_record THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Conflicting source values for existing record'; END IF;
        ELSE
          INSERT INTO astra_ingestion_v1.records(partition_id,record_key,payload) VALUES(v_part.id,v_key,v_payload_text);v_count:=v_count+1;
        END IF;
      END LOOP;
      v_bytes:=pg_catalog.octet_length(v_raw);
      IF v_job.record_count+v_count>(v_job.spec::jsonb->>'max_records')::integer THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Whole-job record budget exhausted'; END IF;
      IF v_job.receipt_bytes+v_bytes>33554432 THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Whole-job retained source budget exceeds 32 MiB'; END IF;
      IF v_page_token IS NULL AND v_part.record_count+v_count=0 THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Empty source coverage requires explicit review'; END IF;
      INSERT INTO astra_ingestion_v1.receipts(partition_id,page_no,token_in,token_out,request_id,raw_body,body_sha256,received_at)
        VALUES(v_part.id,v_part.page_count,v_part.next_page_token,v_page_token,p_payload->>'request_id',v_raw,v_hash,v_now);
      PERFORM astra_ingestion_v1.rpc_owned(v_claim);
      v_status:=CASE WHEN v_page_token IS NULL THEN 'loaded' ELSE 'pending' END;
      UPDATE astra_ingestion_v1.partitions SET status=v_status,next_page_token=v_page_token,page_count=page_count+1,record_count=record_count+v_count,
        owner=NULL,lease_until=NULL,last_progress_at=v_now,next_attempt_at=0,error=NULL WHERE id=v_part.id;
      UPDATE astra_ingestion_v1.jobs SET record_count=record_count+v_count,receipt_bytes=receipt_bytes+v_bytes,updated_at=v_now,last_progress_at=v_now WHERE id=v_job.id;
      PERFORM astra_ingestion_v1.rpc_event(v_job.id,'page_committed',pg_catalog.jsonb_build_object('partition_id',v_part.id,'page',v_part.page_count,'records',v_count,'receipt_sha256',v_hash),v_now);
      v_result:=pg_catalog.jsonb_build_object('records',v_count,'phase',CASE WHEN v_status='loaded' THEN 'verify' ELSE 'fetch' END);
    WHEN 'verification_material' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['claim']) THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid verification payload'; END IF;
      v_claim:=p_payload->'claim';v_owned:=astra_ingestion_v1.rpc_owned(v_claim);
      IF v_owned->'partition'->>'status'<>'verifying' THEN RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Not a verification claim'; END IF;
      -- One SELECT gives both aggregates the same MVCC snapshot under READ COMMITTED.
      SELECT pg_catalog.jsonb_build_object(
        'receipts',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(r) ORDER BY r.page_no) FROM astra_ingestion_v1.receipts r WHERE r.partition_id=v_claim->>'id'),'[]'::jsonb),
        'records',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('record_key',r.record_key,'payload',r.payload::jsonb) ORDER BY r.record_key COLLATE "C") FROM astra_ingestion_v1.records r WHERE r.partition_id=v_claim->>'id'),'[]'::jsonb)) INTO v_result;
      IF pg_catalog.octet_length(v_result::text)>67108864 THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Verification snapshot exceeds bounded response size'; END IF;
      PERFORM astra_ingestion_v1.rpc_owned(v_claim);
    WHEN 'finish_verification' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['claim','result']) OR pg_catalog.jsonb_typeof(p_payload->'result') IS DISTINCT FROM 'object' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid verification result'; END IF;
      v_claim:=p_payload->'claim';v_owned:=astra_ingestion_v1.rpc_owned(v_claim);
      SELECT * INTO v_part FROM pg_catalog.jsonb_populate_record(NULL::astra_ingestion_v1.partitions,v_owned->'partition');
      SELECT * INTO v_job FROM pg_catalog.jsonb_populate_record(NULL::astra_ingestion_v1.jobs,v_owned->'job');v_now:=(v_owned->>'now')::double precision;
      IF v_part.status<>'verifying' THEN RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Not a verification claim'; END IF;
      v_result:=p_payload->'result';
      IF NOT astra_ingestion_v1.rpc_keys(v_result,ARRAY['status','expected_count','actual_count','expected_hash','actual_hash',
          'missing_count','changed_count','unexpected_count','expected_duplicate_count','actual_duplicate_count',
          'missing_keys','changed_keys','unexpected_keys','expected_duplicate_keys','actual_duplicate_keys',
          'scope_hash','receipt_count','coverage_certification','verification_kind']) THEN
        RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Verification must retain the complete comparison evidence';
      END IF;
      FOREACH v_key IN ARRAY ARRAY['expected_count','actual_count','missing_count','changed_count','unexpected_count',
          'expected_duplicate_count','actual_duplicate_count','receipt_count'] LOOP
        IF pg_catalog.jsonb_typeof(v_result->v_key) IS DISTINCT FROM 'number' OR (v_result->>v_key)!~'^[0-9]{1,6}$' THEN
          RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Verification counts must be bounded nonnegative integers';
        END IF;
      END LOOP;
      FOREACH v_key IN ARRAY ARRAY['expected_hash','actual_hash','scope_hash'] LOOP
        IF pg_catalog.jsonb_typeof(v_result->v_key) IS DISTINCT FROM 'string' OR (v_result->>v_key)!~'^[0-9a-f]{64}$' THEN
          RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Verification digests must be complete SHA256 values';
        END IF;
      END LOOP;
      FOREACH v_key IN ARRAY ARRAY['missing_keys','changed_keys','unexpected_keys','expected_duplicate_keys','actual_duplicate_keys'] LOOP
        IF pg_catalog.jsonb_typeof(v_result->v_key) IS DISTINCT FROM 'array' THEN
          RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Verification key examples must be bounded arrays';
        END IF;
        IF pg_catalog.jsonb_array_length(v_result->v_key)<>LEAST((v_result->>pg_catalog.replace(v_key,'_keys','_count'))::integer,20)
            OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(v_result->v_key) e(v)
            WHERE pg_catalog.jsonb_typeof(v)<>'string' OR pg_catalog.char_length(v#>>'{}')>128) THEN
          RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Verification key examples must be bounded arrays';
        END IF;
      END LOOP;
      -- Bind the worker's actual digest to the current retained target snapshot.
      SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(astra_ingestion_v1.rpc_canonical(
        COALESCE(pg_catalog.jsonb_agg(payload::jsonb ORDER BY record_key COLLATE "C"),'[]'::jsonb)),'UTF8')),'hex')
        INTO v_hash FROM astra_ingestion_v1.records WHERE partition_id=v_part.id;
      IF v_result->>'actual_hash' IS DISTINCT FROM v_hash THEN
        RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Verification target digest changed before finalization';
      END IF;
      IF v_result->>'status' NOT IN ('passed','failed') OR v_result->>'status' IS NULL
        OR v_result->>'scope_hash' IS DISTINCT FROM v_job.scope_hash
        OR v_result->>'coverage_certification' IS DISTINCT FROM 'NOT_CERTIFIED'
        OR v_result->>'verification_kind' IS DISTINCT FROM 'source_to_target_exact'
        OR (v_result->>'receipt_count')::integer IS DISTINCT FROM v_part.page_count
        OR (v_result->>'actual_count')::integer IS DISTINCT FROM v_part.record_count THEN
        RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Verification evidence does not match its immutable claim';
      END IF;
      IF v_result->>'status'='passed' AND ((v_result->>'expected_count')::integer IS DISTINCT FROM v_part.record_count
          OR v_result->>'expected_hash' IS DISTINCT FROM v_result->>'actual_hash'
          OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_each_text(v_result) e(k,v)
              WHERE k IN ('missing_count','changed_count','unexpected_count','expected_duplicate_count','actual_duplicate_count') AND v<>'0')) THEN
        RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Passing verification contains inconsistent counts or digests';
      END IF;
      INSERT INTO astra_ingestion_v1.verifications(partition_id,checked_at,result) VALUES(v_part.id,v_now,astra_ingestion_v1.rpc_canonical(v_result))
        ON CONFLICT(partition_id) DO UPDATE SET checked_at=excluded.checked_at,result=excluded.result;
      PERFORM astra_ingestion_v1.rpc_owned(v_claim);
      v_status:=CASE WHEN v_result->>'status'='passed' THEN 'verified' ELSE 'blocked' END;
      UPDATE astra_ingestion_v1.partitions SET status=v_status,verification_status=v_result->>'status',owner=NULL,lease_until=NULL,last_progress_at=v_now,
        error=CASE WHEN v_status='verified' THEN NULL ELSE 'Source-to-target reconciliation failed' END WHERE id=v_part.id;
      UPDATE astra_ingestion_v1.jobs SET last_progress_at=v_now,updated_at=v_now WHERE id=v_job.id;
      PERFORM astra_ingestion_v1.rpc_event(v_job.id,'verification_'||(v_result->>'status'),pg_catalog.jsonb_build_object('partition_id',v_part.id)||v_result,v_now);
      PERFORM astra_ingestion_v1.rpc_refresh(v_job.id,v_now);v_result:='null';
    WHEN 'fail_claim' THEN
      IF NOT astra_ingestion_v1.rpc_keys(p_payload,ARRAY['claim','code','message','retryable','retry_after','raw_response'])
        OR pg_catalog.jsonb_typeof(p_payload->'code') IS DISTINCT FROM 'string' OR pg_catalog.jsonb_typeof(p_payload->'message') IS DISTINCT FROM 'string'
        OR pg_catalog.jsonb_typeof(p_payload->'retryable') IS DISTINCT FROM 'boolean' OR pg_catalog.jsonb_typeof(p_payload->'retry_after') IS DISTINCT FROM 'number'
        OR pg_catalog.length(p_payload->>'retry_after')>30 THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid bounded failure payload'; END IF;
      v_claim:=p_payload->'claim';v_owned:=astra_ingestion_v1.rpc_owned(v_claim,true);
      SELECT * INTO v_part FROM pg_catalog.jsonb_populate_record(NULL::astra_ingestion_v1.partitions,v_owned->'partition');
      SELECT * INTO v_job FROM pg_catalog.jsonb_populate_record(NULL::astra_ingestion_v1.jobs,v_owned->'job');v_now:=(v_owned->>'now')::double precision;
      v_failures:=v_part.retry_count+1;v_delay:=(p_payload->>'retry_after')::double precision;
      IF v_delay<0 OR v_delay>253402300799 THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid retry delay'; END IF;
      v_proposed:=v_now+GREATEST(v_delay,5.0*v_failures);v_retry:=(p_payload->>'retryable')::boolean AND v_failures<2 AND v_proposed<v_job.deadline_at;
      v_reason:=p_payload->>'message';
      IF (p_payload->>'retryable')::boolean AND v_proposed>=v_job.deadline_at THEN v_reason:=v_reason||'; provider wait exceeds the original job deadline'; END IF;
      v_reason:=pg_catalog.left((p_payload->>'code')||': '||v_reason,500);
      IF v_retry THEN v_status:=CASE WHEN v_part.status='verifying' THEN 'loaded' ELSE 'pending' END;v_verification:='pending';v_next:=v_proposed;
      ELSE v_status:=CASE WHEN (p_payload->>'retryable')::boolean THEN 'failed' ELSE 'blocked' END;v_verification:=v_status;v_next:=0; END IF;
      UPDATE astra_ingestion_v1.partitions SET status=v_status,verification_status=v_verification,
        retry_count=v_failures,next_attempt_at=v_next,error=v_reason WHERE id=v_part.id;
      IF v_delay>0 AND (p_payload->>'retryable')::boolean THEN UPDATE astra_ingestion_v1.source_limits SET next_request_at=GREATEST(next_request_at,LEAST(v_now+v_delay,253402300799)) WHERE id='alpaca'; END IF;
      IF p_payload->'raw_response'<>'null'::jsonb THEN
        IF pg_catalog.jsonb_typeof(p_payload->'raw_response')<>'string' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid rejected response'; END IF;
        v_raw:=p_payload->>'raw_response';IF pg_catalog.octet_length(v_raw)>2097152 THEN v_raw:='[Response exceeds retained-body bound]';END IF;
        INSERT INTO astra_ingestion_v1.rejections(id,partition_id,received_at,reason,raw_body,body_sha256)
          VALUES(pg_catalog.gen_random_uuid()::text,v_part.id,v_now,v_reason,v_raw,pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_raw,'UTF8')),'hex'));
      END IF;
      PERFORM astra_ingestion_v1.rpc_event(v_job.id,CASE WHEN v_retry THEN 'retry_scheduled' ELSE 'partition_'||v_status END,
        pg_catalog.jsonb_build_object('partition_id',v_part.id,'symbol',v_part.symbol,'reason',v_reason,'next_attempt_at',CASE WHEN v_next>0 THEN astra_ingestion_v1.rpc_time(pg_catalog.to_timestamp(v_next)) ELSE NULL END),v_now);
      PERFORM astra_ingestion_v1.rpc_owned(v_claim,true);
      UPDATE astra_ingestion_v1.partitions SET owner=NULL,lease_until=NULL WHERE id=v_part.id;
      PERFORM astra_ingestion_v1.rpc_refresh(v_job.id,v_now);v_result:='null';
    ELSE RAISE EXCEPTION USING ERRCODE='PT403',MESSAGE='Operation is outside this capability';
    END CASE;
    RETURN pg_catalog.jsonb_build_object('ok',true,'result',v_result);
  EXCEPTION
    WHEN SQLSTATE 'AI001' OR SQLSTATE 'AI002' OR SQLSTATE 'AI004' OR SQLSTATE 'AI005' THEN
      GET STACKED DIAGNOSTICS v_errcode=RETURNED_SQLSTATE,v_errmessage=MESSAGE_TEXT;
      RETURN pg_catalog.jsonb_build_object('ok',false,'error',pg_catalog.jsonb_build_object('code',
        CASE v_errcode WHEN 'AI001' THEN 'lease_lost' WHEN 'AI002' THEN 'quality_hold' WHEN 'AI004' THEN 'not_found' ELSE 'conflict' END,'message',v_errmessage));
    WHEN invalid_text_representation OR numeric_value_out_of_range OR datetime_field_overflow OR invalid_datetime_format OR null_value_not_allowed THEN
      RETURN pg_catalog.jsonb_build_object('ok',false,'error',pg_catalog.jsonb_build_object('code','conflict','message','Invalid operation value'));
  END;
END $fn$;

CREATE FUNCTION public.astra_ingestion_rpc_v1(operation text,payload jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path = '' SET statement_timeout='10s' SET lock_timeout='3s' AS $fn$
SELECT astra_ingestion_v1.rpc_dispatch(operation,payload)
$fn$;

-- Temporary CREATE is needed to transfer function ownership; revoke below.
GRANT USAGE,CREATE ON SCHEMA astra_ingestion_v1 TO astra_ingestion_rpc_owner_v1;

-- Clear copied default privileges on our new objects before enabling the endpoint.
DO $acl$
DECLARE v_object record; v_grantee record; v_table text;
BEGIN
  FOR v_object IN
    SELECT p.oid,p.proowner,n.nspname,p.proname,pg_catalog.pg_get_function_identity_arguments(p.oid) args,p.proacl
    FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
    WHERE (n.nspname='astra_ingestion_v1' AND p.proname LIKE 'rpc_%') OR (n.nspname='public' AND p.proname='astra_ingestion_rpc_v1')
  LOOP
    EXECUTE pg_catalog.format('REVOKE ALL ON FUNCTION %I.%I(%s) FROM PUBLIC',v_object.nspname,v_object.proname,v_object.args);
    FOR v_grantee IN SELECT DISTINCT r.rolname FROM pg_catalog.aclexplode(v_object.proacl) a JOIN pg_catalog.pg_roles r ON r.oid=a.grantee WHERE a.grantee<>v_object.proowner LOOP
      EXECUTE pg_catalog.format('REVOKE ALL ON FUNCTION %I.%I(%s) FROM %I',v_object.nspname,v_object.proname,v_object.args,v_grantee.rolname);
    END LOOP;
    IF v_object.nspname='astra_ingestion_v1' THEN
      EXECUTE pg_catalog.format('ALTER FUNCTION %I.%I(%s) OWNER TO astra_ingestion_rpc_owner_v1',v_object.nspname,v_object.proname,v_object.args);
    END IF;
  END LOOP;
  REVOKE ALL ON astra_ingestion_v1.runtime_credentials FROM PUBLIC;
  FOR v_grantee IN SELECT DISTINCT r.rolname FROM pg_catalog.pg_class c CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
       WHERE c.oid='astra_ingestion_v1.runtime_credentials'::regclass AND a.grantee<>c.relowner LOOP
    EXECUTE pg_catalog.format('REVOKE ALL ON astra_ingestion_v1.runtime_credentials FROM %I',v_grantee.rolname);
  END LOOP;
  FOREACH v_table IN ARRAY ARRAY['schema_info','jobs','partitions','receipts','records','verifications','events','rejections','source_limits','runtime_credentials'] LOOP
    EXECUTE pg_catalog.format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',v_table);
    EXECUTE pg_catalog.format('CREATE POLICY ingestion_rpc_owner ON astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1 USING (true) WITH CHECK (true)',v_table);
  END LOOP;
END $acl$;
REVOKE CREATE ON SCHEMA astra_ingestion_v1 FROM astra_ingestion_rpc_owner_v1;
GRANT USAGE ON SCHEMA astra_ingestion_v1,auth TO astra_ingestion_rpc_owner_v1;
GRANT EXECUTE ON FUNCTION auth.uid() TO astra_ingestion_rpc_owner_v1;
GRANT SELECT ON astra_ingestion_v1.schema_info,astra_ingestion_v1.runtime_credentials TO astra_ingestion_rpc_owner_v1;
GRANT SELECT,INSERT,UPDATE ON astra_ingestion_v1.jobs,astra_ingestion_v1.partitions,astra_ingestion_v1.verifications TO astra_ingestion_rpc_owner_v1;
GRANT SELECT,INSERT ON astra_ingestion_v1.receipts,astra_ingestion_v1.records,astra_ingestion_v1.events,astra_ingestion_v1.rejections TO astra_ingestion_rpc_owner_v1;
GRANT SELECT,UPDATE ON astra_ingestion_v1.source_limits TO astra_ingestion_rpc_owner_v1;
-- No DELETE/TRUNCATE/DDL, no credential writes, no role switching or table ownership.
GRANT USAGE ON SCHEMA astra_ingestion_v1 TO anon;
GRANT EXECUTE ON FUNCTION astra_ingestion_v1.rpc_dispatch(text,jsonb) TO anon;
GRANT EXECUTE ON FUNCTION public.astra_ingestion_rpc_v1(text,jsonb) TO anon;
NOTIFY pgrst,'reload schema';
COMMIT;
