# Finance Twin Agent Platform: Agent Build Spec

Version 0.2 · October 6, 2026
Inputs: Phase 1 schema + Meridian Financial Group seed (client `200`) plus finance operations domain analysis.
Status tags: **[V]** verified against a primary source, **[S]** secondary or vendor source, **[D]** design decision (ours, change if you disagree), **[C]** confirm with domain expert before building.

---

## 1. Consolidated findings

### 1.1 The three problems, restated

| # | Problem | Why it costs money | Where the agent works |
|---|---|---|---|
| 1 | **Journal entry errors:** postings fail (closed period, blocked or reconciliation accounts, wrong currency, unbalanced) or land on the wrong account. Corrections require reversal + re-post, never deletion. | Finance teams spend 40–60% of close time on posting errors and corrections **[S]** (BlackLine 2024 Close Survey). Audit findings and restatement risk when errors reach the financial statements. | Draft balanced lines from plain language; diagnose failures with fix owner and valid alternative; create reversal + corrected re-post drafts. |
| 2 | **Duplicate payments:** duplicate vendor invoices lead to duplicate payments, direct cash leakage. Exact-match checks miss near-duplicates (typo in reference, ±3-day date shift, ±1% amount). Recovery requires knowing which copy was paid and which is still open. | Duplicate payments represent 0.1–0.5% of AP spend **[S]** (IOFM 2023 AP Fraud Study). Recovery is slow and depends on vendor cooperation. | Find candidate duplicates per vendor (exact and fuzzy); confirm paid vs open per document; total recoverable amount; list open items for affected vendors. |
| 3 | **Period-end delays:** before and during close, accountants manually review flux, accruals, ledger differences, and anomalous entries. Slow, error-prone, and exceptions are easy to miss under time pressure. | Average corporate close takes 6.4 days **[S]** (Hackett Group 2024 Finance Study). Undetected exceptions carry forward as misstatements. | Produce a review memo: biggest movers, accrual chain, ledger diff, anomalies — every exception citing a document number from a tool result. |

### 1.2 Market

- Finance automation is active. **BlackLine** (reconciliation, journal entry management), **Workiva** (close management), **HighRadius** (AR/AP AI), **Trintech** (close automation), **FloQast** (close checklist AI). All focus on productivity dashboards and reconciliation, not on an agent testing infrastructure. **[S]**
- Agentic AI in finance is emerging. JPMorgan DocLLM (document processing), Goldman Sachs GS AI platform, HSBC FX anomaly detection, Citi AI for trade finance. All are internal or early-access. **[S]**
- SAP Joule AI assistant is expanding from conversational Q&A into transaction processing. **[V]** (SAP TechEd 2025 announcement)
- No player offers a safe digital twin environment for agent development and testing against realistic ERP data. That is the gap this platform fills. **[D]**
- All performance claims (minutes saved, auto-clear rates) are marketing. Nothing here is a benchmark until we measure it on our twin.

### 1.3 Regulation that shapes the product

- **SOX Section 302/404:** CEO and CFO certify internal controls over financial reporting. AI agents writing journal entries are in scope. Every agent action must be traceable to an audit trail. **[V]**
- **Basel III/IV (BCBS 239):** risk data quality and aggregation requirements for banks. Automated entries must be traceable to source, validated, and reversible. **[V]**
- **IFRS 9 / ASC 842:** complex accounting standards requiring parallel ledger entries (IFRS `2L` vs US GAAP `0L`). Exactly what the twin models. **[V]**
- **MAS Technology Risk Management Guidelines (2021):** technology risk management for AI in banking for Meridian's India and Europe entities; requires human oversight of automated financial actions. **[V]**
- **Consequence for us:** we ship the audit artifacts (`tool_call_log`, `draft_entries`, `eval_scenarios`, `CLAUDE.md`, `verify_seed.sql`). These are product features, not paperwork. **[D]**
- Confirm with counsel which items map to which regulatory sections before making compliance claims to customers. **[C]**

### 1.4 Domain facts the agents depend on

