"""
tests/test_parser.py
--------------------
Validates that parser.py correctly extracts and normalises transactions
from the Scotiabank credit and debit PDFs.

Run with:
    python -m pytest tests/test_parser.py -v
    
Or without pytest (plain Python):
    python tests/test_parser.py
"""

import sys
import os
import math
import pandas as pd
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — works whether you run from project root or tests/ folder
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from parser import parse_statements

# ---------------------------------------------------------------------------
# Shared fixture — parse once, reuse across all tests
# ---------------------------------------------------------------------------
CREDIT_PDF = PROJECT_ROOT / "data" / "raw" / "Bank_Statement_Credit.pdf"
DEBIT_PDF  = PROJECT_ROOT / "data" / "raw" / "Bank_Statement_Debit.pdf"

# Fallback to uploads folder (for running in the dev environment)
if not CREDIT_PDF.exists():
    CREDIT_PDF = Path("/mnt/user-data/uploads/Bank_Statement_Credit.pdf")
if not DEBIT_PDF.exists():
    DEBIT_PDF  = Path("/mnt/user-data/uploads/Bank_Statement_Debit.pdf")


def load_data() -> pd.DataFrame:
    return parse_statements(
        credit_pdf=str(CREDIT_PDF),
        debit_pdf=str(DEBIT_PDF),
    )


# ---------------------------------------------------------------------------
# Test runner (used when running as plain Python, not pytest)
# ---------------------------------------------------------------------------
_results: list[tuple[str, bool, str]] = []

def run_test(name: str, fn):
    try:
        fn()
        _results.append((name, True, ""))
        print(f"  ✅  {name}")
    except AssertionError as e:
        _results.append((name, False, str(e)))
        print(f"  ❌  {name}")
        print(f"       → {e}")
    except Exception as e:
        _results.append((name, False, f"EXCEPTION: {e}"))
        print(f"  💥  {name}")
        print(f"       → {e}")


# ===========================================================================
# TEST GROUP 1 — Row counts
# ===========================================================================
def test_total_row_count(df):
    """Combined DataFrame should have exactly 126 rows (89 credit + 37 debit)."""
    assert len(df) == 126, f"Expected 126 rows, got {len(df)}"

def test_credit_row_count(df):
    """Credit card should produce exactly 89 transactions."""
    cc = df[df["source"] == "credit_card"]
    assert len(cc) == 89, f"Expected 89 credit rows, got {len(cc)}"

def test_debit_row_count(df):
    """Chequing account should produce exactly 37 transactions."""
    ch = df[df["source"] == "chequing"]
    assert len(ch) == 37, f"Expected 37 debit rows, got {len(ch)}"


# ===========================================================================
# TEST GROUP 2 — Totals match the PDF's own subtotals (ground truth)
# ===========================================================================
def test_credit_charges_total(df):
    """
    Sum of all positive credit-card amounts must equal $3,116.64
    (the SUB-TOTAL DEBITS printed on page 4 of the credit PDF).
    """
    cc = df[df["source"] == "credit_card"]
    total = round(cc[cc["amount"] > 0]["amount"].sum(), 2)
    assert total == 3116.64, f"Credit charges: expected $3116.64, got ${total}"

def test_credit_refunds_total(df):
    """
    Sum of all negative credit-card amounts must equal $4,902.22
    (the SUB-TOTAL CREDITS printed on page 4 of the credit PDF).
    """
    cc = df[df["source"] == "credit_card"]
    total = round(cc[cc["amount"] < 0]["amount"].abs().sum(), 2)
    assert total == 4902.22, f"Credit refunds: expected $4902.22, got ${total}"

def test_debit_withdrawals_total(df):
    """
    Sum of all positive chequing amounts must equal $17,812.66
    (the 'total withdrawals' printed on page 1 of the debit PDF).
    """
    ch = df[df["source"] == "chequing"]
    total = round(ch[ch["amount"] > 0]["amount"].sum(), 2)
    assert total == 17812.66, f"Debit withdrawals: expected $17812.66, got ${total}"

def test_debit_deposits_total(df):
    """
    Sum of all negative chequing amounts must equal $14,525.87
    (the 'total deposits' printed on page 1 of the debit PDF).
    """
    ch = df[df["source"] == "chequing"]
    total = round(ch[ch["amount"] < 0]["amount"].abs().sum(), 2)
    assert total == 14525.87, f"Debit deposits: expected $14525.87, got ${total}"


