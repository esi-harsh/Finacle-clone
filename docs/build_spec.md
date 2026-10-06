---

## title: Finance Twin Agent Platform: Build Spec status: draft version: 0.2 date: 2026-10-05

# Finance Twin Agent Platform: Build Spec

Builds on `finance_digital_twin_documentation.md` (Phase 1 schema + client `200` "Meridian Financial Group" seed). This spec covers **what to build** (MCP server, seed additions, eval harness) and **how to build it**.

## 1. Summary

Expose the finance twin to an AI agent through an **MCP server of 15 tools**, extend the seed data with **scenarios that have known answers**, and add an **eval harness** that scores the agent on **3 core use cases**. The agent reads freely, and writes only through validated, approval-gated tools.

## 2. Goals, non-goals, success metrics

**Goals**

1. Agent can complete the 3 core use cases (Section 8) using only the tools below.
2. Every use case has seeded data and an expected answer, so results are scorable.
3. Experiments are repeatable: reset to the same state in under 60 seconds.
4. Every tool call is logged for tracing and evaluation.

**Non-goals (v0.1)**

- Phase 2+ modules (business partners, payment runs, assets, intercompany, consolidation).
- Real SAP connectivity. Tool names and errors mirror SAP, but nothing connects to it.
- A UI. The harness runs from CLI.
- Autonomous posting without approval.

**Success metrics**

| Metric | Target |
| --- | --- |
| Use-case pass rate on the eval suite | ≥ 80% (3 use cases × ≥ 5 scenarios each) |
| Tool error rate from bad inputs the agent could not have known | 0 |
| Hallucinated document numbers or amounts in answers | 0 across the suite |
| Write actions executed without approval | 0 |
| DB reset time | \< 60 s |

## 3. Architecture

```
Agent (LLM client)
      │  MCP (stdio or streamable HTTP)
      ▼
MCP server (Python)  ── validates input ── logs call ──┐
      │                                                │
      ├─ reader pool  (role: twin_reader, SELECT only) │
      └─ writer pool  (role: twin_writer, validated)   ▼
                       PostgreSQL 16 ◄──── finance schema + tool_call_log + draft_entries
Eval harness ── runs scenarios ── reads tool_call_log ── scores
```

## 4. Tech stack and decisions

| Area | Choice | Reason |
| --- | --- | --- |
| Database | PostgreSQL 16, existing `finance` schema | Already loaded and verified |
| Server | Python 3.11+, MCP Python SDK (FastMCP) | Fastest path to a spec-compliant MCP server |
| DB access | `psycopg` 3 with connection pools, raw SQL | Keeps triggers and views in play; no ORM hiding behaviour |
| Validation | `pydantic` models per tool | Input and output schemas double as tool definitions |
| Tests | `pytest` + a throwaway template database | Reset by cloning the template |
| Packaging | Docker Compose (db + server) | One command to start |
| Config | `.env` for DSNs, row limits, approval mode | No secrets in code |

**Roles:** `twin_reader` has SELECT on `finance.*` only. `twin_writer` can INSERT headers, lines and drafts, and UPDATE only the clearing and reversal fields (the existing triggers already enforce this). Read tools must never use the writer pool.

## 5. Repo layout

```
finance-twin/
├── CLAUDE.md                     # orientation: read specs first, never bypass approval
├── docs/
│   ├── finance_digital_twin_documentation.md
│   └── spec.md                   # this file
├── db/
│   ├── finance_twin_phase1.sql   # existing
│   ├── seed_200.sql              # existing
│   ├── migrations/               # new tables, roles, scenario seeds
│   └── verify_seed.sql           # existing + new checks
├── server/
│   ├── main.py                   # MCP entry point
│   ├── tools/                    # one module per tool group
│   ├── models.py                 # pydantic input/output
│   ├── errors.py                 # SAP-style error mapping
│   └── logging.py                # tool_call_log writer
├── evals/
│   ├── scenarios/*.yaml          # prompt + expected answer + allowed tools
│   └── run_evals.py
└── tests/                        # unit tests per tool
```

## 6. Cross-cutting rules (apply to every tool)