- **Document key uniqueness:** `company_code + fiscal_year + document_number` (10-digit zero-padded TEXT). Document number alone is not unique — ranges reset per company and fiscal year. This is a deliberate agent trap. **[V]** (SAP BKPF primary key)
- **Reconciliation accounts:** a vendor invoice posts a vendor line + expense line. The vendor line lands on a reconciliation account (Trade Payables, flagged in `gl_account_company_settings`). Direct posting to that G/L is rejected by trigger. Sub-ledger always equals G/L balance. Agent must never attempt direct posting to a reconciliation account. **[V]**
- **Sign convention:** debit positive, credit negative, as stored in `amount_company_currency`. Every tool follows this. **[D]**
- **Period status:** periods 1–8 CLOSED, 9–12 OPEN as of October 2026, client `200`. **[V]** (seed data, `posting_period_controls`)
- **`created_at TIMESTAMPTZ`** is confirmed present on `journal_entry_headers` (DDL line 263). No migration needed for weekend or after-hours anomaly detection. **[V]**
- **Anomaly rules are rule-based** (`weekend_posting`, `round_amount`, `near_period_end`, `after_close`, `rare_account`, `unusual_creator`). The LLM interprets; it never computes the arithmetic. **[D]**
- The guide text (account master, period controls) changes. Control flags are live DB records, never hard-coded in agent logic. **[D]**

### 1.5 Integration facts (PostgreSQL first)

- PostgreSQL 16 with Phase 1 schema (`finacle_tables.sql`) is already loaded and all integrity checks pass. **[V]**
- Phase 1 includes: triggers (balance check, period check, reconciliation account guard, blocked account guard, immutability guards), views (`trial_balance()`, `journal_entries_flat`, `gl_account_period_balances`, `sap_compat.*`), 806 documents and 4,090 lines seeded.
- New tables required via migrations (not edits to Phase 1 DDL): `tool_call_log`, `draft_entries`, `eval_scenarios`. **[D]**
- DB roles: `twin_reader` (SELECT only on `finance.*`), `twin_writer` (INSERT on headers/lines/drafts, UPDATE only clearing and reversal fields). **[D]**
- MCP server: Python 3.11+ with FastMCP. psycopg3 for raw SQL (no ORM, so triggers and views stay in play). Pydantic for input/output schemas per tool. **[D]**
- MCP transport: stdio for local dev and evals. Streamable HTTP for multi-user or remote deployment. **[C]** Confirm before production deployment.
- Agent runtime: Claude (Anthropic SDK) — signalled by `CLAUDE.md` file naming convention. **[D]**
- A real SAP adapter can later implement the same 15 tools with the same contracts; agents change a server URL, not code. **[D]**

---

## 2. Product definition

**One platform, three agents, one finance twin state.**

| Agent | Trigger | Output | Human gate |
|---|---|---|---|
| **FA1 Journal Entry Assistant** | User provides a plain-language transaction, a failed posting error, or flags a suspected misposted line | Validated draft entry with trial balance impact, OR structured error diagnosis with fix owner and valid alternative | Approval Actor reviews and approves the pending draft before any INSERT into `journal_entry_headers` |
| **FA2 Payables Risk Agent** | Periodic or on-demand payables risk review for a company code | Duplicate report (document numbers, paid/open status, recoverable_amount) and open-item aging summary | Human must approve any payment block or reversal initiated |
| **FA3 Period-End Reviewer** | Period close workflow initiated, or ad-hoc period review request | Review memo with four checks: flux, accruals, ledger diff, anomalies — every exception cites a document number | Reviewer must act on flagged items; agent proposes only |

**Build order. [D]** Platform first, then FA1, FA2, FA3. FA1 has the cleanest, most deterministic rules (trigger errors are exact codes) and the sharpest ROI (posting failures have direct audit risk). FA2 reuses FA1's read tools and adds two analysis tools. FA3 requires all 15 tools and the most complex cross-source reasoning.

