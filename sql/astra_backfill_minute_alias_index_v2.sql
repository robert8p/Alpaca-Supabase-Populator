-- Cover the exact P01-to-P02 reporting predicate. This is a normal,
-- transactional build: reads continue, but task writes wait until COMMIT.
-- The finite deadlines make a blocked or slow build roll back atomically.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
-- One statement includes lock acquisition, validation, and the ordinary build;
-- the eight-second statement budget therefore covers their combined duration.
DO $build$
DECLARE d text; namespace text; matched integer;
BEGIN
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 IF to_regclass('astra_ingestion_v1.backfill_tasks_minute_alias_status_v2') IS NOT NULL THEN
  RAISE EXCEPTION 'Minute alias index name already exists; reconcile the installed object before any retry';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_class WHERE oid=to_regclass('astra_ingestion_v1.backfill_tasks_v2') AND relkind='r') THEN
  RAISE EXCEPTION 'Expected ordinary replacement task table is absent';
 END IF;
 SELECT count(*) INTO matched FROM pg_attribute a JOIN (VALUES
  ('run_id','text'::regtype),('status','text'::regtype),('next_retry_at','timestamptz'::regtype),
  ('family','text'::regtype),('kind','text'::regtype),('scope','jsonb'::regtype)
 ) e(name,type_oid) ON a.attname=e.name AND a.atttypid=e.type_oid
 WHERE a.attrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass
  AND a.attnum>0 AND NOT a.attisdropped AND a.attnotnull;
 IF matched<>6 THEN
  RAISE EXCEPTION 'Minute alias index requires the qualified task key and predicate column types';
 END IF;
 SELECT pg_get_viewdef('astra_ingestion_v1.backfill_family_receipt_status_v2'::regclass,true) INTO STRICT d;
 SELECT n.nspname INTO STRICT namespace FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE c.oid='astra_ingestion_v1.backfill_family_receipt_status_v2'::regclass;
 IF encode(sha256(convert_to(replace(d,namespace,'astra'||'_ingestion_v1'),'UTF8')),'hex')
  <> '8f965a3d153272c5bcbafcbfbf469a4676cf3d8366a08606749cab53564dd50c' THEN
  RAISE EXCEPTION 'Minute alias index requires the independently verified indexed-count receipt view';
 END IF;
 EXECUTE $index$
  CREATE INDEX backfill_tasks_minute_alias_status_v2
   ON astra_ingestion_v1.backfill_tasks_v2(run_id,status,next_retry_at)
   WHERE family='P01' AND kind IN('alpaca_stock_bars','retained_reuse')
    AND COALESCE(scope->>'timeframe','1Min')='1Min'
 $index$;
END $build$;

COMMIT;
