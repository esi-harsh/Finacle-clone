"""
Balances & Reporting Tools:
- get_trial_balance
- get_account_line_items
- get_period_summary
- list_open_items
- compare_ledgers
"""

from typing import Any, Optional
from datetime import date
from server.db import get_reader_connection
from server.errors import FinanceTwinError
from server.audit_logger import log_tool_call


@log_tool_call("get_trial_balance")
def get_trial_balance(
    company_code: str,
    fiscal_year: int,
    period: int,
    ledger: str = "0L",
    compare_period: Optional[int] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    """Retrieve trial balance summing per-account debits and credits up to the given period."""
    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT gl_account, account_name, statement_type,
                           debit_total, credit_total, balance
                    FROM finance.trial_balance('200', %s, %s, %s, %s)
                    """,
                    (ledger, company_code, fiscal_year, period),
                )
                rows = cur.fetchall()
            except Exception:
                cur.execute(
                    """
                    SELECT l.gl_account, COALESCE(txt.short_text, l.gl_account) AS account_name,
                           a.account_group, COALESCE(a.statement_type, 'BALANCE_SHEET') AS statement_type,
                           SUM(CASE WHEN l.debit_credit_indicator = 'D' THEN l.amount_company_currency ELSE 0 END) AS debit_total,
                           SUM(CASE WHEN l.debit_credit_indicator = 'C' THEN l.amount_company_currency ELSE 0 END) AS credit_total,
                           SUM(l.amount_company_currency) AS balance
                    FROM finance.journal_entry_lines l
                    LEFT JOIN finance.gl_accounts a ON a.client_id = l.client_id AND a.gl_account = l.gl_account
                    LEFT JOIN finance.gl_account_texts txt ON txt.client_id = l.client_id AND txt.gl_account = l.gl_account AND txt.language = 'EN'
                    WHERE l.company_code = %s AND l.fiscal_year = %s AND l.posting_period <= %s AND l.ledger = %s
                    GROUP BY l.gl_account, txt.short_text, a.account_group, a.statement_type
                    ORDER BY l.gl_account
                    """,
                    (company_code, fiscal_year, period, ledger),
                )
                rows = cur.fetchall()

            # Add abnormal balance flags (e.g. Asset/Expense with credit balance, Liability/Revenue with debit balance)
            total_debits = 0.0
            total_credits = 0.0
            for r in rows:
                bal = float(r.get("balance") or 0.0)
                total_debits += float(r.get("debit_total") or 0.0)
                total_credits += float(r.get("credit_total") or 0.0)
                
                is_bs = r.get("is_balance_sheet", True)
                grp = r.get("account_group", "")
                
                # Abnormal balance heuristics
                abnormal = False
                if grp in ("CASH", "LOAN", "ASSET", "EXP") and bal < -0.01:
                    abnormal = True
                elif grp in ("REV", "EQUITY", "DEBT", "LIAB") and bal > 0.01:
                    abnormal = True
                r["abnormal_flag"] = abnormal

            return {
                "company_code": company_code,
                "fiscal_year": fiscal_year,
                "period": period,
                "ledger": ledger,
                "total_debits": round(total_debits, 2),
                "total_credits": round(total_credits, 2),
                "net_difference": round(total_debits + total_credits, 2),
                "accounts": rows,
            }


@log_tool_call("get_account_line_items")
def get_account_line_items(
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
    """Fetch line items with running balance for a specific G/L account."""
    acc_num = str(gl_account).zfill(10)
    limit = min(max(1, limit), 200)
    offset = cursor or 0

    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT l.company_code, l.fiscal_year, l.document_number, l.line_number,
                       l.posting_date, l.posting_period, h.document_type,
                       l.debit_credit_indicator, l.amount_company_currency,
                       l.cost_center, l.profit_center, l.line_text,
                       SUM(l.amount_company_currency) OVER (
                           ORDER BY l.posting_date, l.document_number, l.line_number
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                       ) AS running_balance
                FROM finance.journal_entry_lines l
                JOIN finance.journal_entry_headers h
                  ON h.client_id = l.client_id AND h.company_code = l.company_code
                 AND h.fiscal_year = l.fiscal_year AND h.document_number = l.document_number
                WHERE l.company_code = %s AND l.gl_account = %s AND l.fiscal_year = %s
                  AND l.posting_period BETWEEN %s AND %s AND l.ledger = %s
                ORDER BY l.posting_date, l.document_number, l.line_number
                LIMIT %s OFFSET %s
                """,
                (company_code, acc_num, fiscal_year, period_from, period_to, ledger, limit + 1, offset),
            )
            rows = cur.fetchall()
            truncated = len(rows) > limit
            items = rows[:limit]

            return {
                "company_code": company_code,
                "gl_account": acc_num,
                "fiscal_year": fiscal_year,
                "period_range": f"{period_from}-{period_to}",
                "items": items,
                "next_cursor": (offset + limit) if truncated else None,
                "truncated": truncated,
            }


