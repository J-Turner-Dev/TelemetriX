DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        CREATE EXTENSION IF NOT EXISTS timescaledb;
        PERFORM create_hypertable('measurements', 'ts', chunk_time_interval => INTERVAL '1 day', migrate_data => true);
    END IF;
END $$;