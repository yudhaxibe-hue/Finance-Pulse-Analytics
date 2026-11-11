"""Power BI Ready Kit builder (clean 26-col flat ledger, Power Query M, DAX measures)."""
from __future__ import annotations

import io
import zipfile
from typing import Any, Dict

import pandas as pd

from .privacy import mask_dataframe_pii

POWERBI_COLUMNS = [
    "Date",
    "Transaction ID",
    "Transaction Type",
    "Fiscal Year",
    "Fiscal Quarter",
    "Category",
    "Subcategory",
    "Product",
    "Department",
    "Cost Center",
    "Region",
    "Country",
    "Channel",
    "Payment Method",
    "Currency",
    "Customer Segment",
    "Vendor Name",
    "Revenue",
    "Expense",
    "Net Profit",
    "Profit Margin %",
    "Cost",
    "Tax Amount",
    "Discount Amount",
    "Quantity",
    "Unit Price",
    "Investment",
    "ML Risk Tier",
    "ML Risk Score",
    "Predicted Category",
    "Is Anomaly",
    "Notes",
]

POWER_QUERY_M = """// Finance Pulse Analytics — Power BI Power Query (M) Connector
// Option A: Local CSV export from Power BI Ready Kit (recommended offline workflow)
let
    Source = Csv.Document(
        File.Contents("powerbi_transactions.csv"),
        [Delimiter=",", Columns=32, Encoding=65001, QuoteStyle=QuoteStyle.Csv]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    TypedTable = Table.TransformColumnTypes(PromotedHeaders, {
        {"Date", type date},
        {"Transaction ID", type text},
        {"Transaction Type", type text},
        {"Fiscal Year", Int64.Type},
        {"Fiscal Quarter", type text},
        {"Category", type text},
        {"Subcategory", type text},
        {"Product", type text},
        {"Department", type text},
        {"Cost Center", type text},
        {"Region", type text},
        {"Country", type text},
        {"Channel", type text},
        {"Payment Method", type text},
        {"Currency", type text},
        {"Customer Segment", type text},
        {"Vendor Name", type text},
        {"Revenue", type number},
        {"Expense", type number},
        {"Net Profit", type number},
        {"Profit Margin %", type number},
        {"Cost", type number},
        {"Tax Amount", type number},
        {"Discount Amount", type number},
        {"Quantity", type number},
        {"Unit Price", type number},
        {"Investment", type number},
        {"ML Risk Tier", type text},
        {"ML Risk Score", type number},
        {"Predicted Category", type text},
        {"Is Anomaly", Int64.Type},
        {"Notes", type text}
    })
in
    TypedTable
"""

DAX_MEASURES = """// Finance Pulse Analytics — Enterprise DAX Measures Library
// Paste into Power BI Desktop -> Modeling -> New Measure

Total Revenue = SUM('powerbi_transactions'[Revenue])

Total Expenses = SUM('powerbi_transactions'[Expense])

Net Profit = [Total Revenue] - [Total Expenses]

Profit Margin % =
DIVIDE([Net Profit], [Total Revenue], 0)

Gross Profit =
[Total Revenue] - SUM('powerbi_transactions'[Cost])

High Risk Transactions =
CALCULATE(
    COUNTROWS('powerbi_transactions'),
    'powerbi_transactions'[ML Risk Tier] = "High Risk"
)

High Risk Exposure =
CALCULATE(
    SUM('powerbi_transactions'[Expense]),
    'powerbi_transactions'[ML Risk Tier] = "High Risk"
)

Anomaly Count =
CALCULATE(
    COUNTROWS('powerbi_transactions'),
    'powerbi_transactions'[Is Anomaly] = 1
)
"""


