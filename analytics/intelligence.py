import numpy as np
from .financial_metrics import metrics, period_growth


def _money(val, currency="INR"):
    if val is None:
        return "N/A"
    sign = "-" if val < 0 else ""
    return f"{sign}{currency} {abs(float(val)):,.2f}"


def _pct(val):
    return "N/A" if val is None else f"{float(val):.2f}%"


def overview_narrative(df, series_rows, margin_threshold=15.0, currency="INR"):
    if df is None or df.empty or not series_rows:
        return None

    m = metrics(df)
    rev = float(m["revenue"] or 0.0)
    exp = float(m["expenses"] or 0.0)
    prof = float(m["profit"] or 0.0)
    margin = m["margin"]

    first_p = series_rows[0]["period"]
    last_p = series_rows[-1]["period"]
    best = max(series_rows, key=lambda r: r["profit"])
    worst = min(series_rows, key=lambda r: r["profit"])

    revs = [r["revenue"] for r in series_rows]
    exps = [r["expense"] for r in series_rows]
    ratios = [r["expense"] / r["revenue"] for r in series_rows if r["revenue"] > 0]

    growth_note = ""
    if len(series_rows) >= 2:
        import pandas as pd
        rg = period_growth(pd.Series(revs))
        eg = period_growth(pd.Series(exps))
        if rg is not None and eg is not None:
            gap = round(rg - eg, 1)
            leverage = "positive operating leverage" if gap >= 0 else "cost growth outpacing revenue"
            growth_note = f" Latest period ({last_p}): revenue {rg:+.1f}% vs. expense {eg:+.1f}% ({leverage})."

    # Counterfactual: what if all months matched the portfolio's best-quartile expense ratio?
    upside = 0.0
    best_ratio_pct = None
    if ratios and len(ratios) >= 2:
        target_ratio = float(np.percentile(ratios, 25))
        best_ratio_pct = round(target_ratio * 100, 1)
        for r in series_rows:
            if r["revenue"] > 0:
                actual_ratio = r["expense"] / r["revenue"]
                if actual_ratio > target_ratio:
                    upside += r["revenue"] * (actual_ratio - target_ratio)

    if upside > 1.0 and best_ratio_pct is not None:
        new_prof = prof + upside
        new_margin = (new_prof / rev * 100) if rev > 0 else None
        what_could_head = f"+{_money(upside, currency)} recoverable profit upside"
        what_could_detail = (
            f"Had higher-cost months matched your best-quartile expense ratio ({best_ratio_pct:.1f}% of revenue), "
            f"cumulative net profit could have reached {_money(new_prof, currency)} ({_pct(new_margin)} margin). "
            f"Run a matching cost scenario in Optimization."
        )
    else:
        latest = series_rows[-1]
        q_runrate = latest["profit"] * 3.0
        trim_save = exp * 0.05
        what_could_head = f"{_money(q_runrate, currency)} annualized quarter pace"
        what_could_detail = (
            f"At {last_p}'s run rate, next-quarter profit projects to {_money(q_runrate, currency)} before seasonality; "
            f"a 5% operating cost discipline pass across this ledger would retain an extra {_money(trim_save, currency)}."
        )

    return {
        "pillars": [
            {
                "step": "01 · What it is",
                "headline": f"{len(series_rows)} monthly period{'s' if len(series_rows) != 1 else ''} ({first_p} to {last_p})",
                "detail": (
                    f"Reconciles {len(df):,} imported transactions into monthly cashflow and margin performance: "
                    f"{_money(rev, currency)} revenue, {_money(exp, currency)} expenses, and {_money(prof, currency)} net profit "
                    f"(target benchmark {margin_threshold:.1f}%)."
                ),
            },
            {
                "step": "02 · What happened",
                "headline": f"{_pct(margin)} net margin · peak in {best['period']}",
                "detail": (
                    f"Net profit peaked in {best['period']} ({_money(best['profit'], currency)}) and troughed in "
                    f"{worst['period']} ({_money(worst['profit'], currency)}).{growth_note}"
                ),
            },
            {
                "step": "03 · What could have happened",
                "headline": what_could_head,
                "detail": what_could_detail,
            },
        ],
        "action": {"label": "Test in Optimization", "endpoint": "user_optimization"},
    }


