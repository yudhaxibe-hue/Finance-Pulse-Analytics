import numpy as np
import pandas as pd


def safe_pct(numerator, denominator):
    return None if not denominator else round(float(numerator / denominator * 100), 2)


def metrics(df):
    if df.empty:
        return {
            **{k: None for k in ("revenue", "expenses", "cost", "gross_profit", "profit", "margin", "expense_ratio", "roi", "avg_transaction")},
            "transactions": 0,
        }
    revenue, expense, cost = (float(df[c].sum()) for c in ("revenue", "expense", "cost"))
    profit = revenue - expense
    investment = float(df["investment"].sum())
    revenue_count = int((df.revenue > 0).sum())
    return {
        "revenue": revenue,
        "expenses": expense,
        "cost": cost,
        "gross_profit": revenue - cost,
        "profit": profit,
        "margin": safe_pct(profit, revenue),
        "expense_ratio": safe_pct(expense, revenue),
        "roi": safe_pct(profit, investment),
        "avg_transaction": None if not revenue_count else revenue / revenue_count,
        "transactions": len(df),
    }


def monthly(df):
    if df.empty:
        return pd.DataFrame({
            "period": pd.Series([], dtype="datetime64[ns]"),
            "revenue": pd.Series([], dtype=float),
            "expense": pd.Series([], dtype=float),
            "cost": pd.Series([], dtype=float),
            "profit": pd.Series([], dtype=float),
            "margin": pd.Series([], dtype=float),
        })
    out = df.set_index("txn_date").resample("MS")[["revenue", "expense", "cost"]].sum().reset_index()
    out["profit"] = out.revenue - out.expense
    out["margin"] = np.where(out.revenue != 0, out.profit / out.revenue * 100, np.nan)
    out.rename(columns={"txn_date": "period"}, inplace=True)
    return out


def period_growth(series):
    if len(series) < 2 or not series.iloc[-2]:
        return None
    return round(float((series.iloc[-1] - series.iloc[-2]) / series.iloc[-2] * 100), 2)
