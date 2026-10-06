-- =====================================================================
-- Finance Digital Twin - Phase 1 (PostgreSQL 13+)
-- S/4HANA-style model with general (non-abbreviated) names.
-- Scope: org structure, G/L master data, journal entries, posting
--        controls, trial balance. Vendors/customers/payments = Phase 2.
-- Conventions:
--   * client_id is the first column of every table (multi-tenancy)
--   * Business keys are TEXT; numbers like document_number are zero-padded
--   * Sign convention: debit = positive, credit = negative
--   * Each business concept has ONE name everywhere (no BUKRS/RBUKRS drift)
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS finance;
SET search_path = finance, public;

-- ---------------------------------------------------------------------
-- 1. GLOBAL / CLIENT LEVEL                       (SAP: T000, TCURC, TCURR)
-- ---------------------------------------------------------------------
CREATE TABLE clients (
  client_id    TEXT PRIMARY KEY,                    -- MANDT
  name         TEXT NOT NULL,
  description  TEXT
);

CREATE TABLE currencies (                           -- TCURC / TCURX
  currency       TEXT PRIMARY KEY CHECK (currency ~ '^[A-Z]{3}$'),
  name           TEXT NOT NULL,
  decimal_places INT  NOT NULL DEFAULT 2 CHECK (decimal_places BETWEEN 0 AND 4)
);

CREATE TABLE exchange_rates (                       -- TCURR
  client_id     TEXT NOT NULL REFERENCES clients(client_id),
  rate_type     TEXT NOT NULL DEFAULT 'M',          -- M = average, B = bank buy, G = bank sell
  from_currency TEXT NOT NULL REFERENCES currencies(currency),
  to_currency   TEXT NOT NULL REFERENCES currencies(currency),
  valid_from    DATE NOT NULL,
  rate          NUMERIC(18,8) NOT NULL CHECK (rate > 0),  -- 1 unit from = rate units to
  PRIMARY KEY (client_id, rate_type, from_currency, to_currency, valid_from)
);

-- ---------------------------------------------------------------------
-- 2. ORGANIZATIONAL STRUCTURE            (SAP: T004, T009, TKA01, T001)
-- ---------------------------------------------------------------------
CREATE TABLE charts_of_accounts (                   -- T004
  client_id          TEXT NOT NULL REFERENCES clients(client_id),
  chart_of_accounts  TEXT NOT NULL,
  description        TEXT NOT NULL,
  account_length     INT  NOT NULL DEFAULT 10,
  PRIMARY KEY (client_id, chart_of_accounts)
);

CREATE TABLE fiscal_year_variants (                 -- T009
  client_id           TEXT NOT NULL REFERENCES clients(client_id),
  fiscal_year_variant TEXT NOT NULL,
  description         TEXT NOT NULL,
  posting_periods     INT  NOT NULL DEFAULT 12,
  special_periods     INT  NOT NULL DEFAULT 4,      -- periods 13-16 in SAP
  is_calendar_year    BOOLEAN NOT NULL DEFAULT TRUE,-- twin simplification: period = month
  PRIMARY KEY (client_id, fiscal_year_variant)
);

CREATE TABLE ledgers (                              -- FINSC_LEDGER
  client_id             TEXT NOT NULL REFERENCES clients(client_id),
  ledger                TEXT NOT NULL,              -- e.g. '0L'
  description           TEXT NOT NULL,
  is_leading            BOOLEAN NOT NULL DEFAULT FALSE,
  accounting_principle  TEXT,                       -- IFRS, LOCAL_GAAP ...
  PRIMARY KEY (client_id, ledger)
);
-- exactly one leading ledger per client
CREATE UNIQUE INDEX ux_ledgers_one_leading ON ledgers(client_id) WHERE is_leading;

CREATE TABLE company_codes (                        -- T001
  client_id           TEXT NOT NULL REFERENCES clients(client_id),
  company_code        TEXT NOT NULL,
  name                TEXT NOT NULL,
  country             CHAR(2) NOT NULL,
  currency            TEXT NOT NULL REFERENCES currencies(currency),  -- local/company currency
  group_currency      TEXT REFERENCES currencies(currency),
  chart_of_accounts   TEXT NOT NULL,
  fiscal_year_variant TEXT NOT NULL,
  PRIMARY KEY (client_id, company_code),
  UNIQUE (client_id, company_code, chart_of_accounts),   -- target for composite FKs
  FOREIGN KEY (client_id, chart_of_accounts)
    REFERENCES charts_of_accounts(client_id, chart_of_accounts),
  FOREIGN KEY (client_id, fiscal_year_variant)
    REFERENCES fiscal_year_variants(client_id, fiscal_year_variant)
);

CREATE TABLE controlling_areas (                    -- TKA01
  client_id           TEXT NOT NULL REFERENCES clients(client_id),
  controlling_area    TEXT NOT NULL,
  description         TEXT NOT NULL,
  currency            TEXT NOT NULL REFERENCES currencies(currency),
  chart_of_accounts   TEXT NOT NULL,
  fiscal_year_variant TEXT NOT NULL,
  PRIMARY KEY (client_id, controlling_area),
  FOREIGN KEY (client_id, chart_of_accounts)
    REFERENCES charts_of_accounts(client_id, chart_of_accounts),
  FOREIGN KEY (client_id, fiscal_year_variant)
    REFERENCES fiscal_year_variants(client_id, fiscal_year_variant)
);

