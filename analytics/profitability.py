import pandas as pd
from .financial_metrics import safe_pct


def by_dimension(df, dimension):
    if df.empty or dimension not in df:
        return []
    cleaned = df.copy()
    cleaned[dimension] = cleaned[dimension].where(
        cleaned[dimension].notna() & (cleaned[dimension].astype(str).str.strip() != ""),
        "Unassigned",
    )
    group = cleaned.groupby(dimension)[["revenue", "expense", "cost"]].sum().reset_index()
    group["profit"] = group.revenue - group.expense
    group["margin"] = group.apply(lambda x: safe_pct(x.profit, x.revenue), axis=1)
    rows = group.sort_values("profit", ascending=False).to_dict("records")
    for row in rows:
        if row["margin"] is not None and pd.isna(row["margin"]):
            row["margin"] = None
    return rows