@log_tool_call("get_period_summary")
def get_period_summary(
    company_code: str,
    fiscal_year: int,
    group_by: str,
    period_from: int = 1,
    period_to: int = 12,
    ledger: str = "0L",
    session_id: str = "default",
) -> dict[str, Any]:
    """Server-side aggregated totals per period for flux analysis."""
    if group_by not in ("account", "cost_center", "profit_center"):
        raise FinanceTwinError("INVALID_GROUP_BY", "group_by must be 'account', 'cost_center', or 'profit_center'.")

    col_map = {
        "account": "gl_account",
        "cost_center": "cost_center",
        "profit_center": "profit_center",
    }
    dim_col = col_map[group_by]

    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {dim_col} AS dimension_key,
                       posting_period,
                       SUM(CASE WHEN debit_credit_indicator = 'D' THEN amount_company_currency ELSE 0 END) AS debits,
                       SUM(CASE WHEN debit_credit_indicator = 'C' THEN amount_company_currency ELSE 0 END) AS credits,
                       SUM(amount_company_currency) AS net_movement
                FROM finance.journal_entry_lines
                WHERE company_code = %s AND fiscal_year = %s AND posting_period BETWEEN %s AND %s AND ledger = %s
                GROUP BY {dim_col}, posting_period
                ORDER BY {dim_col}, posting_period
                """,
                (company_code, fiscal_year, period_from, period_to, ledger),
            )
            return {
                "company_code": company_code,
                "fiscal_year": fiscal_year,
                "group_by": group_by,
                "period_range": f"{period_from}-{period_to}",
                "data": cur.fetchall(),
            }


@log_tool_call("list_open_items")
def list_open_items(
    company_code: str,
    account_type: str = "vendor",
    vendor_id: Optional[str] = None,
    as_of_date: Optional[date] = None,
    limit: int = 50,
    cursor: Optional[int] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    """List open items with posting-date based aging (payment terms not yet modelled in v0.1)."""
    limit = min(max(1, limit), 200)
    offset = cursor or 0
    ref_date = as_of_date or date(2026, 10, 5)

    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            where_clauses = [
                "company_code = %s",
                "account_type = %s",
                "is_open_item = true",
                "clearing_document IS NULL",
                "posting_date <= %s",
            ]
            params = [company_code, account_type.upper(), ref_date]

            if vendor_id:
                where_clauses.append("vendor_id = %s")
                params.append(vendor_id)

            where_str = " AND ".join(where_clauses)

            cur.execute(
                f"""
                SELECT company_code, fiscal_year, document_number, line_number,
                       vendor_id, customer_id, gl_account, posting_date,
                       amount_company_currency
                FROM finance.journal_entry_lines
                WHERE {where_str}
                ORDER BY posting_date ASC
                LIMIT %s OFFSET %s
                """,
                params + [limit + 1, offset],
            )
            rows = cur.fetchall()
            for r in rows:
                p_date = r.get("posting_date")
                if isinstance(p_date, str):
                    from datetime import datetime
                    try:
                        p_date = datetime.strptime(p_date[:10], "%Y-%m-%d").date()
                    except Exception:
                        p_date = None
                r["age_days"] = (ref_date - p_date).days if (p_date and hasattr(ref_date, '__sub__')) else 0

            truncated = len(rows) > limit
            items = rows[:limit]

            return {
                "company_code": company_code,
                "account_type": account_type,
                "as_of_date": ref_date.isoformat() if hasattr(ref_date, "isoformat") else str(ref_date),
                "note": "Age is calculated from posting_date (payment terms deferred to Phase 2).",
                "items": items,
                "next_cursor": (offset + limit) if truncated else None,
                "truncated": truncated,
            }


@log_tool_call("compare_ledgers")
def compare_ledgers(
    company_code: str,
    fiscal_year: int,
    period: int,
    ledger_a: str = "0L",
    ledger_b: str = "2L",
    session_id: str = "default",
) -> dict[str, Any]:
    """Compare parallel accounting ledgers (e.g. 0L US GAAP vs 2L IFRS)."""
    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_number, line_number, gl_account, ledger, amount_company_currency
                FROM finance.journal_entry_lines
                WHERE company_code = %s AND fiscal_year = %s AND posting_period = %s
                  AND ledger IN (%s, %s)
                ORDER BY document_number, line_number, ledger
                """,
                (company_code, fiscal_year, period, ledger_a, ledger_b),
            )
            all_lines = cur.fetchall()

            # Group by document_number, line_number
            groups: dict[tuple, dict] = {}
            for l in all_lines:
                key = (l["document_number"], l["line_number"], l["gl_account"])
                if key not in groups:
                    groups[key] = {"amount_ledger_a": None, "amount_ledger_b": None}
                if l["ledger"] == ledger_a:
                    groups[key]["amount_ledger_a"] = float(l["amount_company_currency"])
                elif l["ledger"] == ledger_b:
                    groups[key]["amount_ledger_b"] = float(l["amount_company_currency"])

            differences = []
            for (doc_num, line_num, gl_acc), val in groups.items():
                if val["amount_ledger_a"] != val["amount_ledger_b"]:
                    differences.append({
                        "document_number": doc_num,
                        "line_number": line_num,
                        "gl_account": gl_acc,
                        "amount_ledger_a": val["amount_ledger_a"],
                        "amount_ledger_b": val["amount_ledger_b"],
                    })

            return {
                "company_code": company_code,
                "fiscal_year": fiscal_year,
                "period": period,
                "ledger_a": ledger_a,
                "ledger_b": ledger_b,
                "differences_count": len(differences),
                "differences": differences,
            }