# ===========================================================================
# TEST GROUP 3 — Spot-check specific transactions
# ===========================================================================
def test_sephora_transaction(df):
    """SEPHORA charge: $141.25 on 2026-04-03, credit card."""
    row = df[df["description"].str.contains("SEPHORA", case=False)]
    assert len(row) == 1, f"Expected 1 SEPHORA row, got {len(row)}"
    assert row.iloc[0]["amount"] == 141.25
    assert str(row.iloc[0]["trans_date"]) == "2026-04-03"
    assert row.iloc[0]["source"] == "credit_card"

def test_lagos_refund_is_negative(df):
    """
    BANANA BEACH HOUSE LAGOS was a refund (shown as 881.45- in PDF).
    Amount must be negative (-881.45).
    """
    row = df[df["description"].str.contains("BANANA BEACH", case=False)]
    assert len(row) == 1, f"Expected 1 Lagos row, got {len(row)}"
    assert row.iloc[0]["amount"] == -881.45, \
        f"Lagos should be -881.45, got {row.iloc[0]['amount']}"

def test_hotel_booking_refund(df):
    """
    BKG*HOTEL AT BOOKING.C on Apr 8 was a $546.22 refund (negative).
    """
    rows = df[
        df["description"].str.contains("BOOKING", case=False) &
        (df["trans_date"] == date(2026, 4, 8))
    ]
    assert len(rows) == 1, f"Expected 1 Booking.com refund on Apr 8, got {len(rows)}"
    assert rows.iloc[0]["amount"] == -546.22

def test_payroll_deposits_are_negative(df):
    """Payroll deposits should be negative (money coming in)."""
    payroll = df[df["description"].str.contains("Payroll|payroll", case=False)]
    assert len(payroll) == 2, f"Expected 2 payroll rows, got {len(payroll)}"
    assert (payroll["amount"] < 0).all(), \
        f"All payroll entries should be negative:\n{payroll[['trans_date','description','amount']]}"

def test_tax_refund_is_negative(df):
    """Tax refund ($5,329.06) should be negative (money coming in)."""
    row = df[df["description"].str.contains("Taxrefund|Tax refund", case=False)]
    assert len(row) == 1
    assert row.iloc[0]["amount"] == -5329.06, \
        f"Tax refund should be -5329.06, got {row.iloc[0]['amount']}"

def test_investment_is_positive(df):
    """Wealthsimple investment transfer ($2,164.00) should be positive (money out)."""
    row = df[df["description"].str.contains("Investment", case=False)]
    assert len(row) == 1
    assert row.iloc[0]["amount"] == 2164.00

def test_openai_subscription(df):
    """OpenAI ChatGPT subscription: $28.25, credit card."""
    row = df[df["description"].str.contains("OPENAI", case=False)]
    assert len(row) == 1
    assert row.iloc[0]["amount"] == 28.25
    assert row.iloc[0]["source"] == "credit_card"

def test_multiple_uber_trips(df):
    """There are multiple Uber transactions — all should be positive charges."""
    uber = df[df["description"].str.contains("UBER", case=False)]
    assert len(uber) > 5, f"Expected many Uber rows, got {len(uber)}"
    assert (uber["amount"] > 0).all(), \
        "All Uber charges should be positive (money out)"


# ===========================================================================
# TEST GROUP 4 — Data quality / schema checks
# ===========================================================================
def test_no_null_amounts(df):
    """No transaction should have a null/NaN amount."""
    nulls = df["amount"].isna().sum()
    assert nulls == 0, f"{nulls} rows have null amounts"

def test_no_null_dates(df):
    """No transaction should have a null trans_date."""
    nulls = df["trans_date"].isna().sum()
    assert nulls == 0, f"{nulls} rows have null trans_date"

def test_no_null_descriptions(df):
    """No transaction should have a null description."""
    nulls = df["description"].isna().sum()
    assert nulls == 0, f"{nulls} rows have null descriptions"

def test_no_zero_amounts(df):
    """No transaction should have an amount of exactly zero."""
    zeros = (df["amount"] == 0).sum()
    assert zeros == 0, f"{zeros} rows have zero amounts"

def test_source_values_valid(df):
    """The 'source' column should only contain 'credit_card' or 'chequing'."""
    valid = {"credit_card", "chequing"}
    actual = set(df["source"].unique())
    assert actual == valid, f"Unexpected source values: {actual - valid}"

def test_type_values_valid(df):
    """The 'type' column should only contain 'credit' or 'debit'."""
    valid = {"credit", "debit"}
    actual = set(df["type"].unique())
    assert actual == valid, f"Unexpected type values: {actual - valid}"

def test_dates_within_statement_period(df):
    """All dates should fall within the combined statement period (Mar 22 – Apr 30 2026)."""
    dates = pd.to_datetime(df["trans_date"])
    assert dates.min() >= pd.Timestamp("2026-03-22"), \
        f"Earliest date {dates.min()} is before Mar 22 2026"
    assert dates.max() <= pd.Timestamp("2026-04-30"), \
        f"Latest date {dates.max()} is after Apr 30 2026"

