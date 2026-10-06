"""
Lookup Tools: get_document, search_documents, lookup_master_data, get_period_status.
All queries use the twin_reader pool (SELECT only).
"""

from typing import Any, Optional
from datetime import date
from server.db import get_reader_connection
from server.errors import FinanceTwinError
from server.logging import log_tool_call


@log_tool_call("get_document")
def get_document(
    company_code: str,
    fiscal_year: int,
    document_number: str,
    session_id: str = "default",
) -> dict[str, Any]:
    """Retrieve full accounting document (header, lines, tax lines, reversal links)."""
    # Ensure zero-padded 10-digit number
    doc_num = str(document_number).zfill(10)
    
    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            # 1. Fetch Header
            cur.execute(
                """
                SELECT * FROM finance.journal_entry_headers
                WHERE company_code = %s AND fiscal_year = %s AND document_number = %s
                """,
                (company_code, fiscal_year, doc_num),
            )
            header = cur.fetchone()
            if not header:
                raise FinanceTwinError(
                    code="DOC_NOT_FOUND",
                    message=f"Document {company_code}-{fiscal_year}-{doc_num} not found.",
                    details={"company_code": company_code, "fiscal_year": fiscal_year, "document_number": doc_num}
                )

            # 2. Fetch Line Items
            cur.execute(
                """
                SELECT * FROM finance.journal_entry_lines
                WHERE company_code = %s AND fiscal_year = %s AND document_number = %s
                ORDER BY line_number
                """,
                (company_code, fiscal_year, doc_num),
            )
            lines = cur.fetchall()

            # 3. Fetch Tax Lines
            cur.execute(
                """
                SELECT * FROM finance.journal_entry_tax_lines
                WHERE company_code = %s AND fiscal_year = %s AND document_number = %s
                ORDER BY tax_line_number
                """,
                (company_code, fiscal_year, doc_num),
            )
            tax_lines = cur.fetchall()

            header["lines"] = lines
            header["tax_lines"] = tax_lines
            return header


