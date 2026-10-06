# Finance Twin MCP Server

> **A high-fidelity SAP S/4HANA Finance Digital Twin exposed as a Model Context Protocol (MCP) Server.**

The Finance Twin MCP Server provides a deterministic, multi-ledger (US GAAP `0L` / IFRS `2L`), multi-company simulated finance backend for Meridian Financial Group (Client `200`). It exposes **15 standardized MCP tools** over **Streamable HTTP (SSE)** and **stdio** transports.

---

## ⚡ Quickstart: Local Startup with `uv` (No Docker Required)

This repository is powered by **[Astral `uv`](https://docs.astral.sh/uv/)** for ultra-fast dependency management and zero-setup local execution with automated SQLite fallback:

### 1. Install Dependencies
```powershell
uv sync
```

### 2. Initialize Local Database (100% Offline / Non-Docker)
```powershell
uv run python db/init_sqlite.py
```

### 3. Start the MCP Server (Streamable HTTP / SSE)
```powershell
uv run python server/main.py
```
The server will be live immediately at **`http://localhost:8000/sse`**.

---

## 🛠️ The 15 MCP Tools Catalog

### 1. Lookup Tools (SAP: FB03, FBL3N, FS00, OB52)
- **`get_document`**: Retrieve complete accounting document (header, lines, tax lines, reversal links) by `company_code`, `fiscal_year`, and 10-digit zero-padded `document_number`.
- **`search_documents`**: Filter flat journal entries by date range, account, vendor, document type, amount range, or text search.
- **`lookup_master_data`**: Retrieve master data details and control flags for G/L accounts, cost centers, profit centers, document types, or company codes.
- **`get_period_status`**: Check if an accounting period is `OPEN` or `CLOSED` per company code and fiscal year.

### 2. Balances & Reporting Tools (SAP: FAGLB03, FBL1N/FBL5N, S_ALR)
- **`get_trial_balance`**: Compute trial balance per account (debit total, credit total, balance, abnormal balance flags).
- **`get_account_line_items`**: Paged line items with cumulative running balance for a specific G/L account.
- **`get_period_summary`**: Server-side aggregated period totals grouped by account, cost center, or profit center for flux analysis.
- **`list_open_items`**: List open vendor or customer items with posting-date based aging.
- **`compare_ledgers`**: Reconcile parallel accounting ledgers (US GAAP `0L` vs IFRS `2L`) and identify adjustments present in only one ledger.

### 3. Analysis Tools
- **`find_duplicate_invoices`**: Detect candidate duplicate vendor invoices (exact or fuzzy matching per vendor) with paid vs open status and recoverable cash amounts.
- **`scan_journal_anomalies`**: Audit journal entries using 6 deterministic rules (weekend posting, round amounts, rare accounts, after close, near period end, unusual creators).
- **`get_account_usage_profile`**: Historical account usage percentages by vendor, cost center, or text pattern to identify mispostings.

### 4. Validation & Writing Tools
- **`validate_journal_entry`**: Simulate posting inside a transaction that always rolls back. Fires all SAP triggers (balance check, period open, reconciliation accounts, blocked accounts) and returns trial balance impact without persisting rows.
- **`post_journal_entry`**: Stages a journal entry draft in `draft_entries` with status `pending`. Supports idempotency keys to prevent duplicate drafts.
- **`reverse_document`**: Stages a document reversal draft in `draft_entries` with status `pending` after checking that the target document is not already reversed or cleared.

---

## 🔌 Connecting MCP Clients

You can connect any standard MCP client (Cursor, Claude Desktop, Windsurf, LangChain, or custom clients) using the following configuration:

### SSE (HTTP) Transport
```json
{
  "mcpServers": {
    "finance-twin": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### Stdio Transport (via `uv`)
```json
{
  "mcpServers": {
    "finance-twin": {
      "command": "uv",
      "args": ["run", "python", "server/main.py"],
      "env": {
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

---

## 🧪 Testing

Run automated unit tests using `uv`:
```powershell
uv run python -m unittest tests/test_tools.py
```