def prepare_powerbi_dataframe(df: pd.DataFrame, currency: str = "INR", mask_pii: bool = True) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=POWERBI_COLUMNS)

    work = df.copy()
    if mask_pii:
        work, _ = mask_dataframe_pii(work, enabled=True)

    def _col(name: str, default: Any = "") -> pd.Series:
        if name in work.columns:
            return work[name].fillna(default) if default is not None else work[name]
        return pd.Series([default] * len(work), index=work.index)

    def _num_col(name: str, default: float = 0.0) -> pd.Series:
        if name in work.columns:
            return pd.to_numeric(work[name], errors="coerce").fillna(default)
        return pd.Series([default] * len(work), index=work.index, dtype="float64")

    rev = _num_col("revenue", 0.0)
    exp = _num_col("expense", 0.0)
    net = rev - exp
    margin_pct = (net / rev.where(rev != 0)).fillna(0.0) * 100.0

    dates = pd.to_datetime(_col("txn_date", ""), errors="coerce")
    fy_series = _num_col("fiscal_year", 0.0).replace(0.0, float("nan"))
    if fy_series.isna().any():
        fy_series = fy_series.fillna(dates.dt.year)

    out = pd.DataFrame({
        "Date": dates.dt.strftime("%Y-%m-%d").fillna(""),
        "Transaction ID": _col("transaction_id", ""),
        "Transaction Type": _col("transaction_type", "Sale"),
        "Fiscal Year": fy_series.fillna(0).astype(int),
        "Fiscal Quarter": _col("fiscal_quarter", ""),
        "Category": _col("category", ""),
        "Subcategory": _col("subcategory", ""),
        "Product": _col("product", ""),
        "Department": _col("department", ""),
        "Cost Center": _col("cost_center", ""),
        "Region": _col("region", ""),
        "Country": _col("country", ""),
        "Channel": _col("channel", ""),
        "Payment Method": _col("payment_method", ""),
        "Currency": _col("currency_code", currency).replace("", currency),
        "Customer Segment": _col("customer_segment", ""),
        "Vendor Name": _col("vendor_name", ""),
        "Revenue": rev.round(2),
        "Expense": exp.round(2),
        "Net Profit": net.round(2),
        "Profit Margin %": margin_pct.round(2),
        "Cost": _num_col("cost", 0.0).round(2),
        "Tax Amount": _num_col("tax_amount", 0.0).round(2),
        "Discount Amount": _num_col("discount_amount", 0.0).round(2),
        "Quantity": _num_col("quantity", 0.0).round(2),
        "Unit Price": _num_col("unit_price", 0.0).round(2),
        "Investment": _num_col("investment", 0.0).round(2),
        "ML Risk Tier": _col("risk_tier", "Low Risk"),
        "ML Risk Score": _num_col("risk_score", 0.0).round(1),
        "Predicted Category": _col("predicted_category", ""),
        "Is Anomaly": _num_col("is_anomaly", 0.0).astype(int),
        "Notes": _col("notes", ""),
    })
    return out


def build_powerbi_kit_zip(df: pd.DataFrame, currency: str = "INR", mask_pii: bool = True) -> bytes:
    """Package typed flat CSV + Power Query M script + DAX measures into a Power BI Ready Kit."""
    pbi_df = prepare_powerbi_dataframe(df, currency=currency, mask_pii=mask_pii)
    csv_text = pbi_df.to_csv(index=False)

    readme = (
        "Finance Pulse Analytics - Power BI Ready Kit\n"
        "============================================\n"
        f"Rows exported: {len(pbi_df):,}  |  PII Masking: {'Enabled' if mask_pii else 'Disabled'}\n\n"
        "Quick Setup in Power BI Desktop:\n"
        "1. Extract this ZIP into a local folder.\n"
        "2. Open Power BI Desktop -> Get Data -> Text/CSV -> select 'powerbi_transactions.csv'.\n"
        "   (Or use Blank Query -> Advanced Editor and paste 'finance_pulse_powerquery.pq'.)\n"
        "3. Create Measures using the formulas in 'finance_pulse_measures.dax'.\n"
        "4. Optional live local feed endpoint: GET /api/v1/powerbi/feed (Bearer token auth).\n"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("powerbi_transactions.csv", csv_text.encode("utf-8"))
        zf.writestr("finance_pulse_powerquery.pq", POWER_QUERY_M.encode("utf-8"))
        zf.writestr("finance_pulse_measures.dax", DAX_MEASURES.encode("utf-8"))
        zf.writestr("README_PowerBI.txt", readme.encode("utf-8"))
    buf.seek(0)
    return buf.getvalue()


def build_powerbi_feed(df: pd.DataFrame, currency: str = "INR", mask_pii: bool = True, limit: int = 5000) -> Dict[str, Any]:
    pbi_df = prepare_powerbi_dataframe(df, currency=currency, mask_pii=mask_pii).head(max(1, min(25000, int(limit))))
    return {
        "ok": True,
        "schema": "finance_pulse_powerbi_v1",
        "count": int(len(pbi_df)),
        "pii_masked": bool(mask_pii),
        "rows": pbi_df.to_dict("records"),
    }
