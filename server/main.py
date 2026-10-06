"""
Finance Twin MCP Server Entrypoint.
Exposes the 15 MCP tools over Streamable HTTP (SSE / FastMCP) or stdio transport.
"""

import os
from datetime import date
from typing import Any, Optional
from fastmcp import FastMCP
from dotenv import load_dotenv

from server.tools.lookup import (
    get_document,
    search_documents,
    lookup_master_data,
    get_period_status,
)
from server.tools.balances import (
    get_trial_balance,
    get_account_line_items,
    get_period_summary,
    list_open_items,
    compare_ledgers,
)
from server.tools.analysis import (
    find_duplicate_invoices,
    scan_journal_anomalies,
    get_account_usage_profile,
)
from server.tools.write import (
    validate_journal_entry,
    post_journal_entry,
    reverse_document,
)

load_dotenv()

# Initialize FastMCP Server
mcp = FastMCP("Finance Twin Agent Platform")

# ---------------------------------------------------------
# Group 1: Lookup Tools (SAP: FB03, FBL3N, FS00/BP, OB52)
# ---------------------------------------------------------

@mcp.tool(name="get_document", description="Retrieve accounting document by company code, fiscal year, and 10-digit document number (SAP: FB03).")
def tool_get_document(company_code: str, fiscal_year: int, document_number: str, session_id: str = "default") -> dict[str, Any]:
    return get_document(company_code=company_code, fiscal_year=fiscal_year, document_number=document_number, session_id=session_id)