def test_no_flagged_rows(df):
    """After parsing, zero rows should be flagged for manual review."""
    flagged = df[df["parse_flag"] == "REVIEW"]
    if len(flagged) > 0:
        details = flagged[["trans_date", "description", "amount", "flag_reason"]].to_string()
        assert False, f"{len(flagged)} rows flagged for review:\n{details}"

def test_amounts_are_floats(df):
    """The 'amount' column should be float64."""
    assert df["amount"].dtype == "float64", \
        f"Expected float64, got {df['amount'].dtype}"

def test_no_duplicate_credit_ref_numbers(df):
    """
    Credit card ref numbers (001–089) should each appear exactly once.
    Duplicates would indicate a transaction was parsed twice.
    """
    cc = df[df["source"] == "credit_card"].copy()
    cc = cc[cc["ref_no"] != ""]
    dupes = cc[cc.duplicated(subset=["ref_no"], keep=False)]
    assert len(dupes) == 0, \
        f"Duplicate ref numbers found:\n{dupes[['ref_no','description','amount']]}"


# ===========================================================================
# Entry point — run all tests
# ===========================================================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  FINANCE DASHBOARD — PARSER TEST SUITE")
    print("=" * 60)

    # Load data once
    print("\n[setup] Parsing PDFs...")
    try:
        df = load_data()
        print(f"[setup] Loaded {len(df)} rows\n")
    except Exception as e:
        print(f"[setup] FATAL — could not parse PDFs: {e}")
        sys.exit(1)

    # Group 1: Row counts
    print("── Group 1: Row counts ──────────────────────────────────")
    run_test("Total row count is 126",         lambda: test_total_row_count(df))
    run_test("Credit card has 89 rows",         lambda: test_credit_row_count(df))
    run_test("Chequing has 37 rows",            lambda: test_debit_row_count(df))

    # Group 2: Totals
    print("\n── Group 2: Totals match PDF ground truth ───────────────")
    run_test("Credit charges  = $3,116.64",     lambda: test_credit_charges_total(df))
    run_test("Credit refunds  = $4,902.22",     lambda: test_credit_refunds_total(df))
    run_test("Debit withdrawals = $17,812.66",  lambda: test_debit_withdrawals_total(df))
    run_test("Debit deposits    = $14,525.87",  lambda: test_debit_deposits_total(df))

    # Group 3: Spot checks
    print("\n── Group 3: Spot-check specific transactions ────────────")
    run_test("SEPHORA $141.25 on Apr 3",        lambda: test_sephora_transaction(df))
    run_test("Lagos hotel is a refund (-881.45)",lambda: test_lagos_refund_is_negative(df))
    run_test("Booking.com Apr 8 refund (-546.22)",lambda: test_hotel_booking_refund(df))
    run_test("Payroll deposits are negative",   lambda: test_payroll_deposits_are_negative(df))
    run_test("Tax refund is negative (-5329.06)",lambda: test_tax_refund_is_negative(df))
    run_test("Investment is positive (2164.00)", lambda: test_investment_is_positive(df))
    run_test("OpenAI subscription $28.25",      lambda: test_openai_subscription(df))
    run_test("All Uber charges are positive",   lambda: test_multiple_uber_trips(df))

    # Group 4: Data quality
    print("\n── Group 4: Data quality / schema ───────────────────────")
    run_test("No null amounts",                 lambda: test_no_null_amounts(df))
    run_test("No null dates",                   lambda: test_no_null_dates(df))
    run_test("No null descriptions",            lambda: test_no_null_descriptions(df))
    run_test("No zero-dollar transactions",     lambda: test_no_zero_amounts(df))
    run_test("Source values valid",             lambda: test_source_values_valid(df))
    run_test("Type values valid",               lambda: test_type_values_valid(df))
    run_test("All dates within statement period",lambda: test_dates_within_statement_period(df))
    run_test("Zero rows flagged for review",    lambda: test_no_flagged_rows(df))
    run_test("Amounts are float64",             lambda: test_amounts_are_floats(df))
    run_test("No duplicate credit ref numbers", lambda: test_no_duplicate_credit_ref_numbers(df))

    # Summary
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total  = len(_results)

    print("\n" + "=" * 60)
    print(f"  Results: {passed}/{total} passed", end="")
    print("  🎉" if failed == 0 else f"  ({failed} FAILED)")
    print("=" * 60 + "\n")

    sys.exit(0 if failed == 0 else 1)
