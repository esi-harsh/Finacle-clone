"""
SAP-compatible error mapping and exceptions for the Finance Twin MCP Server.
"""

from typing import Any, Optional
from pydantic import BaseModel


class FinanceTwinError(Exception):
    def __init__(self, code: str, message: str, details: Optional[dict[str, Any]] = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }


# Database trigger message to SAP error code mapping
TRIGGER_ERROR_MAP = {
    "is not balanced": "DOC_NOT_BALANCED",
    "is not open": "PERIOD_CLOSED",
    "is a reconciliation account": "RECON_ACCOUNT_DIRECT_POSTING",
    "is blocked": "ACCOUNT_BLOCKED",
    "only allows postings in currency": "CURRENCY_NOT_ALLOWED",
    "does not belong to fiscal year": "INVALID_POSTING_DATE",
    "must have at least two line items": "MINIMUM_LINES_REQUIRED",
    "cannot be deleted": "CANNOT_DELETE_POSTED_DOC",
}


def map_db_error(error_msg: str, details: Optional[dict[str, Any]] = None) -> FinanceTwinError:
    """Map PostgreSQL trigger/constraint errors into standard SAP error codes."""
    for pattern, code in TRIGGER_ERROR_MAP.items():
        if pattern in error_msg:
            return FinanceTwinError(
                code=code,
                message=error_msg,
                details=details or {},
                retryable=False,
            )
    return FinanceTwinError(
        code="DB_EXECUTION_ERROR",
        message=error_msg,
        details=details or {},
        retryable=False,
    )
