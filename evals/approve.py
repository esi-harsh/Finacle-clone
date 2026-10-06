"""
Approval Actor (Harness side).
Moves pending draft entries to posted status and executes the actual INSERT into
journal_entry_headers and journal_entry_lines.
The agent itself CANNOT call this.
"""

import json
from typing import Any
from server.db import get_admin_connection
from server.errors import FinanceTwinError


def approve_draft(draft_id: str, approved_by: str = "HARNESS_APPROVER") -> dict[str, Any]:
    """Approve a pending draft entry and execute the actual posting to core tables."""
    with get_admin_connection() as conn:
        with conn.cursor() as cur:
            # 1. Fetch Draft
            cur.execute(
                "SELECT * FROM finance.draft_entries WHERE draft_id = %s",
                (draft_id,),
            )
            draft = cur.fetchone()
            if not draft:
                raise FinanceTwinError("DRAFT_NOT_FOUND", f"Draft {draft_id} not found.")

            if draft["status"] != "pending":
                raise FinanceTwinError("DRAFT_NOT_PENDING", f"Draft {draft_id} is already {draft['status']}.")

            payload = draft["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)

            draft_type = draft["draft_type"]

            if draft_type == "post":
                # Fetch next official document number
                cur.execute(
                    "SELECT finance.next_document_number('200', %s, %s, %s) AS doc_num",
                    (payload["company_code"], payload["document_type"], payload["fiscal_year"]),
                )
                doc_num = cur.fetchone()["doc_num"]

                # Insert Header
                cur.execute(
                    """
                    INSERT INTO finance.journal_entry_headers
                      (client_id, company_code, fiscal_year, document_number, document_type,
                       document_date, posting_date, currency, exchange_rate, external_reference,
                       header_text, created_by)
                    VALUES
                      ('200', %s, %s, %s, %s, %s, %s, %s, 1.0, %s, %s, %s)
                    """,
                    (
                        payload["company_code"],
                        payload["fiscal_year"],
                        doc_num,
                        payload["document_type"],
                        payload["document_date"],
                        payload["posting_date"],
                        payload["currency"],
                        payload.get("external_reference"),
                        payload.get("header_text"),
                        approved_by,
                    ),
                )

                # Insert Lines
                for idx, line in enumerate(payload["lines"], start=1):
                    gl_acc = str(line["gl_account"]).zfill(10)
                    dc_ind = line["debit_credit"].upper()
                    raw_amount = abs(float(line["amount"]))
                    amount = raw_amount if dc_ind == "D" else -raw_amount

                    cur.execute(
                        """
                        INSERT INTO finance.journal_entry_lines
                          (client_id, ledger, company_code, fiscal_year, document_number, line_number,
                           account_type, gl_account, debit_credit_indicator, transaction_currency,
                           amount_transaction_currency, amount_company_currency, amount_group_currency,
                           cost_center, profit_center, line_text)
                        VALUES
                          ('200', '0L', %s, %s, %s, %s, 'GL', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            payload["company_code"],
                            payload["fiscal_year"],
                            doc_num,
                            idx,
                            gl_acc,
                            dc_ind,
                            payload["currency"],
                            amount,
                            amount,
                            amount,
                            line.get("cost_center"),
                            line.get("profit_center"),
                            line.get("line_text"),
                        ),
                    )

                # Mark draft as posted
                cur.execute(
                    """
                    UPDATE finance.draft_entries
                    SET status = 'posted', approved_at = now(), approved_by = %s
                    WHERE draft_id = %s
                    """,
                    (approved_by, draft_id),
                )
                conn.commit()

                return {
                    "status": "posted",
                    "draft_id": draft_id,
                    "document_number": doc_num,
                    "company_code": payload["company_code"],
                    "fiscal_year": payload["fiscal_year"],
                }

            elif draft_type == "reverse":
                # Create Reversal Document
                orig_doc_num = payload["document_number"]
                
                # Fetch original header to mirror reversal
                cur.execute(
                    """
                    SELECT * FROM finance.journal_entry_headers
                    WHERE company_code = %s AND fiscal_year = %s AND document_number = %s
                    """,
                    (payload["company_code"], payload["fiscal_year"], orig_doc_num),
                )
                orig_header = cur.fetchone()
                
                cur.execute(
                    "SELECT finance.next_document_number('200', %s, 'AB', %s) AS doc_num",
                    (payload["company_code"], payload["fiscal_year"]),
                )
                rev_doc_num = cur.fetchone()["doc_num"]

                # Insert Reversal Header
                cur.execute(
                    """
                    INSERT INTO finance.journal_entry_headers
                      (client_id, company_code, fiscal_year, document_number, document_type,
                       document_date, posting_date, currency, exchange_rate, external_reference,
                       header_text, created_by, reverses_document)
                    VALUES
                      ('200', %s, %s, %s, 'AB', %s, %s, %s, 1.0, %s, %s, %s, %s)
                    """,
                    (
                        payload["company_code"],
                        payload["fiscal_year"],
                        rev_doc_num,
                        orig_header["document_date"],
                        payload["reversal_date"],
                        orig_header["currency"],
                        orig_header["external_reference"],
                        f"Reversal of {orig_doc_num}: {payload['reason']}",
                        approved_by,
                        orig_doc_num,
                    ),
                )

                # Link original document to reversal document
                cur.execute(
                    """
                    UPDATE finance.journal_entry_headers
                    SET reversed_by_document = %s
                    WHERE company_code = %s AND fiscal_year = %s AND document_number = %s
                    """,
                    (rev_doc_num, payload["company_code"], payload["fiscal_year"], orig_doc_num),
                )

                # Reverse lines (swap signs)
                cur.execute(
                    """
                    SELECT * FROM finance.journal_entry_lines
                    WHERE company_code = %s AND fiscal_year = %s AND document_number = %s
                    """,
                    (payload["company_code"], payload["fiscal_year"], orig_doc_num),
                )
                orig_lines = cur.fetchall()

                for idx, line in enumerate(orig_lines, start=1):
                    new_dc = "C" if line["debit_credit_indicator"] == "D" else "D"
                    new_amount = -line["amount_company_currency"]

                    cur.execute(
                        """
                        INSERT INTO finance.journal_entry_lines
                          (client_id, ledger, company_code, fiscal_year, document_number, line_number,
                           account_type, gl_account, debit_credit_indicator, transaction_currency,
                           amount_transaction_currency, amount_company_currency, amount_group_currency,
                           cost_center, profit_center, line_text)
                        VALUES
                          ('200', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            line["ledger"],
                            payload["company_code"],
                            payload["fiscal_year"],
                            rev_doc_num,
                            idx,
                            line["account_type"],
                            line["gl_account"],
                            new_dc,
                            line["transaction_currency"],
                            new_amount,
                            new_amount,
                            new_amount,
                            line["cost_center"],
                            line["profit_center"],
                            f"Reversal of line {line['line_number']}",
                        ),
                    )

                # Mark draft as posted
                cur.execute(
                    """
                    UPDATE finance.draft_entries
                    SET status = 'posted', approved_at = now(), approved_by = %s
                    WHERE draft_id = %s
                    """,
                    (approved_by, draft_id),
                )
                conn.commit()

                return {
                    "status": "posted",
                    "draft_id": draft_id,
                    "reversal_document_number": rev_doc_num,
                    "reversed_document": orig_doc_num,
                }