1. **Defaults:** ledger `0L`, client from server config (not passed by the agent).
2. **Keys:** documents are always identified by `company_code + fiscal_year + document_number` (10-digit zero-padded text). Reject partial keys with a clear error.
3. **Sign convention:** debit positive, credit negative, as in `journal_entry_lines`.
4. **Pagination:** default 50 rows, max 200. Every list result returns `total_count`, `next_cursor`, and `truncated` (bool).
5. **Errors:** return `{code, message, details}`. DB trigger failures map to stable codes, for example `PERIOD_CLOSED`, `ACCOUNT_BLOCKED`, `RECON_ACCOUNT_DIRECT_POSTING`, `DOC_NOT_BALANCED`, `CURRENCY_NOT_ALLOWED`. Messages keep the SAP-style wording from the Phase 1 triggers.
6. **Logging:** every call writes `tool_call_log(call_id, session_id, tool, input_json, output_summary, error_code, duration_ms, called_at)`.
7. **Descriptions:** each tool description names both worlds, for example "gl_account (SAP: RACCT)".
8. **Approval:** `post_journal_entry` and `reverse_document` create a row in `draft_entries` with status `pending`. Only an approval call from the harness or a human moves it to `posted`. The agent cannot approve.
9. **Determinism:** helper tools (duplicates, anomalies) are rule-based and return the rule that fired. The LLM interprets; it does not do the arithmetic.

## 7. Tool specifications

### 7.1 Lookup

| Tool | Inputs | Output | Acceptance criteria |
| --- | --- | --- | --- |
| `get_document` | company_code, fiscal_year, document_number | header, lines, tax lines, clearing and reversal links | Unknown key returns `DOC_NOT_FOUND`. Reversed documents show both link directions. |
| `search_documents` | optional: date range, document_type, created_by, gl_account, vendor_id, external_reference, amount_min/max, text, ledger, company_code | paged document list | At least one filter required. Results come from `journal_entries_flat`. |
| `lookup_master_data` | object_type (gl_account, cost_center, profit_center, document_type, company_code), id or search text | record + control flags | Returns blocked, reconciliation, open-item managed and allowed-currency flags for accounts. |
| `get_period_status` | company_code, fiscal_year, period | open or closed | Matches `posting_period_controls` (periods 1–8 closed, 9–12 open in seed). |

### 7.2 Balances and reports

| Tool | Inputs | Output | Acceptance criteria |
| --- | --- | --- | --- |
| `get_trial_balance` | company_code, fiscal_year, period, optional ledger, optional compare_period | per-account debit, credit, balance, abnormal_flag, optional prior balance | Sums to zero per company and ledger. Abnormal flag = balance on the wrong side for the account type. |
| `get_account_line_items` | company_code, gl_account, period range, optional ledger | paged lines with running total | Last running total equals the trial balance figure for the same period. |
| `get_period_summary` | company_code, group_by (account, cost_center, profit_center), period range | totals per group per period, with prior period | Server-side aggregation; never returns raw lines. |
| `list_open_items` | account_type (vendor or customer), company_code, optional vendor_id, as_of_date | open lines with age_days | Seed returns 45 open vendor items as of 2026-10-05. Age is from posting date (payment terms are not modelled yet). |
| `compare_ledgers` | company_code, fiscal_year, period, ledger_a, ledger_b | rows present or different in only one ledger | Seed returns exactly the IFRS-only adjustment (until new ones are added). |

### 7.3 Analysis helpers

| Tool | Inputs | Output | Acceptance criteria |
| --- | --- | --- | --- |
| `find_duplicate_invoices` | company_code, mode (exact or fuzzy), window_days, amount_tolerance_pct | candidate groups: members, vendor, amounts, paid or open per member, recoverable_amount | Matching is **per vendor**. Seed exact pairs found: one open, one paid twice. Decoys (same reference, different vendors) are not returned. |
| `scan_journal_anomalies` | company_code, date range, rules (list) | flagged documents with rule and score | Rules: `weekend_posting`, `round_amount`, `near_period_end`, `after_close`, `rare_account`, `unusual_creator`. Each flag names its rule. |
| `get_account_usage_profile` | one of vendor_id, text_pattern, cost_center; company_code | accounts used with counts and share | Used as the baseline for misposting checks. |

### 7.4 Validation and write

| Tool | Inputs | Output | Acceptance criteria |
| --- | --- | --- | --- |
| `validate_journal_entry` | header fields + lines | ok, or list of errors; on ok, trial balance impact by account | Runs in a transaction that always rolls back. Fires all Phase 1 triggers. Leaves no rows. |
| `post_journal_entry` | same as validate + `idempotency_key` | draft_id, status `pending` | Validates first. Same idempotency key never creates two drafts. |
| `reverse_document` | document key, reversal_date, reason | draft_id, status `pending` | Rejects already-reversed, cleared items, and closed periods (unless a later open date is given). On approval creates the reversal, with links in both directions. |

## 8. Core use cases (3)

The earlier list of 8 was consolidated into 3 that are common in real finance operations, have a clear cost when they go wrong, and need the agent to reason across data rather than run one report. The remaining ideas are listed as later extensions at the end of this section.

