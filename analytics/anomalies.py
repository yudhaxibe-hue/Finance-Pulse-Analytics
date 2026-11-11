from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import IsolationForest


def detect(df: pd.DataFrame, multiplier: float = 1.5) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []

    work = df.copy()
    dates = pd.to_datetime(work["txn_date"], errors="coerce")
    work["_iso_flag"] = 0
    work["_iso_score"] = 0.0

    # Fit unsupervised IsolationForest on multi-dimensional ledger records when >= 12 rows exist
    if len(work) >= 12 and "revenue" in work and "expense" in work:
        rev_arr = pd.to_numeric(work["revenue"], errors="coerce").fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)
        exp_arr = pd.to_numeric(work["expense"], errors="coerce").fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)
        net_arr = rev_arr - exp_arr
        ratio_arr = np.where(rev_arr > 0, np.clip(exp_arr / np.maximum(rev_arr, 1.0), 0.0, 5.0), 1.0)
        X_iso = np.column_stack([np.log1p(rev_arr), np.log1p(exp_arr), net_arr, ratio_arr])
        iso = IsolationForest(contamination=0.03, n_estimators=120, random_state=42, n_jobs=1)
        preds = iso.fit_predict(X_iso)
        scores = iso.decision_function(X_iso)
        work["_iso_flag"] = (preds == -1).astype(int)
        work["_iso_score"] = np.round(-scores, 3)

    flags: List[Dict[str, Any]] = []
    seen_iqr_indices = set()

    for column, label in (("expense", "Expense"), ("revenue", "Revenue")):
        if column not in work:
            continue
        series = pd.to_numeric(work[column], errors="coerce").fillna(0.0)
        values = series[series > 0]
        if len(values) < 4:
            continue
        q1, q3 = values.quantile(0.25), values.quantile(0.75)
        iqr = q3 - q1
        limit = q3 + multiplier * iqr

        z_map: Dict[Any, float] = {}
        if len(values) >= 4 and float(values.std(ddof=0)) > 1e-9:
            z_vals = np.abs(stats.zscore(values.to_numpy(dtype=float), ddof=0))
            z_map = {idx: round(float(z), 2) for idx, z in zip(values.index, z_vals)}

        for idx, row in work[series > limit].iterrows():
            seen_iqr_indices.add((idx, column))
            raw_cat = row.get("category")
            entity = "Uncategorized" if raw_cat is None or pd.isna(raw_cat) or not str(raw_cat).strip() else str(raw_cat).strip()
            dt = dates.loc[idx]
            dt_str = dt.strftime("%Y-%m-%d") if pd.notna(dt) else str(row.get("txn_date", ""))
            iso_hit = int(row.get("_iso_flag", 0)) == 1
            method = "IQR + Isolation Forest" if iso_hit else "Statistical IQR"
            z_score = z_map.get(idx, 0.0)
            flags.append({
                "date": dt_str,
                "type": label,
                "entity": entity,
                "value": float(series.loc[idx]),
                "threshold": round(float(limit), 2),
                "z_score": z_score,
                "isolation_score": float(row.get("_iso_score", 0.0)),
                "method": method,
                "reason": (
                    f"{label} exceeds Q3 + {multiplier:g}×IQR ({limit:,.0f})"
                    + (f" and Isolation Forest flagged (Z={z_score:.1f})." if iso_hit else f" (Z={z_score:.1f}).")
                ),
            })

    return sorted(flags, key=lambda x: x["value"], reverse=True)
