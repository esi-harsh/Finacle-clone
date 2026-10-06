# Finance Digital Twin FastMCP Server

An enterprise-grade SAP S/4HANA Finance Digital Twin MCP server implementing **Journal Entry Intake & Validation (FA1)**, **Payables Risk & Duplicate Invoice Review (FA2)**, **Period-End Close & Multi-Ledger Reconciliation (FA3)**, and an immutable **Audit Trace Log** backed by **PostgreSQL 16 / Supabase** and local **SQLite (`uv`)** fallback.

Conforms to **SOX Section 302/404**, **Basel III/IV (BCBS 239)**, and **MAS Technology Risk Management (TRM)** financial data governance requirements.

---

## Architecture Overview

```
                          ┌─────────────────────────────────────────┐
                          │         Finance AI Agent System         │
                          │   (FA1 Journal / FA2 AP Risk / FA3 Close)│
                          └───────────────────┬─────────────────────┘
                                              │ (SSE / Stdio / HTTP)
                          ┌───────────────────▼─────────────────────┐
                          │       FastMCP Server (Port 8000)        │
                          │  lookup.*   | balances.* | analysis.*   │
                          │  validate.* | draft.*    | audit.*      │
                          └───────────────────┬─────────────────────┘
                                              │
                     ┌────────────────────────┴────────────────────────┐
                     ▼                                                 ▼
        ┌──────────────────────────┐                      ┌──────────────────────────┐
        │  PostgreSQL 16 / Supabase│                      │   Embedded SQLite Store  │
        │  Universal Journal ACDOCA│        (or)          │   (Local Zero-Config     │
        │  Multi-Ledger 0L / 2L    │                      │    Offline Fallback)     │
        └──────────────────────────┘                      └──────────────────────────┘
```

---

## 1. Database Setup

### Option A: Local Zero-Config Setup with `uv` (No Docker / PostgreSQL Required)
For instant local testing and evaluation without any database infrastructure:

```bash
# 1. Sync dependencies with uv
uv sync

# 2. Initialize and seed local SQLite database
uv run python db/init_sqlite.py
```
This automatically creates and populates `finance_twin.db` with master data, chart of accounts, posting period controls, and synthetic transactions.

---

### Option B: PostgreSQL 16 via Docker Compose
For full enterprise database simulation with PostgreSQL triggers, row-level security, and stored procedures:

```bash
docker compose up -d
```

This runs the database on port `5432` and automatically executes:
1. `db/finacle_tables.sql`: Phase 1 DDL with 24 tables under `finance` schema and `sap_compat` views.
2. `db/finance_seed_data.sql`: Meridian Financial Group synthetic seed (Client `200`).

---

### Option C: Cloud Supabase Setup & Automated Seeding

Follow these steps to connect and seed your cloud Supabase PostgreSQL instance:

#### 1. Create a Supabase Project
1. Log in to [Supabase](https://supabase.com) and create a new project.
2. Note down your database password.

#### 2. Get Your PostgreSQL Connection String
1. In your Supabase Dashboard, navigate to **Project Settings** (gear icon) -> **Database**.
2. Scroll to the **Connection string** section and select the **URI** tab.
3. Choose either **Session Mode** (port `5432`) or **Transaction Mode** (port `6543`).
4. Copy the URI string, which follows this format:
   ```text
   postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:6543/postgres
   ```

#### 3. Configure `.env`
1. Copy `.env.example` to `.env` if you haven't already:
   ```bash
   cp .env.example .env
   ```
2. Paste your PostgreSQL connection URI into `.env` under `SUPABASE_URL` or `DATABASE_URL` (ensure you replace `[YOUR-PASSWORD]` with your actual password):
   ```env
   SUPABASE_URL=postgresql://postgres.<project-ref>:<your-password>@aws-0-<region>.pooler.supabase.com:6543/postgres
   ```

#### 4. Run the Automated Seeder
Execute the Supabase database seeder script using `uv`:
```bash
uv run python db/seed_supabase.py
```
*(Or with standard python: `python db/seed_supabase.py`)*

This script automatically:
- Resets previous `finance` and `sap_compat` schemas cleanly.
- Executes `db/finacle_tables.sql` (creating 24 tables, SAP views, constraints, and audit triggers).
- Executes `db/finance_seed_data.sql` (seeding 806 documents, 4,090 line items, posting controls, and master data for Client `200`).

#### 5. Verify the Connection
Run the live tool verification suite to confirm all 15 MCP tools interact properly with your seeded Supabase instance:
```bash
uv run python tests/test_tools.py
```

---

## 2. Seed Data Scope (Client 200 — Meridian Financial Group)

The twin is initialized with realistic, messy enterprise financial records:
- **4 Company Codes**: `1000` (Meridian Bank N.A. - USD), `2000` (Capital Markets - USD), `3000` (Europe - EUR), `4000` (India - INR).
- **Dual Accounting Ledgers**: `0L` (US GAAP Leading Ledger) and `2L` (IFRS Parallel Ledger).
- **Period State**: Periods 1–8 CLOSED, Periods 9–12 OPEN (as of October 2026).
- **806 Documents & 4,090 Line Items**: Including open vendor invoices, tax items, cash sweeps, intercompany balances, and accrual reversal chains.
- **Injected Audit Exceptions**:
  - Exact duplicate vendor invoice pairs (open copy vs. paid copy).
  - Fuzzy duplicate pairs (typos in reference, date shifts, ±1% amount differences).
  - Decoy invoice pairs (identical invoice number across *different* suppliers — must not be flagged).
  - Blocked legacy suspense accounts (`0000199000`) and blocked cost centers.
  - Multi-ledger adjustments posted only to `2L` (IFRS lease accounting).
  - Out-of-pattern weekend and round-amount postings.

---

## 3. Environment Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Update your `.env` file with your settings:

```env
# Supabase / Cloud Database Configuration (Optional - defaults to SQLite/PostgreSQL)
SUPABASE_URL=
SUPABASE_KEY=

# FastMCP Server Configuration
MCP_TRANSPORT=http
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8000
MCP_SERVER_URL=http://localhost:8000/sse

# Local SQLite Database Path
LOCAL_DB_PATH=finance_twin.db
```

---

## 4. Installation

Install dependencies using **`uv`** (recommended) or **`pip`**:

```bash
# Using uv (ultra-fast)
uv sync

# Or using standard pip
pip install -r requirements.txt
```

---

## 5. MCP Tools Reference

### A. Lookup & Master Data Tools (`lookup.*`)
Production-parity queries for inspecting accounting documents, master data, and period controls (SAP: FB03, FBL3N, FS00, OB52).

| Tool Name | Description | Key Inputs | Output | SAP Analogue |
| :--- | :--- | :--- | :--- | :--- |
| `get_document` | Retrieves full accounting document (header, lines, tax lines, reversal links) | `company_code`, `fiscal_year`, `document_number` (10-digit zero-padded) | Document detail object with lines & tax | `FB03` |
| `search_documents` | Paged search across flat universal journal view with multi-column filters | `company_code`, `date_from/to`, `gl_account`, `vendor_id`, `text_search` | Paged list of matching line items | `FBL3N` |
| `lookup_master_data` | Checks master data records and control flags (blocked, recon type, currency) | `object_type` (`gl_account`, `cost_center`, `company_code`), `id` | Master record with control flags | `FS00` / `BP` |
| `get_period_status` | Checks if a posting period is OPEN or CLOSED in posting period controls | `company_code`, `fiscal_year`, `period` | Status (`OPEN` or `CLOSED`), `is_open` flag | `OB52` / `T001B` |

---

### B. Balances & Financial Reporting Tools (`balances.*`)
Calculates trial balances, line item ledger roll-forwards, period flux summaries, open item aging, and multi-ledger reconciliations.

| Tool Name | Description | Key Inputs | Output | SAP Analogue |
| :--- | :--- | :--- | :--- | :--- |
| `get_trial_balance` | Computes per-account debits, credits, balances, and abnormal balance flags (sums to zero) | `company_code`, `fiscal_year`, `period`, `ledger` (`0L`/`2L`) | Per-account balance table, total debits/credits | `FAGLB03` |
| `get_account_line_items` | Paged line items with cumulative running balance for a specific G/L account | `company_code`, `gl_account`, `fiscal_year`, `period_from/to` | Line items with running balance | `FBL3N` |
| `get_period_summary` | Server-side aggregated period totals grouped by account, cost center, or profit center | `company_code`, `fiscal_year`, `group_by`, `period_from/to` | Aggregated period movement breakdown | `S_ALR` |
| `list_open_items` | Lists open vendor or customer items with posting-date based aging | `company_code`, `account_type` (`vendor`/`customer`), `as_of_date` | Open items list with calculated `age_days` | `FBL1N` / `FBL5N` |
| `compare_ledgers` | Reconciles parallel ledgers (`0L` US GAAP vs `2L` IFRS) and lists one-sided adjustments | `company_code`, `fiscal_year`, `period`, `ledger_a`, `ledger_b` | Ledger differences count and variance line list | Ledger Diff |

---

### C. Analysis & Anomaly Detection Tools (`analysis.*`)
Rule-based forensic accounting tools for duplicate invoice detection, journal anomaly scans, and historical misposting baselines.

| Tool Name | Description | Key Inputs | Output | Focus Area |
| :--- | :--- | :--- | :--- | :--- |
| `find_duplicate_invoices` | Identifies candidate duplicate vendor invoices (exact or fuzzy) per vendor | `company_code`, `mode` (`exact`/`fuzzy`), `window_days`, `tolerance_pct` | Candidate groups, open vs paid status, recoverable $ | AP Risk / Cash Leakage |
| `scan_journal_anomalies` | Scans postings using 6 deterministic accounting audit rules | `company_code`, `fiscal_year`, `rules` (`weekend`, `round`, `rare_account`) | Flagged anomalies list with scores and details | Close Audit & SOX |
| `get_account_usage_profile` | Analyzes historical account distribution by vendor, cost center, or text pattern | `company_code`, `vendor_id`, `cost_center`, `text_pattern` | Usage count and percentage distribution | Misposting Diagnosis |

---

### D. Validation & Gated Writing Tools (`write.*`)
Safely simulates postings in rollback transactions and stages proposed entries in `draft_entries` for approval gating.

| Tool Name | Description | Key Inputs | Output | Governance Rule |
| :--- | :--- | :--- | :--- | :--- |
| `validate_journal_entry` | Simulates posting inside a transaction that always rolls back; fires all SAP DB triggers | `company_code`, `document_date`, `posting_date`, `lines` (debits/credits) | `valid: true/false`, error code, trial balance impact | Zero rows persisted |
| `post_journal_entry` | Validates entry and stages a draft in `draft_entries` with status `pending` | Header metadata, lines, `idempotency_key`, `session_id` | `draft_id`, `status: pending`, trial balance impact | Approval required |
| `reverse_document` | Checks that document is unreversed and uncleared, then stages reversal draft | `company_code`, `document_number`, `reversal_date`, `reason` | `draft_id`, `status: pending`, reversal details | No manual DELETE |

---

## 6. Running the FastMCP Server

### Option A: Streamable HTTP (SSE Transport — Default)
Starts the FastMCP server over Server-Sent Events (SSE) on port `8000`:

```bash
# Using uv
uv run python server/main.py

# Or standard python
python server/main.py
```
* The SSE endpoint will be available at: **`http://localhost:8000/sse`**

### Option B: Stdio Transport (for CLI / Desktop Clients)
Run the server over standard I/O:

```bash
# Set MCP_TRANSPORT environment variable to stdio
MCP_TRANSPORT=stdio uv run python server/main.py
```

### Option C: Docker Compose
```bash
docker compose up server
```

---

## 7. Testing & Verification

Run the test suite with `unittest` via `uv`:

```bash
uv run python -m unittest tests/test_tools.py
```

Expected output:
```text
....
----------------------------------------------------------------------
Ran 4 tests in 0.001s

OK
```

---

## 8. Connecting to Agent Clients

### Claude Desktop Configuration
Add the following to your `claude_desktop_config.json`:

#### HTTP (SSE) Mode:
```json
{
  "mcpServers": {
    "finance-twin": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

#### Stdio Mode (via `uv`):
```json
{
  "mcpServers": {
    "finance-twin": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "<path-to-repo>/server/main.py"
      ],
      "env": {
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

---

## 9. Security & Governance Invariants

- **Idempotency**: All draft creation tools take an `idempotency_key` ensuring duplicate calls safely replay original drafts without creating duplicates.
- **Zero Direct Writes**: AI agents cannot directly `INSERT` into `journal_entry_headers`. All proposals land in `draft_entries` awaiting harness or human approval.
- **Audit Logging**: Every tool execution, parameter set, response summary, and execution duration is automatically recorded in `tool_call_log`.
- **SOX 302/404 Immutability**: Posted accounting lines cannot be modified or deleted. Corrections are strictly enforced via `reverse_document` plus a new validated re-post draft.
