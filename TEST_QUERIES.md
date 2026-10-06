# Finance Twin MCP Server — Manual Test Queries for GitHub Copilot & MCP Clients

Use these test prompts in **GitHub Copilot Chat**, Claude Desktop, or any MCP client to test all 15 FastMCP tools against live **Supabase PostgreSQL** or local **SQLite** (`finance_twin.db`). All test cases use exact master data, accounts, vendor IDs, and document numbers from the **Client 200 (Meridian Financial Group)** seed database.

---

## 🎯 Use Case 1: Journal Entry Assistant (FA1)

### Test 1.1: Diagnose a Blocked Account Posting Failure
* **Context:** A junior accountant attempted to post an entry debiting the legacy suspense/clearing account `0000199000` for Meridian Bank N.A. (Company Code `1000`). The posting was rejected by the database.
* **Prompt for Copilot:**
  > *"A junior accountant tried to post a journal entry debiting account `0000199000` for Meridian Bank N.A. (Company Code 1000). The posting failed. Using your MCP tools, check why this account failed, verify if it is blocked, and identify active alternative accounts for operating expenses or accrued liabilities."*
* **Expected Tools Called:** `lookup_master_data` (with `object_type="gl_account"`, `id="0000199000"`, `company_code="1000"`)
* **Expected Result:**
  - Identifies that G/L account `0000199000` (*"Legacy clearing account (blocked)"*) has `chart_blocked = true` and `company_blocked = true`.
  - Recommends active valid alternatives from the Chart of Accounts, such as `0000600000` (*"Salaries and benefits"* / Operating Expenses) or `0000270000` (*"Accrued expenses"* / Liabilities).

---

### Test 1.2: Check Posting Period Controls (OB52 / T001B)
* **Context:** Check whether prior closed periods can accept postings versus the current active posting period for Company Code `1000` in Fiscal Year `2026`.
* **Prompt for Copilot:**
  > *"Check if Period 8 is open for Company Code 1000 for fiscal year 2026. If it is closed, check whether Period 9 is available for posting."*
* **Expected Tools Called:** `get_period_status` (for Period 8, then Period 9)
* **Expected Result:**
  - Period 8 returns `status: "CLOSED"` (`is_open: false`).
  - Period 9 returns `status: "OPEN"` (`is_open: true`).

---

### Test 1.3: Prepare and Validate a Payroll Accrual Draft
* **Context:** Simulate posting an end-of-month payroll accrual for September 30, 2026 (Period 9) of USD 2,500,000.00.
* **Prompt for Copilot:**
  > *"Prepare and validate a draft journal entry to accrue September 2026 payroll of USD 2,500,000.00 for Meridian Bank N.A. (Company Code 1000, Date: 2026-09-30). Debit Salaries and benefits (0000600000) and credit Accrued expenses (0000270000). Simulate validation first to verify debit/credit balance and period eligibility."*
* **Expected Tools Called:** `get_period_status` → `lookup_master_data` → `validate_journal_entry`
* **Expected Result:**
  - `validate_journal_entry` executes in a rollback transaction.
  - Returns `valid: true`, `message: "Journal entry is valid and balanced."`, `net_balance: 0.00`, with debit and credit legs of $2,500,000.00. Zero rows persisted.

---

### Test 1.4: Stage and Replay Idempotent Journal Entry Draft
* **Context:** Stage the proposed journal entry in `draft_entries` for approval gating, then replay with the same idempotency key.
* **Prompt for Copilot:**
  > *"Stage a pending journal entry draft for the September 2026 payroll accrual of USD 2,500,000.00 (Company 1000, Debit 0000600000, Credit 0000270000) using idempotency key 'payroll-sep-2026-001'. Check the returned draft ID and trial balance impact."*
* **Expected Tools Called:** `post_journal_entry`
* **Expected Result:**
  - Returns `status: "pending"`, a unique `draft_id`, and stages the proposal in `draft_entries`.
  - Re-submitting with the same `idempotency_key` returns the existing draft without duplicate inserts.

---

### Test 1.5: Inspect Full Accounting Document and Lines (FB03)
* **Context:** Retrieve header, lines, and partner metadata for opening balance document `0100000000` or vendor invoice `0190000017`.
* **Prompt for Copilot:**
  > *"Retrieve the full accounting document details for Document Number 0190000017 in Company Code 1000 for Fiscal Year 2026."*
* **Expected Tools Called:** `get_document` (`company_code="1000"`, `fiscal_year=2026`, `document_number="0190000017"`)
* **Expected Result:**
  - Header: Document type `KR`, posting date `2026-02-23`, reference `INV-003-01017`, header text *"Quantum Colocation Partners - invoice"*.
  - Lines: Vendor liability line for vendor `0000100003` ($74,186.00 credit) and expense line on `0000620000` ($74,186.00 debit).

---

## 🔍 Use Case 2: Payables Risk Review (FA2)

### Test 2.1: Find Candidate Duplicate Invoices & Recoverable Cash
* **Context:** Audit the payables sub-ledger for duplicate invoice submissions per vendor (same vendor, same external invoice reference, same amount).
* **Prompt for Copilot:**
  > *"Scan for duplicate vendor invoices in Meridian Bank N.A. (Company Code 1000). Also check Meridian Bank India (Company Code 4000). Report the vendor ID, external reference number, document numbers, paid vs open status, and calculate the total recoverable cash."*
