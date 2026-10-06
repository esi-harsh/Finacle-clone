-- Migration 002: Infrastructure tables for Tool Logging, Draft Entries, and Evaluation Scenarios

-- 1. Tool Call Log Table
CREATE TABLE IF NOT EXISTS finance.tool_call_log (
    call_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      TEXT NOT NULL,
    tool            TEXT NOT NULL,
    input_json      JSONB NOT NULL,
    output_summary  TEXT,
    error_code      TEXT,
    duration_ms     INTEGER,
    called_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    traceparent     TEXT
);

CREATE INDEX IF NOT EXISTS ix_tool_call_log_session ON finance.tool_call_log (session_id, called_at);
CREATE INDEX IF NOT EXISTS ix_tool_call_log_tool ON finance.tool_call_log (tool);

-- 2. Draft Entries Table (Staging for Approval Gate)
CREATE TABLE IF NOT EXISTS finance.draft_entries (
    draft_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       TEXT NOT NULL,
    idempotency_key  TEXT UNIQUE,
    draft_type       TEXT NOT NULL CHECK (draft_type IN ('post', 'reverse')),
    status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'posted', 'rejected')),
    payload_json     JSONB NOT NULL,
    rejection_reason TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at      TIMESTAMPTZ,
    approved_by      TEXT
);

CREATE INDEX IF NOT EXISTS ix_draft_entries_session ON finance.draft_entries (session_id, status);
CREATE INDEX IF NOT EXISTS ix_draft_entries_idempotency ON finance.draft_entries (idempotency_key);

-- 3. Evaluation Scenarios Table (Ground Truth & Scoring)
CREATE TABLE IF NOT EXISTS finance.eval_scenarios (
    scenario_id     TEXT PRIMARY KEY,
    use_case        TEXT NOT NULL CHECK (use_case IN ('UC1', 'UC2', 'UC3')),
    prompt          TEXT NOT NULL,
    expected_json   JSONB NOT NULL,
    forbidden_json  JSONB,
    allowed_tools   TEXT[] NOT NULL,
    max_tool_calls  INTEGER DEFAULT 20,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_eval_scenarios_use_case ON finance.eval_scenarios (use_case);

-- Grants for the new tables
GRANT SELECT, INSERT ON finance.tool_call_log TO twin_reader, twin_writer;
GRANT SELECT, INSERT, UPDATE ON finance.draft_entries TO twin_writer;
GRANT SELECT ON finance.draft_entries TO twin_reader;
GRANT SELECT ON finance.eval_scenarios TO twin_reader, twin_writer;