**What the agents never do.**
- Post journal entries without an approval step.
- Delete a posted document (SAP rule: corrections use `reverse_document`, never DELETE).
- Compute arithmetic — balances, ages, sums — themselves. Tools return those values.
- Strip zero-padding from document IDs. `'0000004001'` ≠ `'4001'`.
- Access another session's data or a company code outside their configured scope.
- Approve their own pending drafts.

---

## 3. Architecture

### 3.1 Principle: models read and draft, code decides

| Task type | Done by | Why |
|---|---|---|
| Classify intent, draft balanced lines from natural language, interpret anomaly flags, synthesize review memos | Agent (LLM), with structured output and Pydantic validation | Unstructured input; natural language |
| Balance checks, period validation, reconciliation account guard, duplicate matching algorithm, anomaly rule logic | Deterministic DB triggers and server-side tool logic | Must be exact, reproducible, and auditable |
| Whether a draft should be posted, whether a flagged entry is material | Agent proposes with evidence; human or harness decides | Judgment; agent cannot self-approve |

### 3.2 Components

```
PostgreSQL 16 (finance schema + tool_call_log + draft_entries + eval_scenarios)
    ^   twin_reader (SELECT) | twin_writer (validated INSERT)
    |
MCP Server (FastMCP, Python 3.11+, psycopg3, pydantic)
    ^  /mcp/finance  (twin:agent scope)   /mcp/control  (twin:control scope)
    |
Agent runtime (Claude, Anthropic SDK)       Eval harness (run_evals.py)
    |                                           |
    +------------ tool calls ----------------> MCP server
                                               |
                                        Approval Actor
                                        (harness auto-approve or human)
```

### 3.3 Core data model (additions to Phase 1)

```
tool_call_log   (call_id UUID PK, session_id TEXT, tool TEXT, input_json JSONB,
                 output_summary TEXT, error_code TEXT, duration_ms INT,
                 called_at TIMESTAMPTZ DEFAULT now(), traceparent TEXT)

draft_entries   (draft_id UUID PK, session_id TEXT, idempotency_key TEXT UNIQUE,
                 draft_type TEXT CHECK (draft_type IN ('post','reverse')),
                 status TEXT DEFAULT 'pending' CHECK (status IN ('pending','posted','rejected')),
                 payload_json JSONB, created_at TIMESTAMPTZ, approved_at TIMESTAMPTZ, approved_by TEXT)

eval_scenarios  (scenario_id TEXT PK, use_case TEXT, prompt TEXT,
                 expected_json JSONB, forbidden_json JSONB,
                 allowed_tools TEXT[], max_tool_calls INT DEFAULT 20)
```

### 3.4 Write-back contract (MCP → DB)

| Agent produces | Written to | Mode |
|---|---|---|
| Validated, balanced journal entry lines | `draft_entries` (status `pending`) via `post_journal_entry` | Harness or human must call `twin_approve_draft` |
| Reversal proposal | `draft_entries` (status `pending`, type `reverse`) via `reverse_document` | Same approval gate |
| Approved draft | `journal_entry_headers` + `journal_entry_lines` | Only the approval actor executes this INSERT |
| Tool call record | `tool_call_log` | Direct, on every call, before return |

Rules: idempotent writes keyed by `idempotency_key`. Never overwrite a field a human or trigger has protected. Respect immutability guards (posted lines cannot be deleted or updated outside clearing/reversal fields).

### 3.5 Model and extraction controls **[D]**

- Every tool output is JSON validated against a Pydantic schema. Invalid DB responses are caught and returned as `VALIDATION` errors before reaching the agent.
- `validate_journal_entry` runs inside a SAVEPOINT that always rolls back. It fires all Phase 1 triggers. It leaves zero rows. This is the agent's only safe way to test a posting before committing.
- Prompts, tool versions, and scenario IDs are recorded in `tool_call_log` on every call.
- Evaluation harness: scoring compares agent output against `eval_scenarios.expected_json`, a separate record created at seed time and never shown to the agent.

---

## 4. Agent specs

### 4.1 FA1: Journal Entry Assistant (build first)

**Trigger.** User provides a plain-language transaction description, a failed posting attempt with an error code, or flags a line suspected of being misposted.