### UC1. Journal entry assistant: prepare, diagnose, correct

*Merges: posting failure diagnosis, prepare/validate/reverse, wrong account detection.*

**Real-world problem:** Manual journal entries are error-prone. Postings get rejected (closed period, blocked or reconciliation account, currency restriction, unbalanced), amounts land on the wrong account, and corrections must go through reversal and re-posting, never deletion.

**Three modes**

1. **Prepare:** from a plain-language transaction, draft balanced lines, validate, show trial balance impact, submit as a pending draft.
2. **Diagnose:** given a failed entry or error, explain the cause, who can fix it, and a valid alternative (account or period).
3. **Correct:** given a suspect line, compare against historical account usage, confirm the proposed account is valid, then create a reversal draft plus a corrected re-post draft.

**Tools:** `lookup_master_data`, `get_period_status`, `get_account_usage_profile`, `search_documents`, `get_document`, `validate_journal_entry`, `post_journal_entry`, `reverse_document`.

**Pass criteria**

- Correct error code, fix owner and valid alternative for each failing input.
- Drafts balance and pass validation; trial balance impact is stated.
- Misposted lines are found with the seeded correct account, and the proposed account is not blocked.
- Reversal and re-post drafts are correct; nothing is posted without approval.

### UC2. Payables risk review: duplicate invoices and open items

*Merges: duplicate invoice and payment detection, unpaid invoice exposure.*

**Real-world problem:** Duplicate vendor invoices lead to duplicate payments, which is direct cash leakage. Standard checks catch exact matches only, so near-duplicates slip through, and recovery depends on knowing which duplicate was paid and which is still open.

**Flow:** find candidate duplicates per vendor (exact and fuzzy), open each document to confirm, split into *open* (block payment, reverse the invoice via UC1) and *paid* (request refund or credit note), total the recoverable amount, and list open items for the affected vendors to show exposure.

**Tools:** `find_duplicate_invoices`, `get_document`, `list_open_items`, `search_documents`.

**Pass criteria**

- Exact document numbers, paid vs open status, and recoverable amount are correct.
- At least 5 of 6 fuzzy pairs found; zero decoys (same reference, different vendors) reported.
- Aging is labelled as posting-date based until payment terms exist.

### UC3. Period-end review and exception investigation

*Merges: month-end flux analysis, accrual investigation, ledger reconciliation, journal entry testing.*

**Real-world problem:** Before and during close, accountants review what moved, whether accruals are right, whether the two ledgers differ, and whether any entries look unusual. It is slow, manual, and exceptions are easy to miss.

**Flow:** produce a review memo for one company code and period with four checks. Each exception cites document numbers.

1. **Flux:** biggest movers vs prior period by account and cost center, with drill-down.
2. **Accruals:** compare accrual amounts to expected values; follow reversal and re-post chains; state net effect.
3. **Ledgers:** list items present or different between `0L` and `2L`, with the reason.
4. **Anomalies:** weekend postings, round amounts, near or after close, rare accounts, unusual creators.

**Tools:** `get_trial_balance`, `get_period_summary`, `get_account_line_items`, `compare_ledgers`, `scan_journal_anomalies`, `search_documents`, `get_document`, `get_period_status`.

**Pass criteria**

- Injected exceptions are found and ranked sensibly; benign look-alikes are not flagged.
- Every number in the memo appears in a tool result.
- Where the data gives no reason for a movement, the memo says "driver unknown".

### Later extensions (not in v0.1)

Bank reconciliation (needs bank statement data), intercompany reconciliation, due-date aging and cash forecasting (needs payment terms), unrealized FX and period-close checklist (Phase 3), tax reconciliation.

## 9. Data additions (seed v2)

New tables (via migration): `tool_call_log`, `draft_entries`, `eval_scenarios`.

**Schema check first:** weekend and after-hours tests need a posting timestamp. If `journal_entry_headers` has no `created_at`, add it (`TIMESTAMPTZ`) and backfill. Confirm `created_by` has several distinct users.

| UC | Scenario seed | Volume | Purpose |
| --- | --- | --- | --- |
| 1 | Failing entries (unbalanced, blocked account, closed period, reconciliation account, wrong currency) | 8 inputs | Diagnose mode |
| 1 | Misposted lines with a known correct account | 8–10 | Correct mode |
| 1 | Plain-language transactions to draft (loan fee, payroll accrual, vendor invoice) | 5 | Prepare mode |
| 2 | Fuzzy duplicates (typo in reference, shifted date, amount ±1%) | 6 pairs | Near-duplicate detection |
| 2 | Duplicate decoys (same reference, different vendors) | 4 pairs | False-positive test |
| 3 | Extra IFRS-only or GAAP-only adjustments | 3–4 | Ledger check |
| 3 | Anomalous entries (weekend, round amount, post-close, rare account, odd creator) | 2 per rule | Anomaly check |
| 3 | Benign look-alikes (for example legitimate round-amount payroll) | 5 | False-positive test |
| 3 | Cost center and account spikes; 2 extra overstated accruals | 4 + 2 | Flux and accrual checks |

