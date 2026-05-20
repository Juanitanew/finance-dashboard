"""
tests/conftest.py
-----------------
Tells pytest how to set up shared test data.
The df fixture parses both PDFs once and shares the result across all tests.
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from parser import parse_statements

CREDIT_PDF = PROJECT_ROOT / "data" / "raw" / "Bank_Statement_Credit.pdf"
DEBIT_PDF  = PROJECT_ROOT / "data" / "raw" / "Bank_Statement_Debit.pdf"

# Fallback to uploads folder
if not CREDIT_PDF.exists():
    CREDIT_PDF = Path("/mnt/user-data/uploads/Bank_Statement_Credit.pdf")
if not DEBIT_PDF.exists():
    DEBIT_PDF  = Path("/mnt/user-data/uploads/Bank_Statement_Debit.pdf")


@pytest.fixture(scope="session")
def df():
    """Parse both PDFs once and reuse across all tests in the session."""
    return parse_statements(
        credit_pdf=str(CREDIT_PDF),
        debit_pdf=str(DEBIT_PDF),
    )
