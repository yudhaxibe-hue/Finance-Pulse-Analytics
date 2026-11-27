import numpy as np
import pandas as pd
from .financial_metrics import metrics, period_growth


def _money(val, currency="INR"):
    if val is None:
        return "N/A"
    sign = "-" if val < 0 else ""
    return f"{sign}{currency} {abs(float(val)):,.2f}"


def _pct(val):
    return "N/A" if val is None else f"{float(val):.2f}%"


def _format_period(val):
    if val is None:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%b %Y")
    s = str(val).strip()
    if " " in s:
        s = s.split(" ")[0]
    parts = s.split("-")
    if len(parts) >= 2 and len(parts[0]) == 4:
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        try:
            m_idx = int(parts[1]) - 1
            if 0 <= m_idx < 12:
                return f"{months[m_idx]} {parts[0]}"
        except Exception:
            pass
    return s


def detect_audit_persona(df) -> dict:
    if df is None or df.empty:
        return {
            "mode": "enterprise",
            "type_label": "Audit Mode: Corporate P&L",
            "confidence": 0.50,
            "income_label": "Gross Revenue",
            "expense_label": "Operating Expenses (OPEX)",
            "profit_label": "Operating Profit (EBITDA)",
            "margin_label": "Operating Margin %",
            "reasons": ["Default baseline configuration"],
        }

    p_score = 0.0
    e_score = 0.0
    reasons = []

    # Map column names case-insensitively and space-insensitively
    col_map = {str(c).strip().lower().replace(" ", "_"): c for c in df.columns}

    # 1. Schema & Header Fingerprint (Weight: 35%)
    has_need_want = False
    cust_col = col_map.get("customer_segment") or col_map.get("need_or_want")
    if cust_col and cust_col in df:
        val_sample = " ".join(df[cust_col].dropna().astype(str).str.lower().head(40))
        if "need" in val_sample or "want" in val_sample:
            has_need_want = True
            p_score += 20
            reasons.append("Detected 50/30/20 Need vs Want budget classification")

    inv_col = col_map.get("investment") or col_map.get("savings") or col_map.get("savings_inr")
    if inv_col and inv_col in df:
        try:
            inv_sum = float(pd.to_numeric(df[inv_col], errors="coerce").fillna(0.0).sum())
            if inv_sum > 0:
                p_score += 10
                reasons.append("Detected personal recurring deposit / savings retention")
        except Exception:
            pass

    if any(k in col_map for k in ("running_balance", "running_balance_inr", "pocket_money", "allowance")):
        p_score += 8
        reasons.append("Found running bank balance / personal allowance tracking")

    dep_col = col_map.get("department")
    cent_col = col_map.get("cost_center")
    tax_col = col_map.get("tax_amount") or col_map.get("tax") or col_map.get("gstin")
    sku_col = col_map.get("product_sku") or col_map.get("sku")
    reg_col = col_map.get("region") or col_map.get("territory")
    cogs_col = col_map.get("cogs") or col_map.get("cost")

    non_empty_deps = dep_col and (df[dep_col].dropna().astype(str).str.strip().ne("").sum() > 3)
    non_empty_centers = cent_col and (df[cent_col].dropna().astype(str).str.strip().ne("").sum() > 3)
    non_empty_sku = sku_col and (df[sku_col].dropna().astype(str).str.strip().ne("").sum() > 3)
    non_empty_reg = reg_col and (df[reg_col].dropna().astype(str).str.strip().ne("").sum() > 3)
    non_empty_tax = False
    if tax_col and tax_col in df:
        try:
            non_empty_tax = float(pd.to_numeric(df[tax_col], errors="coerce").fillna(0.0).sum()) > 0
        except Exception:
            pass
    non_empty_cogs = False
    if cogs_col and cogs_col in df:
        try:
            non_empty_cogs = float(pd.to_numeric(df[cogs_col], errors="coerce").fillna(0.0).sum()) > 0
        except Exception:
            pass

    if non_empty_deps:
        e_score += 15
        reasons.append("Found multi-department corporate allocations")
    if non_empty_centers:
        e_score += 12
        reasons.append("Found cost center operational units")
    if non_empty_tax or non_empty_cogs:
        e_score += 10
        reasons.append("Found business tax / GST / COGS accounting lines")
    if non_empty_sku or non_empty_reg:
        e_score += 8

    # 2. Semantic Vocabulary & Payee Clustering + Term Density (Weight: 45%)
    personal_keywords = {
        "salary", "stipend", "mess", "tiffin", "rent", "pg", "groceries", "fruits",
        "vegetables", "milk", "tea", "coffee", "snacks", "outing", "outings", "restaurant",
        "restaurants", "dining", "cinema", "movie", "pvr", "bus", "mtc", "metro", "auto",
        "recharge", "airtel", "jio", "laundry", "toiletries", "tuition", "college", "fees",
        "pharmacy", "medical", "doctor", "ott", "netflix", "hotstar", "swiggy", "zomato",
        "sent home", "family support", "recurring deposit", "rd", "sip", "pocket money",
        "saravana bhavan", "tea kadai", "amma mess", "local market", "apollo pharmacy", "pvr cinemas",
    }
    enterprise_keywords = {
        "payroll", "accounts payable", "accounts receivable", "aws", "azure", "gcp", "cloud",
        "saas", "software licenses", "office lease", "logistics", "freight", "b2b",
        "vendor contract", "depreciation", "audit fees", "procurement", "consulting fees",
        "legal compliance", "marketing ad spend", "inventory", "purchase order", "po number",
        "cogs", "client retainer", "sales pipeline", "vendor retainer",
    }

    text_cols = [col_map[k] for k in ("category", "subcategory", "vendor_name", "payee", "notes", "description") if k in col_map]
    total_rows = max(1, len(df))
    p_row_matches = 0
    e_row_matches = 0
    if text_cols:
        row_texts = df[text_cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
        for txt in row_texts.tolist():
            if any(kw in txt for kw in personal_keywords):
                p_row_matches += 1
            if any(kw in txt for kw in enterprise_keywords):
                e_row_matches += 1

    p_density = p_row_matches / total_rows
    e_density = e_row_matches / total_rows

    if p_density > 0:
        p_score += round(min(45.0, p_density * 65.0), 1)
        reasons.append(f"Semantic density: {p_density * 100:.0f}% of transactions match personal lifestyle/payee terms")
    if e_density > 0:
        e_score += round(min(45.0, e_density * 65.0), 1)
        reasons.append(f"Semantic density: {e_density * 100:.0f}% of transactions match B2B enterprise terms")

    # 3. Cashflow Topology & Micro-Transaction Cadence (Weight: 20%)
    rev_col = col_map.get("revenue") or col_map.get("revenue_inr") or col_map.get("credit")
    exp_col = col_map.get("expense") or col_map.get("expenses") or col_map.get("expenses_inr") or col_map.get("debit")
    rev_txns = 0
    if rev_col and rev_col in df:
        try:
            rev_txns = int((pd.to_numeric(df[rev_col], errors="coerce").fillna(0.0) > 0).sum())
        except Exception:
            pass

    if total_rows >= 10:
        inflow_ratio = rev_txns / total_rows
        if inflow_ratio <= 0.08 and rev_txns > 0:
            p_score += 12
            reasons.append(f"Discrete inflow cadence ({rev_txns} income credits across {total_rows} transactions)")
        elif inflow_ratio >= 0.25:
            e_score += 15
            reasons.append(f"Continuous revenue inflow stream ({rev_txns} receipts across {total_rows} transactions)")

    if exp_col and exp_col in df:
        try:
            exp_vals = pd.to_numeric(df[exp_col], errors="coerce").dropna()
            pos_exps = exp_vals[exp_vals > 0]
            if len(pos_exps) >= 5:
                micro_ratio = float((pos_exps <= 500.0).mean())
                if micro_ratio >= 0.45:
                    p_score += 10
                    reasons.append(f"Consumer micro-transaction profile ({micro_ratio * 100:.0f}% outflows <= 500)")
        except Exception:
            pass

    is_personal = (p_score > e_score) or (has_need_want and p_score >= 30)
    confidence = min(0.99, max(0.60, round((p_score / (p_score + e_score + 1e-6)) if is_personal else (e_score / (p_score + e_score + 1e-6)), 2)))

    if is_personal:
        return {
            "mode": "personal",
            "type_label": "Audit Mode: Personal & Household Ledger",
            "confidence": confidence,
            "income_label": "Total Inflow / Monthly Salary",
            "expense_label": "Living & Lifestyle Expenses",
            "profit_label": "Net Surplus & Retained Cash",
            "margin_label": "Savings & Retention Rate %",
            "reasons": reasons[:3],
        }
    else:
        return {
            "mode": "enterprise",
            "type_label": "Audit Mode: Corporate P&L",
            "confidence": confidence,
            "income_label": "Gross Revenue",
            "expense_label": "Operating Expenses (OPEX)",
            "profit_label": "Operating Profit (EBITDA)",
            "margin_label": "Operating Margin %",
            "reasons": reasons[:3],
        }


def overview_narrative(df, series_rows, margin_threshold=15.0, currency="INR"):
    if df is None or df.empty or not series_rows:
        return None

    m = metrics(df)
    rev = float(m["revenue"] or 0.0)
    exp = float(m["expenses"] or 0.0)
    prof = float(m["profit"] or 0.0)
    margin = m["margin"]

    first_p = _format_period(series_rows[0]["period"])
    last_p = _format_period(series_rows[-1]["period"])
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

    persona = detect_audit_persona(df)
    is_personal = persona["mode"] == "personal"

    if is_personal:
        savings_note = f" (Includes {_money(m.get('total_savings', 0), currency)} dedicated RD/SIP savings at a {m.get('savings_rate') or 0:.1f}% savings rate)." if m.get("total_savings") else ""
        step1_detail = (
            f"Reconciles {len(df):,} personal transactions into monthly household cashflow: "
            f"{_money(rev, currency)} total income/inflow, {_money(exp, currency)} living expenses, and {_money(prof, currency)} retained savings "
            f"({_pct(margin)} retention rate).{savings_note}"
        )
        step2_head = f"{_pct(margin)} savings retention rate · peak in {_format_period(best['period'])}"
        step2_detail = (
            f"Net monthly surplus peaked in {_format_period(best['period'])} ({_money(best['profit'], currency)}) and troughed in "
            f"{_format_period(worst['period'])} ({_money(worst['profit'], currency)}).{growth_note}"
        )
        step3_head = f"+{_money(upside or (exp * 0.10), currency)} 50/30/20 budget optimization upside"
        step3_detail = (
            f"Aligning discretionary wants (dining, entertainment, leisure) to 30% of income and curtailing lifestyle leaks "
            f"could retain an additional +{_money(upside or (exp * 0.10), currency)} in emergency funds and recurring investments."
        )
    else:
        step1_detail = (
            f"Reconciles {len(df):,} imported transactions into monthly cashflow and margin performance: "
            f"{_money(rev, currency)} revenue, {_money(exp, currency)} expenses, and {_money(prof, currency)} net profit "
            f"(target benchmark {margin_threshold:.1f}%)."
        )
        step2_head = f"{_pct(margin)} net margin · peak in {_format_period(best['period'])}"
        step2_detail = (
            f"Net profit peaked in {_format_period(best['period'])} ({_money(best['profit'], currency)}) and troughed in "
            f"{_format_period(worst['period'])} ({_money(worst['profit'], currency)}).{growth_note}"
        )
        step3_head = what_could_head
        step3_detail = what_could_detail

    return {
        "pillars": [
            {
                "step": "01 · What it is",
                "headline": f"{len(series_rows)} monthly period{'s' if len(series_rows) != 1 else ''} ({first_p} to {last_p})",
                "detail": step1_detail,
            },
            {
                "step": "02 · What happened",
                "headline": step2_head,
                "detail": step2_detail,
            },
            {
                "step": "03 · What could have happened",
                "headline": step3_head,
                "detail": step3_detail,
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
    is_run_rate = result.get("is_fallback") or result.get("model_code") == "run_rate_pace"
    first_v, last_v = hist[0]["value"], hist[-1]["value"]
    end_v = fc[-1]["value"]
    cum_fc = sum(item["value"] for item in fc)
    hist_delta_pct = ((last_v - first_v) / abs(first_v) * 100) if first_v else None
    fc_delta_pct = ((end_v - last_v) / abs(last_v) * 100) if last_v else None

    hist_dir = "expanded" if last_v >= first_v else "contracted"
    hist_pct_txt = f" ({hist_delta_pct:+.1f}%)" if hist_delta_pct is not None else ""
    fc_pct_txt = f" ({fc_delta_pct:+.1f}%)" if fc_delta_pct is not None else ""
    mape_txt = f", {acc['mape']:.2f}% MAPE" if acc.get("mape") is not None else ""
    first_p = _format_period(hist[0]['period'])
    last_p = _format_period(hist[-1]['period'])
    fc_end_p = _format_period(fc[-1]['period'])

    if is_run_rate:
        method_headline = f"{len(hist)}-month run-rate pace forecast on {target}"
        method_detail = (
            f"Adaptive run-rate velocity model projecting {horizon} periods forward to {fc_end_p} "
            f"based on {len(hist)} historical periods ({first_p} to {last_p}) until 4+ months are accumulated."
        )
    elif is_rf:
        method_headline = f"{len(hist)}-month Random Forest forecast on {target}"
        method_detail = (
            f"Trains an offline 180-tree scikit-learn Random Forest regressor across {first_p} to {last_p} "
            f"using lagged cashflow, 3-month rolling momentum, and seasonality, extending {horizon} months to {fc_end_p}."
        )
    else:
        method_headline = f"{len(hist)}-month linear trend on {target}"
        method_detail = (
            f"Fits an ordinary least-squares trend across {first_p} to {last_p} "
            f"and extends {horizon} monthly periods forward to {fc_end_p}."
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
                    f"{target.title()} moved from {_money(first_v, currency)} ({first_p}) to {_money(last_v, currency)} "
                    f"({last_p}), with {_money(acc['mae'], currency)} historical MAE{mape_txt}."
                ),
            },
            {
                "step": "03 · What could happen",
                "headline": f"Projects {_money(end_v, currency)} by {fc_end_p}{fc_pct_txt}",
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