**Workflow (state machine).**
`INTAKE → CLASSIFY_MODE → [PREPARE | DIAGNOSE | CORRECT] → VALIDATE → DRAFT → AWAIT_APPROVAL → DONE`
Any step can move to `NEEDS_HUMAN` with a reason code and evidence.

**Three modes.**

| Mode | Input | Agent action | Output |
|---|---|---|---|
| Prepare | Plain-language transaction | Draft balanced lines, call `validate_journal_entry`, call `post_journal_entry` | Pending draft + trial balance impact |
| Diagnose | Failed entry or error code | Call `lookup_master_data` and `get_period_status` to confirm the cause | Error code + fix owner + valid alternative account or period |
| Correct | Suspect misposted line | Call `get_account_usage_profile` for historical baseline; confirm proposed account via `lookup_master_data`; call `validate_journal_entry` on correction; create `reverse_document` draft + corrected `post_journal_entry` draft | Two pending drafts: reversal + re-post |

**Error taxonomy (encode as data in `errors.py`, never hard-coded in agent logic). [C]**

| Code | DB trigger condition | Fix owner | Valid alternative |
|---|---|---|---|
| `DOC_NOT_BALANCED` | Lines do not sum to zero in company currency at COMMIT | Agent | Re-balance lines; call `validate_journal_entry` again |
| `PERIOD_CLOSED` | `posting_date` maps to a closed period in `posting_period_controls` | Controller (open period) or Agent (use open period 9–12) | Re-post to next open period; or request period re-open |
| `ACCOUNT_BLOCKED` | `gl_account_company_settings.is_blocked = true` | Finance Admin (unblock in master data) | Use active G/L in same account group |
| `RECON_ACCOUNT_DIRECT_POSTING` | `reconciliation_account_type IS NOT NULL` and `is_system_generated = false` | Agent | Never post directly; post through vendor/customer sub-ledger document type |
| `CURRENCY_NOT_ALLOWED` | `gl_account_company_settings.allowed_currency` mismatch | Agent | Use the allowed currency; or use a different account |
| `ALREADY_REVERSED` | `reversed_by_document IS NOT NULL` | Agent | Cannot reverse again; open the reversal document instead |
| `DOC_NOT_FOUND` | No row for `(company_code, fiscal_year, document_number)` | Agent | Check zero-padding; confirm company code and fiscal year |

**Prepare mode worked example (build as acceptance test FA1-T1).**

User says: "Post a journal entry to accrue September payroll for Meridian Bank N.A."

1. Agent calls `get_period_status(company_code='1000', fiscal_year=2026, period=9)` → `{status: 'open'}`
2. Agent calls `lookup_master_data(object_type='gl_account', id='0000500000')` → Personnel Expense, not blocked, not reconciliation
3. Agent calls `lookup_master_data(object_type='gl_account', id='0000210000')` → Accrued Liabilities, not blocked, not reconciliation
4. Agent calls `validate_journal_entry(header={company_code:'1000', fiscal_year:2026, posting_date:'2026-09-30', currency:'USD', document_type:'SA', header_text:'Sep payroll accrual'}, lines=[{gl_account:'0000500000', debit_credit:'D', amount:2500000.00, cost_center:'HR001'}, {gl_account:'0000210000', debit_credit:'C', amount:-2500000.00}])` → `{valid: true, trial_balance_impact: [{account:'0000500000', change:+2500000}, {account:'0000210000', change:-2500000}]}`
5. Agent calls `post_journal_entry(same payload + idempotency_key='fa1-payroll-sep2026-1000')` → `{draft_id: 'DRF-0042', status: 'pending'}`
6. Harness calls `twin_approve_draft('DRF-0042')` → `journal_entry_headers` row created, document number assigned.

This worked example is unit test FA1-T1. Total cure arithmetic is done by the DB trigger (balance check) and the trial balance view, not by the LLM.

**Diagnose mode worked example (build as acceptance test FA1-T3).**

User says: "Why did posting to account 0000999999 fail?"

