-- ASTRA_NATIVE_READONLY_EXACT_TRANSPORT_PROBE_V2
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
SELECT pg_catalog.jsonb_build_object(
  'probe_id', 'astra-native-readonly-exact-transport-v2',
  'transaction_read_only', pg_catalog.current_setting('transaction_read_only'),
  'query_utf8_bytes', pg_catalog.octet_length(pg_catalog.convert_to(pg_catalog.current_query(), 'UTF8')),
  'query_sha256', pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(pg_catalog.current_query(), 'UTF8')), 'hex'),
  'final_byte_ascii', pg_catalog.ascii(pg_catalog.right(pg_catalog.current_query(), 1))
) AS transport_probe;
ROLLBACK;
-- ASTRA_NATIVE_READONLY_EXACT_TRANSPORT_PROBE_END_V2
