-- Migration 001: Database Roles for Finance Twin MCP Server
-- twin_reader: SELECT-only permissions across all finance tables
-- twin_writer: INSERT on headers/lines/drafts/logs; UPDATE only on clearing and reversal fields

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'twin_reader') THEN
    CREATE ROLE twin_reader WITH LOGIN PASSWORD 'reader_password';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'twin_writer') THEN
    CREATE ROLE twin_writer WITH LOGIN PASSWORD 'writer_password';
  END IF;
END
$$;

-- Grant usage on schemas
GRANT USAGE ON SCHEMA finance TO twin_reader, twin_writer;
GRANT USAGE ON SCHEMA sap_compat TO twin_reader, twin_writer;

-- twin_reader: read-only access
GRANT SELECT ON ALL TABLES IN SCHEMA finance TO twin_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA sap_compat TO twin_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance GRANT SELECT ON TABLES TO twin_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA sap_compat GRANT SELECT ON TABLES TO twin_reader;

-- twin_writer: restricted write access
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA finance TO twin_writer;
GRANT UPDATE ON finance.journal_entry_headers TO twin_writer;
GRANT UPDATE ON finance.journal_entry_lines TO twin_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance GRANT SELECT, INSERT, UPDATE ON TABLES TO twin_writer;
