"""
categorizer.py
--------------
Assigns a category to every transaction using a keyword map.

Flow:
  1. Load (or create) keyword_map.json
  2. Auto-assign categories by matching description keywords
  3. Prompt user to assign any remaining UNCATEGORIZED rows
  4. Save updated keyword map so it improves over time
  5. Return the fully-categorized DataFrame

Categories (defaults — user can add more):
  Food & Dining       Restaurants, fast food, cafes, groceries
  Transport           Uber, transit (PRESTO), gas
  Travel              Hotels, flights, booking sites
  Shopping            Amazon, Temu, retail stores
  Entertainment       Bars, clubs, movies, streaming, books
  Health & Beauty     Pharmacy, salons, fitness
  Bills & Utilities   Phone, hydro, internet
  Income              Payroll, tax refund, GST, deposits
  Transfers           Internal bank transfers, credit card payments
  Other               Anything that doesn't fit
"""

import json
import re
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT  = Path(__file__).resolve().parent.parent
KEYWORD_MAP_PATH = PROJECT_ROOT / "keyword_map.json"


# ---------------------------------------------------------------------------
# Default keyword map
# Each key is a CATEGORY name.
# Each value is a list of substrings to match (case-insensitive) in description.
# ---------------------------------------------------------------------------
DEFAULT_KEYWORD_MAP: dict[str, list[str]] = {
    "Food & Dining": [
        "mcdonald", "mcdonalds", "uber eats", "ubereats", "damiano",
        "eataly", "five guys", "robot boil", "cactus club", "wendy",
        "wendys", "starbucks", "tim horton", "laduree", "artful dodger",
        "greta yyz", "kibo", "queens harbour", "shinyi", "spirited tarts",
        "score on queen", "mademoiselle", "tst-pai", "pai northern",
        "el convento", "bar hop", "perola", "woojoo", "tora",
        "wine rack", "circle k", "costco",
    ],
    "Transport": [
        "uber canada/ubertrip", "uber holdings", "presto fare",
        "presto sherbourne", "fpos pres", "esso", "esso circle",
    ],
    "Travel": [
        "booking.com", "bkg*hotel", "banana beach house",
        "ryanair", "turkish", "tap air", "hotel at booking",
        "oasis zoorun", "smashbox performance", "getyourguide",
    ],
    "Shopping": [
        "amazon", "amzn", "temu", "sephora", "indigo", "dollarama",
        "staples", "rexall", "lcbo", "freedom mobile",
    ],
    "Entertainment": [
        "cineplex", "google *youtube", "youtube", "openai", "chatgpt",
        "fifth social club", "soluna", "score on queen",
    ],
    "Health & Beauty": [
        "rexall pharmacy", "smashbox",
    ],
    "Bills & Utilities": [
        "freedom mobile", "hydrobill", "hydro bill",
        "provident energy", "openai *chatgpt subscr",
    ],
    "Income": [
        "payrolldep", "payroll dep", "tax refund", "taxrefund",
        "gst", "provincial payment", "deposit",
    ],
    "Transfers": [
        "payment from", "mb-transferto", "mb-transfer to",
        "mb-transferfrom", "mb-transfer from", "credit card/loc",
        "scotiabank transit", "withdrawal", "wealthsimple",
        "investment",
    ],
}

# ---------------------------------------------------------------------------
# Load / save keyword map
# ---------------------------------------------------------------------------

def load_keyword_map() -> dict[str, list[str]]:
    """Load from file if it exists, otherwise return defaults."""
    if KEYWORD_MAP_PATH.exists():
        with open(KEYWORD_MAP_PATH, "r") as f:
            data = json.load(f)
        print(f"[categorizer] Loaded keyword map from {KEYWORD_MAP_PATH}")
        return data
    print("[categorizer] No keyword map found — using defaults")
    return DEFAULT_KEYWORD_MAP.copy()


def save_keyword_map(kmap: dict[str, list[str]]) -> None:
    """Persist the keyword map to disk."""
    with open(KEYWORD_MAP_PATH, "w") as f:
        json.dump(kmap, f, indent=2)
    print(f"[categorizer] Keyword map saved to {KEYWORD_MAP_PATH}")


# ---------------------------------------------------------------------------
# Core matching logic
# ---------------------------------------------------------------------------

def match_category(description: str, kmap: dict[str, list[str]]) -> str:
    """
    Return the best matching category for a description string,
    or 'Uncategorized' if nothing matches.

    Longer keyword matches are preferred over shorter ones to avoid
    false positives (e.g. 'circle k' should not match 'uber canada/ubertrip'
    just because both contain common words).
    """
    desc_lower = description.lower()
    best_category = "Uncategorized"
    best_match_len = 0

    for category, keywords in kmap.items():
        for kw in keywords:
            if kw.lower() in desc_lower:
                if len(kw) > best_match_len:
                    best_match_len = len(kw)
                    best_category = category

    return best_category


def auto_categorize(df: pd.DataFrame, kmap: dict[str, list[str]]) -> pd.DataFrame:
    """Apply keyword matching to every row in the DataFrame."""
    df = df.copy()
    df["category"] = df["description"].apply(lambda d: match_category(d, kmap))
    return df


# ---------------------------------------------------------------------------
# Interactive review — CLI prompt for uncategorized rows
# ---------------------------------------------------------------------------

def _print_categories(kmap: dict[str, list[str]]) -> list[str]:
    """Print numbered category menu and return list of category names."""
    categories = list(kmap.keys())
    print("\n  Available categories:")
    for i, cat in enumerate(categories, 1):
        print(f"    {i:2}. {cat}")
    print(f"    {len(categories)+1:2}. [Add new category]")
    print(f"    {len(categories)+2:2}. [Skip for now]")
    return categories


