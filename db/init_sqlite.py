"""
Local SQLite Database Initializer for Finance Twin.
Allows 100% offline, standalone execution without Docker or PostgreSQL.
Creates `finance_twin.db` and populates all core tables and Meridian Financial Group seed records.
"""

import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("LOCAL_DB_PATH", "finance_twin.db")


def init_sqlite_db():
    print(f"[*] Initializing local SQLite database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Base Master Tables
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS company_codes (
        client_id TEXT NOT NULL DEFAULT '200',
        company_code TEXT PRIMARY KEY,
        company_name TEXT NOT NULL,
        country TEXT NOT NULL,
        currency TEXT NOT NULL,
        chart_of_accounts TEXT NOT NULL,
        fiscal_year_variant TEXT NOT NULL DEFAULT 'K4'
    );

    CREATE TABLE IF NOT EXISTS gl_accounts (
        client_id TEXT NOT NULL DEFAULT '200',
        chart_of_accounts TEXT NOT NULL DEFAULT 'CAUS',
        gl_account TEXT PRIMARY KEY,
        account_group TEXT NOT NULL,
        is_balance_sheet INTEGER NOT NULL DEFAULT 1,
        is_blocked INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS gl_account_texts (
        client_id TEXT NOT NULL DEFAULT '200',
        chart_of_accounts TEXT NOT NULL DEFAULT 'CAUS',
        gl_account TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT 'EN',
        name TEXT NOT NULL,
        description TEXT,
        PRIMARY KEY (client_id, chart_of_accounts, gl_account, language)
    );

    CREATE TABLE IF NOT EXISTS gl_account_company_settings (
        client_id TEXT NOT NULL DEFAULT '200',
        company_code TEXT NOT NULL,
        gl_account TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'USD',
        is_open_item_managed INTEGER NOT NULL DEFAULT 0,
        is_blocked INTEGER NOT NULL DEFAULT 0,
        reconciliation_account_type TEXT,
        allowed_currency TEXT,
        PRIMARY KEY (client_id, company_code, gl_account)
    );

    CREATE TABLE IF NOT EXISTS posting_period_controls (
        client_id TEXT NOT NULL DEFAULT '200',
        company_code TEXT NOT NULL,
        fiscal_year INTEGER NOT NULL,
        posting_period INTEGER NOT NULL,
        is_open INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (client_id, company_code, fiscal_year, posting_period)
    );

    CREATE TABLE IF NOT EXISTS cost_centers (
        client_id TEXT NOT NULL DEFAULT '200',
        controlling_area TEXT NOT NULL DEFAULT 'A000',
        cost_center TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        company_code TEXT NOT NULL,
        is_blocked INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS profit_centers (
        client_id TEXT NOT NULL DEFAULT '200',
        controlling_area TEXT NOT NULL DEFAULT 'A000',
        profit_center TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        is_blocked INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS document_types (
        document_type TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        number_range TEXT NOT NULL,
        reverse_document_type TEXT
    );

    CREATE TABLE IF NOT EXISTS journal_entry_headers (
        client_id TEXT NOT NULL DEFAULT '200',
        company_code TEXT NOT NULL,
        fiscal_year INTEGER NOT NULL,
        document_number TEXT NOT NULL,
        document_type TEXT NOT NULL,
        document_date TEXT NOT NULL,
        posting_date TEXT NOT NULL,
        currency TEXT NOT NULL,
        exchange_rate REAL NOT NULL DEFAULT 1.0,
        external_reference TEXT,
        header_text TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        reverses_document TEXT,
        reversed_by_document TEXT,
        PRIMARY KEY (client_id, company_code, fiscal_year, document_number)
    );

    CREATE TABLE IF NOT EXISTS journal_entry_lines (
        client_id TEXT NOT NULL DEFAULT '200',
        ledger TEXT NOT NULL DEFAULT '0L',
        company_code TEXT NOT NULL,
        fiscal_year INTEGER NOT NULL,
        document_number TEXT NOT NULL,
        line_number INTEGER NOT NULL,
        account_type TEXT NOT NULL DEFAULT 'GL',
        gl_account TEXT NOT NULL,
        debit_credit_indicator TEXT NOT NULL,
        transaction_currency TEXT NOT NULL,
        amount_transaction_currency REAL NOT NULL,
        amount_company_currency REAL NOT NULL,
        amount_group_currency REAL NOT NULL,
        posting_date TEXT,
        posting_period INTEGER,
        cost_center TEXT,
        profit_center TEXT,
        vendor_id TEXT,
        customer_id TEXT,
        line_text TEXT,
        is_open_item INTEGER NOT NULL DEFAULT 0,
        clearing_document TEXT,
        clearing_date TEXT,
        PRIMARY KEY (client_id, ledger, company_code, fiscal_year, document_number, line_number)
    );

    CREATE TABLE IF NOT EXISTS journal_entry_tax_lines (
        client_id TEXT NOT NULL DEFAULT '200',
        company_code TEXT NOT NULL,
        fiscal_year INTEGER NOT NULL,
        document_number TEXT NOT NULL,
        tax_line_number INTEGER NOT NULL,
        tax_code TEXT NOT NULL,
        tax_rate REAL NOT NULL,
        base_amount REAL NOT NULL,
        tax_amount REAL NOT NULL,
        PRIMARY KEY (client_id, company_code, fiscal_year, document_number, tax_line_number)
    );

    CREATE TABLE IF NOT EXISTS tool_call_log (
        call_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        tool TEXT NOT NULL,
        input_json TEXT NOT NULL,
        output_summary TEXT,
        error_code TEXT,
        duration_ms INTEGER,
        called_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS draft_entries (
        draft_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        idempotency_key TEXT UNIQUE,
        draft_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        approved_at TEXT,
        approved_by TEXT
    );

    -- Flat journal view for searches
    CREATE VIEW IF NOT EXISTS journal_entries_flat AS
    SELECT h.client_id, h.company_code, h.fiscal_year, h.document_number,
           l.line_number, l.ledger, h.document_type, h.document_date,
           h.posting_date, l.posting_period, h.currency, h.external_reference,
           h.header_text, h.created_by, h.created_at, l.account_type,
           l.gl_account, l.debit_credit_indicator, l.amount_company_currency,
           l.cost_center, l.profit_center, l.vendor_id, l.customer_id,
           l.line_text, l.is_open_item, l.clearing_document, l.clearing_date
    FROM journal_entry_headers h
    JOIN journal_entry_lines l
      ON h.client_id = l.client_id AND h.company_code = l.company_code
     AND h.fiscal_year = l.fiscal_year AND h.document_number = l.document_number;
    """)

    # 2. Seed Baseline Master Data
    cur.executescript("""
    INSERT OR IGNORE INTO company_codes (company_code, company_name, country, currency, chart_of_accounts)
    VALUES 
        ('1000', 'Meridian Bank N.A.', 'US', 'USD', 'CAUS'),
        ('2000', 'Meridian Capital Markets LLC', 'US', 'USD', 'CAUS'),
        ('3000', 'Meridian Bank Europe S.A.', 'DE', 'EUR', 'CAUS'),
        ('4000', 'Meridian Bank India Pvt Ltd', 'IN', 'INR', 'CAUS');

    -- Posting periods: 1-8 closed, 9-12 open for 2026
    INSERT OR IGNORE INTO posting_period_controls (company_code, fiscal_year, posting_period, is_open)
    VALUES
        ('1000', 2026, 1, 0), ('1000', 2026, 2, 0), ('1000', 2026, 3, 0), ('1000', 2026, 4, 0),
        ('1000', 2026, 5, 0), ('1000', 2026, 6, 0), ('1000', 2026, 7, 0), ('1000', 2026, 8, 0),
        ('1000', 2026, 9, 1), ('1000', 2026, 10, 1), ('1000', 2026, 11, 1), ('1000', 2026, 12, 1);

    -- Core G/L Accounts
    INSERT OR IGNORE INTO gl_accounts (gl_account, account_group, is_balance_sheet, is_blocked)
    VALUES
        ('0000100000', 'CASH', 1, 0),
        ('0000210000', 'LIAB', 1, 0),
        ('0000300000', 'LIAB', 1, 0),
        ('0000500000', 'EXP', 0, 0),
        ('0000999999', 'LIAB', 1, 1);

    INSERT OR IGNORE INTO gl_account_texts (gl_account, name, description)
    VALUES
        ('0000100000', 'Cash and Cash Equivalents', 'Main Operating Account'),
        ('0000210000', 'Accrued Liabilities', 'Payroll and Operating Accruals'),
        ('0000300000', 'Trade Accounts Payable', 'Vendor Sub-Ledger Reconciliation Account'),
        ('0000500000', 'Personnel Expense', 'Salaries and Wages'),
        ('0000999999', 'Legacy Suspense (Retired)', 'Blocked Suspense Account');

    INSERT OR IGNORE INTO gl_account_company_settings (company_code, gl_account, currency, reconciliation_account_type, is_blocked)
    VALUES
        ('1000', '0000100000', 'USD', NULL, 0),
        ('1000', '0000210000', 'USD', NULL, 0),
        ('1000', '0000300000', 'USD', 'V', 0),
        ('1000', '0000500000', 'USD', NULL, 0),
        ('1000', '0000999999', 'USD', NULL, 1);

    -- Cost Centers & Profit Centers
    INSERT OR IGNORE INTO cost_centers (cost_center, name, company_code)
    VALUES
        ('CC_FIN_01', 'Finance & Accounting', '1000'),
        ('CC_OPS_01', 'Bank Operations', '1000'),
        ('CC_IT_01', 'Information Technology', '1000');

    INSERT OR IGNORE INTO profit_centers (profit_center, name)
    VALUES
        ('PC_RETAIL', 'Retail Banking Division'),
        ('PC_CORP', 'Corporate Banking Division');

    -- Document Types
    INSERT OR IGNORE INTO document_types (document_type, name, number_range, reverse_document_type)
    VALUES
        ('SA', 'G/L General Journal', '01', 'SA'),
        ('KR', 'Vendor Invoice', '02', 'SA'),
        ('KZ', 'Vendor Payment', '03', 'SA');

    -- 3. Seed Journal Entry Transactions
    -- Doc 1: Opening Capital / Operating Cash
    INSERT OR IGNORE INTO journal_entry_headers (client_id, company_code, fiscal_year, document_number, document_type, document_date, posting_date, currency, created_by, header_text)
    VALUES ('200', '1000', 2026, '0100000001', 'SA', '2026-09-01', '2026-09-01', 'USD', 'SYSTEM_MIGRATE', 'Initial Operating Capital');

    INSERT OR IGNORE INTO journal_entry_lines (client_id, ledger, company_code, fiscal_year, document_number, line_number, account_type, gl_account, debit_credit_indicator, transaction_currency, amount_transaction_currency, amount_company_currency, amount_group_currency, posting_date, posting_period, line_text)
    VALUES 
        ('200', '0L', '1000', 2026, '0100000001', 1, 'GL', '0000100000', 'D', 'USD', 500000.0, 500000.0, 500000.0, '2026-09-01', 9, 'Opening Cash Deposit'),
        ('200', '0L', '1000', 2026, '0100000001', 2, 'GL', '0000210000', 'C', 'USD', -500000.0, -500000.0, -500000.0, '2026-09-01', 9, 'Capital Reserve Accrual');

    -- Doc 2: September Payroll
    INSERT OR IGNORE INTO journal_entry_headers (client_id, company_code, fiscal_year, document_number, document_type, document_date, posting_date, currency, created_by, header_text)
    VALUES ('200', '1000', 2026, '0100000002', 'SA', '2026-09-15', '2026-09-15', 'USD', 'PAYROLL_AGENT', 'September 2026 Payroll Run');

    INSERT OR IGNORE INTO journal_entry_lines (client_id, ledger, company_code, fiscal_year, document_number, line_number, account_type, gl_account, debit_credit_indicator, transaction_currency, amount_transaction_currency, amount_company_currency, amount_group_currency, posting_date, posting_period, cost_center, profit_center, line_text)
    VALUES 
        ('200', '0L', '1000', 2026, '0100000002', 1, 'GL', '0000500000', 'D', 'USD', 45000.0, 45000.0, 45000.0, '2026-09-15', 9, 'CC_FIN_01', 'PC_CORP', 'Personnel Expenses Sep 2026'),
        ('200', '0L', '1000', 2026, '0100000002', 2, 'GL', '0000100000', 'C', 'USD', -45000.0, -45000.0, -45000.0, '2026-09-15', 9, NULL, NULL, 'Payroll Bank Outflow');

    -- Doc 3: Vendor Invoice (Vendor VEND_AWS_01) - $12,500
    INSERT OR IGNORE INTO journal_entry_headers (client_id, company_code, fiscal_year, document_number, document_type, document_date, posting_date, currency, created_by, external_reference, header_text)
    VALUES ('200', '1000', 2026, '0100000003', 'KR', '2026-09-10', '2026-09-10', 'USD', 'AP_CLERK_1', 'INV-AWS-88901', 'Cloud Infrastructure August');

    INSERT OR IGNORE INTO journal_entry_lines (client_id, ledger, company_code, fiscal_year, document_number, line_number, account_type, gl_account, debit_credit_indicator, transaction_currency, amount_transaction_currency, amount_company_currency, amount_group_currency, posting_date, posting_period, vendor_id, cost_center, is_open_item, line_text)
    VALUES 
        ('200', '0L', '1000', 2026, '0100000003', 1, 'VENDOR', '0000300000', 'C', 'USD', -12500.0, -12500.0, -12500.0, '2026-09-10', 9, 'VEND_AWS_01', 'CC_IT_01', 1, 'AP Cloud Services'),
        ('200', '0L', '1000', 2026, '0100000003', 2, 'GL', '0000500000', 'D', 'USD', 12500.0, 12500.0, 12500.0, '2026-09-10', 9, NULL, 'CC_IT_01', 0, 'Cloud Expense');

    -- Doc 4: Duplicate Vendor Invoice (Exact Duplicate for AP Anomaly Detection)
    INSERT OR IGNORE INTO journal_entry_headers (client_id, company_code, fiscal_year, document_number, document_type, document_date, posting_date, currency, created_by, external_reference, header_text)
    VALUES ('200', '1000', 2026, '0100000004', 'KR', '2026-09-12', '2026-09-12', 'USD', 'AP_CLERK_2', 'INV-AWS-88901', 'Cloud Infrastructure August - Resubmitted');

    INSERT OR IGNORE INTO journal_entry_lines (client_id, ledger, company_code, fiscal_year, document_number, line_number, account_type, gl_account, debit_credit_indicator, transaction_currency, amount_transaction_currency, amount_company_currency, amount_group_currency, posting_date, posting_period, vendor_id, cost_center, is_open_item, line_text)
    VALUES 
        ('200', '0L', '1000', 2026, '0100000004', 1, 'VENDOR', '0000300000', 'C', 'USD', -12500.0, -12500.0, -12500.0, '2026-09-12', 9, 'VEND_AWS_01', 'CC_IT_01', 1, 'Duplicate AP Cloud Services'),
        ('200', '0L', '1000', 2026, '0100000004', 2, 'GL', '0000500000', 'D', 'USD', 12500.0, 12500.0, 12500.0, '2026-09-12', 9, NULL, 'CC_IT_01', 0, 'Cloud Expense');
    """)

    conn.commit()
    conn.close()
    print("[+] Local SQLite database successfully created and seeded.")


if __name__ == "__main__":
    init_sqlite_db()