CREATE TABLE company_code_controlling_areas (       -- company code -> controlling area assignment
  client_id        TEXT NOT NULL,
  company_code     TEXT NOT NULL,
  controlling_area TEXT NOT NULL,
  PRIMARY KEY (client_id, company_code),
  FOREIGN KEY (client_id, company_code)     REFERENCES company_codes(client_id, company_code),
  FOREIGN KEY (client_id, controlling_area) REFERENCES controlling_areas(client_id, controlling_area)
);

-- ---------------------------------------------------------------------
-- 3. G/L ACCOUNT MASTER (3 layers)                  (SAP: SKA1, SKB1, SKAT)
-- ---------------------------------------------------------------------
CREATE TABLE gl_accounts (                          -- SKA1: chart-of-accounts level
  client_id          TEXT NOT NULL,
  chart_of_accounts  TEXT NOT NULL,
  gl_account         TEXT NOT NULL CHECK (gl_account ~ '^[0-9]{10}$'),   -- zero-padded
  account_group      TEXT,                          -- e.g. 'CASH', 'REVENUE'
  statement_type     TEXT NOT NULL CHECK (statement_type IN ('BALANCE_SHEET','PROFIT_LOSS')),
  is_blocked         BOOLEAN NOT NULL DEFAULT FALSE,
  created_on         DATE NOT NULL DEFAULT CURRENT_DATE,
  PRIMARY KEY (client_id, chart_of_accounts, gl_account),
  FOREIGN KEY (client_id, chart_of_accounts)
    REFERENCES charts_of_accounts(client_id, chart_of_accounts)
);

CREATE TABLE gl_account_texts (                     -- SKAT
  client_id          TEXT NOT NULL,
  chart_of_accounts  TEXT NOT NULL,
  gl_account         TEXT NOT NULL,
  language           CHAR(2) NOT NULL DEFAULT 'EN',
  short_text         TEXT NOT NULL,
  long_text          TEXT,
  PRIMARY KEY (client_id, chart_of_accounts, gl_account, language),
  FOREIGN KEY (client_id, chart_of_accounts, gl_account)
    REFERENCES gl_accounts(client_id, chart_of_accounts, gl_account)
);

CREATE TABLE gl_account_company_settings (          -- SKB1: company-code level control
  client_id                    TEXT NOT NULL,
  company_code                 TEXT NOT NULL,
  chart_of_accounts            TEXT NOT NULL,
  gl_account                   TEXT NOT NULL,
  account_currency             TEXT REFERENCES currencies(currency),  -- NULL = any currency
  is_open_item_managed         BOOLEAN NOT NULL DEFAULT FALSE,
  is_line_item_displayed       BOOLEAN NOT NULL DEFAULT TRUE,
  -- Reconciliation account: NULL = normal account, otherwise only the matching
  -- sub-ledger may post to it (direct G/L posting is rejected).
  reconciliation_account_type  TEXT CHECK (reconciliation_account_type IN ('VENDOR','CUSTOMER','ASSET')),
  is_blocked_for_posting       BOOLEAN NOT NULL DEFAULT FALSE,
  tax_category                 TEXT,
  field_status_group           TEXT,
  PRIMARY KEY (client_id, company_code, gl_account),
  FOREIGN KEY (client_id, company_code, chart_of_accounts)
    REFERENCES company_codes(client_id, company_code, chart_of_accounts),
  FOREIGN KEY (client_id, chart_of_accounts, gl_account)
    REFERENCES gl_accounts(client_id, chart_of_accounts, gl_account)
);

-- ---------------------------------------------------------------------
-- 4. MANAGEMENT ACCOUNTING DIMENSIONS               (SAP: CSKS, CEPC)
-- ---------------------------------------------------------------------
CREATE TABLE profit_centers (                       -- CEPC
  client_id         TEXT NOT NULL,
  controlling_area  TEXT NOT NULL,
  profit_center     TEXT NOT NULL,
  name              TEXT NOT NULL,
  company_code      TEXT,
  valid_from        DATE NOT NULL DEFAULT DATE '1900-01-01',
  valid_to          DATE NOT NULL DEFAULT DATE '9999-12-31',
  PRIMARY KEY (client_id, controlling_area, profit_center),
  FOREIGN KEY (client_id, controlling_area) REFERENCES controlling_areas(client_id, controlling_area),
  FOREIGN KEY (client_id, company_code)     REFERENCES company_codes(client_id, company_code)
);

CREATE TABLE cost_centers (                         -- CSKS
  client_id         TEXT NOT NULL,
  controlling_area  TEXT NOT NULL,
  cost_center       TEXT NOT NULL,
  name              TEXT NOT NULL,
  company_code      TEXT NOT NULL,
  profit_center     TEXT,
  responsible_person TEXT,
  is_blocked_for_posting BOOLEAN NOT NULL DEFAULT FALSE,
  valid_from        DATE NOT NULL DEFAULT DATE '1900-01-01',
  valid_to          DATE NOT NULL DEFAULT DATE '9999-12-31',
  PRIMARY KEY (client_id, controlling_area, cost_center),
  FOREIGN KEY (client_id, controlling_area) REFERENCES controlling_areas(client_id, controlling_area),
  FOREIGN KEY (client_id, company_code)     REFERENCES company_codes(client_id, company_code),
  FOREIGN KEY (client_id, controlling_area, profit_center)
    REFERENCES profit_centers(client_id, controlling_area, profit_center)
);

