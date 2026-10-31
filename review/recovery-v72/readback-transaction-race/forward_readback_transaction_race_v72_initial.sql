-- PREPARATION ONLY. One predicate defers pages that the unchanged verifier
-- cannot independently read in this transaction. Existing failure exclusions,
-- verifier, provider paths, gate, limits, exceptions, return and metadata remain.
-- Root must reconcile all other selected forwards before any separate dispatch.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $readback_transaction_race$
DECLARE
 v_before text;
 v_after text;
 v_before_metadata jsonb;
 v_after_metadata jsonb;
 v_other_before jsonb;
 v_other_after jsonb;
 v_expected_metadata constant jsonb := $metadata${"oid":"16041463","proacl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","astra_ingestion_monitor_owner_v1=X/astra_ingestion_rpc_owner_v1"],"proallargtypes":null,"proargdefaults":"({CONST :consttype 23 :consttypmod -1 :constcollid 0 :constlen 4 :constbyval true :constisnull false :location -1 :constvalue 4 [ 2 0 0 0 0 0 0 0 ]})","proargmodes":null,"proargnames":["p_limit"],"proargtypes":["23"],"probin":null,"proconfig":["search_path=\"\"","statement_timeout=8s","lock_timeout=2s"],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"backfill_maintain_v2","pronamespace":"15984556","pronargdefaults":1,"pronargs":1,"proowner":"15985999","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":true,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$metadata$::jsonb;
 v_old constant text := $selector$  WHERE rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') AND NOT EXISTS($selector$;
 v_new constant text := $selector$  WHERE rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') AND pg.committed_at<transaction_timestamp() AND NOT EXISTS($selector$;
 g record;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s'
  OR current_setting('transaction_read_only')<>'off' THEN
  RAISE EXCEPTION 'Readback transaction repair requires reviewed8-second statement and3-second lock writable bounds';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()
 FOR SHARE;
 IF NOT FOUND OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2
  WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
  RAISE EXCEPTION 'Readback transaction repair owner, lease, active run, fence or fixed cohort differs';
 END IF;
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc'
 INTO STRICT v_before,v_before_metadata FROM pg_proc p
 WHERE p.oid='astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 IF encode(sha256(convert_to(v_before,'UTF8')),'hex')<>'cd10046d9c9aa15e8bc66724d1258d95151364ffeee9070d761c4f7d930b5859'
  OR v_before_metadata IS DISTINCT FROM v_expected_metadata THEN
  RAISE EXCEPTION 'Readback transaction repair exact baseline source or metadata changed; reconcile before replay';
 END IF;
 FOR g IN SELECT * FROM (VALUES
  ('astra_ingestion_v1.backfill_recheck_page_v2(text,integer)','0ccd4018d16e3ed3932176d2886fe78c2c1b442d70473d71e137d86e7b6dfb37'),
  ('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)','28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'),
  ('astra_ingestion_v1.rpc_dispatch(text,jsonb)','a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520')
 ) p(signature,expected_sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(g.signature::regprocedure),'UTF8')),'hex')<>g.expected_sha256 THEN
   RAISE EXCEPTION 'Readback transaction repair unchanged verifier or authenticated dispatch source differs';
  END IF;
 END LOOP;
 IF (length(v_before)-length(replace(v_before,v_old,'')))/length(v_old)<>1
  OR strpos(v_before,v_new)>0 THEN
  RAISE EXCEPTION 'Readback transaction repair must change exactly one original selector';
 END IF;
 v_after:=replace(v_before,v_old,v_new);
 IF encode(sha256(convert_to(v_after,'UTF8')),'hex')<>'6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7'
  OR replace(v_after,v_new,v_old) IS DISTINCT FROM v_before THEN
  RAISE EXCEPTION 'Readback transaction repair candidate is not the reviewed single predicate';
 END IF;
 SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) INTO v_other_before FROM pg_proc p
 WHERE p.pronamespace='astra_ingestion_v1'::regnamespace
  AND p.oid<>'astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 EXECUTE v_after;
 SELECT to_jsonb(p)-'prosrc' INTO STRICT v_after_metadata FROM pg_proc p
 WHERE p.oid='astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) INTO v_other_after FROM pg_proc p
 WHERE p.pronamespace='astra_ingestion_v1'::regnamespace
  AND p.oid<>'astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 IF v_after_metadata IS DISTINCT FROM v_before_metadata OR v_other_after IS DISTINCT FROM v_other_before
  OR pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) IS DISTINCT FROM v_after THEN
  RAISE EXCEPTION 'Readback transaction repair altered metadata, another function or unexpected source';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
  WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
   AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
   AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
   AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()) THEN
  RAISE EXCEPTION 'Readback transaction repair run, owner or lease changed before completion';
 END IF;
END $readback_transaction_race$;
COMMIT;
