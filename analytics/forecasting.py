import numpy as np
import pandas as pd
from .financial_metrics import monthly


def forecast(df, target="revenue", horizon=6):
    if target not in {"revenue", "expense", "profit"}:
        target = "revenue"
    data = monthly(df)
    if len(data) < 4:
        return {
            "error": "Insufficient historical data for reliable forecasting (at least 4 monthly periods are required).",
            "history": [],
            "forecast": [],
        }
    y = data[target].astype(float).values
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    predictions = intercept + slope * x
    mae = float(np.mean(np.abs(y - predictions)))
    rmse = float(np.sqrt(np.mean((y - predictions) ** 2)))
    mape = None if np.any(y == 0) else float(np.mean(np.abs((y - predictions) / y)) * 100)
    future = pd.date_range(data.period.iloc[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    raw_fvalues = intercept + slope * np.arange(len(y), len(y) + horizon)
    fvalues = raw_fvalues if target == "profit" else np.maximum(0, raw_fvalues)
    return {
        "model": "Linear trend regression",
        "history": [{"period": d.strftime("%Y-%m"), "value": round(float(v), 2)} for d, v in zip(data.period, y)],
        "forecast": [{"period": d.strftime("%Y-%m"), "value": round(float(v), 2)} for d, v in zip(future, fvalues)],
        "accuracy": {
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "mape": None if mape is None else round(mape, 2),
        },
    }
