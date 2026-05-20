"""
parser.py
---------
Extracts transactions from Scotiabank credit (Visa) and debit (Preferred
Package) PDF statements, normalises them into a common schema, and flags
any rows that couldn't be parsed for manual review.

Output columns
--------------
ref_no          : reference number (credit only, '' for debit)
trans_date      : datetime.date – transaction date
post_date       : datetime.date – posting date  (credit only, same as trans_date for debit)
description     : str           – merchant / payee name, cleaned
amount          : float         – positive = money OUT (charge/withdrawal)
                                  negative = money IN (credit/refund/deposit)
type            : 'debit' | 'credit'
source          : 'credit_card' | 'chequing'
parse_flag      : '' | 'REVIEW'  – non-empty means the row needs a human look
flag_reason     : str           – why it was flagged
"""

import re
import pdfplumber
from datetime import datetime, date
from pathlib import Path
import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The PDFs use abbreviated month names with a 2-digit day and no year.
# We infer the year from the statement period that appears in the header.
MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_date(raw: str, year: int) -> date | None:
    """Convert 'Mar 24' or 'Apr 1' to a date object."""
    raw = raw.strip()
    parts = raw.split()
    if len(parts) != 2:
        return None
    month_str, day_str = parts
    month = MONTH_MAP.get(month_str.lower())
    if not month:
        return None
    try:
        return date(year, month, int(day_str))
    except ValueError:
        return None


def parse_amount(raw: str) -> tuple[float | None, str]:
    """
    Convert amount string to float.
    Scotiabank uses a trailing '-' for credits (e.g. '881.45-').
    Returns (float, flag_reason).
    """
    raw = raw.strip()
    if not raw:
        return None, "empty amount"
    # Remove commas (thousands separator)
    raw = raw.replace(",", "")
    # Strip leading '$' if present
    raw = raw.lstrip("$")
    negative = raw.endswith("-")
    raw = raw.rstrip("-").strip()
    try:
        value = float(raw)
        return (-value if negative else value), ""
    except ValueError:
        return None, f"unparseable amount: '{raw}'"


def infer_year(text: str) -> int:
    """Extract statement year from page text."""
    m = re.search(r"\b(20\d{2})\b", text)
    if m:
        return int(m.group(1))
    return datetime.today().year


# ---------------------------------------------------------------------------
# Credit card parser  (Scotiabank Scene+ Visa)
# ---------------------------------------------------------------------------

# Pattern:  NNN  Mon DD  Mon DD  DESCRIPTION   AMOUNT
# The ref# is 3 digits; dates are abbreviated month + 1-2 digit day.
# Amounts may be negative (trailing '-').
CREDIT_TXN = re.compile(
    r"^(\d{3})\s+"                      # ref#
    r"([A-Za-z]{3}\s+\d{1,2})\s+"      # trans date
    r"([A-Za-z]{3}\s+\d{1,2})\s+"      # post date
    r"(.+?)\s+"                          # description (non-greedy)
    r"(\d[\d,]*\.\d{2}-?)$"             # amount
)

# Some long descriptions wrap to the next line (e.g. 'BANANA BEACH HOUSE LAGOS\nAMT 567.00 EUR')
# We capture those continuation lines and append them to the description.
CONTINUATION = re.compile(r"^(AMT\s+[\d.,]+\s+[A-Z]{3})$")


def parse_credit_pdf(pdf_path: str) -> pd.DataFrame:
    """Return a DataFrame of transactions from a Scotiabank Visa statement."""
    rows = []
    flagged = []
    year = datetime.today().year

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""

            # Grab statement year from any page that has it
            y = infer_year(text)
            if y:
                year = y

            lines = text.splitlines()
            prev_row = None  # used for multi-line descriptions

            for line in lines:
                line = line.strip()
                m = CREDIT_TXN.match(line)
                if m:
                    ref, trans_raw, post_raw, desc, amt_raw = m.groups()
                    desc = desc.strip()
                    trans_d = parse_date(trans_raw, year)
                    post_d  = parse_date(post_raw, year)
                    amount, err = parse_amount(amt_raw)

                    flag, reason = "", ""
                    if trans_d is None:
                        flag, reason = "REVIEW", f"bad trans_date: '{trans_raw}'"
                    elif post_d is None:
                        flag, reason = "REVIEW", f"bad post_date: '{post_raw}'"
                    elif amount is None:
                        flag, reason = "REVIEW", err

                    row = {
                        "ref_no":      ref,
                        "trans_date":  trans_d,
                        "post_date":   post_d,
                        "description": desc,
                        "amount":      amount,
                        "type":        "credit",
                        "source":      "credit_card",
                        "parse_flag":  flag,
                        "flag_reason": reason,
                    }
                    rows.append(row)
                    prev_row = row

                elif prev_row is not None and CONTINUATION.match(line):
                    # Append foreign-currency detail to the previous description
                    prev_row["description"] += " | " + line
                else:
                    prev_row = None  # reset; this line isn't a continuation

    df = pd.DataFrame(rows)
    return df