-- ---------------------------------------------------------------------
-- 5. POSTING CONFIGURATION (behaviour as data)  (SAP: T003, TBSL, T001B, NRIV)
-- ---------------------------------------------------------------------
CREATE TABLE document_types (                       -- T003
  client_id               TEXT NOT NULL REFERENCES clients(client_id),
  document_type           TEXT NOT NULL,            -- 'SA' G/L doc, 'KR' vendor inv, 'DR' cust inv ...
  description             TEXT NOT NULL,
  number_range            TEXT NOT NULL,            -- links to document_number_ranges
  allows_gl_postings      BOOLEAN NOT NULL DEFAULT TRUE,
  allows_vendor_postings  BOOLEAN NOT NULL DEFAULT FALSE,
  allows_customer_postings BOOLEAN NOT NULL DEFAULT FALSE,
  allows_asset_postings   BOOLEAN NOT NULL DEFAULT FALSE,
  reversal_document_type  TEXT,
  PRIMARY KEY (client_id, document_type)
);

CREATE TABLE posting_keys (                         -- TBSL
  client_id                TEXT NOT NULL REFERENCES clients(client_id),
  posting_key              TEXT NOT NULL,           -- '40' debit G/L, '50' credit G/L ...
  description              TEXT NOT NULL,
  debit_credit_indicator   CHAR(1) NOT NULL CHECK (debit_credit_indicator IN ('D','C')),
  account_type             TEXT NOT NULL CHECK (account_type IN ('GL','VENDOR','CUSTOMER','ASSET')),
  is_reversal_key          BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (client_id, posting_key)
);

CREATE TABLE posting_period_controls (              -- T001B (simplified)
  client_id      TEXT NOT NULL,
  company_code   TEXT NOT NULL,
  fiscal_year    INT  NOT NULL,
  posting_period INT  NOT NULL CHECK (posting_period BETWEEN 1 AND 16),
  is_open        BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (client_id, company_code, fiscal_year, posting_period),
  FOREIGN KEY (client_id, company_code) REFERENCES company_codes(client_id, company_code)
);

CREATE TABLE document_number_ranges (               -- NRIV
  client_id       TEXT NOT NULL,
  company_code    TEXT NOT NULL,
  number_range    TEXT NOT NULL,
  fiscal_year     INT  NOT NULL,
  range_from      BIGINT NOT NULL,
  range_to        BIGINT NOT NULL,
  current_number  BIGINT NOT NULL,
  PRIMARY KEY (client_id, company_code, number_range, fiscal_year),
  FOREIGN KEY (client_id, company_code) REFERENCES company_codes(client_id, company_code),
  CHECK (current_number BETWEEN range_from - 1 AND range_to)
);

-- ---------------------------------------------------------------------
-- 6. JOURNAL ENTRIES: header + universal-journal lines   (SAP: BKPF, ACDOCA)
-- ---------------------------------------------------------------------
CREATE TABLE journal_entry_headers (                -- BKPF
  client_id            TEXT NOT NULL,
  company_code         TEXT NOT NULL,
  fiscal_year          INT  NOT NULL,
  document_number      TEXT NOT NULL CHECK (document_number ~ '^[0-9]{10}$'),
  document_type        TEXT NOT NULL,
  document_date        DATE NOT NULL,
  posting_date         DATE NOT NULL,
  posting_period       INT  NOT NULL,               -- filled by trigger if NULL
  currency             TEXT NOT NULL REFERENCES currencies(currency),   -- document currency
  exchange_rate        NUMERIC(18,8) NOT NULL DEFAULT 1,
  external_reference   TEXT,                        -- XBLNR: supplier invoice no., etc.
  header_text          TEXT,
  source_system        TEXT NOT NULL DEFAULT 'MANUAL',  -- MANUAL, P2P, O2C, CLOSING, API ...
  created_by           TEXT NOT NULL,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  reverses_document    TEXT,                        -- set on the reversal document
  reversed_by_document TEXT,                        -- set on the original document
  PRIMARY KEY (client_id, company_code, fiscal_year, document_number),
  FOREIGN KEY (client_id, company_code)  REFERENCES company_codes(client_id, company_code),
  FOREIGN KEY (client_id, document_type) REFERENCES document_types(client_id, document_type),
  CHECK (posting_period BETWEEN 1 AND 16)
);
CREATE INDEX ix_headers_posting_date ON journal_entry_headers (client_id, company_code, posting_date);
CREATE INDEX ix_headers_external_ref ON journal_entry_headers (client_id, company_code, external_reference);

