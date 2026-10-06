"""
Write & Validation Tools:
- validate_journal_entry (runs in a rollback transaction; fires triggers; leaves no rows)
- post_journal_entry (stages pending draft in draft_entries)
- reverse_document (stages pending reversal draft in draft_entries)
"""

import json
from typing import Any, Optional
from datetime import date
from server.db import get_writer_connection, get_reader_connection
from server.errors import FinanceTwinError, map_db_error
from server.logging import log_tool_call


@log_tool_call("validate_journal_entry")
def validate_journal_entry(
    company_code: str,
    fiscal_year: int,
    document_type: str,
    document_date: date,
    posting_date: date,
    lines: list[dict[str, Any]],
    currency: str = "USD",
    header_text: Optional[str] = None,
    external_reference: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    """
    Simulate posting in a transaction that ALWAYS ROLLS BACK.
    Fires all DB triggers (balance, period open, blocked account, reconciliation account).
    Leaves ZERO rows in any table.
    """
    if len(lines) < 2:
        raise FinanceTwinError("MINIMUM_LINES_REQUIRED", "A journal entry must contain at least two line items.")

    with get_writer_connection() as conn:
        try:
            with conn.cursor() as cur:
                # 1. Fetch next temporary document number for simulation
                cur.execute(
                    "SELECT finance.next_document_number('200', %s, %s, %s) AS next_doc",
                    (company_code, document_type, fiscal_year),
                )
                temp_doc_num = cur.fetchone()["next_doc"]

                # 2. Insert Header (triggers header_validate)
                cur.execute(
                    """
                    INSERT INTO finance.journal_entry_headers
                      (client_id, company_code, fiscal_year, document_number, document_type,
                       document_date, posting_date, currency, exchange_rate, external_reference,
                       header_text, created_by)
                    VALUES
                      ('200', %s, %s, %s, %s, %s, %s, %s, 1.0, %s, %s, 'AGENT_VALIDATE')
                    """,
                    (
                        company_code,
                        fiscal_year,
                        temp_doc_num,
                        document_type,
                        document_date,
                        posting_date,
                        currency,
                        external_reference,
                        header_text,
                    ),
                )

                # 3. Insert Lines (triggers line_validate & balance checks)
                tb_impact = []
                for idx, line in enumerate(lines, start=1):
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
                            company_code,
                            fiscal_year,
                            temp_doc_num,
                            idx,
                            gl_acc,
                            dc_ind,
                            currency,
                            amount,
                            amount,
                            amount,
                            line.get("cost_center"),
                            line.get("profit_center"),
                            line.get("line_text"),
                        ),
                    )

                    tb_impact.append({
                        "gl_account": gl_acc,
                        "debit_credit": dc_ind,
                        "change_amount": amount,
                    })

                # Always roll back to guarantee zero persistence
                conn.rollback()

                return {
                    "valid": True,
                    "errors": [],
                    "message": "Validation succeeded. Entry is balanced and all posting constraints are satisfied.",
                    "trial_balance_impact": tb_impact,
                }
        except Exception as ex:
            conn.rollback()
            db_err = map_db_error(str(ex))
            return {
                "valid": False,
                "error_code": db_err.code,
                "message": db_err.message,
                "details": db_err.details,
            }


