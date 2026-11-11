"""Headless Matplotlib + Seaborn chart rendering and ZIP chart-pack builder."""
from __future__ import annotations

import io
import zipfile
from typing import Dict, Optional

import pandas as pd

from .financial_metrics import monthly
from .forecasting import forecast
from .ml_engine import ml_summary
from .profitability import by_dimension

_CHART_LIBS = None


def _chart_libs():
    global _CHART_LIBS
    if _CHART_LIBS is not None:
        return _CHART_LIBS
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import seaborn as sns

    sns.set_theme(
        style="whitegrid",
        rc={
            "axes.edgecolor": "#D2D2D7",
            "axes.linewidth": 0.8,
            "grid.color": "#ECECF0",
            "grid.linestyle": "-",
            "grid.linewidth": 0.7,
            "font.family": "sans-serif",
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "figure.facecolor": "#FFFFFF",
            "axes.facecolor": "#FFFFFF",
        },
    )
    _CHART_LIBS = (plt, ticker, sns)
    return _CHART_LIBS

_APPLE = {
    "graphite": "#1D1D1F",
    "cobalt": "#0066CC",
    "emerald": "#0E6027",
    "amber": "#C2590A",
    "crimson": "#A61B1B",
    "muted": "#636368",
}


def _compact_money_formatter(val: float, _pos: int) -> str:
    av = abs(val)
    if av >= 1_000_000_000:
        return f"{val / 1_000_000_000:.1f}B"
    if av >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    if av >= 1_000:
        return f"{val / 1_000:.0f}k"
    return f"{val:.0f}"


def _fig_to_png_bytes(fig, dpi: int = 180) -> bytes:
    plt, _ticker, _sns = _chart_libs()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="#FFFFFF")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_monthly_cashflow_png(df: pd.DataFrame, currency: str = "INR") -> Optional[bytes]:
    if df is None or df.empty:
        return None
    m = monthly(df)
    if m.empty:
        return None
    plt, ticker, sns = _chart_libs()
    if len(m) > 24:
        # Show last 24 reporting periods to keep labels clean and readable
        m = m.tail(24).copy()

    labels = m["period"].dt.strftime("%Y-%m").tolist()
    x = list(range(len(labels)))
    rev = m["revenue"].astype(float).tolist()
    exp = m["expense"].astype(float).tolist()
    prof = m["profit"].astype(float).tolist()

    fig, ax = plt.subplots(figsize=(8.6, 4.0))
    width = 0.36
    ax.bar([i - width / 2 for i in x], rev, width=width, color=_APPLE["cobalt"], alpha=0.88, label="Revenue")
    ax.bar([i + width / 2 for i in x], exp, width=width, color=_APPLE["amber"], alpha=0.78, label="Expenses")
    ax.plot(x, prof, color=_APPLE["emerald"], linewidth=2.2, marker="o", markersize=4, label="Net Profit")

    ax.set_title(f"Monthly Cashflow & Net Profit ({currency})", pad=10, color=_APPLE["graphite"], loc="left")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(_compact_money_formatter))
    step = max(1, len(labels) // 8)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([labels[i] for i in range(0, len(labels), step)], rotation=22, ha="right")
    ax.axhline(0, color="#8E8E93", linewidth=0.8)
    sns.despine(ax=ax, top=True, right=True)
    ax.legend(frameon=False, loc="upper left", ncol=3, fontsize=9)
    return _fig_to_png_bytes(fig)


def render_segment_profit_png(df: pd.DataFrame, dimension: str = "product", currency: str = "INR") -> Optional[bytes]:
    if df is None or df.empty:
        return None
    rows = by_dimension(df, dimension)
    if not rows:
        return None
    plt, ticker, sns = _chart_libs()
    top = rows[:8]
    seg_df = pd.DataFrame(top)
    names = [str(r.get(dimension) or "Unassigned")[:28] for r in top]
    profits = [float(r.get("profit") or 0.0) for r in top]
    palette = [_APPLE["emerald"] if p >= 0 else _APPLE["crimson"] for p in profits]

    fig, ax = plt.subplots(figsize=(8.4, 3.8))
    y_pos = list(range(len(names)))[::-1]
    ax.barh(y_pos, profits, color=palette, height=0.58, alpha=0.9)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, color=_APPLE["graphite"])
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(_compact_money_formatter))
    ax.axvline(0, color="#8E8E93", linewidth=0.9)
    ax.set_title(f"Top {dimension.title()} Net Profit Ranking ({currency})", pad=10, color=_APPLE["graphite"], loc="left")
    ax.set_xlabel(f"Net Profit ({currency})", color=_APPLE["muted"])
    sns.despine(ax=ax, top=True, right=True)
    # Keep seg_df referenced cleanly so linter knows seaborn compatibility
    _ = len(seg_df)
    return _fig_to_png_bytes(fig)


