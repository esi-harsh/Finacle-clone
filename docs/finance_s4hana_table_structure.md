# Finance & Accounting Digital Twin
## S/4HANA-Style Table Structure — Tables, Examples and Relationships

> This document explains the Phase 1 table structure of the Finance & Accounting Digital Twin using the S/4HANA-style Universal Journal approach. Names are intentionally readable rather than SAP abbreviations, while the documentation maintains SAP mappings for traceability.

---

## 1. Architecture Overview

The model follows the S/4HANA pattern:

```text
Client
 ├── Company Code
 │    ├── G/L Account Settings
 │    ├── Posting Controls
 │    └── Journal Entries
 │         ├── Header
 │         └── Universal Journal Lines
 │
 ├── Chart of Accounts
 │    └── G/L Accounts
 │
 ├── Controlling Area
 │    ├── Cost Centers
 │    └── Profit Centers
 │
 └── Ledger
      └── Journal Entry Lines
```

The central transaction table is:

```text
journal_entry_headers
        |
        | 1 : many
        v
journal_entry_lines
```

`journal_entry_lines` represents the S/4HANA-style **Universal Journal (ACDOCA)** concept. Reports such as trial balance are generated from these line items.

---

# 2. Foundation Tables

## 2.1 `clients`

### SAP Equivalent
`T000`

### Purpose
Represents the top-level tenant/client. It isolates multiple independent synthetic business environments inside one database.

### Important Fields

| Field | Meaning |
|---|---|
| `client_id` | Unique client/tenant identifier |
| `name` | Client name |
| `description` | Description |
| `is_active` | Whether the client is active |

### Example

| client_id | name | is_active |
|---|---|---|
| 200 | Meridian Financial Group | true |

### Relationship

```text
clients
   ├── company_codes
   ├── charts_of_accounts
   ├── ledgers
   ├── controlling_areas
   ├── document_types
   └── posting_keys
```

---

## 2.2 `currencies`

### SAP Equivalent
`TCURC`

### Purpose
Stores valid currencies and their decimal precision.

### Example

| currency_code | name | decimals |
|---|---|---:|
| USD | US Dollar | 2 |
| EUR | Euro | 2 |
| INR | Indian Rupee | 2 |
| JPY | Japanese Yen | 0 |

### Used By

`exchange_rates`, `company_codes`, and journal entries.

---

## 2.3 `exchange_rates`

### SAP Equivalent
`TCURR`

### Purpose
Stores currency conversion rates by date.

### Example

| client_id | rate_date | from | to | rate |
|---|---|---|---|---:|
| 200 | 2026-10-01 | USD | INR | 88.20 |
| 200 | 2026-10-01 | EUR | USD | 1.17 |

### Example Use

A EUR 10,000 invoice can be converted to USD using the rate applicable on the transaction date.

---

# 3. Organization Structure

## 3.1 `charts_of_accounts`

### SAP Equivalent
`T004`

### Purpose
Defines the shared list of G/L accounts used by one or more company codes.

### Example

| chart_id | client_id | code | name |
|---|---|---|---|
| COA100 | 200 | MFG1 | Meridian Group Chart |

### Relationship

```text
charts_of_accounts
        |
        +---- gl_accounts
        |
        +---- company_codes
```

---

## 3.2 `fiscal_year_variants`

### SAP Equivalent
`T009`

### Purpose
Defines the fiscal calendar and number of posting periods.

### Example

| variant | client_id | periods | calendar_year |
|---|---|---:|---|
| K4 | 200 | 12 | true |

For this Phase 1 model:

```text
Period 1 = January
Period 2 = February
...
Period 12 = December
```

---

## 3.3 `ledgers`

### SAP Equivalent
`FINSC_LEDGER`

### Purpose
Represents parallel accounting books.

For example:

```text
0L = US GAAP
2L = IFRS
```

### Example

| ledger | client_id | name | leading |
|---|---|---|---|
| 0L | 200 | US GAAP | true |
| 2L | 200 | IFRS | false |

### Why It Matters

The same business event can have different accounting treatment under different accounting standards.

---

## 3.4 `company_codes`

### SAP Equivalent
`T001`

### Purpose
Represents a legal entity that maintains its own books, currency and fiscal calendar.

### Example

| company_code | name | currency | chart |
|---|---|---|---|
| 1000 | Meridian Bank N.A. | USD | MFG1 |
| 3000 | Meridian Bank Europe S.A. | EUR | MFG1 |
| 4000 | Meridian Bank India Pvt Ltd | INR | MFG1 |

### Important Concept

A company code is the main legal accounting unit.

```text
Company Code 4000
      |
      ├── INR
      ├── Balance Sheet
      ├── P&L
      └── Journal Entries
```