@log_tool_call("post_journal_entry")
def post_journal_entry(
    company_code: str,
    fiscal_year: int,
    document_type: str,
    document_date: date,
    posting_date: date,
    lines: list[dict[str, Any]],
    currency: str = "USD",
    header_text: Optional[str] = None,
    external_reference: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    session_id: str = "default",
) -> dict[str, Any]:
    """
    Stage a journal entry as a PENDING DRAFT.
    Validates first. Duplicate idempotency_key returns the existing draft without re-creating.
    The agent CANNOT approve. Approval is granted only via the harness.
    """
    # 1. First validate
    val_result = validate_journal_entry(
        company_code=company_code,
        fiscal_year=fiscal_year,
        document_type=document_type,
        document_date=document_date,
        posting_date=posting_date,
        lines=lines,
        currency=currency,
        header_text=header_text,
        external_reference=external_reference,
        session_id=session_id,
    )

    if not val_result.get("valid"):
        raise FinanceTwinError(
            code=val_result.get("error_code", "VALIDATION_FAILED"),
            message=f"Journal entry validation failed: {val_result.get('message')}",
        )

    # 2. Check Idempotency Key
    if idempotency_key:
        with get_reader_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT draft_id, status, created_at FROM finance.draft_entries WHERE idempotency_key = %s",
                    (idempotency_key,),
                )
                existing = cur.fetchone()
                if existing:
                    return {
                        "draft_id": str(existing["draft_id"]),
                        "status": existing["status"],
                        "note": "Idempotent replay: returning existing draft record.",
                    }

    # 3. Insert into draft_entries
    payload = {
        "company_code": company_code,
        "fiscal_year": fiscal_year,
        "document_type": document_type,
        "document_date": document_date.isoformat(),
        "posting_date": posting_date.isoformat(),
        "currency": currency,
        "header_text": header_text,
        "external_reference": external_reference,
        "lines": lines,
    }

    with get_writer_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO finance.draft_entries
                  (session_id, idempotency_key, draft_type, status, payload_json)
                VALUES
                  (%s, %s, 'post', 'pending', %s)
                RETURNING draft_id, status, created_at
                """,
                (session_id, idempotency_key, json.dumps(payload)),
            )
            draft = cur.fetchone()
            conn.commit()

            return {
                "draft_id": str(draft["draft_id"]),
                "status": draft["status"],
                "trial_balance_impact": val_result.get("trial_balance_impact"),
                "message": "Draft created successfully with status 'pending'. Awaiting approval.",
            }


@log_tool_call("reverse_document")
def reverse_document(
    company_code: str,
    fiscal_year: int,
    document_number: str,
    reversal_date: date,
    reason: str,
    session_id: str = "default",
) -> dict[str, Any]:
    """
    Stage a document reversal as a PENDING DRAFT.
    Checks that the document exists, is not already reversed, and has no cleared items.
    """
    doc_num = str(document_number).zfill(10)

    with get_reader_connection() as conn:
        with conn.cursor() as cur:
            # Check document header
            cur.execute(
                """
                SELECT document_number, reversed_by_document, posting_period
                FROM finance.journal_entry_headers
                WHERE company_code = %s AND fiscal_year = %s AND document_number = %s
                """,
                (company_code, fiscal_year, doc_num),
            )
            doc = cur.fetchone()
            if not doc:
                raise FinanceTwinError("DOC_NOT_FOUND", f"Document {company_code}-{fiscal_year}-{doc_num} not found.")

            if doc.get("reversed_by_document"):
                raise FinanceTwinError(
                    "ALREADY_REVERSED",
                    f"Document {doc_num} is already reversed by document {doc['reversed_by_document']}."
                )

            # Check for cleared items
            cur.execute(
                """
                SELECT line_number, clearing_document FROM finance.journal_entry_lines
                WHERE company_code = %s AND fiscal_year = %s AND document_number = %s
                  AND clearing_document IS NOT NULL
                """,
                (company_code, fiscal_year, doc_num),
            )
            cleared_lines = cur.fetchall()
            if cleared_lines:
                raise FinanceTwinError(
                    "CLEARED_ITEMS_EXIST",
                    f"Cannot reverse document {doc_num}: line {cleared_lines[0]['line_number']} is cleared by {cleared_lines[0]['clearing_document']}."
                )

    # Insert reversal draft
    payload = {
        "company_code": company_code,
        "fiscal_year": fiscal_year,
        "document_number": doc_num,
        "reversal_date": reversal_date.isoformat(),
        "reason": reason,
    }

    with get_writer_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO finance.draft_entries
                  (session_id, draft_type, status, payload_json)
                VALUES
                  (%s, 'reverse', 'pending', %s)
                RETURNING draft_id, status, created_at
                """,
                (session_id, json.dumps(payload)),
            )
            draft = cur.fetchone()
            conn.commit()

            return {
                "draft_id": str(draft["draft_id"]),
                "status": draft["status"],
                "target_document": doc_num,
                "reversal_reason": reason,
                "message": f"Reversal draft for document {doc_num} created with status 'pending'. Awaiting approval.",
            }
