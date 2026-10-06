"""
Pydantic input and output schemas for all 15 Finance Twin MCP tools.
"""

from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Common & Pagination Models
# ---------------------------------------------------------

class PaginationParams(BaseModel):
    limit: int = Field(50, ge=1, le=200, description="Max rows to return (default 50, max 200)")
    cursor: Optional[int] = Field(None, ge=0, description="Offset cursor for pagination")


class PagedResult(BaseModel):
    total_count: int
    next_cursor: Optional[int] = None
    truncated: bool = False


# ---------------------------------------------------------
# 1. Lookup Models (get_document, search_documents, lookup_master_data, get_period_status)
# ---------------------------------------------------------

class DocumentKey(BaseModel):
    company_code: str = Field(..., min_length=4, max_length=4, description="4-digit company code (e.g. '1000')")
    fiscal_year: int = Field(..., ge=2000, le=2099, description="4-digit fiscal year (e.g. 2026)")
    document_number: str = Field(..., pattern=r"^[0-9]{10}$", description="10-digit zero-padded document number")


class JournalLineItem(BaseModel):
    line_number: int
    gl_account: str
    account_type: str
    debit_credit_indicator: str
    amount_company_currency: float
    amount_transaction_currency: float
    transaction_currency: str
    cost_center: Optional[str] = None
    profit_center: Optional[str] = None
    vendor_id: Optional[str] = None
    customer_id: Optional[str] = None
    is_open_item: bool = False
    clearing_document: Optional[str] = None
    clearing_date: Optional[date] = None


class DocumentDetail(BaseModel):
    client_id: str
    company_code: str
    fiscal_year: int
    document_number: str
    document_type: str
    document_date: date
    posting_date: date
    posting_period: int
    currency: str
    exchange_rate: float
    external_reference: Optional[str] = None
    header_text: Optional[str] = None
    created_by: str
    created_at: datetime
    reverses_document: Optional[str] = None
    reversed_by_document: Optional[str] = None
    lines: list[JournalLineItem] = []
    tax_lines: list[dict[str, Any]] = []


class SearchDocumentsFilter(BaseModel):
    company_code: Optional[str] = None
    fiscal_year: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    document_type: Optional[str] = None
    created_by: Optional[str] = None
    gl_account: Optional[str] = None
    vendor_id: Optional[str] = None
    external_reference: Optional[str] = None
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    text_search: Optional[str] = None
    ledger: Optional[str] = "0L"
    limit: int = Field(50, ge=1, le=200)
    cursor: Optional[int] = None


class MasterDataLookupRequest(BaseModel):
    object_type: str = Field(..., description="gl_account | cost_center | profit_center | document_type | company_code")
    id: Optional[str] = Field(None, description="Exact ID/code")
    search_text: Optional[str] = Field(None, description="Search text in description/name")
    company_code: Optional[str] = Field(None, description="Required for company-specific account settings")


class PeriodStatusRequest(BaseModel):
    company_code: str
    fiscal_year: int
    period: int = Field(..., ge=1, le=16)


# ---------------------------------------------------------
# 2. Balances & Reporting Models
# ---------------------------------------------------------

class TrialBalanceRequest(BaseModel):
    company_code: str
    fiscal_year: int
    period: int = Field(..., ge=1, le=16)
    ledger: str = Field("0L", description="0L (US GAAP) or 2L (IFRS)")
    compare_period: Optional[int] = Field(None, ge=1, le=16)


class TrialBalanceItem(BaseModel):
    gl_account: str
    account_name: str
    account_type: str
    debit_total: float
    credit_total: float
    balance: float
    abnormal_flag: bool = False
    prior_balance: Optional[float] = None


class AccountLineItemsRequest(BaseModel):
    company_code: str
    gl_account: str
    fiscal_year: int
    period_from: int = Field(1, ge=1, le=16)
    period_to: int = Field(12, ge=1, le=16)
    ledger: str = "0L"
    limit: int = Field(50, ge=1, le=200)
    cursor: Optional[int] = None


class PeriodSummaryRequest(BaseModel):
    company_code: str
    fiscal_year: int
    group_by: str = Field(..., description="account | cost_center | profit_center")
    period_from: int = Field(1, ge=1, le=16)
    period_to: int = Field(12, ge=1, le=16)
    ledger: str = "0L"


class OpenItemsRequest(BaseModel):
    account_type: str = Field("vendor", description="vendor | customer")
    company_code: str
    vendor_id: Optional[str] = None
    as_of_date: Optional[date] = None
    limit: int = Field(50, ge=1, le=200)
    cursor: Optional[int] = None


class CompareLedgersRequest(BaseModel):
    company_code: str
    fiscal_year: int
    period: int
    ledger_a: str = "0L"
    ledger_b: str = "2L"


# ---------------------------------------------------------
# 3. Analysis Helpers
# ---------------------------------------------------------

class FindDuplicateInvoicesRequest(BaseModel):
    company_code: str
    mode: str = Field("exact", description="'exact' (same ref+amount) or 'fuzzy' (typo/shifted date/tolerance)")
    window_days: int = Field(90, ge=1, le=365)
    amount_tolerance_pct: float = Field(0.0, ge=0.0, le=5.0)
    vendor_id: Optional[str] = None


class ScanAnomaliesRequest(BaseModel):
    company_code: str
    fiscal_year: int
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    rules: list[str] = Field(
        default=["weekend_posting", "round_amount", "near_period_end", "after_close", "rare_account", "unusual_creator"],
        description="Rules to scan for"
    )


class AccountUsageProfileRequest(BaseModel):
    company_code: str
    vendor_id: Optional[str] = None
    text_pattern: Optional[str] = None
    cost_center: Optional[str] = None


# ---------------------------------------------------------
# 4. Validation and Write Models
# ---------------------------------------------------------

class PostJournalEntryLine(BaseModel):
    gl_account: str
    debit_credit: str = Field(..., pattern=r"^[DCdc]$", description="'D' for Debit (+), 'C' for Credit (-)")
    amount: float = Field(..., description="Amount (positive for D, negative for C or absolute with D/C flag)")
    transaction_currency: Optional[str] = None
    cost_center: Optional[str] = None
    profit_center: Optional[str] = None
    vendor_id: Optional[str] = None
    customer_id: Optional[str] = None
    line_text: Optional[str] = None


class PostJournalEntryRequest(BaseModel):
    company_code: str
    fiscal_year: int
    document_type: str = Field("SA", description="Document type: SA, KR, KZ, AB, etc.")
    document_date: date
    posting_date: date
    currency: str = "USD"
    header_text: Optional[str] = None
    external_reference: Optional[str] = None
    lines: list[PostJournalEntryLine] = Field(..., min_length=2)
    idempotency_key: Optional[str] = None
    session_id: Optional[str] = None


class ReverseDocumentRequest(BaseModel):
    company_code: str
    fiscal_year: int
    document_number: str
    reversal_date: date
    reason: str
    session_id: Optional[str] = None