CREATE TABLE journal_entry_lines (                  -- ACDOCA (Universal Journal)
  client_id        TEXT NOT NULL,
  ledger           TEXT NOT NULL,
  company_code     TEXT NOT NULL,
  fiscal_year      INT  NOT NULL,
  document_number  TEXT NOT NULL,
  line_number      INT  NOT NULL CHECK (line_number > 0),

  -- denormalised from header for fast reporting (filled by trigger)
  document_type    TEXT,
  posting_date     DATE,
  posting_period   INT,

  -- what was posted
  posting_key      TEXT,
  account_type     TEXT NOT NULL CHECK (account_type IN ('GL','VENDOR','CUSTOMER','ASSET')),
  gl_account       TEXT NOT NULL,                   -- always filled; sub-ledger lines carry their recon account
  debit_credit_indicator CHAR(1) NOT NULL CHECK (debit_credit_indicator IN ('D','C')),

  -- amounts: debit positive, credit negative
  transaction_currency        TEXT NOT NULL REFERENCES currencies(currency),
  amount_transaction_currency NUMERIC(23,2) NOT NULL,
  amount_company_currency     NUMERIC(23,2) NOT NULL,
  amount_group_currency       NUMERIC(23,2),

  -- management dimensions
  controlling_area TEXT,
  cost_center      TEXT,
  profit_center    TEXT,
  segment          TEXT,

  -- sub-ledger / partner references (FKs added in Phase 2 when vendors/customers exist)
  vendor_id        TEXT,
  customer_id      TEXT,
  asset_id         TEXT,
  tax_code         TEXT,

  -- open item management & clearing
  is_open_item     BOOLEAN NOT NULL DEFAULT FALSE,
  clearing_date    DATE,
  clearing_document TEXT,

  line_text        TEXT,
  assignment       TEXT,
  is_system_generated BOOLEAN NOT NULL DEFAULT FALSE,   -- TRUE for auto recon-account lines

  PRIMARY KEY (client_id, ledger, company_code, fiscal_year, document_number, line_number),
  FOREIGN KEY (client_id, company_code, fiscal_year, document_number)
    REFERENCES journal_entry_headers(client_id, company_code, fiscal_year, document_number),
  FOREIGN KEY (client_id, ledger) REFERENCES ledgers(client_id, ledger),
  FOREIGN KEY (client_id, posting_key) REFERENCES posting_keys(client_id, posting_key),
  FOREIGN KEY (client_id, company_code, gl_account)
    REFERENCES gl_account_company_settings(client_id, company_code, gl_account),
  FOREIGN KEY (client_id, controlling_area, cost_center)
    REFERENCES cost_centers(client_id, controlling_area, cost_center),
  FOREIGN KEY (client_id, controlling_area, profit_center)
    REFERENCES profit_centers(client_id, controlling_area, profit_center),

  -- sign must agree with the debit/credit indicator
  CONSTRAINT ck_sign_matches_indicator CHECK (
    (debit_credit_indicator = 'D' AND amount_transaction_currency >= 0 AND amount_company_currency >= 0) OR
    (debit_credit_indicator = 'C' AND amount_transaction_currency <= 0 AND amount_company_currency <= 0)),
  CONSTRAINT ck_clearing_consistent CHECK (
    (is_open_item AND clearing_date IS NULL AND clearing_document IS NULL) OR
    (NOT is_open_item))
);
CREATE INDEX ix_lines_account_period ON journal_entry_lines (client_id, ledger, company_code, fiscal_year, gl_account, posting_period);
CREATE INDEX ix_lines_cost_center    ON journal_entry_lines (client_id, controlling_area, cost_center) WHERE cost_center IS NOT NULL;
CREATE INDEX ix_lines_open_items     ON journal_entry_lines (client_id, company_code, gl_account) WHERE is_open_item;
CREATE INDEX ix_lines_vendor         ON journal_entry_lines (client_id, company_code, vendor_id)   WHERE vendor_id   IS NOT NULL;
CREATE INDEX ix_lines_customer       ON journal_entry_lines (client_id, company_code, customer_id) WHERE customer_id IS NOT NULL;

CREATE TABLE journal_entry_tax_lines (              -- BSET (populated in Phase 3)
  client_id        TEXT NOT NULL,
  company_code     TEXT NOT NULL,
  fiscal_year      INT  NOT NULL,
  document_number  TEXT NOT NULL,
  tax_line_number  INT  NOT NULL,
  tax_code         TEXT NOT NULL,
  tax_base_amount  NUMERIC(23,2) NOT NULL,
  tax_amount       NUMERIC(23,2) NOT NULL,
  tax_rate         NUMERIC(7,4),
  PRIMARY KEY (client_id, company_code, fiscal_year, document_number, tax_line_number),
  FOREIGN KEY (client_id, company_code, fiscal_year, document_number)
    REFERENCES journal_entry_headers(client_id, company_code, fiscal_year, document_number)
);

-- ---------------------------------------------------------------------
-- 7. BUSINESS RULES (SAP-style validations as triggers)
-- ---------------------------------------------------------------------

-- 7.1 Header: derive posting period, enforce open period
CREATE OR REPLACE FUNCTION trg_header_validate() RETURNS trigger AS $$
DECLARE v_open BOOLEAN;
BEGIN
  IF NEW.posting_period IS NULL THEN
    NEW.posting_period := EXTRACT(MONTH FROM NEW.posting_date)::INT;  -- calendar-year variant
  END IF;

  IF EXTRACT(YEAR FROM NEW.posting_date)::INT <> NEW.fiscal_year THEN
    RAISE EXCEPTION 'Posting date % does not belong to fiscal year %', NEW.posting_date, NEW.fiscal_year
      USING ERRCODE = 'P0001';
  END IF;

  SELECT is_open INTO v_open FROM posting_period_controls
   WHERE client_id = NEW.client_id AND company_code = NEW.company_code
     AND fiscal_year = NEW.fiscal_year AND posting_period = NEW.posting_period;

  IF v_open IS NULL OR v_open = FALSE THEN
    RAISE EXCEPTION 'Posting period %/% is not open for company code %',
      NEW.posting_period, NEW.fiscal_year, NEW.company_code USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER header_validate BEFORE INSERT ON journal_entry_headers
  FOR EACH ROW EXECUTE FUNCTION trg_header_validate();