def render_risk_distribution_png(df: pd.DataFrame, currency: str = "INR") -> Optional[bytes]:
    if df is None or df.empty:
        return None
    plt, _ticker, sns = _chart_libs()
    ms = ml_summary(df)
    counts = [ms["low_risk"], ms["moderate_risk"], ms["high_risk"]]
    labels = [
        f"Low Risk ({ms['low_risk']:,})",
        f"Moderate Risk ({ms['moderate_risk']:,})",
        f"High Risk ({ms['high_risk']:,})",
    ]
    colors = [_APPLE["emerald"], _APPLE["amber"], _APPLE["crimson"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.8, 3.6), gridspec_kw={"width_ratios": [1.0, 1.35]})
    non_zero = [(c, l, col) for c, l, col in zip(counts, labels, colors) if c > 0]
    if non_zero:
        ax1.pie(
            [c for c, _, _ in non_zero],
            labels=[l for _, l, _ in non_zero],
            colors=[col for _, _, col in non_zero],
            wedgeprops={"width": 0.42, "edgecolor": "#FFFFFF", "linewidth": 1.5},
            startangle=90,
            textprops={"fontsize": 8.5, "color": _APPLE["graphite"]},
        )
    ax1.set_title("Random Forest Risk Split", pad=8, color=_APPLE["graphite"], fontsize=11)

    feats = ms.get("feature_importances") or []
    if feats:
        f_names = [f["feature"] for f in feats][::-1]
        f_vals = [f["importance"] for f in feats][::-1]
        ax2.barh(range(len(f_names)), f_vals, color=_APPLE["cobalt"], height=0.52, alpha=0.88)
        ax2.set_yticks(range(len(f_names)))
        ax2.set_yticklabels(f_names, fontsize=8.5, color=_APPLE["graphite"])
        ax2.set_xlabel("Importance (%)", fontsize=9, color=_APPLE["muted"])
        ax2.set_title(f"Top RF Risk Drivers (Mean Score: {ms['avg_risk_score']}/100)", pad=8, color=_APPLE["graphite"], fontsize=11)
        sns.despine(ax=ax2, top=True, right=True)
    else:
        ax2.axis("off")

    fig.suptitle(f"Offline ML Risk Posture ({currency})", fontsize=12, fontweight="bold", color=_APPLE["graphite"], y=1.02)
    return _fig_to_png_bytes(fig)


def render_forecast_png(fc_result: Dict, target: str = "revenue", currency: str = "INR") -> Optional[bytes]:
    if not fc_result or fc_result.get("error"):
        return None
    hist = fc_result.get("history") or []
    fut = fc_result.get("forecast") or []
    if not hist or not fut:
        return None
    plt, ticker, sns = _chart_libs()

    hist_tail = hist[-24:]
    h_labels = [r["period"] for r in hist_tail]
    f_labels = [r["period"] for r in fut]
    all_labels = h_labels + f_labels
    h_vals = [float(r["value"]) for r in hist_tail]
    f_vals = [float(r["value"]) for r in fut]
    lows = [float(r.get("low", r["value"])) for r in fut]
    highs = [float(r.get("high", r["value"])) for r in fut]

    x_hist = list(range(len(h_labels)))
    x_fut = [len(h_labels) - 1] + list(range(len(h_labels), len(all_labels)))
    y_fut = [h_vals[-1]] + f_vals
    y_low = [h_vals[-1]] + lows
    y_high = [h_vals[-1]] + highs

    fig, ax = plt.subplots(figsize=(8.6, 3.8))
    ax.plot(x_hist, h_vals, color=_APPLE["graphite"], linewidth=2.1, marker="o", markersize=3.5, label="Observed History")
    ax.plot(x_fut, y_fut, color=_APPLE["cobalt"], linewidth=2.2, linestyle="--", marker="o", markersize=4, label=fc_result.get("model", "Forecast"))
    ax.fill_between(x_fut, y_low, y_high, color=_APPLE["cobalt"], alpha=0.14, label="Confidence Interval")

    ax.yaxis.set_major_formatter(ticker.FuncFormatter(_compact_money_formatter))
    step = max(1, len(all_labels) // 8)
    ax.set_xticks(list(range(0, len(all_labels), step)))
    ax.set_xticklabels([all_labels[i] for i in range(0, len(all_labels), step)], rotation=22, ha="right")
    ax.set_title(f"{target.title()} Trajectory & {len(f_labels)}-Month Projection ({currency})", pad=10, color=_APPLE["graphite"], loc="left")
    sns.despine(ax=ax, top=True, right=True)
    ax.legend(frameon=False, loc="upper left", ncol=3, fontsize=9)
    return _fig_to_png_bytes(fig)


def build_charts_zip(df: pd.DataFrame, currency: str = "INR", horizon: int = 6) -> bytes:
    """Bundle all rendered Matplotlib/Seaborn executive PNG figures into an in-memory ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        cash = render_monthly_cashflow_png(df, currency=currency)
        if cash:
            zf.writestr("01_monthly_cashflow.png", cash)
        seg = render_segment_profit_png(df, dimension="product", currency=currency)
        if seg:
            zf.writestr("02_top_product_profitability.png", seg)
        dept = render_segment_profit_png(df, dimension="department", currency=currency)
        if dept:
            zf.writestr("03_top_department_profitability.png", dept)
        risk = render_risk_distribution_png(df, currency=currency)
        if risk:
            zf.writestr("04_random_forest_risk_audit.png", risk)
        fc_rev = forecast(df, target="revenue", horizon=horizon)
        fc_png = render_forecast_png(fc_rev, target="revenue", currency=currency)
        if fc_png:
            zf.writestr("05_revenue_forecast_band.png", fc_png)

        zf.writestr(
            "README_Charts.txt",
            (
                "Finance Pulse Analytics - Offline Executive Chart Pack\n"
                "=====================================================\n"
                "Generated 100% locally via Matplotlib + Seaborn at 180 DPI.\n"
                "Ready for slide decks, audit committees, and management reports.\n"
            ),
        )
    buf.seek(0)
    return buf.getvalue()