def dimension_narrative(df, dimension, rows, margin_threshold=15.0, currency="INR"):
    if df is None or df.empty or not rows:
        return None

    dim_label = dimension.title()
    total_rev = sum(float(r.get("revenue") or 0.0) for r in rows)
    total_profit = sum(float(r.get("profit") or 0.0) for r in rows)
    leader = rows[0]
    with_margin = [r for r in rows if r.get("margin") is not None]
    laggard = min(with_margin, key=lambda r: r["margin"]) if with_margin else rows[-1]
    best_margin_row = max(with_margin, key=lambda r: r["margin"]) if with_margin else leader
    below_threshold = [r for r in rows if r.get("margin") is not None and r["margin"] < margin_threshold]

    leader_name = leader.get(dimension) or "Unassigned"
    laggard_name = laggard.get(dimension) or "Unassigned"
    leader_share = (leader["profit"] / total_profit * 100) if total_profit > 0 else None

    share_txt = f" ({leader_share:.1f}% of net profit)" if leader_share is not None else ""
    if len(rows) > 1 and laggard_name != leader_name:
        spread_txt = (
            f" Margins span from {_pct(best_margin_row.get('margin'))} ({best_margin_row.get(dimension)}) "
            f"to {_pct(laggard.get('margin'))} ({laggard_name}), with {len(below_threshold)} segment(s) below your {margin_threshold:.1f}% floor."
        )
    else:
        spread_txt = f" Segment net margin is {_pct(leader.get('margin'))} vs. your {margin_threshold:.1f}% target."

    portfolio_margin = (total_profit / total_rev * 100) if total_rev > 0 else margin_threshold
    benchmark = max(float(margin_threshold), float(portfolio_margin))
    lag_lift = sum(
        r["revenue"] * (benchmark / 100.0) - r["profit"]
        for r in rows
        if r.get("revenue", 0) > 0 and r.get("margin") is not None and r["margin"] < benchmark
    )

    if lag_lift > 1.0 and len(rows) > 1:
        trim_save = float(laggard.get("expense") or 0.0) * 0.10
        new_total = total_profit + lag_lift
        new_margin = (new_total / total_rev * 100) if total_rev > 0 else None
        what_could_head = f"+{_money(lag_lift, currency)} if laggards matched {benchmark:.1f}%"
        what_could_detail = (
            f"Had below-benchmark {dimension}s reached a {benchmark:.1f}% margin, total profit could have risen to "
            f"{_money(new_total, currency)} ({_pct(new_margin)}). Even a 10% expense cut in {laggard_name} adds "
            f"+{_money(trim_save, currency)}."
        )
    else:
        scale_up = float(leader.get("profit") or 0.0) * 0.15
        shock_down = abs(float(leader.get("profit") or 0.0) * 0.20)
        what_could_head = f"+{_money(scale_up, currency)} (+15% leader expansion)"
        what_could_detail = (
            f"Scaling {leader_name} volume by +15% adds +{_money(scale_up, currency)} net profit; conversely, "
            f"a 20% pullback in {leader_name} exposes {_money(shock_down, currency)} of current earnings."
        )

    return {
        "pillars": [
            {
                "step": "01 · What it is",
                "headline": f"{len(rows)} {dimension} segment{'s' if len(rows) != 1 else ''} ranked by profit",
                "detail": (
                    f"Evaluates {_money(total_rev, currency)} total revenue and {_money(total_profit, currency)} net profit "
                    f"across {len(df):,} transactions grouped by {dim_label}, benchmarked against {margin_threshold:.1f}% minimum margin."
                ),
            },
            {
                "step": "02 · What happened",
                "headline": f"{leader_name} leads at {_money(leader['profit'], currency)}{share_txt}",
                "detail": (
                    f"{leader_name} earned {_pct(leader.get('margin'))} margin on {_money(leader['revenue'], currency)} revenue."
                    f"{spread_txt}"
                ),
            },
            {
                "step": "03 · What could have happened",
                "headline": what_could_head,
                "detail": what_could_detail,
            },
        ],
        "action": {"label": "Model segment levers", "endpoint": "user_optimization"},
    }


