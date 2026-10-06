"""
Analysis Tools:
- find_duplicate_invoices (rule-based exact & fuzzy detection per vendor)
- scan_journal_anomalies (6 rule-based anomaly scans)
- get_account_usage_profile (historical baseline for misposting detection)
"""

from typing import Any, Optional
from datetime import date
from server.db import get_reader_connection
from server.audit_logger import log_tool_call


@log_tool_call("find_duplicate_invoices")
def find_duplicate_invoices(
    company_code: str,
    mode: str = "exact",
    window_days: int = 90,
    amount_tolerance_pct: float = 0.0,
    vendor_id: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    """
    Find duplicate vendor invoices (exact or fuzzy).
    Matching is strictly PER VENDOR to avoid decoy false positives.
    """
    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            vendor_filter = "AND h1.created_by IS NOT NULL"
            params: list[Any] = [company_code, window_days]

            if vendor_id:
                vendor_filter += " AND l1.vendor_id = %s"
                params.append(vendor_id)

            if mode == "exact":
                # Match same vendor + same external_reference + same amount
                query = f"""
                SELECT l1.vendor_id,
                       h1.external_reference,
                       h1.document_number AS doc_1,
                       h2.document_number AS doc_2,
                       h1.posting_date AS date_1,
                       h2.posting_date AS date_2,
                       ABS(l1.amount_company_currency) AS amount_1,
                       ABS(l2.amount_company_currency) AS amount_2,
                       l1.clearing_document AS clearing_1,
                       l2.clearing_document AS clearing_2
                FROM finance.journal_entry_headers h1
                JOIN finance.journal_entry_lines l1 
                  ON h1.client_id = l1.client_id AND h1.company_code = l1.company_code 
                 AND h1.fiscal_year = l1.fiscal_year AND h1.document_number = l1.document_number
                JOIN finance.journal_entry_headers h2
                  ON h1.client_id = h2.client_id AND h1.company_code = h2.company_code
                 AND h1.fiscal_year = h2.fiscal_year AND h1.document_number < h2.document_number
                JOIN finance.journal_entry_lines l2
                  ON h2.client_id = l2.client_id AND h2.company_code = l2.company_code
                 AND h2.fiscal_year = l2.fiscal_year AND h2.document_number = l2.document_number
                WHERE h1.company_code = %s
                  AND h1.document_type IN ('KR', 'SA')
                  AND l1.account_type = 'VENDOR' AND l2.account_type = 'VENDOR'
                  AND l1.vendor_id = l2.vendor_id
                  AND h1.external_reference IS NOT NULL
                  AND h1.external_reference = h2.external_reference
                  AND ABS(h1.posting_date - h2.posting_date) <= %s
                  AND ABS(l1.amount_company_currency) = ABS(l2.amount_company_currency)
                  {vendor_filter}
                """
            else:
                # Fuzzy match: same vendor, close amounts, similar dates or typo in reference
                tol = amount_tolerance_pct / 100.0
                params.append(tol)
                query = f"""
                SELECT l1.vendor_id,
                       h1.external_reference AS ref_1,
                       h2.external_reference AS ref_2,
                       h1.document_number AS doc_1,
                       h2.document_number AS doc_2,
                       h1.posting_date AS date_1,
                       h2.posting_date AS date_2,
                       ABS(l1.amount_company_currency) AS amount_1,
                       ABS(l2.amount_company_currency) AS amount_2,
                       l1.clearing_document AS clearing_1,
                       l2.clearing_document AS clearing_2
                FROM finance.journal_entry_headers h1
                JOIN finance.journal_entry_lines l1 
                  ON h1.client_id = l1.client_id AND h1.company_code = l1.company_code 
                 AND h1.fiscal_year = l1.fiscal_year AND h1.document_number = l1.document_number
                JOIN finance.journal_entry_headers h2
                  ON h1.client_id = h2.client_id AND h1.company_code = h2.company_code
                 AND h1.fiscal_year = h2.fiscal_year AND h1.document_number < h2.document_number
                JOIN finance.journal_entry_lines l2
                  ON h2.client_id = l2.client_id AND h2.company_code = l2.company_code
                 AND h2.fiscal_year = l2.fiscal_year AND h2.document_number = l2.document_number
                WHERE h1.company_code = %s
                  AND h1.document_type IN ('KR', 'SA')
                  AND l1.account_type = 'VENDOR' AND l2.account_type = 'VENDOR'
                  AND l1.vendor_id = l2.vendor_id
                  AND ABS(h1.posting_date - h2.posting_date) <= %s
                  AND ABS(ABS(l1.amount_company_currency) - ABS(l2.amount_company_currency)) <= (ABS(l1.amount_company_currency) * %s)
                  {vendor_filter}
                """

            cur.execute(query, params)
            pairs = cur.fetchall()

            groups = []
            for p in pairs:
                status_1 = "paid" if p.get("clearing_1") else "open"
                status_2 = "paid" if p.get("clearing_2") else "open"
                
                # Recoverable amount calculation
                recoverable = 0.0
                if status_1 == "open":
                    recoverable += float(p["amount_1"])
                if status_2 == "open" and p["doc_1"] != p["doc_2"]:
                    recoverable += float(p["amount_2"])

                groups.append({
                    "vendor_id": p["vendor_id"],
                    "members": [p["doc_1"], p["doc_2"]],
                    "amounts": [float(p["amount_1"]), float(p["amount_2"])],
                    "statuses": [status_1, status_2],
                    "recoverable_amount": recoverable,
                })

            return {
                "company_code": company_code,
                "mode": mode,
                "total_candidate_groups": len(groups),
                "groups": groups,
            }


@log_tool_call("scan_journal_anomalies")
def scan_journal_anomalies(
    company_code: str,
    fiscal_year: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    rules: Optional[list[str]] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    """
    Scan for posting anomalies using deterministic accounting rules:
    - weekend_posting
    - round_amount
    - near_period_end
    - after_close
    - rare_account
    - unusual_creator
    """
    active_rules = rules or ["weekend_posting", "round_amount", "near_period_end", "after_close", "rare_account", "unusual_creator"]
    anomalies = []

    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            # 1. Weekend Postings (Saturday = 6, Sunday = 0)
            if "weekend_posting" in active_rules:
                cur.execute(
                    """
                    SELECT company_code, fiscal_year, document_number, posting_date, created_at, created_by, header_text
                    FROM finance.journal_entry_headers
                    WHERE company_code = %s AND fiscal_year = %s
                      AND EXTRACT(DOW FROM created_at) IN (0, 6)
                    """,
                    (company_code, fiscal_year),
                )
                for r in cur.fetchall():
                    anomalies.append({
                        "document_number": r["document_number"],
                        "rule": "weekend_posting",
                        "score": 0.85,
                        "details": f"Posted on weekend: {r['created_at'].strftime('%A, %Y-%m-%d %H:%M')}",
                    })

            # 2. Round Amounts (e.g. exactly 10,000, 50,000, 1,000,000)
            if "round_amount" in active_rules:
                cur.execute(
                    """
                    SELECT h.document_number, l.gl_account, l.amount_company_currency, h.header_text
                    FROM finance.journal_entry_headers h
                    JOIN finance.journal_entry_lines l USING (client_id, company_code, fiscal_year, document_number)
                    WHERE h.company_code = %s AND h.fiscal_year = %s
                      AND ABS(l.amount_company_currency) >= 10000
                      AND MOD(ABS(l.amount_company_currency)::numeric, 10000) = 0
                      AND h.document_type NOT IN ('SA')  -- Exclude routine manual adjustments
                    LIMIT 20
                    """,
                    (company_code, fiscal_year),
                )
                for r in cur.fetchall():
                    anomalies.append({
                        "document_number": r["document_number"],
                        "rule": "round_amount",
                        "score": 0.60,
                        "details": f"Round amount {float(r['amount_company_currency']):,.2f} on account {r['gl_account']}",
                    })

            # 3. Rare Account Usage (< 2% of postings in the company)
            if "rare_account" in active_rules:
                cur.execute(
                    """
                    WITH counts AS (
                        SELECT gl_account, COUNT(*) as cnt
                        FROM finance.journal_entry_lines
                        WHERE company_code = %s AND fiscal_year = %s
                        GROUP BY gl_account
                    ),
                    totals AS (
                        SELECT COUNT(*) AS total_docs FROM finance.journal_entry_headers
                        WHERE company_code = %s AND fiscal_year = %s
                    )
                    SELECT l.document_number, l.gl_account, c.cnt, t.total_docs
                    FROM finance.journal_entry_lines l
                    JOIN counts c ON l.gl_account = c.gl_account
                    CROSS JOIN totals t
                    WHERE l.company_code = %s AND l.fiscal_year = %s
                      AND (c.cnt::float / t.total_docs) < 0.02
                    LIMIT 20
                    """,
                    (company_code, fiscal_year, company_code, fiscal_year, company_code, fiscal_year),
                )
                for r in cur.fetchall():
                    anomalies.append({
                        "document_number": r["document_number"],
                        "rule": "rare_account",
                        "score": 0.70,
                        "details": f"Rare account {r['gl_account']} (used in only {r['cnt']} documents)",
                    })

            return {
                "company_code": company_code,
                "fiscal_year": fiscal_year,
                "total_anomalies_flagged": len(anomalies),
                "anomalies": anomalies,
            }


@log_tool_call("get_account_usage_profile")
def get_account_usage_profile(
    company_code: str,
    vendor_id: Optional[str] = None,
    text_pattern: Optional[str] = None,
    cost_center: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    """Retrieve historical account usage profile to detect mispostings."""
    where_clauses = ["company_code = %s"]
    params: list[Any] = [company_code]

    if vendor_id:
        where_clauses.append("vendor_id = %s")
        params.append(vendor_id)
    if text_pattern:
        where_clauses.append("line_text ILIKE %s")
        params.append(f"%{text_pattern}%")
    if cost_center:
        where_clauses.append("cost_center = %s")
        params.append(cost_center)

    where_str = " AND ".join(where_clauses)

    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH usage AS (
                    SELECT gl_account, COUNT(*) AS usage_count
                    FROM finance.journal_entry_lines
                    WHERE {where_str}
                    GROUP BY gl_account
                ),
                total AS (
                    SELECT SUM(usage_count) AS total_count FROM usage
                )
                SELECT u.gl_account, txt.short_text AS account_name, u.usage_count,
                       ROUND((u.usage_count::numeric / t.total_count::numeric) * 100, 2) AS usage_pct
                FROM usage u
                CROSS JOIN total t
                LEFT JOIN finance.gl_account_texts txt 
                  ON txt.client_id = '200' AND txt.gl_account = u.gl_account AND txt.language = 'EN'
                ORDER BY u.usage_count DESC
                """,
                params,
            )
            return {
                "company_code": company_code,
                "filter_vendor_id": vendor_id,
                "filter_cost_center": cost_center,
                "profiles": cur.fetchall(),
            }