1. Agent calls `lookup_master_data(object_type='gl_account', id='0000999999')` → `{is_blocked: true, account_name: 'Legacy Suspense (Retired)'}`
2. Agent responds: "Error code `ACCOUNT_BLOCKED`. Account 0000999999 is a blocked legacy suspense account. Fix owner: Finance Admin — unblock via `gl_account_company_settings.is_blocked` or FS00 in SAP. Valid alternative: 0000210000 (Accrued Liabilities) for accruals, or 0000200099 (Clearing Account) for suspense items. Verify with `lookup_master_data` before posting."

Every number and account name in the response appears in a tool result.

**Acceptance tests.**

| ID | Given | Then |
|---|---|---|
| FA1-T1 | Plain-language payroll accrual for company 1000, period 9 | Balanced draft; correct accounts; trial balance impact stated; `status=pending`; harness approves successfully |
| FA1-T2 | `validate_journal_entry` with unbalanced lines (debit ≠ credit) | `DOC_NOT_BALANCED`; zero rows in `journal_entry_headers` or `journal_entry_lines` after return |
| FA1-T3 | Posting to account 0000999999 (blocked legacy account) | `ACCOUNT_BLOCKED` + fix owner (Finance Admin) + valid alternative account |
| FA1-T4 | Posting to period 8 (closed) for any company code | `PERIOD_CLOSED` + suggest period 9 or request period re-open |
| FA1-T5 | Direct posting to a reconciliation account (Trade Payables) | `RECON_ACCOUNT_DIRECT_POSTING`; agent explains to use vendor document type |
| FA1-T6 | Posting in EUR to an account restricted to USD | `CURRENCY_NOT_ALLOWED`; agent suggests correct currency or alternate account |
| FA1-T7 | Same `idempotency_key` submitted twice with identical payload | Second call returns original draft; no second row in `draft_entries` |
| FA1-T8 | Misposted expense line flagged by user | `get_account_usage_profile` shows correct historical account; proposed account not blocked; reversal + re-post drafts balance and pass `validate_journal_entry`; nothing posted without approval |

**Metrics.** Posting-error resolution rate; drafts that pass first-time approval; reversal + re-post pairs correct; `validate_journal_entry` call rate before `post_journal_entry` (target 100%); false error-code rate (target 0%).

---

### 4.2 FA2: Payables Risk Agent

**Trigger.** Periodic or on-demand payables risk review request for a company code, or a user flagging a suspected duplicate invoice.

**Workflow (state machine).**
`INTAKE → SCAN_EXACT → SCAN_FUZZY → FETCH_DOCUMENTS → CLASSIFY_STATUS → CALCULATE_EXPOSURE → GENERATE_REPORT → AWAIT_HUMAN`

**Inputs.** Company code, optional `as_of_date`, optional `vendor_id` to scope the review, `window_days` for the duplicate search window.

| Step | Detail |
|---|---|
| SCAN_EXACT | `find_duplicate_invoices(mode='exact')` — same vendor, same amount, same external reference |
| SCAN_FUZZY | `find_duplicate_invoices(mode='fuzzy', amount_tolerance_pct=1.0, window_days=30)` — catches typos in reference, date shifts, small amount variations |
| FETCH_DOCUMENTS | `get_document` on each candidate pair member to confirm header, lines, clearing status |
| CLASSIFY_STATUS | Open: `is_open_item=true` on vendor line; clearing_document is null. Paid: `clearing_document` is set. A document can be open with a cleared expense line — always check the vendor line. |
| CALCULATE_EXPOSURE | Recoverable amount = sum of open duplicates. Total open-item exposure = `list_open_items` for all affected vendors. |
| GENERATE_REPORT | Report cites document numbers, vendor, reference, amounts, paid/open status, recoverable amount, and aging. Every number from a tool result. |

**Decoy check.** Matching is per vendor. Same external reference across different vendor IDs is a decoy and must not be returned. Acceptance test FA2-T2 covers this explicitly.

**Stop condition.** If a fuzzy candidate pair has different vendor IDs, different company codes, or amounts differing by more than `amount_tolerance_pct`, exclude it and note the exclusion reason.

**Worked example (build as acceptance test FA2-T1).**