# ---------------------------------------------------------------------------
# Debit / chequing parser  (Scotiabank Preferred Package)
# ---------------------------------------------------------------------------

# The debit PDF collapses spaces so all words run together.
# Strategy: extract each page's text and look for the date + transaction block.
#
# Pattern (after cleaning):  Apr DD  TRANSACTION TYPE  [amount_w]  [amount_d]  BALANCE
# The 'withdrawn' column comes before 'deposited', and one of the two is blank.
# We detect which column is which by the column header.

_MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"

DEBIT_TXN = re.compile(
    rf"^({_MON}\s*\d{{1,2}})\s+"   # date  e.g. "Apr 2" or "Mar13"
    r"(.+?)\s+"                      # description (non-greedy)
    r"([\d,]+\.\d{2})\s+"         # first numeric  (withdrawn OR deposited)
    r"([\d,]+\.\d{2})\s+"         # second numeric (deposited OR balance)
    r"([\d,]+\.\d{2})$"            # balance (always last)
)

DEBIT_TXN_2COL = re.compile(
    rf"^({_MON}\s*\d{{1,2}})\s+"   # date
    r"(.+?)\s+"                      # description
    r"([\d,]+\.\d{2})\s+"         # single amount
    r"([\d,]+\.\d{2})$"            # balance
)

# Keywords that indicate money coming IN (negative amount = deposit/income)
DEBIT_INCOME_KEYWORDS = {
    "deposit", "payroll", "payrolldep", "taxrefund", "gst", "hst",
    "provincialpayment", "provincial payment", "mb-transferfrom",
    "mb-transfer from", "mbtransferfrom", "interac e-transfer",
}

# Keywords that indicate money going OUT (positive amount = withdrawal/purchase)
DEBIT_EXPENSE_KEYWORDS = {
    "withdrawal", "pointofsalepurchase", "point of sale purchase",
    "investment", "mb-transferto", "mb-transfer to", "mbtransferto",
    "credit card", "creditcard", "hydrobill", "hydro bill",
    "bill payment", "billpayment",
}


def _clean_debit_line(line: str) -> str:
    """The debit PDF merges words. Re-insert spaces at common boundaries."""
    # Insert space before capital letters that follow lowercase (CamelCase joins)
    line = re.sub(r"([a-z])([A-Z])", r"\1 \2", line)
    # Insert space before digits that follow letters (e.g. 'Apr2' → 'Apr 2')
    line = re.sub(r"([A-Za-z])(\d)", r"\1 \2", line)
    # Insert space before letters that follow digits (e.g. '4310.66Apr' → '4310.66 Apr')
    line = re.sub(r"(\d)([A-Za-z])", r"\1 \2", line)
    return line.strip()


def _extract_debit_transactions_from_text(text: str, year: int) -> list[dict]:
    """Parse all transaction lines from one page of a debit statement."""
    rows = []
    lines = text.splitlines()

    # Skip header/boilerplate lines (no 'Apr' prefix)
    # Also skip the Opening/Closing Balance lines
    skip_keywords = {
        "openingbalance", "closingbalance", "openingbal", "closingbal",
        "opening balance", "closing balance",
    }

    for line in lines:
        cleaned = _clean_debit_line(line)
        lower = cleaned.lower().replace(" ", "")

        # Skip non-transaction lines — must start with a 3-letter month name
        if not re.match(r"^[A-Z][a-z]{2}\s*\d", cleaned):
            continue
        if any(kw in lower for kw in skip_keywords):
            continue

        # Try 3-number pattern (withdrawn, deposited, balance) first
        m3 = DEBIT_TXN.match(cleaned)
        m2 = DEBIT_TXN_2COL.match(cleaned)

        if m3:
            date_raw, desc, n1, n2, balance = m3.groups()
            # n1=withdrawn, n2=deposited; the non-zero one is the actual amount
            # In practice exactly one of n1/n2 is the meaningful amount;
            # n2 here is the deposited column.  We treat n1 as withdrawal.
            withdrawn  = float(n1.replace(",", ""))
            deposited  = float(n2.replace(",", ""))
            # If both are non-zero something is odd — flag it
            if withdrawn > 0 and deposited > 0:
                flag, reason = "REVIEW", "both withdrawn and deposited non-zero"
                amount = withdrawn  # best guess
            elif deposited > 0:
                amount = -deposited   # money IN → negative
                flag, reason = "", ""
            else:
                amount = withdrawn    # money OUT → positive
                flag, reason = "", ""
        elif m2:
            date_raw, desc, n1, balance = m2.groups()
            raw_amount = float(n1.replace(",", ""))
            desc_lower = desc.lower().replace(" ", "").replace("-", "")
            if any(kw.replace(" ", "") in desc_lower for kw in DEBIT_INCOME_KEYWORDS):
                amount = -raw_amount   # money IN
                flag, reason = "", ""
            elif any(kw.replace(" ", "") in desc_lower for kw in DEBIT_EXPENSE_KEYWORDS):
                amount = raw_amount    # money OUT
                flag, reason = "", ""
            else:
                amount = raw_amount
                flag, reason = "REVIEW", "unknown direction — check manually"
        else:
            continue  # line matched 'Apr' prefix but not our pattern — skip

        trans_d = parse_date(date_raw, year)
        if trans_d is None:
            flag, reason = "REVIEW", f"bad date: '{date_raw}'"

        rows.append({
            "ref_no":      "",
            "trans_date":  trans_d,
            "post_date":   trans_d,   # debit statements don't have a separate post date
            "description": desc.strip(),
            "amount":      amount,
            "type":        "debit",
            "source":      "chequing",
            "parse_flag":  flag,
            "flag_reason": reason,
        })

    return rows