@log_tool_call("search_documents")
def search_documents(
    company_code: Optional[str] = None,
    fiscal_year: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
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
    """Search journal entries from the flat journal view with pagination."""
    limit = min(max(1, limit), 200)
    offset = cursor or 0

    where_clauses = ["ledger = %s"]
    params: list[Any] = [ledger]

    if company_code:
        where_clauses.append("company_code = %s")
        params.append(company_code)
    if fiscal_year:
        where_clauses.append("fiscal_year = %s")
        params.append(fiscal_year)
    if date_from:
        where_clauses.append("posting_date >= %s")
        params.append(date_from)
    if date_to:
        where_clauses.append("posting_date <= %s")
        params.append(date_to)
    if document_type:
        where_clauses.append("document_type = %s")
        params.append(document_type)
    if created_by:
        where_clauses.append("created_by = %s")
        params.append(created_by)
    if gl_account:
        where_clauses.append("gl_account = %s")
        params.append(gl_account)
    if vendor_id:
        where_clauses.append("vendor_id = %s")
        params.append(vendor_id)
    if external_reference:
        where_clauses.append("external_reference ILIKE %s")
        params.append(f"%{external_reference}%")
    if amount_min is not None:
        where_clauses.append("ABS(amount_company_currency) >= %s")
        params.append(amount_min)
    if amount_max is not None:
        where_clauses.append("ABS(amount_company_currency) <= %s")
        params.append(amount_max)
    if text_search:
        where_clauses.append("(header_text ILIKE %s OR line_text ILIKE %s)")
        params.extend([f"%{text_search}%", f"%{text_search}%"])

    if len(where_clauses) == 1:
        raise FinanceTwinError(
            code="INVALID_SEARCH_FILTER",
            message="At least one filter criterion is required for search_documents."
        )

    where_str = " AND ".join(where_clauses)

    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            # Count total matching rows
            cur.execute(f"SELECT COUNT(*) AS count FROM finance.journal_entries_flat WHERE {where_str}", params)
            total_count = cur.fetchone()["count"]

            # Fetch page
            cur.execute(
                f"""
                SELECT * FROM finance.journal_entries_flat
                WHERE {where_str}
                ORDER BY posting_date DESC, document_number, line_number
                LIMIT %s OFFSET %s
                """,
                params + [limit + 1, offset],
            )
            rows = cur.fetchall()
            truncated = len(rows) > limit
            results = rows[:limit]

            return {
                "total_count": total_count,
                "items": results,
                "next_cursor": (offset + limit) if truncated else None,
                "truncated": truncated,
            }


@log_tool_call("lookup_master_data")
def lookup_master_data(
    object_type: str,
    id: Optional[str] = None,
    search_text: Optional[str] = None,
    company_code: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    """Retrieve master data records and control flags (G/L accounts, cost centers, profit centers, etc.)."""
    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            if object_type == "gl_account":
                if id:
                    acc_num = str(id).zfill(10)
                    cur.execute(
                        """
                        SELECT a.gl_account, a.account_group, a.is_balance_sheet, a.is_blocked AS chart_blocked,
                               t.name AS account_name,
                               s.company_code, s.is_open_item_managed, s.is_blocked AS company_blocked,
                               s.reconciliation_account_type, s.allowed_currency
                        FROM finance.gl_accounts a
                        LEFT JOIN finance.gl_account_texts t ON a.client_id = t.client_id AND a.gl_account = t.gl_account AND t.language = 'EN'
                        LEFT JOIN finance.gl_account_company_settings s ON a.client_id = s.client_id AND a.gl_account = s.gl_account
                        WHERE a.gl_account = %s AND (s.company_code = %s OR %s IS NULL)
                        """,
                        (acc_num, company_code, company_code),
                    )
                    records = cur.fetchall()
                    if not records:
                        raise FinanceTwinError("ACCOUNT_NOT_FOUND", f"G/L Account {acc_num} not found.")
                    return {"object_type": object_type, "records": records}
                elif search_text:
                    cur.execute(
                        """
                        SELECT a.gl_account, a.account_group, a.is_balance_sheet, t.name AS account_name
                        FROM finance.gl_accounts a
                        JOIN finance.gl_account_texts t ON a.client_id = t.client_id AND a.gl_account = t.gl_account
                        WHERE t.name ILIKE %s
                        LIMIT 20
                        """,
                        (f"%{search_text}%",),
                    )
                    return {"object_type": object_type, "records": cur.fetchall()}

            elif object_type == "cost_center":
                cur.execute(
                    "SELECT * FROM finance.cost_centers WHERE cost_center = %s OR name ILIKE %s",
                    (id, f"%{search_text or id}%"),
                )
                return {"object_type": object_type, "records": cur.fetchall()}

            elif object_type == "profit_center":
                cur.execute(
                    "SELECT * FROM finance.profit_centers WHERE profit_center = %s OR name ILIKE %s",
                    (id, f"%{search_text or id}%"),
                )
                return {"object_type": object_type, "records": cur.fetchall()}

            elif object_type == "document_type":
                cur.execute(
                    "SELECT * FROM finance.document_types WHERE document_type = %s OR name ILIKE %s",
                    (id, f"%{search_text or id}%"),
                )
                return {"object_type": object_type, "records": cur.fetchall()}

            elif object_type == "company_code":
                cur.execute(
                    "SELECT * FROM finance.company_codes WHERE company_code = %s",
                    (id,),
                )
                return {"object_type": object_type, "records": cur.fetchall()}

            raise FinanceTwinError("INVALID_OBJECT_TYPE", f"Object type {object_type} is not supported.")


@log_tool_call("get_period_status")
def get_period_status(
    company_code: str,
    fiscal_year: int,
    period: int,
    session_id: str = "default",
) -> dict[str, Any]:
    """Check if a posting period is open or closed for a company code."""
    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT client_id, company_code, fiscal_year, posting_period, is_open
                FROM finance.posting_period_controls
                WHERE company_code = %s AND fiscal_year = %s AND posting_period = %s
                """,
                (company_code, fiscal_year, period),
            )
            row = cur.fetchone()
            if not row:
                raise FinanceTwinError(
                    "PERIOD_NOT_CONFIGURED",
                    f"No period control record found for company {company_code}, year {fiscal_year}, period {period}."
                )
            return {
                "company_code": company_code,
                "fiscal_year": fiscal_year,
                "period": period,
                "status": "OPEN" if row["is_open"] else "CLOSED",
                "is_open": row["is_open"],
            }