`find_duplicate_invoices(company_code='1000', mode='exact', window_days=90, amount_tolerance_pct=0)` returns:
```json
{"groups": [{"vendor_id": "V000123", "external_reference": "INV-2026-0891",
  "members": ["0000004001", "0000004042"], "amounts": [45000.00, 45000.00],
  "statuses": ["open", "paid"], "recoverable_amount": 45000.00}]}
```

Agent calls `get_document` on each member. Confirms 0000004001: vendor line `is_open_item=true`, `clearing_document=null` → open. Confirms 0000004042: vendor line `clearing_document='0000004099'` → paid 2026-08-15.

Report: "Exact duplicate: vendor V000123, reference INV-2026-0891. Document 0000004001 is open — block payment. Document 0000004042 was paid on 2026-08-15 — request refund or credit note. Recoverable amount: USD 45,000.00."

**Acceptance tests.**

| ID | Given | Then |
|---|---|---|
| FA2-T1 | Seed exact duplicate pair (1 open, 1 paid) | Correct document numbers, paid/open status, recoverable amount; matches `eval_scenarios.expected_json` |
| FA2-T2 | Seed decoy pairs (same reference, different vendors) | Zero decoy documents in any returned group |
| FA2-T3 | Fuzzy mode on seed | ≥ 5 of 6 seeded fuzzy pairs found (typo, date shift, ±1% amount) |
| FA2-T4 | `list_open_items(account_type='vendor', company_code='1000', as_of_date='2026-10-05')` | Returns 45 open vendor items; aging computed from posting date |
| FA2-T5 | Any `list_open_items` call | Output notes: "Age is posting-date based; payment terms not yet modelled in v0.1" |

**Metrics.** Exact duplicate detection rate; fuzzy pair recall (target ≥ 83%); false-positive rate on decoys (target 0%); recoverable amount accuracy (exact match to `expected_json`); aging accuracy.

---

### 4.3 FA3: Period-End Reviewer

**Trigger.** Period close workflow initiated for a company code and fiscal period, or an ad-hoc review request.

**Workflow (state machine).**
`INTAKE → FLUX_ANALYSIS → ACCRUAL_REVIEW → LEDGER_DIFF → ANOMALY_SCAN → SYNTHESIZE_MEMO → DONE`

**Inputs.** Company code, fiscal year, period (current), optional compare_period (prior period for flux), optional ledger (default `0L`).

| Step | Detail |
|---|---|
| FLUX_ANALYSIS | `get_period_summary(group_by='account')` and `get_period_summary(group_by='cost_center')` current vs prior. Rank by absolute delta. Drill into biggest movers with `get_account_line_items`. |
| ACCRUAL_REVIEW | `search_documents(document_type='AB', date_range=period)` to find accrual entries. For each, `get_document` to follow reversal links (`reverses_document`, `reversed_by_document`). Compare accrual amounts to expected values in `eval_scenarios`. State net effect of reversal + re-post chain. |
| LEDGER_DIFF | `compare_ledgers(ledger_a='0L', ledger_b='2L')`. `get_document` on each difference. State the IFRS or GAAP reason for each. |
| ANOMALY_SCAN | `scan_journal_anomalies(rules=['weekend_posting','round_amount','near_period_end','after_close','rare_account','unusual_creator'])`. `get_document` on each flagged item. Distinguish flagged from benign look-alikes in the memo. |
| SYNTHESIZE_MEMO | Produce a structured memo with four sections. Every exception cites a document number from a tool result. Where data gives no driver for a movement, state "driver unknown". No invented numbers. |

**Hard rules.**
- Every number in the memo must appear verbatim in a tool output for that session.
- Where the data gives no reason for a movement, the memo must say "driver unknown", not invent one.
- `scan_journal_anomalies` rules are rule-based; the LLM interprets the flagged set but must not compute ages, sums, or percentages itself.
- No write tools may be called during a period review. The memo is read-only output.

**Acceptance tests.**

