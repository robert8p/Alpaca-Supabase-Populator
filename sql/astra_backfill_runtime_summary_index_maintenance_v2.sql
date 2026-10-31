-- Independent bounded maintenance variant after two8s production build expiries.
-- Same index, source/type/replay guards, permissions, and transaction semantics
-- as the retained8s artifact. Only this maintenance DO budget becomes20s.
-- Its advisory acquisition, validation and ordinary CREATE INDEX share that
-- budget. Task writers and advisory-sharing RPCs can be blocked; their existing
--3s lock deadline can cause temporary worker failures/restarts. Locks release
-- at transaction end; cancellation/commit latency is not a hard20s wall bound.
-- Reconcile authoritative index state after any uncertain result before retry.
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL lock_timeout='3s';
DO $build$
DECLARE s text;b text;namespace text;start_at integer;end_at integer;matched integer;
BEGIN
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 IF to_regclass('astra_ingestion_v1.backfill_tasks_runtime_summary_v2') IS NOT NULL THEN
  RAISE EXCEPTION 'Runtime summary index name exists; reconcile before replay';
 END IF;
 SELECT p.prosrc,n.nspname INTO STRICT s,namespace FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE p.oid='astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure;
 start_at:=strpos(s,$start$ IF p_operation='backfill_status' THEN$start$);
 end_at:=strpos(s,$end$ ELSIF p_operation='backfill_claim' THEN$end$);
 IF start_at=0 OR end_at<=start_at THEN RAISE EXCEPTION 'Runtime status boundaries changed';END IF;
 b:=substring(s FROM start_at FOR end_at-start_at);
 IF encode(sha256(convert_to(replace(b,namespace,'astra'||'_ingestion_v1'),'UTF8')),'hex')<>'cee8f62d034a88e3fb5166fce2b4b4903cdd1aee802e2efebfc3f08cf6c0a5de' THEN
  RAISE EXCEPTION 'Covering summary index requires the qualified report-as-of rewrite';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_class WHERE oid=to_regclass('astra_ingestion_v1.backfill_tasks_v2') AND relkind='r') THEN
  RAISE EXCEPTION 'Expected ordinary replacement task table is absent';
 END IF;
 SELECT count(*) INTO matched FROM pg_attribute a JOIN (VALUES
  ('run_id','text'::regtype,true),('family','text'::regtype,true),('kind','text'::regtype,true),
  ('provider','text'::regtype,true),('status','text'::regtype,true),('records_committed','bigint'::regtype,true),
  ('last_progress_at','timestamptz'::regtype,false)
 )e(name,type_oid,not_null) ON a.attname=e.name AND a.atttypid=e.type_oid AND a.attnotnull=e.not_null
 WHERE a.attrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass AND a.attnum>0 AND NOT a.attisdropped;
 IF matched<>7 THEN RAISE EXCEPTION 'Runtime summary key/aggregate column types changed';END IF;
 EXECUTE $index$CREATE INDEX backfill_tasks_runtime_summary_v2
  ON astra_ingestion_v1.backfill_tasks_v2(run_id,family,kind,provider,status,records_committed,last_progress_at)$index$;
END $build$;
COMMIT;
