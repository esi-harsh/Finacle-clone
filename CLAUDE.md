# Finance Twin Agent Platform

## Orientation & Rules of Engagement
- Always read [`docs/mcp_spec.md`](file:///C:/Finacle%20Clone%20New/docs/mcp_spec.md) and [`docs/finance_digital_twin_documentation.md`](file:///C:/Finacle%20Clone%20New/docs/finance_digital_twin_documentation.md) first.
- **Never bypass the approval step**: `post_journal_entry` and `reverse_document` create pending drafts in `draft_entries`. Only the harness or a human can approve them to post into `journal_entry_headers`.
- **Never write raw SQL**: All database operations from agents must use MCP tools.
- **Document Key Convention**: Every accounting document is strictly identified by `company_code` (4-char string) + `fiscal_year` (4-digit integer) + `document_number` (10-digit zero-padded text, e.g. `'0000001001'`). Never strip leading zeroes.
- **Sign Convention**: Debits are positive (`+`), Credits are negative (`-`).
- **Default Ledger**: `0L` (US GAAP Leading Ledger).
- **Error Codes**: SAP-compatible codes (`PERIOD_CLOSED`, `ACCOUNT_BLOCKED`, `RECON_ACCOUNT_DIRECT_POSTING`, `DOC_NOT_BALANCED`, `CURRENCY_NOT_ALLOWED`, `DOC_NOT_FOUND`).