Rules: new data uses client `200` with non-overlapping number ranges, passes every `verify_seed.sql` check, and each seeded item is recorded in `eval_scenarios` with its expected answer. The generator (`generate_seed.py`) stays deterministic.

## 10. Eval harness

- **Scenario file:** `id`, `use_case`, `prompt`, `expected` (facts to find), `forbidden` (things that must not appear, such as decoy documents), `allowed_tools`, `max_tool_calls`.
- **Run:** reset DB from template → run agent with the MCP server → collect final answer and `tool_call_log` for the session.
- **Scoring:** (a) correctness of facts against `expected`, (b) no `forbidden` items, (c) tool trajectory reasonable (no needless calls, no write tools on read tasks), (d) no invented numbers (every number in the answer must appear in tool outputs), (e) approval rule respected.
- **Output:** per-scenario pass or fail with reasons, plus a summary table by use case.

## 11. Build plan

Built as vertical slices: each use case ships with its tools, seed data and evals, so there is a working, testable result after every milestone.

| Milestone | Deliverable | Done when |
| --- | --- | --- |
| M0 Setup | Repo, Docker Compose, roles, `tool_call_log`, template DB and reset script, eval harness skeleton | Reset runs in under 60 s; reader role cannot write |
| M1 UC1 slice | `get_document`, `lookup_master_data`, `get_period_status`, `search_documents`, `get_account_usage_profile`, `validate_journal_entry`, `post_journal_entry`, `reverse_document`, approval step; UC1 seed and ≥ 5 eval scenarios | All 8 failing inputs return the correct code; validate leaves no rows; UC1 pass criteria met |
| M2 UC2 slice | `list_open_items`, `find_duplicate_invoices`; UC2 seed and ≥ 5 eval scenarios | Known exact pairs found; decoys not returned; ≥ 5 of 6 fuzzy pairs found |
| M3 UC3 slice | `get_trial_balance`, `get_account_line_items`, `get_period_summary`, `compare_ledgers`, `scan_journal_anomalies`; UC3 seed and ≥ 5 eval scenarios | Trial balance and line-item totals agree; injected exceptions found; benign ones not flagged |
| M4 Tune | Fix tool descriptions, error messages and gaps found by evals | Success metrics in Section 2 met |

Inside M1, build in this order: `get_document`, `lookup_master_data`, `get_period_status`, `validate_journal_entry`, then the rest.

## 12. What NOT to do

- Do not let the agent write SQL. Tools only.
- Do not give read tools the writer connection.
- Do not return unbounded result sets; aggregate on the server.
- Do not strip zero-padding from IDs; the join pitfall is intentional.
- Do not let the LLM compute sums or ages; tools return them.
- Do not tune the seed to make the agent pass. Add scenarios, not hints.
- Do not edit `finance_twin_phase1.sql` triggers to make an error friendlier; map errors in `errors.py`.

## 13. Open questions

| Date | Question | Blocks |
| --- | --- | --- |
| 2026-10-05 | Does `journal_entry_headers` already have a creation timestamp? | Anomaly rules, seed v2 |
| 2026-10-05 | Which agent client runs the evals (and which model)? | M5 |
| 2026-10-05 | MCP transport: stdio (simple) or streamable HTTP (remote)? | M0 |
| 2026-10-05 | Who approves drafts in tests: harness auto-approve or a manual step? | M3 |
| 2026-10-05 | Add payment terms now so aging uses due date, or keep posting-date aging for v0.1? | Tool 7.2 `list_open_items` |

## 14. Definition of done (v0.1)

- All 15 tools implemented, documented, and covered by unit tests.
- Seed v2 loaded, verified, and recorded in `eval_scenarios`.
- Eval suite meets the Section 2 targets.
- Every tool call is traceable in `tool_call_log`.
- `CLAUDE.md` and this spec are up to date with any decisions made during the build.

## Changelog

- **v0.2 (2026-10-05):** consolidated the 8 use cases into 3 core use cases (Section 8); seed volumes, eval scope and build plan reorganised around them (vertical slices). Tool set (15) unchanged.
- **v0.1 (2026-10-05):** initial draft.