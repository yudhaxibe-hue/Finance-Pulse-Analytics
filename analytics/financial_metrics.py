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
    revenue = float(df["revenue"].sum()) if "revenue" in df else 0.0
    expense = float(df["expense"].sum()) if "expense" in df else 0.0
    cost = float(df["cost"].sum()) if "cost" in df else 0.0
    profit = revenue - expense
    investment = float(df["investment"].sum()) if "investment" in df else 0.0
    revenue_count = int((df.revenue > 0).sum()) if "revenue" in df else 0
    savings_rate = safe_pct(investment, revenue) if revenue > 0 else None
    return {
        "revenue": revenue,
        "expenses": expense,
        "cost": cost,
        "gross_profit": revenue - cost,
        "profit": profit,
        "investment": investment,
        "total_savings": investment,
        "savings_rate": savings_rate,
        "margin": safe_pct(profit, revenue),
        "expense_ratio": safe_pct(expense, revenue),
        "roi": safe_pct(profit, investment),
        "avg_transaction": None if not revenue_count else revenue / revenue_count,
        "transactions": len(df),
    }


def budget_50_30_20(df):
    """
    Computes 50/30/20 personal budget allocation:
    - Needs (Essential living costs: rent, utilities, food, groceries, transport, healthcare)
    - Wants (Discretionary lifestyle: restaurants, outings, entertainment, shopping)
    - Savings & Investment (RD, SIP, debt payoff, retained surplus)
    """
    if df.empty:
        return None
    revenue = float(df["revenue"].sum()) if "revenue" in df else 0.0
    investment = float(df["investment"].sum()) if "investment" in df else 0.0

    needs_amt = 0.0
    wants_amt = 0.0

    # 1. If explicit customer_segment / budget classification exists
    if "customer_segment" in df:
        seg = df["customer_segment"].astype(str).str.strip().str.lower()
        needs_amt = float(df[seg.str.contains("need", na=False)]["expense"].sum())
        wants_amt = float(df[seg.str.contains("want", na=False)]["expense"].sum())

    # 2. If not tagged explicitly, classify by category/description heuristics
    if needs_amt == 0.0 and wants_amt == 0.0 and "expense" in df:
        need_keywords = {"housing", "rent", "mess", "groceries", "utility", "utilities", "electricity", "transport", "bus", "fuel", "education", "health", "healthcare", "medical", "laundry", "family"}
        want_keywords = {"outing", "outings", "restaurant", "restaurants", "dining", "entertainment", "movie", "shopping", "tea", "snacks", "ott", "subscription", "lifestyle"}

        for _, row in df[df["expense"] > 0].iterrows():
            text = f"{row.get('category', '')} {row.get('subcategory', '')} {row.get('notes', '')}".lower()
            exp_val = float(row.get("expense", 0.0))
            if any(k in text for k in need_keywords):
                needs_amt += exp_val
            elif any(k in text for k in want_keywords):
                wants_amt += exp_val
            else:
                needs_amt += exp_val

    total_income = revenue if revenue > 0 else (needs_amt + wants_amt + investment)
    if total_income <= 0:
        return None

    savings_amt = investment + max(0.0, total_income - (needs_amt + wants_amt + investment))

    needs_pct = safe_pct(needs_amt, total_income) or 0.0
    wants_pct = safe_pct(wants_amt, total_income) or 0.0
    savings_pct = safe_pct(savings_amt, total_income) or 0.0

    return {
        "total_income": total_income,
        "needs": {"amount": needs_amt, "pct": needs_pct, "benchmark_pct": 50.0, "status": "On Track" if needs_pct <= 55.0 else "Over Budget"},
        "wants": {"amount": wants_amt, "pct": wants_pct, "benchmark_pct": 30.0, "status": "Disciplined" if wants_pct <= 35.0 else "Elevated"},
        "savings": {"amount": savings_amt, "pct": savings_pct, "benchmark_pct": 20.0, "status": "Healthy" if savings_pct >= 18.0 else "Needs Boost"},
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
    work = df.copy()
    work["txn_date"] = pd.to_datetime(work["txn_date"], errors="coerce")
    work = work[work["txn_date"].notna()]
    for col in ("revenue", "expense", "cost"):
        if col not in work:
            work[col] = 0.0
        else:
            work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0.0)
    if work.empty:
        return pd.DataFrame({
            "period": pd.Series([], dtype="datetime64[ns]"),
            "revenue": pd.Series([], dtype=float),
            "expense": pd.Series([], dtype=float),
            "cost": pd.Series([], dtype=float),
            "profit": pd.Series([], dtype=float),
            "margin": pd.Series([], dtype=float),
        })
    out = work.set_index("txn_date").resample("MS")[["revenue", "expense", "cost"]].sum().reset_index()
    out["profit"] = out.revenue - out.expense
    out["margin"] = np.where(out.revenue != 0, out.profit / out.revenue * 100, np.nan)
    out.rename(columns={"txn_date": "period"}, inplace=True)
    return out