| ID | Given | Then |
|---|---|---|
| FA3-T1 | `get_trial_balance` for any company and ledger in seed | Total debits equal total credits; last running total from `get_account_line_items` matches trial balance figure for same period |
| FA3-T2 | Seed contains a cost-center expense spike (period 9 vs 8, injected in UC3 seed) | Spike detected and ranked in flux section; benign stable accounts not flagged |
| FA3-T3 | Seed contains 2 overstated accruals with reversal + re-post chains | Accruals found via `search_documents`; reversal links confirmed via `get_document`; net effect stated correctly |
| FA3-T4 | `compare_ledgers('0L','2L')` on seed | IFRS-only adjustments appear; documents posted only to `0L` do not appear as `2L` differences |
| FA3-T5 | Seed contains injected anomalies (2 per rule, 12 total) and 5 benign look-alikes | All 6 rule types fire on injected entries; 5 benign look-alikes produce zero flags |
| FA3-T6 | Complete period memo | Every number in the memo appears in a tool result for that session; no amount is invented |

**Metrics.** Injected exception detection rate; false-positive rate on benign look-alikes (target 0%); memo completeness (all 4 sections present); invented-number rate (target 0%); "driver unknown" used correctly where applicable.

---

## 5. Governance features (ship with v0.1)

Because SOX, Basel III/IV, and MAS TRM push AI governance onto institutions and their vendors, the platform ships these artifacts as features:

| Feature | Purpose |
|---|---|
| `tool_call_log` (immutable) | Reconstruct any agent action: tool name, inputs, outputs, error code, duration, timestamp, traceparent. Exportable per session. |
| `draft_entries` audit trail | Every proposed write with payload, status history, approved_by, and approved_at. The agent never directly modifies this after creation. |
| `eval_scenarios` with expected_json | Versioned ground truth. Scoring is reproducible and independent of the agent. |
| `CLAUDE.md` | Agent orientation file: read spec first, never bypass approval, never delete a document, never compute arithmetic. |
| DB template reset + `verify_seed.sql` | Reproducible experiments. Same state in under 60 seconds. Integrity checks on every reset (trial balance, reversal links, tax ties). |
| Session export | `twin_export_log` returns the full `tool_call_log` for a session as JSON for external audit. |

Confirm with counsel which items map to which sections of SOX, Basel, and MAS TRM before making any compliance claim to customers. **[C]**

---

## 6. Non-functional requirements

| Area | Target **[D]** |
|---|---|
| FA1 validate + draft | Under 30 seconds end-to-end |
| FA2 full duplicate scan (45 open items) | Under 2 minutes |
| FA3 period review memo (one company code, one period) | Under 5 minutes |
| DB reset | Under 60 seconds from template |
| Determinism | Same seed + same agent actions → identical `tool_call_log` hash |
| Eval suite pass rate | ≥ 80% across 3 use cases × ≥ 5 scenarios each |
| Tool error rate from unknown inputs | 0 (every possible failure is in the error taxonomy) |
| Hallucinated numbers in agent answers | 0 across the full eval suite |
| Write actions without approval | 0 |
| Observability | `traceparent` from client on every `tool_call_log` row; per-session log queryable |

---

## 7. Delivery plan

Team of 2: 1 backend engineer, 1 finance domain expert. **[D]**

| Phase | Weeks | Deliverable | Exit test |
|---|---|---|---|
| M0 | 1–2 | Repo skeleton, Docker Compose, DB roles (`twin_reader`, `twin_writer`), new tables (`tool_call_log`, `draft_entries`, `eval_scenarios`), template DB + reset script, eval harness skeleton (`run_evals.py`) | Reset runs in under 60 s; `twin_reader` cannot INSERT; eval harness runs with 0 scenarios |
| M1 | 3–7 | FA1: all 8 read/write tools, approval step, UC1 seed (8 failing inputs + 8–10 misposted lines + 5 plain-language transactions), ≥ 5 eval scenarios | FA1-T1 through FA1-T8 pass; `validate_journal_entry` leaves zero rows; UC1 pass rate ≥ 80% |
| M2 | 8–10 | FA2: `list_open_items`, `find_duplicate_invoices`; UC2 seed (6 fuzzy pairs + 4 decoy pairs); ≥ 5 eval scenarios | FA2-T1 through FA2-T5 pass; exact pairs found; decoys not returned; ≥ 5 of 6 fuzzy pairs found |
| M3 | 11–14 | FA3: `get_trial_balance`, `get_account_line_items`, `get_period_summary`, `compare_ledgers`, `scan_journal_anomalies`; UC3 seed (anomalies, spikes, accruals); ≥ 5 eval scenarios | FA3-T1 through FA3-T6 pass; injected exceptions found; benign look-alikes not flagged |
| M4 | 15–16 | Tune tool descriptions, error messages, and gaps found by evals; fault injection; update `CLAUDE.md`; final eval run | All success metrics in Section 6 met; ≥ 80% pass rate across full suite |