-- 7.2 Line: copy header fields, block blocked/recon accounts, check currency
CREATE OR REPLACE FUNCTION trg_line_validate() RETURNS trigger AS $$
DECLARE
  h journal_entry_headers%ROWTYPE;
  s gl_account_company_settings%ROWTYPE;
  a gl_accounts%ROWTYPE;
BEGIN
  SELECT * INTO h FROM journal_entry_headers
   WHERE client_id = NEW.client_id AND company_code = NEW.company_code
     AND fiscal_year = NEW.fiscal_year AND document_number = NEW.document_number;

  NEW.document_type  := h.document_type;
  NEW.posting_date   := h.posting_date;
  NEW.posting_period := h.posting_period;

  SELECT * INTO s FROM gl_account_company_settings
   WHERE client_id = NEW.client_id AND company_code = NEW.company_code AND gl_account = NEW.gl_account;
  SELECT * INTO a FROM gl_accounts
   WHERE client_id = NEW.client_id AND chart_of_accounts = s.chart_of_accounts AND gl_account = NEW.gl_account;

  IF a.is_blocked OR s.is_blocked_for_posting THEN
    RAISE EXCEPTION 'G/L account % is blocked for posting in company code %', NEW.gl_account, NEW.company_code
      USING ERRCODE = 'P0001';
  END IF;

  IF s.account_currency IS NOT NULL AND s.account_currency <> NEW.transaction_currency THEN
    RAISE EXCEPTION 'Account % only allows postings in currency %', NEW.gl_account, s.account_currency
      USING ERRCODE = 'P0001';
  END IF;

  IF s.reconciliation_account_type IS NOT NULL AND NEW.account_type = 'GL' AND NOT NEW.is_system_generated THEN
    RAISE EXCEPTION 'Account % is a reconciliation account (%); direct posting is not allowed',
      NEW.gl_account, s.reconciliation_account_type USING ERRCODE = 'P0001';
  END IF;

  IF NEW.is_open_item AND NOT s.is_open_item_managed AND NEW.account_type = 'GL' THEN
    RAISE EXCEPTION 'Account % is not open-item managed', NEW.gl_account USING ERRCODE = 'P0001';
  END IF;

  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER line_validate BEFORE INSERT ON journal_entry_lines
  FOR EACH ROW EXECUTE FUNCTION trg_line_validate();

-- 7.3 Document must balance (checked at COMMIT so lines can be inserted in any order)
CREATE OR REPLACE FUNCTION trg_document_balanced() RETURNS trigger AS $$
DECLARE v_company NUMERIC; v_bad_currency TEXT;
BEGIN
  SELECT SUM(amount_company_currency) INTO v_company FROM journal_entry_lines
   WHERE client_id = NEW.client_id AND ledger = NEW.ledger AND company_code = NEW.company_code
     AND fiscal_year = NEW.fiscal_year AND document_number = NEW.document_number;
  IF v_company <> 0 THEN
    RAISE EXCEPTION 'Document % is not balanced in company currency (difference %)', NEW.document_number, v_company
      USING ERRCODE = 'P0001';
  END IF;

  SELECT transaction_currency INTO v_bad_currency FROM journal_entry_lines
   WHERE client_id = NEW.client_id AND ledger = NEW.ledger AND company_code = NEW.company_code
     AND fiscal_year = NEW.fiscal_year AND document_number = NEW.document_number
   GROUP BY transaction_currency HAVING SUM(amount_transaction_currency) <> 0 LIMIT 1;
  IF v_bad_currency IS NOT NULL THEN
    RAISE EXCEPTION 'Document % is not balanced in transaction currency %', NEW.document_number, v_bad_currency
      USING ERRCODE = 'P0001';
  END IF;
  RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER document_balanced AFTER INSERT ON journal_entry_lines
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION trg_document_balanced();

-- 7.4 A document needs at least two lines (checked at COMMIT on the header)
CREATE OR REPLACE FUNCTION trg_document_min_lines() RETURNS trigger AS $$
BEGIN
  IF (SELECT COUNT(*) FROM journal_entry_lines
       WHERE client_id = NEW.client_id AND company_code = NEW.company_code
         AND fiscal_year = NEW.fiscal_year AND document_number = NEW.document_number) < 2 THEN
    RAISE EXCEPTION 'Document % must have at least two line items', NEW.document_number USING ERRCODE = 'P0001';
  END IF;
  RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER document_min_lines AFTER INSERT ON journal_entry_headers
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION trg_document_min_lines();

-- 7.5 Immutability: posted documents are never deleted; only clearing / reversal fields may change
CREATE OR REPLACE FUNCTION trg_no_delete() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Posted documents cannot be deleted; use reverse_document instead' USING ERRCODE = 'P0001';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER lines_no_delete   BEFORE DELETE ON journal_entry_lines   FOR EACH ROW EXECUTE FUNCTION trg_no_delete();
CREATE TRIGGER headers_no_delete BEFORE DELETE ON journal_entry_headers FOR EACH ROW EXECUTE FUNCTION trg_no_delete();
-- NOTE: for snapshot/reset use TRUNCATE (not blocked) or restore a template database.

CREATE OR REPLACE FUNCTION trg_lines_immutable() RETURNS trigger AS $$
BEGIN
  IF (to_jsonb(NEW) - ARRAY['is_open_item','clearing_date','clearing_document'])
     IS DISTINCT FROM
     (to_jsonb(OLD) - ARRAY['is_open_item','clearing_date','clearing_document']) THEN
    RAISE EXCEPTION 'Posted line items cannot be changed (only clearing data)' USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER lines_immutable BEFORE UPDATE ON journal_entry_lines
  FOR EACH ROW EXECUTE FUNCTION trg_lines_immutable();

