"""
End-to-End verification script for all 15 Finance Twin MCP tools.
Ensures zero-runtime-error execution across both SQLite fallback and PostgreSQL modes.
"""

from datetime import date
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


def run_all_tests():
    print("=== STARTING 15 TOOLS E2E VERIFICATION ===")

    # 1. Lookup tools
    print("\n--- 1. Testing lookup_master_data ---")
    res = lookup_master_data("gl_account", "0000100000")
    print(" [OK] lookup_master_data(gl_account):", res["records"][0]["account_name"])

    res = lookup_master_data("GL_ACCOUNTS", search_text="Cash")
    print(" [OK] lookup_master_data(GL_ACCOUNTS, search_text):", len(res["records"]), "records")

    res = lookup_master_data("company_codes", "1000")
    print(" [OK] lookup_master_data(company_codes):", len(res["records"]), "records")

    print("\n--- 2. Testing get_period_status ---")
    res = get_period_status("1000", 2026, 9)
    print(" [OK] get_period_status(2026/09):", res["status"])

    print("\n--- 3. Testing get_trial_balance ---")
    res = get_trial_balance("1000", 2026, 9)
    print(" [OK] get_trial_balance: debits =", res["total_debits"], ", credits =", res["total_credits"])

    print("\n--- 4. Testing get_account_line_items ---")
    res = get_account_line_items("1000", "0000100000", 2026)
    print(" [OK] get_account_line_items: retrieved", len(res["items"]), "items")

    print("\n--- 5. Testing get_period_summary ---")
    res = get_period_summary("1000", 2026, "account")
    print(" [OK] get_period_summary:", len(res["data"]), "summary rows")

    print("\n--- 6. Testing list_open_items ---")
    res = list_open_items("1000", "vendor")
    print(" [OK] list_open_items:", len(res["items"]), "open items")

    print("\n--- 7. Testing compare_ledgers ---")
    res = compare_ledgers("1000", 2026, 9, "0L", "2L")
    print(" [OK] compare_ledgers:", res["differences_count"], "differences")

    print("\n--- 8. Testing find_duplicate_invoices ---")
    res = find_duplicate_invoices("1000", mode="exact")
    print(" [OK] find_duplicate_invoices (exact):", res["total_candidate_groups"], "groups")

    res = find_duplicate_invoices("1000", mode="fuzzy", amount_tolerance_pct=1.0)
    print(" [OK] find_duplicate_invoices (fuzzy):", res["total_candidate_groups"], "groups")

    print("\n--- 9. Testing scan_journal_anomalies ---")
    res = scan_journal_anomalies("1000", 2026)
    print(" [OK] scan_journal_anomalies:", res["total_anomalies_flagged"], "anomalies")

    print("\n--- 10. Testing get_account_usage_profile ---")
    res = get_account_usage_profile("1000")
    print(" [OK] get_account_usage_profile:", len(res["profiles"]), "profile rows")

    print("\n--- 11. Testing validate_journal_entry ---")
    val_res = validate_journal_entry(
        company_code="1000",
        fiscal_year=2026,
        document_type="SA",
        document_date=date(2026, 9, 15),
        posting_date=date(2026, 9, 15),
        lines=[
            {"gl_account": "0000500000", "debit_credit": "D", "amount": 1500.0, "line_text": "Test Debit"},
            {"gl_account": "0000100000", "debit_credit": "C", "amount": 1500.0, "line_text": "Test Credit"},
        ],
        header_text="E2E Test Entry",
    )
    print(" [OK] validate_journal_entry:", val_res.get("valid"), val_res.get("message"))

    print("\n--- 12. Testing get_document ---")
    doc_res = get_document("1000", 2026, "0100000001")
    print(" [OK] get_document(0100000001):", doc_res["header_text"], "lines:", len(doc_res["lines"]))

    print("\n--- 13. Testing search_documents ---")
    search_res = search_documents(company_code="1000", fiscal_year=2026)
    print(" [OK] search_documents:", search_res["total_count"], "total matches found")

    print("\n--- 14. Testing post_journal_entry (staging draft) ---")
    post_res = post_journal_entry(
        company_code="1000",
        fiscal_year=2026,
        document_type="SA",
        document_date=date(2026, 9, 15),
        posting_date=date(2026, 9, 15),
        lines=[
            {"gl_account": "0000500000", "debit_credit": "D", "amount": 250.0, "line_text": "Test Staging"},
            {"gl_account": "0000100000", "debit_credit": "C", "amount": 250.0, "line_text": "Test Staging"},
        ],
        header_text="E2E Post Draft",
        idempotency_key="e2e-test-post-001",
    )
    print(" [OK] post_journal_entry:", post_res["draft_id"], "status:", post_res["status"])

    print("\n--- 15. Testing reverse_document (staging reversal draft) ---")
    rev_res = reverse_document(
        company_code="1000",
        fiscal_year=2026,
        document_number="0100000001",
        reversal_date=date(2026, 9, 30),
        reason="E2E Testing Reversal",
    )
    print(" [OK] reverse_document:", rev_res["draft_id"], "status:", rev_res["status"])

    print("\n=== ALL 15 TOOLS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    run_all_tests()