---

## 3.5 `controlling_areas`

### SAP Equivalent
`TKA01`

### Purpose
Defines the management-accounting scope used for internal cost and profit reporting.

### Example

| controlling_area | client_id | name |
|---|---|---|
| A000 | 200 | Meridian Management Accounting |

---

## 3.6 `company_code_controlling_areas`

### Purpose
Connects company codes to controlling areas.

### Example

| company_code | controlling_area |
|---|---|
| 1000 | A000 |
| 2000 | A000 |
| 3000 | A000 |
| 4000 | A000 |

### Relationship

```text
company_codes
      |
      v
company_code_controlling_areas
      |
      v
controlling_areas
```

---

# 4. G/L Account Master

## 4.1 `gl_accounts`

### SAP Equivalent
`SKA1`

### Purpose
Defines the G/L account itself at chart-of-accounts level.

### Example

| gl_account | name | account_group | type |
|---|---|---|---|
| 0000100000 | Cash | CASH | Balance Sheet |
| 0000200000 | Loans | LOAN | Balance Sheet |
| 0000400000 | Interest Income | REV | P&L |
| 0000500000 | Personnel Expense | EXP | P&L |

### Important

This table defines **what the account is**.

---

## 4.2 `gl_account_texts`

### SAP Equivalent
`SKAT`

### Purpose
Stores language-specific descriptions of G/L accounts.

### Example

| gl_account | language | name |
|---|---|---|
| 0000100000 | EN | Cash |
| 0000100000 | DE | Kasse |

### Why Separate It?

The account remains the same while its description can change by language.

---

## 4.3 `gl_account_company_settings`

### SAP Equivalent
`SKB1`

### Purpose
Controls how a G/L account behaves inside a particular company code.

### Example

| company_code | gl_account | open_item | blocked | reconciliation |
|---|---|---|---|---|
| 4000 | 0000300000 | true | false | true |
| 4000 | 0000400000 | false | false | false |

### Important Difference

```text
gl_accounts
    = What is this account?

gl_account_company_settings
    = How does this account behave in this company code?
```

---

# 5. Management Accounting

## 5.1 `cost_centers`

### SAP Equivalent
`CSKS`

### Purpose
Represents an internal organizational unit where costs are collected.

### Example

| cost_center | controlling_area | name |
|---|---|---|
| CC1000 | A000 | Digital Banking |
| CC2000 | A000 | HR |
| CC3000 | A000 | Technology |

### Example

A ₹500,000 technology expense can be posted to:

```text
G/L Account: Technology Expense
Cost Center: CC3000
Company Code: 4000
```

---

## 5.2 `profit_centers`

### SAP Equivalent
`CEPC`

### Purpose
Represents a business unit whose profitability can be measured.

### Example

| profit_center | controlling_area | name |
|---|---|---|
| PC1000 | A000 | Retail Banking |
| PC2000 | A000 | Commercial Banking |
| PC3000 | A000 | Wealth Management |

### Difference

```text
Cost Center  → Where did we spend money?

Profit Center → Which business unit generated profit?
```

---

# 6. Posting Configuration

## 6.1 `document_types`

### SAP Equivalent
`T003`

### Purpose
Defines the type/category of an accounting document.

### Example

| document_type | name | purpose |
|---|---|---|
| SA | G/L Account Document | General journal |
| AB | Accounting Document | Adjustment/reversal |
| KR | Vendor Invoice | Vendor invoice |
| KZ | Vendor Payment | Vendor payment |

### Used During

```text
Posting Request
      |
      v
document_types
      |
      v
Journal Entry Header
```

---

## 6.2 `posting_keys`

### SAP Equivalent
`TBSL`

### Purpose
Controls whether a line is debit/credit and which account type it can use.

### Example

| posting_key | debit_credit | account_type |
|---|---|---|
| 40 | Debit | G/L |
| 50 | Credit | G/L |
| 31 | Credit | Vendor |
| 21 | Debit | Vendor |

### Example

```text
40 → Debit G/L
50 → Credit G/L
```

---

## 6.3 `posting_period_controls`

### SAP Equivalent
`T001B`

### Purpose
Controls which fiscal periods are open for posting.

### Example

| company_code | fiscal_year | period | status |
|---|---:|---:|---|
| 4000 | 2026 | 8 | CLOSED |
| 4000 | 2026 | 9 | OPEN |
| 4000 | 2026 | 10 | OPEN |

### Example

If an agent attempts:

```text
Posting Date = 2026-08-15
Company Code = 4000
```

and period 8 is closed:

```text
ERROR: Posting period 8 is not open
```

---