CREATE OR REPLACE FUNCTION trg_headers_immutable() RETURNS trigger AS $$
BEGIN
  IF (to_jsonb(NEW) - ARRAY['reversed_by_document'])
     IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['reversed_by_document']) THEN
    RAISE EXCEPTION 'Posted document headers cannot be changed' USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER headers_immutable BEFORE UPDATE ON journal_entry_headers
  FOR EACH ROW EXECUTE FUNCTION trg_headers_immutable();

-- 7.6 Number range helper
CREATE OR REPLACE FUNCTION next_document_number(p_client TEXT, p_company TEXT, p_doc_type TEXT, p_year INT)
RETURNS TEXT AS $$
DECLARE v_range TEXT; v_next BIGINT; v_to BIGINT;
BEGIN
  SELECT number_range INTO v_range FROM document_types
   WHERE client_id = p_client AND document_type = p_doc_type;
  IF v_range IS NULL THEN
    RAISE EXCEPTION 'Document type % does not exist', p_doc_type USING ERRCODE = 'P0001';
  END IF;

  UPDATE document_number_ranges SET current_number = current_number + 1
   WHERE client_id = p_client AND company_code = p_company
     AND number_range = v_range AND fiscal_year = p_year
   RETURNING current_number, range_to INTO v_next, v_to;

  IF v_next IS NULL THEN
    RAISE EXCEPTION 'No number range % for company code % and year %', v_range, p_company, p_year
      USING ERRCODE = 'P0001';
  END IF;
  RETURN lpad(v_next::TEXT, 10, '0');
END $$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 8. REPORTING VIEWS & FUNCTIONS
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW gl_account_period_balances AS      -- replaces GLT0 / FAGLFLEXT
SELECT client_id, ledger, company_code, fiscal_year, posting_period, gl_account,
       SUM(amount_company_currency) FILTER (WHERE amount_company_currency > 0)  AS debit_total,
       -SUM(amount_company_currency) FILTER (WHERE amount_company_currency < 0) AS credit_total,
       SUM(amount_company_currency)                                             AS period_balance
FROM journal_entry_lines
GROUP BY client_id, ledger, company_code, fiscal_year, posting_period, gl_account;

CREATE OR REPLACE FUNCTION trial_balance(
  p_client TEXT, p_ledger TEXT, p_company TEXT, p_year INT, p_through_period INT)
RETURNS TABLE (
  gl_account TEXT, account_name TEXT, statement_type TEXT,
  debit_total NUMERIC, credit_total NUMERIC, balance NUMERIC) AS $$
  SELECT l.gl_account,
         t.short_text,
         a.statement_type,
         COALESCE(SUM(l.amount_company_currency) FILTER (WHERE l.amount_company_currency > 0), 0),
         COALESCE(-SUM(l.amount_company_currency) FILTER (WHERE l.amount_company_currency < 0), 0),
         SUM(l.amount_company_currency)
    FROM journal_entry_lines l
    JOIN gl_account_company_settings s
      ON s.client_id = l.client_id AND s.company_code = l.company_code AND s.gl_account = l.gl_account
    JOIN gl_accounts a
      ON a.client_id = s.client_id AND a.chart_of_accounts = s.chart_of_accounts AND a.gl_account = s.gl_account
    LEFT JOIN gl_account_texts t
      ON t.client_id = a.client_id AND t.chart_of_accounts = a.chart_of_accounts
     AND t.gl_account = a.gl_account AND t.language = 'EN'
   WHERE l.client_id = p_client AND l.ledger = p_ledger AND l.company_code = p_company
     AND l.fiscal_year = p_year AND l.posting_period <= p_through_period
   GROUP BY l.gl_account, t.short_text, a.statement_type
   ORDER BY l.gl_account;
$$ LANGUAGE sql STABLE;
-- Note: balance-sheet carry-forward from prior years is a Phase 3 closing step.

CREATE OR REPLACE VIEW journal_entries_flat AS             -- convenient join for agent tools
SELECT h.client_id, h.company_code, h.fiscal_year, h.document_number, h.document_type,
       h.document_date, h.posting_date, h.posting_period, h.currency AS document_currency,
       h.external_reference, h.header_text, h.created_by, h.reverses_document, h.reversed_by_document,
       l.ledger, l.line_number, l.posting_key, l.account_type, l.gl_account,
       l.debit_credit_indicator, l.amount_transaction_currency, l.transaction_currency,
       l.amount_company_currency, l.cost_center, l.profit_center,
       l.vendor_id, l.customer_id, l.tax_code, l.is_open_item, l.line_text
FROM journal_entry_headers h
JOIN journal_entry_lines   l USING (client_id, company_code, fiscal_year, document_number);

-- ---------------------------------------------------------------------
-- 9. SCHEMA NAME MAPPING (friendly <-> SAP) - data, not tribal knowledge
-- ---------------------------------------------------------------------
CREATE TABLE schema_name_mapping (
  friendly_table   TEXT NOT NULL,
  friendly_column  TEXT NOT NULL DEFAULT '*',
  sap_table        TEXT NOT NULL,
  sap_column       TEXT NOT NULL DEFAULT '*',
  PRIMARY KEY (friendly_table, friendly_column)
);

