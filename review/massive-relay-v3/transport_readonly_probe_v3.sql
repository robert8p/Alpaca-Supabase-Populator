-- ASTRA_RELAY_TRANSPORT_PROBE_SQL_BEGIN_V3
-- Read-only transport qualification only; always aborts before connector history.
SET LOCAL transaction_read_only=on;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $preflight$
DECLARE approval jsonb; confirmed timestamptz;
 supplied text:=current_query(); reviewed text; remaining text; transport_suffix text;
 start_marker text:='-- ASTRA_RELAY_TRANSPORT_PROBE_SQL_'||'BEGIN_V3'||chr(10);
 end_marker text:='-- ASTRA_RELAY_TRANSPORT_PROBE_SQL_'||'END_V3'||chr(10);
 transport_prefix text:=E'begin;\n\n-- apply sql from post body\n';
 wrapped boolean; end_at integer; tag_match text[]; tag text; before_account text;
 account_tail text; account_identifier text; expected_suffix text; candidate_sha256 text;
BEGIN
 -- The admitted Supabase transport executes the exact body and stores a
 -- second identical body in a dollar-quoted migration-history insert. Match
 -- that entire transport grammar; never normalize or ignore arbitrary SQL.
 IF left(supplied,length(start_marker))=start_marker THEN
  wrapped:=false;remaining:=supplied;
 ELSIF left(supplied,length(transport_prefix))=transport_prefix THEN
  wrapped:=true;remaining:=substr(supplied,length(transport_prefix)+1);
 ELSE
  RAISE EXCEPTION 'Managed relay transport differs from the reviewed exact SQL or trusted migration wrapper';
 END IF;
 end_at:=strpos(remaining,end_marker);
 IF left(remaining,length(start_marker))<>start_marker OR end_at=0 THEN
  RAISE EXCEPTION 'Managed relay reviewed SQL boundary is missing'; END IF;
 reviewed:=left(remaining,end_at+length(end_marker)-1);
 transport_suffix:=substr(remaining,length(reviewed)+1);
 IF (length(reviewed)-length(replace(reviewed,start_marker,'')))/length(start_marker)<>1
  OR (length(reviewed)-length(replace(reviewed,end_marker,'')))/length(end_marker)<>1 THEN
  RAISE EXCEPTION 'Managed relay executable body has repeated review boundaries'; END IF;
 IF NOT wrapped THEN
  IF transport_suffix<>'' THEN RAISE EXCEPTION 'Managed relay exact submission has unreviewed trailing SQL'; END IF;
 ELSE
  tag_match:=regexp_match(transport_suffix,'\$([A-Za-z]{20})\$');
  tag:='$'||tag_match[1]||'$';
  IF tag IS NULL OR strpos(reviewed,tag)>0 THEN
   RAISE EXCEPTION 'Managed relay migration-history delimiter is invalid'; END IF;
  before_account:=$relay_wrapper_head$;

-- track statements in history table
insert into supabase_migrations.schema_migrations as old
  (version, name, statements, created_by, idempotency_key, rollback)
values (
  to_char(current_timestamp, 'YYYYMMDDHH24MISS'),
  $relay_wrapper_head$||tag||'astra_backfill_massive_relay_v3_transport_probe'||tag||E',\n  array['||tag||reviewed||tag||E'],\n  '||tag;
  IF left(transport_suffix,length(before_account))<>before_account THEN
   RAISE EXCEPTION 'Managed relay history wrapper or duplicated reviewed body differs'; END IF;
  account_tail:=substr(transport_suffix,length(before_account)+1);
  end_at:=strpos(account_tail,tag);
  IF end_at=0 THEN RAISE EXCEPTION 'Managed relay migration-history account boundary is missing'; END IF;
  account_identifier:=left(account_tail,end_at-1);
  IF account_identifier !~ '^[A-Za-z0-9][A-Za-z0-9@._+:/-]{0,253}$' THEN
   RAISE EXCEPTION 'Managed relay migration-history account field differs from the admitted transport'; END IF;
  expected_suffix:=before_account||account_identifier||tag||$relay_wrapper_tail$,
  null,
  null
)
on conflict (idempotency_key) do update set
  version = EXCLUDED.version,
  name = coalesce(EXCLUDED.name, old.name),
  statements = EXCLUDED.statements,
  rollback = EXCLUDED.rollback,
  created_by = EXCLUDED.created_by;

commit;
$relay_wrapper_tail$;
  -- v3 accepts two exact transport byte strings: the reviewed wrapper with
  -- its final LF, or the same wrapper ending at the commit semicolon.
  -- No trimming, normalization, ignored comments or additional SQL is allowed.
  IF transport_suffix<>expected_suffix
   AND transport_suffix<>left(expected_suffix,length(expected_suffix)-1) THEN
   RAISE EXCEPTION 'Managed relay migration-history suffix has unreviewed SQL'; END IF;
 END IF;
 candidate_sha256:=encode(sha256(convert_to(reviewed,'UTF8')),'hex');
 IF current_setting('transaction_read_only')<>'on' THEN
  RAISE EXCEPTION 'Managed relay transport probe requires a read-only transaction'; END IF;
 RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='ASTRA_RELAY_V3_TRANSPORT_PROBE_ACCEPTED '||
  jsonb_build_object('probe_sha256',candidate_sha256,'probe_bytes',octet_length(reviewed),
   'final_body_byte_ascii',ascii(right(reviewed,1)),
   'wrapper_variant',CASE WHEN NOT wrapped THEN 'EXACT_RAW_REVIEWED_FILE'
    WHEN transport_suffix=expected_suffix THEN 'EXACT_WRAPPER_FINAL_LF'
    ELSE 'EXACT_WRAPPER_NO_FINAL_LF' END,
   'history_copy_verified',wrapped,'read_only',true,'migration_applied',false,
   'approval_modified',false,'provider_requests',0)::text;
END $preflight$;
-- ASTRA_RELAY_TRANSPORT_PROBE_SQL_END_V3
