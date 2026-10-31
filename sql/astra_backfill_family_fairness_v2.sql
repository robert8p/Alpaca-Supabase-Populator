-- Durable family fairness inside the existing worker and authenticated queue.
-- One indexed candidate lookup per family; no global million-task priority sort.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $preflight$ BEGIN
 IF to_regclass('astra_ingestion_v1.backfill_family_turn_v2') IS NOT NULL
  OR to_regprocedure('astra_ingestion_v1.backfill_breadth_ready_v2(text)') IS NULL
  OR to_regprocedure('astra_ingestion_v1.backfill_reuse_commit_v2(jsonb)') IS NULL THEN
  RAISE EXCEPTION 'Family fairness requires the installed replacement/reuse/breadth runtime and applies once';
 END IF;
END $preflight$;

CREATE TABLE astra_ingestion_v1.backfill_family_turn_v2 (
 run_id text PRIMARY KEY REFERENCES astra_ingestion_v1.backfill_runs_v2(id),
 next_family_index smallint NOT NULL DEFAULT 1 CHECK(next_family_index BETWEEN 1 AND 16),
 last_family text,
 last_claimed_task_id text,
 claim_turns bigint NOT NULL DEFAULT 0 CHECK(claim_turns>=0),
 changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX backfill_tasks_family_turn_v2
 ON astra_ingestion_v1.backfill_tasks_v2(run_id,family,priority,next_retry_at,created_at,id)
 WHERE status IN ('PENDING','RUNNING','RETRY_WAIT');

ALTER TABLE astra_ingestion_v1.backfill_family_turn_v2 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.backfill_family_turn_v2 FROM PUBLIC;
DO $acl$
DECLARE g record;
BEGIN
 FOR g IN SELECT DISTINCT r.rolname FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a
  JOIN pg_roles r ON r.oid=a.grantee WHERE c.oid='astra_ingestion_v1.backfill_family_turn_v2'::regclass AND a.grantee<>c.relowner
 LOOP EXECUTE format('REVOKE ALL ON astra_ingestion_v1.backfill_family_turn_v2 FROM %I',g.rolname); END LOOP;
END $acl$;
GRANT SELECT,INSERT,UPDATE ON astra_ingestion_v1.backfill_family_turn_v2 TO astra_ingestion_rpc_owner_v1;
CREATE POLICY family_turn_read ON astra_ingestion_v1.backfill_family_turn_v2 FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true);
CREATE POLICY family_turn_insert ON astra_ingestion_v1.backfill_family_turn_v2 FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true);
CREATE POLICY family_turn_update ON astra_ingestion_v1.backfill_family_turn_v2 FOR UPDATE TO astra_ingestion_rpc_owner_v1 USING(true) WITH CHECK(true);