INSERT INTO schema_name_mapping (friendly_table, friendly_column, sap_table, sap_column) VALUES
 ('clients','*','T000','*'), ('currencies','*','TCURC','*'), ('exchange_rates','*','TCURR','*'),
 ('charts_of_accounts','*','T004','*'), ('fiscal_year_variants','*','T009','*'),
 ('ledgers','*','FINSC_LEDGER','*'), ('company_codes','*','T001','*'),
 ('controlling_areas','*','TKA01','*'), ('gl_accounts','*','SKA1','*'),
 ('gl_account_texts','*','SKAT','*'), ('gl_account_company_settings','*','SKB1','*'),
 ('cost_centers','*','CSKS','*'), ('profit_centers','*','CEPC','*'),
 ('document_types','*','T003','*'), ('posting_keys','*','TBSL','*'),
 ('posting_period_controls','*','T001B','*'), ('document_number_ranges','*','NRIV','*'),
 ('journal_entry_headers','*','BKPF','*'), ('journal_entry_lines','*','ACDOCA','*'),
 ('journal_entry_tax_lines','*','BSET','*'),
 -- columns: headers
 ('journal_entry_headers','client_id','BKPF','MANDT'),
 ('journal_entry_headers','company_code','BKPF','BUKRS'),
 ('journal_entry_headers','document_number','BKPF','BELNR'),
 ('journal_entry_headers','fiscal_year','BKPF','GJAHR'),
 ('journal_entry_headers','document_type','BKPF','BLART'),
 ('journal_entry_headers','document_date','BKPF','BLDAT'),
 ('journal_entry_headers','posting_date','BKPF','BUDAT'),
 ('journal_entry_headers','posting_period','BKPF','MONAT'),
 ('journal_entry_headers','currency','BKPF','WAERS'),
 ('journal_entry_headers','external_reference','BKPF','XBLNR'),
 ('journal_entry_headers','header_text','BKPF','BKTXT'),
 ('journal_entry_headers','created_by','BKPF','USNAM'),
 ('journal_entry_headers','reversed_by_document','BKPF','STBLG'),
 -- columns: lines
 ('journal_entry_lines','client_id','ACDOCA','RCLNT'),
 ('journal_entry_lines','ledger','ACDOCA','RLDNR'),
 ('journal_entry_lines','company_code','ACDOCA','RBUKRS'),
 ('journal_entry_lines','fiscal_year','ACDOCA','GJAHR'),
 ('journal_entry_lines','document_number','ACDOCA','BELNR'),
 ('journal_entry_lines','line_number','ACDOCA','DOCLN'),
 ('journal_entry_lines','gl_account','ACDOCA','RACCT'),
 ('journal_entry_lines','account_type','ACDOCA','KOART'),
 ('journal_entry_lines','debit_credit_indicator','ACDOCA','DRCRK'),
 ('journal_entry_lines','amount_transaction_currency','ACDOCA','WSL'),
 ('journal_entry_lines','transaction_currency','ACDOCA','RTCUR'),
 ('journal_entry_lines','amount_company_currency','ACDOCA','HSL'),
 ('journal_entry_lines','amount_group_currency','ACDOCA','KSL'),
 ('journal_entry_lines','cost_center','ACDOCA','RCNTR'),
 ('journal_entry_lines','profit_center','ACDOCA','PRCTR'),
 ('journal_entry_lines','vendor_id','ACDOCA','LIFNR'),
 ('journal_entry_lines','customer_id','ACDOCA','KUNNR'),
 ('journal_entry_lines','tax_code','ACDOCA','MWSKZ'),
 ('journal_entry_lines','clearing_date','ACDOCA','AUGDT'),
 ('journal_entry_lines','clearing_document','ACDOCA','AUGBL'),
 ('journal_entry_lines','is_open_item','ACDOCA','XOPVW'),
 ('journal_entry_lines','line_text','ACDOCA','SGTXT');

-- Optional: SAP-style alias views to test portability of agent queries.
CREATE SCHEMA IF NOT EXISTS sap_compat;
CREATE OR REPLACE VIEW sap_compat.bkpf AS
SELECT client_id AS mandt, company_code AS bukrs, document_number AS belnr, fiscal_year AS gjahr,
       document_type AS blart, document_date AS bldat, posting_date AS budat,
       posting_period AS monat, currency AS waers, external_reference AS xblnr,
       header_text AS bktxt, created_by AS usnam, reversed_by_document AS stblg
FROM finance.journal_entry_headers;

CREATE OR REPLACE VIEW sap_compat.acdoca AS
SELECT client_id AS rclnt, ledger AS rldnr, company_code AS rbukrs, fiscal_year AS gjahr,
       document_number AS belnr, line_number AS docln, gl_account AS racct,
       account_type AS koart, debit_credit_indicator AS drcrk,
       amount_transaction_currency AS wsl, transaction_currency AS rtcur,
       amount_company_currency AS hsl, amount_group_currency AS ksl,
       cost_center AS rcntr, profit_center AS prctr, vendor_id AS lifnr,
       customer_id AS kunnr, tax_code AS mwskz, clearing_date AS augdt,
       clearing_document AS augbl, is_open_item AS xopvw, line_text AS sgtxt
FROM finance.journal_entry_lines;

-- ---------------------------------------------------------------------
-- 10. MINIMAL SEED DATA (one demo company so the schema is usable immediately)
-- ---------------------------------------------------------------------
INSERT INTO clients VALUES ('100', 'Demo Client', 'Synthetic test client');
INSERT INTO currencies VALUES ('USD','US Dollar',2), ('EUR','Euro',2), ('INR','Indian Rupee',2), ('JPY','Japanese Yen',0);