def interactive_review(
    df: pd.DataFrame,
    kmap: dict[str, list[str]],
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """
    Show the user each uncategorized transaction and ask them to assign
    a category. Optionally learns the keyword for future auto-assignment.
    Returns the updated DataFrame and keyword map.
    """
    uncategorized = df[df["category"] == "Uncategorized"].copy()

    if uncategorized.empty:
        print("\n[categorizer] All transactions categorized automatically — nothing to review!")
        return df, kmap

    total = len(uncategorized)
    print(f"\n[categorizer] {total} transaction(s) need manual categorization.")
    print("─" * 60)

    df = df.copy()

    for idx, (row_idx, row) in enumerate(uncategorized.iterrows(), 1):
        print(f"\n[{idx}/{total}]")
        print(f"  Date:        {row['trans_date']}")
        print(f"  Description: {row['description']}")
        amount_sign = "-$" if row["amount"] < 0 else " $"
        print(f"  Amount:      {amount_sign}{abs(row['amount']):.2f}")
        print(f"  Source:      {row['source']}")

        categories = _print_categories(kmap)
        n_cats = len(categories)

        while True:
            try:
                choice = input("\n  Enter number (or press Enter to skip): ").strip()

                if choice == "":
                    print("  → Skipped")
                    break

                choice_int = int(choice)

                if choice_int == n_cats + 2:
                    # Skip
                    print("  → Skipped")
                    break

                elif choice_int == n_cats + 1:
                    # Add new category
                    new_cat = input("  New category name: ").strip()
                    if new_cat:
                        kmap[new_cat] = []
                        categories.append(new_cat)
                        n_cats += 1
                        df.at[row_idx, "category"] = new_cat
                        print(f"  → Assigned to new category: '{new_cat}'")
                    else:
                        print("  → No name entered, skipping")
                    break

                elif 1 <= choice_int <= n_cats:
                    chosen = categories[choice_int - 1]
                    df.at[row_idx, "category"] = chosen
                    print(f"  → Assigned to: '{chosen}'")

                    # Offer to save keyword for future auto-assignment
                    learn = input(
                        f"  Save a keyword so '{row['description'][:30]}...' "
                        f"auto-assigns to '{chosen}' next time? (y/n): "
                    ).strip().lower()

                    if learn == "y":
                        suggested = input(
                            f"  Keyword to match (press Enter to use full description): "
                        ).strip()
                        keyword = suggested if suggested else row["description"].lower()
                        if keyword not in kmap[chosen]:
                            kmap[chosen].append(keyword)
                            print(f"  → Keyword '{keyword}' added to '{chosen}'")
                    break

                else:
                    print(f"  Please enter a number between 1 and {n_cats + 2}")

            except ValueError:
                print(f"  Please enter a number between 1 and {n_cats + 2}")

    return df, kmap


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(df: pd.DataFrame) -> None:
    """Print a breakdown of spending by category."""
    print("\n" + "=" * 50)
    print("  CATEGORY SUMMARY")
    print("=" * 50)

    # Only show spending (positive amounts = money out)
    spending = df[df["amount"] > 0].copy()
    summary = (
        spending.groupby("category")["amount"]
        .agg(total="sum", count="count")
        .sort_values("total", ascending=False)
        .reset_index()
    )

    for _, row in summary.iterrows():
        bar = "█" * int(row["total"] / 50)
        print(f"  {row['category']:<20} ${row['total']:>8.2f}  ({int(row['count'])} txns)  {bar}")

    total_spend = spending["amount"].sum()
    print(f"\n  {'TOTAL SPENDING':<20} ${total_spend:>8.2f}")

    uncategorized = df[df["category"] == "Uncategorized"]
    if not uncategorized.empty:
        print(f"\n  ⚠️  {len(uncategorized)} transaction(s) still uncategorized")

    print("=" * 50)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def categorize(
    df: pd.DataFrame,
    interactive: bool = True,
) -> pd.DataFrame:
    """
    Full categorization pipeline:
      1. Load keyword map
      2. Auto-assign categories
      3. Optionally prompt user for uncategorized rows
      4. Save updated keyword map
      5. Return categorized DataFrame

    Args:
        df:          Normalized transactions DataFrame from parser.py
        interactive: If True, prompt user to assign uncategorized rows.
                     Set to False for automated/testing runs.
    """
    # Step 1 — load keyword map
    kmap = load_keyword_map()

    # Step 2 — auto-categorize
    df = auto_categorize(df, kmap)

    auto_count   = (df["category"] != "Uncategorized").sum()
    manual_count = (df["category"] == "Uncategorized").sum()
    print(f"[categorizer] Auto-assigned: {auto_count}  |  Needs review: {manual_count}")

    # Step 3 — interactive review
    if interactive and manual_count > 0:
        df, kmap = interactive_review(df, kmap)

    # Step 4 — save updated keyword map
    save_keyword_map(kmap)

    # Step 5 — print summary
    print_summary(df)

    return df


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from parser import parse_statements

    credit = sys.argv[1] if len(sys.argv) > 1 else None
    debit  = sys.argv[2] if len(sys.argv) > 2 else None

    if not credit and not debit:
        print("Usage: python categorizer.py <credit_pdf> [debit_pdf]")
        sys.exit(1)

    # Parse
    df = parse_statements(credit_pdf=credit, debit_pdf=debit)

    # Categorize (interactive)
    df = categorize(df, interactive=True)

    # Save output
    out = PROJECT_ROOT / "data" / "processed" / "transactions_categorized.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\n[categorizer] Saved to {out}")