def period_growth(series):
    if len(series) < 2 or not series.iloc[-2]:
        return None
    return round(float((series.iloc[-1] - series.iloc[-2]) / series.iloc[-2] * 100), 2)


def compute_cashflow_runway(df, cash_reserve=None):
    """Estimate monthly burn/surplus pace, savings buffer, and cash-flow runway."""
    if df is None or df.empty:
        return {
            "months": 0,
            "avg_monthly_revenue": 0.0,
            "avg_monthly_expense": 0.0,
            "avg_monthly_net": 0.0,
            "recent_monthly_net": 0.0,
            "savings_rate_pct": None,
            "cash_reserve": 0.0,
            "reserve_basis": "No ledger history",
            "runway_months": None,
            "status": "No data",
        }

    m = monthly(df)
    n_months = len(m)
    recent = m.tail(min(6, n_months))
    avg_rev = float(m["revenue"].mean())
    avg_exp = float(m["expense"].mean())
    avg_net = float(m["profit"].mean())
    rec_rev = float(recent["revenue"].mean())
    rec_exp = float(recent["expense"].mean())
    rec_net = float(recent["profit"].mean())

    savings_rate = None if rec_rev <= 0 else round((rec_net / rec_rev) * 100.0, 2)
    total_net = float(m["profit"].sum())

    if cash_reserve is not None:
        reserve = max(0.0, float(cash_reserve))
        basis = "User-specified cash reserve"
    else:
        # Derive conservative liquidity cushion from cumulative surplus or 2 months revenue buffer
        reserve = round(max(0.0, total_net), 2)
        basis = "Cumulative net ledger surplus"

    if rec_net >= 0:
        runway = None
        if rec_rev > 0 and rec_net / rec_rev >= 0.20:
            status = "Healthy Surplus (Self-Sustaining)"
        else:
            status = "Cash-Positive (Tight Cushion)"
    else:
        burn = abs(rec_net)
        runway = round(reserve / burn, 1) if burn > 0 else None
        if runway is None or runway < 3.0:
            status = "Critical Runway (<3 months)"
        elif runway < 6.0:
            status = "Watch Runway (<6 months)"
        else:
            status = "Stable Buffer (Burning Cash)"

    return {
        "months": n_months,
        "avg_monthly_revenue": round(avg_rev, 2),
        "avg_monthly_expense": round(avg_exp, 2),
        "avg_monthly_net": round(avg_net, 2),
        "recent_monthly_revenue": round(rec_rev, 2),
        "recent_monthly_expense": round(rec_exp, 2),
        "recent_monthly_net": round(rec_net, 2),
        "savings_rate_pct": savings_rate,
        "cash_reserve": round(reserve, 2),
        "reserve_basis": basis,
        "runway_months": runway,
        "status": status,
    }