@mcp.tool(name="search_documents", description="Search journal entries from flat journal view with filters (date, type, account, vendor, text).")
def tool_search_documents(
    company_code: Optional[str] = None,
    fiscal_year: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    document_type: Optional[str] = None,
    created_by: Optional[str] = None,
    gl_account: Optional[str] = None,
    vendor_id: Optional[str] = None,
    external_reference: Optional[str] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
    text_search: Optional[str] = None,
    ledger: str = "0L",
    limit: int = 50,
    cursor: Optional[int] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    d_from = date.fromisoformat(date_from) if date_from else None
    d_to = date.fromisoformat(date_to) if date_to else None
    return search_documents(
        company_code=company_code,
        fiscal_year=fiscal_year,
        date_from=d_from,
        date_to=d_to,
        document_type=document_type,
        created_by=created_by,
        gl_account=gl_account,
        vendor_id=vendor_id,
        external_reference=external_reference,
        amount_min=amount_min,
        amount_max=amount_max,
        text_search=text_search,
        ledger=ledger,
        limit=limit,
        cursor=cursor,
        session_id=session_id,
    )


@mcp.tool(name="lookup_master_data", description="Retrieve master data records and control flags (gl_account, cost_center, profit_center, document_type, company_code) (SAP: FS00/BP).")
def tool_lookup_master_data(
    object_type: str,
    id: Optional[str] = None,
    search_text: Optional[str] = None,
    company_code: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    return lookup_master_data(object_type=object_type, id=id, search_text=search_text, company_code=company_code, session_id=session_id)


@mcp.tool(name="get_period_status", description="Check if a specific posting period is OPEN or CLOSED for a company code (SAP: OB52/T001B).")
def tool_get_period_status(company_code: str, fiscal_year: int, period: int, session_id: str = "default") -> dict[str, Any]:
    return get_period_status(company_code=company_code, fiscal_year=fiscal_year, period=period, session_id=session_id)


# ---------------------------------------------------------
# Group 2: Balances & Reports (SAP: FAGLB03, FBL1N/FBL5N, S_ALR)
# ---------------------------------------------------------

@mcp.tool(name="get_trial_balance", description="Get per-account debit, credit, balance, and abnormal balance flags (SAP: FAGLB03). Sums to zero.")
def tool_get_trial_balance(
    company_code: str,
    fiscal_year: int,
    period: int,
    ledger: str = "0L",
    compare_period: Optional[int] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    return get_trial_balance(company_code=company_code, fiscal_year=fiscal_year, period=period, ledger=ledger, compare_period=compare_period, session_id=session_id)


@mcp.tool(name="get_account_line_items", description="Fetch paged line items with running balance for a specific G/L account (SAP: FBL3N).")
def tool_get_account_line_items(
    company_code: str,
    gl_account: str,
    fiscal_year: int,
    period_from: int = 1,
    period_to: int = 12,
    ledger: str = "0L",
    limit: int = 50,
    cursor: Optional[int] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    return get_account_line_items(
        company_code=company_code,
        gl_account=gl_account,
        fiscal_year=fiscal_year,
        period_from=period_from,
        period_to=period_to,
        ledger=ledger,
        limit=limit,
        cursor=cursor,
        session_id=session_id,
    )


@mcp.tool(name="get_period_summary", description="Get server-side aggregated period totals grouped by account, cost_center, or profit_center for flux analysis.")
def tool_get_period_summary(
    company_code: str,
    fiscal_year: int,
    group_by: str,
    period_from: int = 1,
    period_to: int = 12,
    ledger: str = "0L",
    session_id: str = "default",
) -> dict[str, Any]:
    return get_period_summary(company_code=company_code, fiscal_year=fiscal_year, group_by=group_by, period_from=period_from, period_to=period_to, ledger=ledger, session_id=session_id)


@mcp.tool(name="list_open_items", description="List open vendor or customer items with posting-date based aging (SAP: FBL1N/FBL5N).")
def tool_list_open_items(
    company_code: str,
    account_type: str = "vendor",
    vendor_id: Optional[str] = None,
    as_of_date: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[int] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    d_as_of = date.fromisoformat(as_of_date) if as_of_date else None
    return list_open_items(company_code=company_code, account_type=account_type, vendor_id=vendor_id, as_of_date=d_as_of, limit=limit, cursor=cursor, session_id=session_id)


@mcp.tool(name="compare_ledgers", description="Compare parallel accounting ledgers (0L US GAAP vs 2L IFRS) and list adjustments present in only one.")
def tool_compare_ledgers(
    company_code: str,
    fiscal_year: int,
    period: int,
    ledger_a: str = "0L",
    ledger_b: str = "2L",
    session_id: str = "default",
) -> dict[str, Any]:
    return compare_ledgers(company_code=company_code, fiscal_year=fiscal_year, period=period, ledger_a=ledger_a, ledger_b=ledger_b, session_id=session_id)


# ---------------------------------------------------------
# Group 3: Analysis Helpers
# ---------------------------------------------------------

@mcp.tool(name="find_duplicate_invoices", description="Find candidate duplicate vendor invoices (exact or fuzzy per vendor) with paid/open status and recoverable amount.")
def tool_find_duplicate_invoices(
    company_code: str,
    mode: str = "exact",
    window_days: int = 90,
    amount_tolerance_pct: float = 0.0,
    vendor_id: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    return find_duplicate_invoices(company_code=company_code, mode=mode, window_days=window_days, amount_tolerance_pct=amount_tolerance_pct, vendor_id=vendor_id, session_id=session_id)


@mcp.tool(name="scan_journal_anomalies", description="Scan journal entries using 6 deterministic rules (weekend_posting, round_amount, near_period_end, after_close, rare_account, unusual_creator).")
def tool_scan_journal_anomalies(
    company_code: str,
    fiscal_year: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    rules: Optional[list[str]] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    d_from = date.fromisoformat(date_from) if date_from else None
    d_to = date.fromisoformat(date_to) if date_to else None
    return scan_journal_anomalies(company_code=company_code, fiscal_year=fiscal_year, date_from=d_from, date_to=d_to, rules=rules, session_id=session_id)


@mcp.tool(name="get_account_usage_profile", description="Get historical account usage profile by vendor, cost center, or text pattern as a baseline for misposting detection.")
def tool_get_account_usage_profile(
    company_code: str,
    vendor_id: Optional[str] = None,
    text_pattern: Optional[str] = None,
    cost_center: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    return get_account_usage_profile(company_code=company_code, vendor_id=vendor_id, text_pattern=text_pattern, cost_center=cost_center, session_id=session_id)


# ---------------------------------------------------------
# Group 4: Validation & Write (Approval Gated)
# ---------------------------------------------------------

@mcp.tool(name="validate_journal_entry", description="Simulate posting in a transaction that always rolls back. Fires all SAP triggers and returns trial balance impact without persisting rows.")
def tool_validate_journal_entry(
    company_code: str,
    fiscal_year: int,
    document_type: str,
    document_date: str,
    posting_date: str,
    lines: list[dict[str, Any]],
    currency: str = "USD",
    header_text: Optional[str] = None,
    external_reference: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    return validate_journal_entry(
        company_code=company_code,
        fiscal_year=fiscal_year,
        document_type=document_type,
        document_date=date.fromisoformat(document_date),
        posting_date=date.fromisoformat(posting_date),
        lines=lines,
        currency=currency,
        header_text=header_text,
        external_reference=external_reference,
        session_id=session_id,
    )


@mcp.tool(name="post_journal_entry", description="Stage a journal entry draft with status 'pending' (SAP: BAPI_ACC_DOCUMENT_POST). Requires approval step before posting.")
def tool_post_journal_entry(
    company_code: str,
    fiscal_year: int,
    document_type: str,
    document_date: str,
    posting_date: str,
    lines: list[dict[str, Any]],
    currency: str = "USD",
    header_text: Optional[str] = None,
    external_reference: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    return post_journal_entry(
        company_code=company_code,
        fiscal_year=fiscal_year,
        document_type=document_type,
        document_date=date.fromisoformat(document_date),
        posting_date=date.fromisoformat(posting_date),
        lines=lines,
        currency=currency,
        header_text=header_text,
        external_reference=external_reference,
        idempotency_key=idempotency_key,
        session_id=session_id,
    )


@mcp.tool(name="reverse_document", description="Stage a document reversal draft with status 'pending' (SAP: BAPI_ACC_DOCUMENT_REV_POST). Requires approval step before posting.")
def tool_reverse_document(
    company_code: str,
    fiscal_year: int,
    document_number: str,
    reversal_date: str,
    reason: str,
    session_id: str = "default",
) -> dict[str, Any]:
    return reverse_document(
        company_code=company_code,
        fiscal_year=fiscal_year,
        document_number=document_number,
        reversal_date=date.fromisoformat(reversal_date),
        reason=reason,
        session_id=session_id,
    )


def main():
    """Main function for CLI and module execution."""
    transport = os.getenv("MCP_TRANSPORT", "http").lower()
    host = os.getenv("MCP_SERVER_HOST", os.getenv("MCP_HOST", "0.0.0.0"))
    port = int(os.getenv("MCP_SERVER_PORT", os.getenv("MCP_PORT", "8000")))

    if transport == "stdio":
        print("[MCP SERVER] Starting in stdio transport mode...")
        mcp.run(transport="stdio")
    else:
        print(f"[MCP SERVER] Starting Streamable HTTP (SSE) server at http://{host}:{port}/sse ...")
        mcp.run(transport="sse", host=host, port=port)


if __name__ == "__main__":
    main()