def parse_debit_pdf(pdf_path: str) -> pd.DataFrame:
    """Return a DataFrame of transactions from a Scotiabank debit statement."""
    all_rows = []
    year = datetime.today().year

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            y = infer_year(text)
            if y:
                year = y
            rows = _extract_debit_transactions_from_text(text, year)
            all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    return df


# ---------------------------------------------------------------------------
# Post-processing / normalisation
# ---------------------------------------------------------------------------

def clean_description(desc: str) -> str:
    """Normalise merchant names for easier matching later."""
    # Collapse multiple spaces
    desc = re.sub(r"\s{2,}", " ", desc).strip()
    # Remove trailing location noise like 'TORONTO ON', 'Toronto ON'
    desc = re.sub(r"\s+(TORONTO|Toronto|ETOBICOKE|LONDON|AMSTERDAM)\s+ON$", "", desc)
    desc = re.sub(r"\s+ON$", "", desc)
    return desc


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Apply final type conversions and cleaning to a combined DataFrame."""
    if df.empty:
        return df

    df = df.copy()

    # Clean descriptions
    df["description"] = df["description"].apply(clean_description)

    # Ensure dates are proper date objects (not strings)
    for col in ("trans_date", "post_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    # Ensure amount is float
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    # Flag rows where amount is NaN (parse failure)
    mask = df["amount"].isna() & (df["parse_flag"] == "")
    df.loc[mask, "parse_flag"]  = "REVIEW"
    df.loc[mask, "flag_reason"] = "amount is NaN"

    # Sort by date
    df = df.sort_values("trans_date").reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_statements(
    credit_pdf: str | None = None,
    debit_pdf:  str | None = None,
) -> pd.DataFrame:
    """
    Parse one or both PDFs and return a single normalised DataFrame.
    At least one path must be provided.
    """
    frames = []

    if credit_pdf:
        print(f"[parser] Parsing credit PDF: {credit_pdf}")
        df_credit = parse_credit_pdf(credit_pdf)
        frames.append(df_credit)
        print(f"         → {len(df_credit)} rows extracted "
              f"({(df_credit['parse_flag']=='REVIEW').sum()} flagged)")

    if debit_pdf:
        print(f"[parser] Parsing debit PDF: {debit_pdf}")
        df_debit = parse_debit_pdf(debit_pdf)
        frames.append(df_debit)
        print(f"         → {len(df_debit)} rows extracted "
              f"({(df_debit['parse_flag']=='REVIEW').sum()} flagged)")

    if not frames:
        raise ValueError("Provide at least one PDF path.")

    combined = pd.concat(frames, ignore_index=True)
    combined = normalise(combined)

    return combined


# ---------------------------------------------------------------------------
# CLI / quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    credit = sys.argv[1] if len(sys.argv) > 1 else None
    debit  = sys.argv[2] if len(sys.argv) > 2 else None

    df = parse_statements(credit_pdf=credit, debit_pdf=debit)

    print("\n=== ALL TRANSACTIONS ===")
    pd.set_option("display.max_colwidth", 50)
    pd.set_option("display.max_rows", 200)
    print(df[["trans_date", "description", "amount", "type", "source", "parse_flag"]].to_string())

    flagged = df[df["parse_flag"] == "REVIEW"]
    if not flagged.empty:
        print(f"\n=== FLAGGED FOR REVIEW ({len(flagged)} rows) ===")
        print(flagged[["trans_date", "description", "amount", "flag_reason"]].to_string())

    # Save to CSV
    out = Path("data/processed/transactions_raw.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\n[parser] Saved to {out}")
