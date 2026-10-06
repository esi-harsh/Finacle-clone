# Finance Twin MCP Server — Manual Test Queries for GitHub Copilot

Use these test prompts in **GitHub Copilot Chat** (or any MCP client) to manually test all 15 tools and verify the 3 core finance use cases against your live Supabase / local database.

---

## 🎯 Use Case 1: Journal Entry Assistant (FA1)

### Test 1.1: Diagnose a Blocked Account Posting Failure
> **Prompt for Copilot:**
> *"A junior accountant tried to post a journal entry debiting account 0000999999 for Meridian Bank N.A. (Company 1000). The posting failed. Using your MCP tools, find out why this account failed, identify who owns the fix, and find an active alternative account for liabilities."*
>
> **Expected Tools Called:** `lookup_master_data`  
> **Expected Result:** Diagnoses error code `ACCOUNT_BLOCKED`, names *Finance Admin* as fix owner, and suggests `0000210000` (Accrued Liabilities).

---

### Test 1.2: Diagnose a Closed Period Posting Failure
> **Prompt for Copilot:**
> *"Check if Period 8 is open for Company Code 1000 for fiscal year 2026. If it is closed, check which period is currently available for posting."*
>
> **Expected Tools Called:** `get_period_status`  
> **Expected Result:** Reports Period 8 is `CLOSED` and Period 9 is `OPEN`.

---

### Test 1.3: Prepare and Validate a Payroll Accrual Draft
> **Prompt for Copilot:**
> *"Prepare a draft journal entry to accrue September 2026 payroll of USD 2,500,000.00 for Meridian Bank N.A. (Company 1000). Debit Personnel Expense and credit Accrued Liabilities. Check that period 9 is open first, simulate validation, and stage the draft."*
>
> **Expected Tools Called:** `get_period_status` → `lookup_master_data` → `validate_journal_entry` → `post_journal_entry`  
> **Expected Result:** Simulates debit/credit balance, creates a pending draft, and outputs the trial balance impact.

---

## 🔍 Use Case 2: Payables Risk Review (FA2)

### Test 2.1: Find Candidate Duplicate Invoices & Recoverable Cash
> **Prompt for Copilot:**
> *"Scan for duplicate vendor invoices in Meridian Bank N.A. (Company 1000). Report the vendor ID, external reference, amounts, and determine which document is open (block payment) vs paid (request refund), and calculate the total recoverable amount."*
>
> **Expected Tools Called:** `find_duplicate_invoices`, `get_document`  
> **Expected Result:** Flags duplicate vendor invoices with paid vs open status and exact recoverable cash.

---

### Test 2.2: List Open Vendor Items and Aging
> **Prompt for Copilot:**
> *"List the open vendor items for Meridian Bank N.A. as of October 5, 2026, and summarize the oldest unpaid items."*
>
> **Expected Tools Called:** `list_open_items`  
> **Expected Result:** Returns open vendor items with computed `age_days` from posting date.

---

## 📊 Use Case 3: Period-End Close Reviewer (FA3)

### Test 3.1: Trial Balance Verification
> **Prompt for Copilot:**
> *"Run the trial balance for Meridian Bank N.A. (Company 1000) for Period 9 in Ledger 0L. Confirm that total debits equal total credits and check if any accounts have abnormal balance flags."*
>
> **Expected Tools Called:** `get_trial_balance`  
> **Expected Result:** Returns per-account balances, confirms net difference is `0.00`, and highlights abnormal balances.

---

### Test 3.2: Parallel Ledger Reconciliation (US GAAP 0L vs IFRS 2L)
> **Prompt for Copilot:**
> *"Compare Ledger 0L (US GAAP) against Ledger 2L (IFRS) for Period 9 in Company 1000. List all differences and explain what adjustments exist in IFRS only."*
>
> **Expected Tools Called:** `compare_ledgers`, `get_document`  
> **Expected Result:** Identifies IFRS lease / parallel ledger adjustment entries.

---

### Test 3.3: Scan for Journal Posting Anomalies
> **Prompt for Copilot:**
> *"Run an anomaly scan on journal entries for Company 1000 for fiscal year 2026. Look for weekend postings, round amount transactions, and rare account usage."*
>
> **Expected Tools Called:** `scan_journal_anomalies`, `get_document`  
> **Expected Result:** Flags anomalous weekend or round-amount postings with rule scores and details.
