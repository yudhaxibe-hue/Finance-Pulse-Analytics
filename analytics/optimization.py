from .financial_metrics import metrics, monthly, period_growth
from .profitability import by_dimension


def scenario(base, revenue_change=0, expense_change=0):
    revenue = base["revenue"] * (1 + revenue_change / 100)
    expenses = base["expenses"] * (1 + expense_change / 100)
    profit = revenue - expenses
    return {
        "revenue": revenue,
        "expenses": expenses,
        "profit": profit,
        "margin": None if not revenue else round(profit / revenue * 100, 2),
        "profit_change": profit - base["profit"],
    }


def recommendations(df, margin_threshold=15):
    result = []
    base = metrics(df)
    m = monthly(df)
    if len(m) >= 2:
        rg, eg = period_growth(m.revenue), period_growth(m.expense)
        if rg is not None and eg is not None and eg > rg:
            result.append({
                "title": "Cost pressure",
                "detail": f"Latest monthly expense growth ({eg:.1f}%) exceeds revenue growth ({rg:.1f}%). Review controllable spending.",
            })
    for row in by_dimension(df, "product"):
        if row["revenue"] > 0 and row["margin"] is not None and row["margin"] < margin_threshold:
            result.append({
                "title": "Low-margin product",
                "detail": f"{row['product']} has {row['margin']:.1f}% margin, below the {margin_threshold:.1f}% warning threshold.",
            })
    if base["expense_ratio"] is not None and base["expense_ratio"] > 85:
        result.append({
            "title": "High expense ratio",
            "detail": f"Expenses are {base['expense_ratio']:.1f}% of revenue; reducing avoidable expenses has direct profit impact.",
        })
    return result


def target_margin_plan(base, target_margin=20.0):
    revenue = base.get("revenue")
    expenses = base.get("expenses")
    if revenue is None or expenses is None or revenue <= 0:
        return None
    target = max(-100.0, min(95.0, float(target_margin)))
    current_margin = base.get("margin") if base.get("margin") is not None else 0.0
    target_profit = revenue * (target / 100.0)
    profit_gap = target_profit - base["profit"]

    needed_expenses = revenue * (1.0 - target / 100.0)
    expense_cut_amount = max(0.0, expenses - needed_expenses)
    expense_cut_pct = 0.0 if expenses <= 0 else round(-(expense_cut_amount / expenses) * 100.0, 1)

    denom = 1.0 - target / 100.0
    needed_revenue = expenses / denom if denom > 0 else revenue
    revenue_lift_amount = max(0.0, needed_revenue - revenue)
    revenue_lift_pct = round((revenue_lift_amount / revenue) * 100.0, 1)

    breakeven_revenue = expenses
    safety_margin_amount = revenue - breakeven_revenue

    return {
        "target_margin": round(target, 1),
        "current_margin": round(current_margin, 2),
        "margin_gap": round(target - current_margin, 2),
        "already_achieved": current_margin >= target,
        "profit_gap": round(profit_gap, 2),
        "expense_cut_amount": round(expense_cut_amount, 2),
        "expense_cut_pct": expense_cut_pct,
        "revenue_lift_amount": round(revenue_lift_amount, 2),
        "revenue_lift_pct": revenue_lift_pct,
        "breakeven_revenue": round(breakeven_revenue, 2),
        "safety_margin_amount": round(safety_margin_amount, 2),
    }


def segment_opportunities(df, margin_threshold=15.0):
    if df.empty:
        return []
    levers = []
    for dim in ("product", "department", "category", "region"):
        rows = by_dimension(df, dim)
        for row in rows:
            name = row.get(dim)
            rev = float(row.get("revenue") or 0.0)
            exp = float(row.get("expense") or 0.0)
            profit = float(row.get("profit") or 0.0)
            margin = row.get("margin")
            if rev <= 0 and exp <= 0:
                continue
            if rev <= 0 and exp > 0:
                levers.append({
                    "dimension": dim.title(),
                    "segment": name,
                    "revenue": rev,
                    "profit": profit,
                    "margin": margin,
                    "opportunity": "Eliminate unrecovered spend",
                    "impact": round(exp, 2),
                })
            elif margin is not None and margin < margin_threshold:
                target_profit = rev * (margin_threshold / 100.0)
                levers.append({
                    "dimension": dim.title(),
                    "segment": name,
                    "revenue": rev,
                    "profit": profit,
                    "margin": margin,
                    "opportunity": f"Lift margin to {margin_threshold:.1f}% threshold",
                    "impact": round(max(0.0, target_profit - profit), 2),
                })
            elif margin is not None and margin >= margin_threshold and profit > 0:
                levers.append({
                    "dimension": dim.title(),
                    "segment": name,
                    "revenue": rev,
                    "profit": profit,
                    "margin": margin,
                    "opportunity": "Scale high-margin volume (+10%)",
                    "impact": round(profit * 0.10, 2),
                })
    return sorted(levers, key=lambda x: x["impact"], reverse=True)[:8]