* **Expected Tools Called:** `find_duplicate_invoices` (with `mode="exact"` or `mode="fuzzy"`)
* **Expected Result:**
  - **Company 1000:** Identifies vendor `0000100007` invoice `INV-007-01019` posted twice as documents `0190000019` and `0190000020` for $478,155.00 each (both cleared/paid via clearing docs `0150000018` and `0150000019`).
  - **Company 4000:** Identifies vendor `0000100014` invoice `INV-014-01217` posted as documents `0190000030` (cleared) and `0190000031` (open) for INR 6,281,885.76, flagging INR 6,281,885.76 in immediate recoverable cash.

---

### Test 2.2: List Open Vendor Items and Aging (FBL1N)
* **Context:** Review open vendor payable items with posting date aging as of October 2026.
* **Prompt for Copilot:**
  > *"List the open vendor items for Meridian Bank N.A. (Company Code 1000) as of October 5, 2026. Identify the oldest unpaid vendor invoices and summarize their age in days."*
* **Expected Tools Called:** `list_open_items` (`company_code="1000"`, `account_type="vendor"`, `as_of_date="2026-10-05"`)
* **Expected Result:**
  - Returns 38 open line items for Company Code 1000.
  - Highlights oldest unpaid vendor items such as `0190000017` (Vendor `0000100003` Quantum Colocation Partners, posted `2026-02-23`, age > 220 days, amount $74,186.00) and `0190000050` (posted `2026-06-16`, amount $137,031.00).

---

### Test 2.3: Historical Account Usage Profiling
* **Context:** Baseline historical G/L account distribution for specific vendors or text patterns to avoid mispostings.
* **Prompt for Copilot:**
  > *"Retrieve the historical account usage profile for vendor 0000100003 in Company Code 1000 to determine which expense accounts are normally charged."*
* **Expected Tools Called:** `get_account_usage_profile` (`company_code="1000"`, `vendor_id="0000100003"`)
* **Expected Result:**
  - Shows 100% historical allocation to G/L account `0000620000` (*"Technology and communications"*).

---

## 📊 Use Case 3: Period-End Close Reviewer (FA3)

### Test 3.1: Trial Balance Verification (FAGLB03)
* **Context:** Compute the trial balance for September 2026 (Period 9) under US GAAP (Leading Ledger `0L`) and verify the zero-balance invariant.
* **Prompt for Copilot:**
  > *"Run the trial balance for Meridian Bank N.A. (Company Code 1000) for Period 9 in Fiscal Year 2026 for Ledger 0L. Confirm total debits equal total credits and report net difference."*
* **Expected Tools Called:** `get_trial_balance` (`company_code="1000"`, `fiscal_year=2026`, `period=9`, `ledger="0L"`)
* **Expected Result:**
  - Total Debits: **$1,169,443,671.21**
  - Total Credits: **$1,169,443,671.21**
  - Net Difference: **0.00**
  - Per-account breakdown across Cash (`0000100000`), Loans (`0000150000`, `0000151000`), Credit Loss Allowances (`0000159000`), Interest Receivables (`0000180000`), etc.

---

### Test 3.2: Parallel Ledger Reconciliation (US GAAP 0L vs IFRS 2L)
* **Context:** Reconcile US GAAP Leading Ledger `0L` against IFRS Parallel Ledger `2L` for Period 9 and Period 6 in Company Code `1000`.
* **Prompt for Copilot:**
  > *"Compare Ledger 0L (US GAAP) against Ledger 2L (IFRS) for Period 9 in Company Code 1000 for Fiscal Year 2026. Also check Period 6. List all variance accounts and differences."*
* **Expected Tools Called:** `compare_ledgers` (`company_code="1000"`, `fiscal_year=2026`, `period=9`, `ledger_a="0L"`, `ledger_b="2L"`)
* **Expected Result:**
  - **Period 9:** Identifies $1,750.00 variance between Cash (`0000100000`) and Provision for Credit Losses (`0000500000`).
  - **Period 6:** Identifies $18,000,000.00 multi-ledger adjustment in Allowance for Credit Losses (`0000159000`) vs Provision (`0000500000`) posted under IFRS CECL/ECL model differences.

---

### Test 3.3: Scan for Journal Posting Anomalies
* **Context:** Forensic accounting scan across 2026 postings for rare account usage, round-amount transactions, and out-of-pattern weekend postings.
* **Prompt for Copilot:**
  > *"Scan for journal entry anomalies in Company Code 1000 for fiscal year 2026. Inspect rare account usage, round amounts, and weekend postings."*
* **Expected Tools Called:** `scan_journal_anomalies` (`company_code="1000"`, `fiscal_year=2026`)
* **Expected Result:**
  - Reports anomaly scores and flags rare accounts used in < 2% of postings (such as equity adjustments or legacy accounts).

---

### Test 3.4: Stage Document Reversal Draft
* **Context:** Safely stage a document reversal draft for document `0100000001` in Company Code `1000`.
* **Prompt for Copilot:**
  > *"Prepare a reversal draft for document 0100000001 in Company Code 1000 with reversal date 2026-09-30 and reason 'Period-end accrual true-up'."*
* **Expected Tools Called:** `reverse_document` (`company_code="1000"`, `fiscal_year=2026`, `document_number="0100000001"`, `reversal_date="2026-09-30"`, `reason="Period-end accrual true-up"`)
* **Expected Result:**
  - Validates that document `0100000001` is not already reversed or cleared.
  - Returns `status: "pending"` and stages a draft reversal in `draft_entries` (zero direct deletion/mutation of posted entries).