## 6.4 `document_number_ranges`

### SAP Equivalent
`NRIV`

### Purpose
Generates document numbers.

### Example

| company_code | fiscal_year | document_type | next_number |
|---|---:|---|---:|
| 4000 | 2026 | SA | 0000001524 |

### Important

A document number is not globally unique.

The effective identity is:

```text
company_code
+
fiscal_year
+
document_number
```

---

# 7. Transaction Tables

## 7.1 `journal_entry_headers`

### SAP Equivalent
`BKPF`

### Purpose
Stores information common to the complete accounting document.

### Important Fields

| Field | Meaning |
|---|---|
| `company_code` | Legal entity |
| `fiscal_year` | Fiscal year |
| `document_number` | Accounting document |
| `document_type` | Document category |
| `document_date` | Date of business event |
| `posting_date` | Date entered into accounting |
| `currency` | Transaction currency |
| `created_by` | User/agent |

### Example

Suppose Meridian India pays ₹100,000 for software:

| company_code | document_number | type | posting_date | currency |
|---|---|---|---|---|
| 4000 | 0000010524 | SA | 2026-10-05 | INR |

The header identifies the document.

---

## 7.2 `journal_entry_lines`

### SAP Equivalent
`ACDOCA`

### Purpose

This is the **Universal Journal line-item table**.

Every debit/credit line of a business event is stored here.

### Important Fields

| Field | Meaning |
|---|---|
| `ledger` | Accounting ledger |
| `line_number` | Line within document |
| `gl_account` | G/L account |
| `account_type` | G/L, vendor, customer, asset |
| `debit_credit_indicator` | Debit or credit |
| `amount_transaction_currency` | Transaction amount |
| `amount_company_currency` | Company currency amount |
| `amount_group_currency` | Group currency amount |
| `cost_center` | Cost allocation |
| `profit_center` | Profit attribution |
| `vendor_id` | Vendor reference |
| `customer_id` | Customer reference |
| `tax_code` | Tax |
| `clearing_document` | Clearing reference |
| `is_open_item` | Open/cleared status |

### Example

A ₹100,000 software expense:

```text
Debit:
G/L Account      = Software Expense
Amount           = +100,000
Cost Center      = Technology

Credit:
G/L Account      = Bank
Amount           = -100,000
```

Database representation:

| line | account | debit/credit | amount | cost_center |
|---:|---|---|---:|---|
| 1 | Software Expense | D | 100000 | CC3000 |
| 2 | Bank | C | -100000 | — |

### Key Principle

```text
Debit total = Credit total
```

This table is the main source for financial reporting.

---

## 7.3 `journal_entry_tax_lines`

### SAP Equivalent
`BSET`

### Purpose
Stores tax information associated with accounting documents.

### Example

For an invoice of ₹100,000 with 18% GST:

```text
Tax Base = ₹100,000
GST      = ₹18,000
```

Example:

| document_number | tax_code | base_amount | tax_amount | rate |
|---|---|---:|---:|---:|
| 0000010524 | GST18 | 100000 | 18000 | 18% |

---

# 8. Support / Mapping

## 8.1 `schema_name_mapping`

### Purpose
Maintains the relationship between your readable table/column names and SAP names.

### Example

| general_name | sap_name | object |
|---|---|---|
| company_code | BUKRS | field |
| document_number | BELNR | field |
| fiscal_year | GJAHR | field |
| gl_account | RACCT | field |
| journal_entry_headers | BKPF | table |
| journal_entry_lines | ACDOCA | table |

### Why It Matters

Your AI agent can work with:

```text
company_code
```

while the mapping layer still preserves:

```text
SAP = BUKRS
```

---

# 9. Views and Functions

## 9.1 `gl_account_period_balances`

### Purpose
Provides account balances aggregated by account and period.

### Example

```text
Account: Interest Income
January:   1,200,000
February:  1,350,000
March:     1,420,000
```

Instead of manually aggregating thousands of journal lines, the agent can query this view.

---

## 9.2 `trial_balance()`

### Purpose
Returns the balance of every G/L account up to a selected period.

### Example Request

```text
trial_balance(
    company_code = 4000,
    fiscal_year = 2026,
    period = 9
)
```

Example result:

| Account | Debit | Credit | Balance |
|---|---:|---:|---:|
| Cash | 50,000,000 | 10,000,000 | 40,000,000 |
| Loans | 100,000,000 | 20,000,000 | 80,000,000 |
| Interest Income | 0 | 8,000,000 | -8,000,000 |

---

## 9.3 `journal_entries_flat`

### Purpose
Combines journal-entry header and line information into an agent-friendly structure.

