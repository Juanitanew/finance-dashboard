# 💳 Personal Finance Dashboard

A end-to-end data pipeline that parses real Scotiabank bank statements, categorizes transactions, models the data with SQL, and visualizes insights in a Power BI dashboard.

**Built with:** Python · SQL · Power BI

---

## 📌 Project Overview

Most people have no idea where their money actually goes. This project solves that by:

1. **Parsing** raw PDF bank statements (credit card + chequing) into structured data
2. **Categorizing** each transaction automatically using keyword matching
3. **Modeling** the data in SQL for analytics queries
4. **Visualizing** spending patterns in an interactive Power BI dashboard
5. *(Optional)* **Budgeting** — set monthly limits per category and track variance

---

## 🗂️ Project Structure

```
finance-dashboard/
├── src/
│   ├── parser.py          # PDF extraction & normalization
│   ├── categorizer.py     # Keyword-based transaction categorization
│   ├── db_loader.py       # Loads cleaned data into SQLite
│   └── budget.py          # Optional budgeting feature
├── sql/
│   ├── schema.sql         # Database schema
│   └── analytics.sql      # Analytical queries
├── tests/
│   ├── conftest.py        # Pytest fixtures
│   └── test_parser.py     # Parser test suite (25 tests)
├── data/
│   ├── raw/               # Place your PDFs here (gitignored)
│   └── processed/         # Generated CSVs (gitignored)
├── dashboard/
│   └── finance.pbix       # Power BI dashboard
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🚀 Getting Started

### 1. Clone the repo
```bash
git clone https://github.com/Juanitanew/finance-dashboard.git
cd finance-dashboard
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate       # Mac/Linux
venv\Scripts\activate          # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Add your bank statements
Drop your Scotiabank PDF statements into `data/raw/`:
```
data/raw/
├── Bank_Statement_Credit.pdf
└── Bank_Statement_Debit.pdf
```
> ⚠️ This folder is gitignored — your real bank data never leaves your machine.

### 5. Run the parser
```bash
python src/parser.py data/raw/Bank_Statement_Credit.pdf data/raw/Bank_Statement_Debit.pdf
```

### 6. Run the tests
```bash
python -m pytest tests/test_parser.py -v
```

---

## 🧪 Testing

The test suite validates the parser against the bank's own printed subtotals as ground truth — if the parsed totals match the PDF to the cent, the extraction is provably correct.

```
── Group 1: Row counts ──────────────────────
  ✅  Total row count is correct
  ✅  Credit card row count matches
  ✅  Chequing row count matches

── Group 2: Totals match PDF ground truth ───
  ✅  Credit charges match statement subtotal
  ✅  Credit refunds match statement subtotal
  ✅  Debit withdrawals match statement total
  ✅  Debit deposits match statement total

── Group 3: Spot-check specific transactions 
  ✅  Specific charges verified by amount/date
  ✅  Refunds correctly parsed as negative
  ✅  Payroll deposits correctly negative

── Group 4: Data quality / schema ───────────
  ✅  No null amounts, dates, or descriptions
  ✅  No zero-dollar transactions
  ✅  All amounts are float64
  ✅  No duplicate reference numbers
```

---

## 📊 Dashboard Preview

*(Coming soon — Power BI dashboard screenshot)*

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Extraction | Python, pdfplumber | Parse PDF bank statements |
| Transformation | Python, pandas | Clean and normalize data |
| Storage | SQLite | Relational data modeling |
| Analytics | SQL | Spending queries and aggregations |
| Visualization | Power BI | Interactive dashboard |

---

## ⚠️ Privacy Note

This repo contains **no real financial data**. The `data/raw/` and `data/processed/` folders are gitignored. Only code is committed. To test the pipeline, use your own Scotiabank statements or create sample data.

---

## 📅 Roadmap

- [x] PDF parsing (credit card + chequing)
- [x] Data normalization and cleaning
- [x] Automated test suite
- [ ] Transaction categorization engine
- [ ] SQL schema and analytics queries
- [ ] Power BI dashboard
- [ ] Budgeting feature