**Pilot design.** Run the full eval suite against the twin on every milestone. Capture the baseline pass rate before any tuning. Do not tune the seed data to make the agent pass — add scenarios and fix tool bugs. Report scores as "rule adherence and failure handling", never as expected production accuracy.

---

## 8. Open items

1. **Claude model for evals:** `claude-sonnet-4-5` (fast, most scenarios) vs `claude-opus-4` (hard UC3 multi-source reasoning). Recommend sonnet for M1–M2, opus for UC3 and the held-out set. **[C]**
2. **MCP transport for multi-user production:** stdio sufficient for single-evaluator runs; streamable HTTP for shared access or CI. Decide before M2 so server config is final. **[C]**
3. **Payment terms:** posting-date aging confirmed for v0.1. `list_open_items` output must include the note "payment terms not modelled". Due-date aging deferred to Phase 2 when `payment_terms` table is added. **[D]**
4. **Anomaly thresholds:** `rare_account` = account used in < 2% of company postings; `unusual_creator` = creator with < 5 documents in the company. Tune after first M3 eval run. **[D]**
5. **Multi-company scope:** single company code per session (passed in server config) for v0.1, or can the agent span all four Meridian entities? Single-company scope for now. **[D]**
6. **UC3 IFRS seed volume:** 3–4 IFRS-only (`2L`) adjustments confirmed sufficient for the ledger diff test. Confirm count with finance domain expert before M3 seeding. **[C]**
7. **Harness approval mode:** auto-approve all pending drafts after the agent run (default), or selective (`--no-approve` flag for read-only UC2/UC3 eval runs). **[D]**

---

## Sources

- Model Context Protocol specification, 2026-07-28 (modelcontextprotocol.io) **[V]**
- SAP S/4HANA Finance documentation: BKPF journal entry header, ACDOCA Universal Journal, BAPI_ACC_DOCUMENT_POST, FB03, FAGLB03, FBL1N, FS00 (help.sap.com) **[V]**
- FastMCP Python SDK (github.com/jlowin/fastmcp)
- PostgreSQL 16 documentation — triggers, row-level security, template databases (postgresql.org)
- `finacle_tables.sql` — Phase 1 DDL with triggers and views, loaded and verified **[V]**
- `finance_seed_data.sql` — Meridian Financial Group synthetic seed, client `200`, 806 documents **[V]**
- `finance_digital_twin_documentation.md` — Phase 1 design rationale and integrity verification results **[V]**
- BlackLine 2024 Finance Close Survey, finance team productivity benchmarks **[S]**
- IOFM 2023 AP Fraud and Duplicate Payment Study **[S]**
- Hackett Group 2024 Finance Benchmarks, corporate close cycle time **[S]**
- JPMorgan DocLLM research paper, 2024 **[S]**
- SAP TechEd 2025: Joule AI assistant expansion announcements **[S]**
- SOX Section 302 and 404, PCAOB AS 2201 (internal controls over financial reporting) **[V]**
- Basel III/IV risk data aggregation principles (BCBS 239) **[V]**
- IFRS 9 Financial Instruments and ASC 842 Leases standards **[V]**
- MAS Technology Risk Management Guidelines 2021 **[V]**
- BlackLine, Workiva, HighRadius, Trintech, FloQast — product documentation (secondary, unverified claims) **[S]**