def anomalies_narrative(df, flags, threshold=1.5, currency="INR"):
    if df is None or df.empty:
        return None

    m = metrics(df)
    rev = float(m["revenue"] or 0.0)
    prof = float(m["profit"] or 0.0)
    reported_margin = m["margin"]

    if not flags:
        return {
            "pillars": [
                {
                    "step": "01 · What it is",
                    "headline": f"IQR outlier screen ({threshold:.1f}× fence)",
                    "detail": (
                        f"Independently evaluates positive revenue and expense distributions across {len(df):,} transactions "
                        f"using Q3 + {threshold:.1f} × (Q3 − Q1)."
                    ),
                },
                {
                    "step": "02 · What happened",
                    "headline": "0 statistical outliers flagged",
                    "detail": (
                        f"Every transaction remained inside your {threshold:.1f}× interquartile cutoff. Baseline net profit sits at "
                        f"{_money(prof, currency)} ({_pct(reported_margin)} margin)."
                    ),
                },
                {
                    "step": "03 · What could happen",
                    "headline": "Tighten sensitivity to surface milder spikes",
                    "detail": (
                        f"Lowering the anomaly threshold from {threshold:.1f}× toward 1.0× IQR in Admin Settings increases sensitivity "
                        f"if moderate seasonal or vendor cost drifts require review."
                    ),
                },
            ],
            "action": {"label": "Review optimization impact", "endpoint": "user_optimization"},
        }

    exp_flags = [f for f in flags if f.get("type") == "Expense"]
    rev_flags = [f for f in flags if f.get("type") == "Revenue"]
    iso_hits = sum(1 for f in flags if "Isolation Forest" in str(f.get("method", "")))
    top = flags[0]
    exp_excess = sum(max(0.0, float(f["value"]) - float(f.get("threshold") or f["value"])) for f in exp_flags)
    rev_excess = sum(max(0.0, float(f["value"]) - float(f.get("threshold") or f["value"])) for f in rev_flags)

    if exp_excess > 0:
        norm_prof = prof + exp_excess
        norm_margin = (norm_prof / rev * 100) if rev > 0 else None
        what_could_head = f"+{_money(exp_excess, currency)} absorbed by expense spikes"
        what_could_detail = (
            f"Had the {len(exp_flags)} outlier expense(s) stayed at the {threshold:.1f}× IQR ceiling instead of exceeding it, "
            f"normalized net profit would have been {_money(norm_prof, currency)} ({_pct(norm_margin)} vs. {_pct(reported_margin)} reported)."
        )
    else:
        norm_prof = prof - rev_excess
        norm_rev = rev - rev_excess
        norm_margin = (norm_prof / norm_rev * 100) if norm_rev > 0 else None
        what_could_head = f"{_money(norm_prof, currency)} recurring ex-spike profit"
        what_could_detail = (
            f"Removing +{_money(rev_excess, currency)} of outlier revenue surges above normal cadence leaves "
            f"{_money(norm_prof, currency)} recurring profit ({_pct(norm_margin)} margin) so budgets don't over-extrapolate one-offs."
        )

    iso_note = f" ({iso_hits} confirmed by Isolation Forest)" if iso_hits else ""
    return {
        "pillars": [
            {
                "step": "01 · What it is",
                "headline": f"Hybrid IQR + Isolation Forest audit across {len(df):,} records",
                "detail": (
                    f"Screens individual transactions exceeding Q3 + {threshold:.1f} × IQR alongside multi-feature "
                    f"Isolation Forest density & SciPy Z-scores for audit review."
                ),
            },
            {
                "step": "02 · What happened",
                "headline": f"{len(flags)} outlier{'s' if len(flags) != 1 else ''} detected ({len(exp_flags)} expense, {len(rev_flags)} revenue){iso_note}",
                "detail": (
                    f"Largest flag: {top['date']} · {top['entity']} ({top['type']} of {_money(top['value'], currency)}, "
                    f"above cutoff {_money(top.get('threshold'), currency)})."
                ),
            },
            {
                "step": "03 · What could have happened",
                "headline": what_could_head,
                "detail": what_could_detail,
            },
        ],
        "action": {"label": "Stress-test in Optimization", "endpoint": "user_optimization"},
    }