DO $wire$
DECLARE d text; old_query text; fair_query text; original_block text; new_block text;
 start_at integer; end_at integer;
 start_marker text:='  SELECT q.* INTO t FROM astra_ingestion_v1.backfill_tasks_v2 q JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=q.run_id';
 end_marker text:='   ORDER BY q.priority,q.next_retry_at,q.created_at,q.id LIMIT 1 FOR UPDATE OF q;';
 empty_marker text:='  IF NOT FOUND THEN RETURN NULL; END IF;';
 declare_marker text:=' v_not_before double precision; v_epoch double precision;';
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_family_fairness_hook_v2')>0 OR strpos(d,declare_marker)=0
  OR strpos(d,'backfill_breadth_ready_v2(q.id)')=0
  OR strpos(d,'gap.scope->>''reuse_parent''=ANY(q.dependencies)')=0 THEN
  RAISE EXCEPTION 'Family fairness baseline differs; retain all existing readiness hooks before changing selection';
 END IF;
 start_at:=strpos(d,start_marker);
 IF start_at=0 THEN RAISE EXCEPTION 'Existing replacement candidate query is absent'; END IF;
 end_at:=strpos(substr(d,start_at),end_marker);
 IF end_at=0 THEN RAISE EXCEPTION 'Existing indexed candidate ordering is absent'; END IF;
 old_query:=substr(d,start_at,end_at+length(end_marker)-1);
 original_block:=old_query||chr(10)||empty_marker;
 IF strpos(d,original_block)=0 THEN RAISE EXCEPTION 'Existing empty-claim guard differs'; END IF;
 IF strpos(old_query,'   WHERE rr.status=''ACTIVE''')=0 THEN RAISE EXCEPTION 'Existing active-run guard differs'; END IF;
 -- Copy the actual installed candidate predicate, including forward extensions.
 -- Only restrict its run/family and make the partial-index predicate explicit.
 fair_query:=replace(old_query,'   WHERE rr.status=''ACTIVE''',
  '   WHERE q.run_id=v_fair_run AND q.family=v_fair_pick.family'||chr(10)||
  '    AND q.status IN (''PENDING'',''RUNNING'',''RETRY_WAIT'') AND rr.status=''ACTIVE''');
 new_block:=$prefix$
  -- backfill_family_fairness_hook_v2: one coherent queue, at most16 indexed family probes.
  SELECT id INTO v_fair_run FROM astra_ingestion_v1.backfill_runs_v2 WHERE status='ACTIVE' ORDER BY created_at,id LIMIT 1;
  IF v_fair_run IS NULL THEN RETURN NULL; END IF;
  INSERT INTO astra_ingestion_v1.backfill_family_turn_v2(run_id) VALUES(v_fair_run) ON CONFLICT(run_id) DO NOTHING;
  SELECT next_family_index INTO STRICT v_fair_start FROM astra_ingestion_v1.backfill_family_turn_v2 WHERE run_id=v_fair_run FOR UPDATE;
  v_fair_selected:=false;
  FOR v_fair_pick IN
   SELECT family,ordinality::integer family_index
   FROM unnest(ARRAY['REF01','REF03','P01','P02','D01','D02','D03','D04','D05','N01','N02','N03','S01','S02','CTX02','CTX06']) WITH ORDINALITY f(family,ordinality)
   ORDER BY mod(ordinality::integer-v_fair_start+16,16)
  LOOP
$prefix$||fair_query||$suffix$
   IF FOUND THEN
    v_fair_selected:=true;
    UPDATE astra_ingestion_v1.backfill_family_turn_v2
     SET next_family_index=(v_fair_pick.family_index%16)+1,last_family=t.family,last_claimed_task_id=t.id,
      claim_turns=claim_turns+1,changed_at=v_now WHERE run_id=v_fair_run;
    EXIT;
   END IF;
  END LOOP;
  IF NOT v_fair_selected THEN RETURN NULL; END IF;
$suffix$;
 d:=replace(d,declare_marker,declare_marker||chr(10)||
  ' v_fair_run text; v_fair_start integer; v_fair_pick record; v_fair_selected boolean;');
 d:=replace(d,original_block,new_block);
 EXECUTE d;
END $wire$;

UPDATE astra_ingestion_v1.backfill_runs_v2
 SET metadata=metadata||jsonb_build_object('family_scheduling_policy',jsonb_build_object(
  'version','fixed3000-family-round-robin-v2.1',
  'family_order',jsonb_build_array('REF01','REF03','P01','P02','D01','D02','D03','D04','D05','N01','N02','N03','S01','S02','CTX02','CTX06'),
  'maximum_family_probes_per_claim',16,
  'within_family_order','priority,next_retry_at,created_at,id',
  'cursor','astra_ingestion_v1.backfill_family_turn_v2',
  'scope','Existing worker and global queue only; interleave eligible configured families',
  'preserved_guards','Frozen membership, current run/fence, finite lease, supported kind, provider dependency, persisted retry, original and generated gap dependencies, complete breadth readiness',
  'progress_policy','Claim turns are scheduling accounting and never useful ingestion progress',
  'applied_at',clock_timestamp()))
 WHERE id='fixed3000-20250901-20260731-v1-20261030';
COMMIT;
