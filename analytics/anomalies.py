import pandas as pd


def detect(df, multiplier=1.5):
    if df.empty:
        return []
    flags = []
    for column, label in (("expense", "Expense"), ("revenue", "Revenue")):
        if column not in df:
            continue
        values = df[df[column] > 0][column]
        if len(values) < 4:
            continue
        q1, q3 = values.quantile(0.25), values.quantile(0.75)
        iqr = q3 - q1
        limit = q3 + multiplier * iqr
        for _, row in df[df[column] > limit].iterrows():
            raw_cat = row.get("category")
            entity = "Uncategorized" if raw_cat is None or pd.isna(raw_cat) or not str(raw_cat).strip() else str(raw_cat).strip()
            flags.append({
                "date": row.txn_date.strftime("%Y-%m-%d"),
                "type": label,
                "entity": entity,
                "value": float(row[column]),
                "threshold": round(float(limit), 2),
                "reason": f"{label} is above the IQR-based expected range (threshold {limit:,.0f}).",
            })
    return sorted(flags, key=lambda x: x["value"], reverse=True)