def forecast_narrative(result, target, horizon, currency="INR"):
    if not result or result.get("error") or not result.get("history") or not result.get("forecast"):
        return None

    hist = result["history"]
    fc = result["forecast"]
    acc = result["accuracy"]
    model_name = result.get("model", "Linear trend regression")
    is_rf = result.get("model_code") == "random_forest" or "Random Forest" in model_name
    first_v, last_v = hist[0]["value"], hist[-1]["value"]
    end_v = fc[-1]["value"]
    cum_fc = sum(item["value"] for item in fc)
    hist_delta_pct = ((last_v - first_v) / abs(first_v) * 100) if first_v else None
    fc_delta_pct = ((end_v - last_v) / abs(last_v) * 100) if last_v else None

    hist_dir = "expanded" if last_v >= first_v else "contracted"
    hist_pct_txt = f" ({hist_delta_pct:+.1f}%)" if hist_delta_pct is not None else ""
    fc_pct_txt = f" ({fc_delta_pct:+.1f}%)" if fc_delta_pct is not None else ""
    mape_txt = f", {acc['mape']:.2f}% MAPE" if acc.get("mape") is not None else ""
    method_headline = (
        f"{len(hist)}-month Random Forest forecast on {target}"
        if is_rf else f"{len(hist)}-month linear trend on {target}"
    )
    method_detail = (
        f"Trains an offline 180-tree scikit-learn Random Forest regressor across {hist[0]['period']} to {hist[-1]['period']} "
        f"using lagged cashflow, 3-month rolling momentum, and seasonality, extending {horizon} months to {fc[-1]['period']}."
        if is_rf else
        f"Fits an ordinary least-squares trend across {hist[0]['period']} to {hist[-1]['period']} "
        f"and extends {horizon} monthly periods forward to {fc[-1]['period']}."
    )

    return {
        "pillars": [
            {
                "step": "01 · What it is",
                "headline": method_headline,
                "detail": method_detail,
            },
            {
                "step": "02 · What happened",
                "headline": f"Historically {hist_dir} to {_money(last_v, currency)}{hist_pct_txt}",
                "detail": (
                    f"{target.title()} moved from {_money(first_v, currency)} ({hist[0]['period']}) to {_money(last_v, currency)} "
                    f"({hist[-1]['period']}), with {_money(acc['mae'], currency)} historical MAE{mape_txt}."
                ),
            },
            {
                "step": "03 · What could happen",
                "headline": f"Projects {_money(end_v, currency)} by {fc[-1]['period']}{fc_pct_txt}",
                "detail": (
                    f"Projected cumulative {horizon}-month {target} totals "
                    f"{_money(cum_fc, currency)} (±{_money(acc['mae'], currency)} historical MAE band)."
                ),
            },
        ],
        "action": {"label": "Simulate deliberate changes", "endpoint": "user_optimization"},
    }


def ml_insights_narrative(ml_summary_data, runway_data, currency="INR"):
    if not ml_summary_data or not ml_summary_data.get("total"):
        return None
    total = ml_summary_data["total"]
    high_c = ml_summary_data["high_risk"]
    mod_c = ml_summary_data["moderate_risk"]
    low_c = ml_summary_data["low_risk"]
    exposure = ml_summary_data.get("high_risk_exposure", 0.0)
    top_feat = ml_summary_data["feature_importances"][0]["feature"] if ml_summary_data.get("feature_importances") else "Margin Ratio"
    runway_status = (runway_data or {}).get("status", "Evaluated")
    rec_net = (runway_data or {}).get("recent_monthly_net", 0.0)
    runway_m = (runway_data or {}).get("runway_months")
    runway_txt = f"{runway_m} months buffer" if runway_m is not None else "self-sustaining positive cashflow"
    return {
        "pillars": [
            {
                "step": "01 · What it is",
                "headline": f"Random Forest risk & runway score across {total:,} entries",
                "detail": f"Classifies ledger entries offline into Low ({low_c:,}), Moderate ({mod_c:,}), and High Risk ({high_c:,}) with 0 external calls.",
            },
            {
                "step": "02 · What happened",
                "headline": f"{high_c:,} High Risk entries · {runway_status}",
                "detail": f"Recent monthly net pace is {_money(rec_net, currency)} ({runway_txt}); top RF risk driver is {top_feat}.",
            },
            {
                "step": "03 · What could happen",
                "headline": f"{_money(exposure, currency)} high-risk spend exposure under watch",
                "detail": "Inspecting top flagged disbursements before approvals protects liquidity and lifts baseline savings rate.",
            },
        ],
        "action": {"label": "Inspect flagged entries", "endpoint": "user_analytics", "args": {"view": "anomalies"}},
    }