```text
journal_entry_headers
          +
journal_entry_lines
          ↓
journal_entries_flat
```

Useful for AI tools that need document context without performing multiple joins.

---

## 9.4 `next_document_number()`

### Purpose
Returns the next available document number from the configured number range.

### Example

```text
next_document_number(
    client = 200,
    company_code = 4000,
    document_type = SA,
    year = 2026
)
```

Result:

```text
0000010525
```

---

# 10. SAP Compatibility Views

## `sap_compat.bkpf`

Provides the readable journal header table using SAP-style names.

```text
company_code      → BUKRS
document_number   → BELNR
fiscal_year       → GJAHR
document_type     → BLART
posting_date      → BUDAT
currency          → WAERS
```

## `sap_compat.acdoca`

Provides the Universal Journal using SAP-style field names.

```text
ledger             → RLDNR
gl_account         → RACCT
cost_center        → RCNTR
profit_center      → PRCTR
vendor_id          → LIFNR
customer_id        → KUNNR
```

This allows your digital twin to maintain **readable schema + SAP traceability**.

---

# 11. Complete Posting Example

## Business Event

> Meridian Bank India pays ₹100,000 for software expenses.

### Step 1 — Identify Company

```text
company_code = 4000
currency     = INR
```

### Step 2 — Identify G/L Accounts

```text
Software Expense → 0000500000
Bank             → 0000100000
```

### Step 3 — Validate Period

```text
Posting Date = 2026-10-05
Period       = 10
Status       = OPEN
```

### Step 4 — Create Header

```text
journal_entry_headers
        |
        └── Document 0000010524
```

### Step 5 — Create Lines

```text
Line 1:
Software Expense
Debit
+100,000
Cost Center = CC3000

Line 2:
Bank
Credit
-100,000
```

### Step 6 — Validate

```text
100,000 - 100,000 = 0
```

Document is balanced.

### Step 7 — Commit

The document becomes part of the Universal Journal.

---

# 12. Table Relationship Summary

```text
clients
   |
   +── company_codes
   |      |
   |      +── gl_account_company_settings
   |      |       |
   |      |       └── gl_accounts
   |      |
   |      +── posting_period_controls
   |      +── document_number_ranges
   |      |
   |      └── journal_entry_headers
   |              |
   |              +── journal_entry_lines
   |              |       |
   |              |       +── gl_accounts
   |              |       +── cost_centers
   |              |       +── profit_centers
   |              |       +── ledgers
   |              |       └── posting_keys
   |              |
   |              └── journal_entry_tax_lines
   |
   +── charts_of_accounts
   |       └── gl_accounts
   |
   +── controlling_areas
   |       ├── cost_centers
   |       └── profit_centers
   |
   +── ledgers
   |
   +── document_types
   |
   └── posting_keys

currencies
   └── exchange_rates
```

---

# 13. S/4HANA Concept Mapping

| Digital Twin Table | SAP Object | Main Concept |
|---|---|---|
| `clients` | T000 | Client |
| `company_codes` | T001 | Legal entity |
| `charts_of_accounts` | T004 | G/L account structure |
| `gl_accounts` | SKA1 | G/L master |
| `gl_account_company_settings` | SKB1 | Company-code G/L settings |
| `gl_account_texts` | SKAT | G/L descriptions |
| `controlling_areas` | TKA01 | Management accounting |
| `cost_centers` | CSKS | Cost collection |
| `profit_centers` | CEPC | Profitability |
| `ledgers` | FINSC_LEDGER | Parallel accounting |
| `document_types` | T003 | Document classification |
| `posting_keys` | TBSL | Debit/credit control |
| `posting_period_controls` | T001B | Period control |
| `document_number_ranges` | NRIV | Number generation |
| `journal_entry_headers` | BKPF | Accounting document header |
| `journal_entry_lines` | ACDOCA | Universal Journal |
| `journal_entry_tax_lines` | BSET | Tax information |
| `exchange_rates` | TCURR | FX rates |
| `currencies` | TCURC | Currency master |

---

# 14. Key Concept to Remember

The most important part of the architecture is:

```text
MASTER DATA
    ↓
Company Code + G/L + Cost Center + Profit Center
    ↓
POSTING CONFIGURATION
    ↓
Document Type + Posting Key + Period + Number Range
    ↓
ACCOUNTING DOCUMENT
    ↓
Header (BKPF-style)
    +
Universal Journal Lines (ACDOCA-style)
    ↓
REPORTING
    ↓
Trial Balance / P&L / Balance Sheet / Analysis
```

The central design principle is:

> **One business event → one accounting document → multiple Universal Journal lines → multiple reporting views.**

This is the core pattern your digital twin is using from the S/4HANA model.
