-- Applied production security migration for public.rd_bars and
-- public.ra_intraday_features. No permissive client policy is created.

CREATE SCHEMA IF NOT EXISTS research_control;

CREATE OR REPLACE FUNCTION research_control.secure_market_data_partition(p_partition regclass)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, research_control
AS $$
DECLARE
    v_is_target boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM pg_inherits i
        WHERE i.inhrelid = p_partition
          AND i.inhparent IN (
              'public.rd_bars'::regclass,
              'public.ra_intraday_features'::regclass
          )
    ) INTO v_is_target;

    IF NOT v_is_target THEN
        RAISE EXCEPTION '% is not a direct partition of an approved market-data parent', p_partition
            USING ERRCODE = '22023';
    END IF;

    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', p_partition);
    EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %s FROM anon, authenticated', p_partition);
END;
$$;

REVOKE ALL ON FUNCTION research_control.secure_market_data_partition(regclass)
FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION research_control.secure_market_data_partition_ddl()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, research_control
AS $$
DECLARE
    v_command record;
    v_parent oid;
BEGIN
    FOR v_command IN SELECT * FROM pg_event_trigger_ddl_commands()
    LOOP
        v_parent := NULL;
        IF v_command.classid = 'pg_class'::regclass AND v_command.objid IS NOT NULL THEN
            SELECT i.inhparent INTO v_parent
            FROM pg_inherits i
            WHERE i.inhrelid = v_command.objid
              AND i.inhparent IN (
                  'public.rd_bars'::regclass,
                  'public.ra_intraday_features'::regclass
              )
            LIMIT 1;
        END IF;
        IF v_parent IS NOT NULL THEN
            PERFORM research_control.secure_market_data_partition(v_command.objid::regclass);
        END IF;
    END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION research_control.secure_market_data_partition_ddl()
FROM PUBLIC, anon, authenticated, service_role;

DROP EVENT TRIGGER IF EXISTS secure_market_data_partition_on_create;
CREATE EVENT TRIGGER secure_market_data_partition_on_create
ON ddl_command_end
WHEN TAG IN ('CREATE TABLE')
EXECUTE FUNCTION research_control.secure_market_data_partition_ddl();

ALTER TABLE public.rd_bars ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ra_intraday_features ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public.rd_bars FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.ra_intraday_features FROM anon, authenticated;

DO $$
DECLARE
    v_partition regclass;
BEGIN
    FOR v_partition IN
        SELECT i.inhrelid::regclass
        FROM pg_inherits i
        WHERE i.inhparent IN (
            'public.rd_bars'::regclass,
            'public.ra_intraday_features'::regclass
        )
        ORDER BY i.inhrelid::regclass::text
    LOOP
        PERFORM research_control.secure_market_data_partition(v_partition);
    END LOOP;
END;
$$;

COMMENT ON FUNCTION research_control.secure_market_data_partition(regclass) IS
'Targeted RLS and ACL hardening for direct rd_bars and ra_intraday_features partitions.';

COMMENT ON EVENT TRIGGER secure_market_data_partition_on_create IS
'Automatically enables RLS and removes client-role access when a direct partition of rd_bars or ra_intraday_features is created.';