INSERT INTO charts_of_accounts VALUES ('100', 'CAUS', 'Demo chart of accounts', 10);
INSERT INTO fiscal_year_variants VALUES ('100', 'K4', 'Calendar year, 4 special periods', 12, 4, TRUE);
INSERT INTO ledgers VALUES ('100', '0L', 'Leading ledger', TRUE, 'IFRS');
INSERT INTO company_codes VALUES ('100', '1000', 'Demo Inc.', 'US', 'USD', 'USD', 'CAUS', 'K4');
INSERT INTO controlling_areas VALUES ('100', '1000', 'Demo controlling area', 'USD', 'CAUS', 'K4');
INSERT INTO company_code_controlling_areas VALUES ('100', '1000', '1000');

INSERT INTO gl_accounts (client_id, chart_of_accounts, gl_account, account_group, statement_type) VALUES
 ('100','CAUS','0000100000','CASH','BALANCE_SHEET'),
 ('100','CAUS','0000140000','RECEIVABLES','BALANCE_SHEET'),
 ('100','CAUS','0000160000','PAYABLES','BALANCE_SHEET'),
 ('100','CAUS','0000300000','EQUITY','BALANCE_SHEET'),
 ('100','CAUS','0000400000','REVENUE','PROFIT_LOSS'),
 ('100','CAUS','0000500000','COGS','PROFIT_LOSS'),
 ('100','CAUS','0000600000','OPEX','PROFIT_LOSS');
INSERT INTO gl_account_texts (client_id, chart_of_accounts, gl_account, short_text) VALUES
 ('100','CAUS','0000100000','Bank account'),
 ('100','CAUS','0000140000','Trade receivables'),
 ('100','CAUS','0000160000','Trade payables'),
 ('100','CAUS','0000300000','Share capital'),
 ('100','CAUS','0000400000','Sales revenue'),
 ('100','CAUS','0000500000','Cost of goods sold'),
 ('100','CAUS','0000600000','Operating expenses');
INSERT INTO gl_account_company_settings
  (client_id, company_code, chart_of_accounts, gl_account, is_open_item_managed, reconciliation_account_type) VALUES
 ('100','1000','CAUS','0000100000', FALSE, NULL),
 ('100','1000','CAUS','0000140000', TRUE,  'CUSTOMER'),
 ('100','1000','CAUS','0000160000', TRUE,  'VENDOR'),
 ('100','1000','CAUS','0000300000', FALSE, NULL),
 ('100','1000','CAUS','0000400000', FALSE, NULL),
 ('100','1000','CAUS','0000500000', FALSE, NULL),
 ('100','1000','CAUS','0000600000', FALSE, NULL);

INSERT INTO profit_centers (client_id, controlling_area, profit_center, name, company_code) VALUES
 ('100','1000','PC1000','Corporate','1000');
INSERT INTO cost_centers (client_id, controlling_area, cost_center, name, company_code, profit_center) VALUES
 ('100','1000','CC1000','Administration','1000','PC1000'),
 ('100','1000','CC2000','Sales','1000','PC1000');

INSERT INTO document_types (client_id, document_type, description, number_range,
                            allows_vendor_postings, allows_customer_postings, reversal_document_type) VALUES
 ('100','SA','G/L account document','01', FALSE, FALSE, 'AB'),
 ('100','KR','Vendor invoice','19',       TRUE,  FALSE, 'KA'),
 ('100','DR','Customer invoice','18',     FALSE, TRUE,  'DA'),
 ('100','AB','Reversal document','02',    TRUE,  TRUE,  NULL);

INSERT INTO posting_keys VALUES
 ('100','40','Debit G/L account',  'D','GL',FALSE),
 ('100','50','Credit G/L account', 'C','GL',FALSE),
 ('100','31','Vendor credit (invoice)','C','VENDOR',FALSE),
 ('100','21','Vendor debit (credit memo)','D','VENDOR',FALSE),
 ('100','01','Customer debit (invoice)','D','CUSTOMER',FALSE),
 ('100','11','Customer credit (credit memo)','C','CUSTOMER',FALSE);

INSERT INTO posting_period_controls
SELECT '100','1000', 2026, p, TRUE FROM generate_series(1,12) AS p;

INSERT INTO document_number_ranges VALUES
 ('100','1000','01',2026, 100000000, 199999999, 99999999),
 ('100','1000','02',2026, 200000000, 299999999, 199999999),
 ('100','1000','18',2026, 180000000, 189999999, 179999999),
 ('100','1000','19',2026, 190000000, 199999999, 189999999);

-- ---------------------------------------------------------------------
-- Example: post a balanced G/L document (run inside one transaction)
-- ---------------------------------------------------------------------
-- BEGIN;
--   INSERT INTO journal_entry_headers (client_id, company_code, fiscal_year, document_number,
--          document_type, document_date, posting_date, currency, header_text, created_by)
--   VALUES ('100','1000',2026, next_document_number('100','1000','SA',2026),
--          'SA', DATE '2026-10-05', DATE '2026-10-05', 'USD', 'Initial capital', 'TWIN_USER');
--   -- then insert two lines (debit 0000100000 +10000.00, credit 0000300000 -10000.00)
-- COMMIT;   -- balance and min-line checks fire here
