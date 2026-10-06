"""
Unit tests for Finance Twin MCP tools, error handling, and models.
"""

import pytest
from server.errors import map_db_error, FinanceTwinError
from server.models import (
    DocumentKey,
    TrialBalanceRequest,
    FindDuplicateInvoicesRequest,
    PostJournalEntryRequest,
    PostJournalEntryLine,
)


def test_document_key_validation():
    # Valid 10-digit zero-padded key
    key = DocumentKey(company_code="1000", fiscal_year=2026, document_number="0000001001")
    assert key.document_number == "0000001001"
    assert key.company_code == "1000"


def test_document_key_invalid_length():
    with pytest.raises(Exception):
        DocumentKey(company_code="1000", fiscal_year=2026, document_number="1001")


def test_db_error_mapping():
    err1 = map_db_error("ERROR: Document 1000-2026-0000001001 is not balanced: debits 1000 != credits 0")
    assert err1.code == "DOC_NOT_BALANCED"

    err2 = map_db_error("ERROR: Posting period 8 is not open for company code 1000")
    assert err2.code == "PERIOD_CLOSED"

    err3 = map_db_error("ERROR: Account 0000300000 is a reconciliation account; direct posting not allowed")
    assert err3.code == "RECON_ACCOUNT_DIRECT_POSTING"

    err4 = map_db_error("ERROR: G/L account 0000999999 is blocked for posting")
    assert err4.code == "ACCOUNT_BLOCKED"


def test_post_journal_entry_model():
    req = PostJournalEntryRequest(
        company_code="1000",
        fiscal_year=2026,
        document_type="SA",
        document_date="2026-09-30",
        posting_date="2026-09-30",
        currency="USD",
        lines=[
            PostJournalEntryLine(gl_account="0000500000", debit_credit="D", amount=2500000.00),
            PostJournalEntryLine(gl_account="0000210000", debit_credit="C", amount=-2500000.00),
        ],
        idempotency_key="test-key-01",
    )
    assert len(req.lines) == 2
    assert req.lines[0].debit_credit == "D"
