-- Bound member admission to one complete deterministic member per existing RPC.
-- The persisted cursor remains the durable successor; no scope is repartitioned.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $repair$
DECLARE d text;
 old_loop text:=E'  FOR m IN SELECT * FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id AND selection_order>=v_next\n   ORDER BY selection_order LIMIT v_limit\n  LOOP';
 new_loop text:=E'  -- backfill_planner_one_member_v2: commit one complete member before the next existing worker call.\n  FOR m IN SELECT * FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id AND selection_order>=v_next\n   ORDER BY selection_order LIMIT LEAST(v_limit,1)\n  LOOP';
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_plan_next_v2(jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_planner_one_member_v2')>0
  OR (length(d)-length(replace(d,old_loop,'')))/length(old_loop)<>1
  OR strpos(d,'IF v_phase=''MEMBERS'' THEN')=0
  OR strpos(d,'v_next:=m.selection_order+1;v_members:=v_members+1;')=0
  OR strpos(d,'ORDER BY e->>''date'' OFFSET v_after LIMIT v_limit')=0 THEN
  RAISE EXCEPTION 'Planner batch repair requires the original member loop, atomic cursor and independent breadth bound; reconcile before applying';
 END IF;
 -- Only the number of complete members admitted by one call changes. Task IDs,
 -- scopes, definitions, original plan hash, member/date coverage, receipt state,
 -- expected-count checkpoint, breadth admission and final sealing are unchanged.
 EXECUTE replace(d,old_loop,new_loop);
END $repair$;
COMMIT;
