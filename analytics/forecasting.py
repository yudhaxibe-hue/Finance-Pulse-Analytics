from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from .financial_metrics import monthly


def _build_lag_features(y: np.ndarray, alt_flow: np.ndarray, dates: pd.Series) -> np.ndarray:
    n = len(y)
    rows: List[List[float]] = []
    for i in range(n):
        m = int(dates.iloc[i].month)
        lag1 = float(y[i - 1]) if i >= 1 else float(y[0])
        lag2 = float(y[i - 2]) if i >= 2 else lag1
        lag3 = float(y[i - 3]) if i >= 3 else lag2
        window = y[max(0, i - 3):i] if i > 0 else y[:1]
        roll_mean = float(np.mean(window))
        roll_std = float(np.std(window))
        alt_lag1 = float(alt_flow[i - 1]) if i >= 1 else float(alt_flow[0])
        rows.append([
            float(i),
            float(np.sin(2.0 * np.pi * m / 12.0)),
            float(np.cos(2.0 * np.pi * m / 12.0)),
            lag1,
            lag2,
            lag3,
            roll_mean,
            roll_std,
            alt_lag1,
        ])
    return np.array(rows, dtype=float)


def forecast(df: pd.DataFrame, target: str = "revenue", horizon: int = 6, model_type: str = "auto") -> Dict[str, Any]:
    if target not in {"revenue", "expense", "profit"}:
        target = "revenue"
    horizon = max(1, min(36, int(horizon or 6)))
    data = monthly(df)
    if len(data) < 4:
        return {
            "error": "Insufficient historical data for reliable forecasting (at least 4 monthly periods are required).",
            "history": [],
            "forecast": [],
        }

    y = data[target].astype(float).values
    alt_col = "expense" if target == "revenue" else "revenue"
    alt_vals = data[alt_col].astype(float).values
    x = np.arange(len(y), dtype=float)

    # Always compute OLS baseline for accuracy comparison and <6-month fallback
    slope, intercept = np.polyfit(x, y, 1)
    ols_in = intercept + slope * x
    ols_mae = float(np.mean(np.abs(y - ols_in)))
    ols_rmse = float(np.sqrt(np.mean((y - ols_in) ** 2)))
    ols_future = intercept + slope * np.arange(len(y), len(y) + horizon)
    if target != "profit":
        ols_future = np.maximum(0.0, ols_future)

    future_dates = pd.date_range(data.period.iloc[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")

    use_ols = (len(data) < 6) or (model_type in {"ols", "linear"})
    if use_ols:
        mape = None if np.any(y == 0) else float(np.mean(np.abs((y - ols_in) / y)) * 100)
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        ss_res = float(np.sum((y - ols_in) ** 2))
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-9 else 0.0
        band = max(ols_mae, ols_rmse * 0.8)
        return {
            "model": "Linear trend regression",
            "model_code": "ols",
            "history": [{"period": d.strftime("%Y-%m"), "value": round(float(v), 2)} for d, v in zip(data.period, y)],
            "forecast": [
                {
                    "period": d.strftime("%Y-%m"),
                    "value": round(float(v), 2),
                    "low": round(float(v - band if target == "profit" else max(0.0, v - band)), 2),
                    "high": round(float(v + band), 2),
                    "ols_baseline": round(float(v), 2),
                }
                for d, v in zip(future_dates, ols_future)
            ],
            "accuracy": {
                "mae": round(ols_mae, 2),
                "rmse": round(ols_rmse, 2),
                "mape": None if mape is None else round(mape, 2),
                "r2": round(float(r2), 3),
                "ols_mae": round(ols_mae, 2),
                "ols_rmse": round(ols_rmse, 2),
            },
            "feature_importances": [{"feature": "Time Trend Index", "importance": 100.0}],
        }

    # Random Forest Regressor with lag, rolling momentum, seasonality & trend features
    # Learn trend-normalized residuals or full values safely so RF captures seasonality AND long-run trend
    residuals = y - ols_in
    X_all = _build_lag_features(residuals, alt_vals, data.period)
    rf = RandomForestRegressor(
        n_estimators=180,
        max_depth=8,
        min_samples_leaf=1,
        random_state=42,
        n_jobs=1,
    )
    rf.fit(X_all, residuals)

    rf_in_res = rf.predict(X_all)
    predictions = ols_in + rf_in_res
    mae = float(np.mean(np.abs(y - predictions)))
    rmse = float(np.sqrt(np.mean((y - predictions) ** 2)))
    non_zero = np.abs(y) > 1e-6
    mape = None if not np.any(non_zero) else float(np.mean(np.abs((y[non_zero] - predictions[non_zero]) / y[non_zero])) * 100)
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    ss_res = float(np.sum((y - predictions) ** 2))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-9 else 0.0

    # Recursive multi-step projection with tree-ensemble prediction interval
    res_buf = list(residuals.astype(float))
    alt_last = float(np.mean(alt_vals[-3:]))
    n_hist = len(y)
    forecast_rows = []
    for step, dt in enumerate(future_dates):
        idx = n_hist + step
        m = int(dt.month)
        lag1 = res_buf[-1]
        lag2 = res_buf[-2] if len(res_buf) >= 2 else lag1
        lag3 = res_buf[-3] if len(res_buf) >= 3 else lag2
        win = res_buf[-3:]
        feat = np.array([[
            float(idx),
            float(np.sin(2.0 * np.pi * m / 12.0)),
            float(np.cos(2.0 * np.pi * m / 12.0)),
            float(lag1),
            float(lag2),
            float(lag3),
            float(np.mean(win)),
            float(np.std(win)),
            float(alt_last),
        ]], dtype=float)
        tree_res = np.array([float(est.predict(feat)[0]) for est in rf.estimators_], dtype=float)
        base_ols = float(intercept + slope * idx)
        tree_preds = base_ols + tree_res
        val = float(np.mean(tree_preds))
        low = min(val, float(np.percentile(tree_preds, 15)) - rmse * 0.35)
        high = max(val, float(np.percentile(tree_preds, 85)) + rmse * 0.35)
        if target != "profit":
            val = max(0.0, val)
            low = max(0.0, low)
            high = max(val, high)
            base_ols = max(0.0, base_ols)
        res_buf.append(val - (intercept + slope * idx))
        forecast_rows.append({
            "period": dt.strftime("%Y-%m"),
            "value": round(val, 2),
            "low": round(low, 2),
            "high": round(high, 2),
            "ols_baseline": round(base_ols, 2),
        })

    feature_names = [
        "Trend Index", "Seasonality (Sin)", "Seasonality (Cos)",
        "Lag 1 Month", "Lag 2 Months", "Lag 3 Months",
        "3M Rolling Mean", "3M Volatility", f"Prior {alt_col.title()}",
    ]
    importances = sorted(
        [
            {"feature": name, "importance": round(float(imp * 100.0), 1)}
            for name, imp in zip(feature_names, rf.feature_importances_)
        ],
        key=lambda row: row["importance"],
        reverse=True,
    )

    return {
        "model": "Random Forest Regressor",
        "model_code": "random_forest",
        "history": [{"period": d.strftime("%Y-%m"), "value": round(float(v), 2)} for d, v in zip(data.period, y)],
        "forecast": forecast_rows,
        "accuracy": {
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "mape": None if mape is None else round(mape, 2),
            "r2": round(float(r2), 3),
            "ols_mae": round(ols_mae, 2),
            "ols_rmse": round(ols_rmse, 2),
        },
        "feature_importances": importances[:6],
    }
