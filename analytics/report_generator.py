"""
Executive Financial Report PDF Generator.
Produces publication-grade, Goldman Sachs / Apple tear-sheet PDF reports
with mode-aware intelligence, structured KPI matrix, breakdown tables,
and visual trend decomposition. 100% offline via ReportLab.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .financial_metrics import budget_50_30_20, compute_cashflow_runway, metrics, monthly
from .intelligence import detect_audit_persona, overview_narrative
from .ml_engine import ml_summary
from .profitability import by_dimension
from .visuals import render_monthly_cashflow_png, render_segment_profit_png

# Design Tokens (Apple / Executive Tear-sheet)
_C_PRIMARY = HexColor("#1D1D1F")
_C_SECONDARY = HexColor("#48484A")
_C_MUTED = HexColor("#86868B")
_C_BORDER = HexColor("#E5E5EA")
_C_CARD_BG = HexColor("#F8F9FA")
_C_CARD_ALT = HexColor("#F2F4F7")
_C_WHITE = HexColor("#FFFFFF")
_C_COBALT = HexColor("#0066CC")
_C_COBALT_LIGHT = HexColor("#EBF3FC")
_C_EMERALD = HexColor("#0E6027")
_C_EMERALD_LIGHT = HexColor("#EAF7EE")
_C_AMBER = HexColor("#C2590A")
_C_AMBER_LIGHT = HexColor("#FEF5EB")
_C_CRIMSON = HexColor("#A61B1B")
_C_CRIMSON_LIGHT = HexColor("#FDECEC")

PAGE_W, PAGE_H = A4  # 595.28, 841.89
MARGIN = 36.0
USABLE_W = PAGE_W - (MARGIN * 2)  # 523.28


def _draw_pill(pdf: canvas.Canvas, x: float, y: float, w: float, h: float, text: str, bg: HexColor, fg: HexColor, font_size: float = 7.5):
    pdf.setFillColor(bg)
    pdf.setStrokeColor(bg)
    pdf.roundRect(x, y, w, h, h / 2, fill=1, stroke=0)
    pdf.setFillColor(fg)
    pdf.setFont("Helvetica-Bold", font_size)
    pdf.drawCentredString(x + (w / 2), y + (h / 2) - (font_size * 0.35), text)


def _draw_kpi_card(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    label: str,
    value: str,
    sub: str = "",
    accent_color: HexColor = _C_COBALT,
):
    pdf.setFillColor(_C_CARD_BG)
    pdf.setStrokeColor(_C_BORDER)
    pdf.setLineWidth(0.8)
    pdf.roundRect(x, y, w, h, 6, fill=1, stroke=1)

    # Accent top stripe (2pt)
    pdf.setFillColor(accent_color)
    pdf.setStrokeColor(accent_color)
    pdf.roundRect(x + 10, y + h - 2.5, w - 20, 2.5, 1, fill=1, stroke=0)

    # Label
    pdf.setFillColor(_C_MUTED)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(x + 12, y + h - 16, label.upper())

    # Value
    pdf.setFillColor(_C_PRIMARY)
    pdf.setFont("Helvetica-Bold", 12.5)
    pdf.drawString(x + 12, y + h - 31, value)

    # Subtext (if any)
    if sub:
        pdf.setFillColor(_C_MUTED)
        pdf.setFont("Helvetica", 7.5)
        # truncate if too long
        if len(sub) > 36:
            sub = sub[:34] + "…"
        pdf.drawString(x + 12, y + 8, sub)


def build_executive_pdf(
    df: pd.DataFrame,
    currency: str = "INR",
    user_name: str = "Workspace",
    persona: Optional[Dict[str, Any]] = None,
    margin_threshold: float = 15.0,
) -> bytes:
    """Builds a 2-page executive financial tear-sheet PDF."""
    if df is None:
        df = pd.DataFrame(columns=["txn_date", "revenue", "expense", "cost", "investment"])
    if persona is None:
        persona = detect_audit_persona(df)

    is_pers = (persona.get("mode") == "personal")
    m = metrics(df)
    runway = compute_cashflow_runway(df)
    ms = ml_summary(df)
    b_rule = budget_50_30_20(df) if is_pers else None

    # Series rows for 3-pillar narrative
    series_df = monthly(df)
    series_rows = []
    if not series_df.empty:
        series_rows = [
            {
                "period": r["period"].strftime("%Y-%m"),
                "revenue": float(r["revenue"]),
                "expense": float(r["expense"]),
                "profit": float(r["profit"]),
                "margin": float(r["margin"]) if r["margin"] is not None else 0.0,
            }
            for _, r in series_df.iterrows()
        ]
    brief = overview_narrative(df, series_rows, margin_threshold=margin_threshold, currency=currency)

    # Dimension for breakdown table
    dim = "category" if is_pers else ("product" if "product" in df and df["product"].nunique() > 1 else "department")
    dim_rows = by_dimension(df, dim)
    top_dims = [r for r in dim_rows if str(r.get(dim) or "").strip() not in ("", "Unassigned")][:5]
    if not top_dims:
        top_dims = dim_rows[:5]

    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    pdf.setTitle("Finance Pulse Analytics — Executive Financial Tear-Sheet")

    # =========================================================================
    # PAGE 1: Executive Financial Tear-Sheet
    # =========================================================================

    # 1. Top Decorative Brand Stripe
    pdf.setFillColor(_C_COBALT)
    pdf.rect(0, PAGE_H - 5, PAGE_W, 5, fill=1, stroke=0)

    # 2. Header Block
    y = PAGE_H - 36
    pdf.setFillColor(_C_PRIMARY)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(MARGIN, y, "Finance Pulse Analytics")

    # Mode Pill next to title
    mode_text = "PERSONAL & HOUSEHOLD LEDGER" if is_pers else "CORPORATE P&L INTELLIGENCE"
    mode_bg = _C_EMERALD_LIGHT if is_pers else _C_COBALT_LIGHT
    mode_fg = _C_EMERALD if is_pers else _C_COBALT
    _draw_pill(pdf, MARGIN + 235, y - 2, 160, 16, mode_text, mode_bg, mode_fg, font_size=7)

    # Metadata (Right Aligned)
    pdf.setFillColor(_C_PRIMARY)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawRightString(PAGE_W - MARGIN, y + 2, f"Workspace: {user_name}")
    pdf.setFillColor(_C_MUTED)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawRightString(PAGE_W - MARGIN, y - 10, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | Currency: {currency}")

    # Subtitle
    pdf.setFillColor(_C_SECONDARY)
    pdf.setFont("Helvetica", 9)
    sub_title = (
        "Personal Cashflow, 50/30/20 Budget Optimization & Net Surplus Audit"
        if is_pers
        else "Enterprise Financial Performance Intelligence & Profitability Analytics Platform"
    )
    pdf.drawString(MARGIN, y - 18, sub_title)

    # Hairline divider
    pdf.setStrokeColor(_C_BORDER)
    pdf.setLineWidth(0.8)
    pdf.line(MARGIN, y - 26, PAGE_W - MARGIN, y - 26)

    # 3. KPI Cards Grid (2 rows x 3 columns)
    card_gap = 10.0
    card_w = (USABLE_W - (card_gap * 2)) / 3.0  # ~167.76
    card_h = 48.0
    r1_y = y - 82.0
    r2_y = r1_y - card_h - card_gap

    rev_val = float(m.get("revenue") or 0.0)
    exp_val = float(m.get("expenses") or 0.0)
    prof_val = float(m.get("profit") or 0.0)
    margin_val = m.get("margin")
    total_sav = float(m.get("total_savings") or 0.0)

    def _fmt_curr(val: float) -> str:
        return f"{currency} {val:,.2f}"

    def _fmt_pct(val: Optional[float]) -> str:
        return f"{val:.2f}%" if val is not None else "N/A"

    if is_pers:
        kpis = [
            ("Total Inflow / Salary", _fmt_curr(rev_val), f"{m.get('transactions', 0)} transactions", _C_COBALT),
            ("Living Expenses", _fmt_curr(exp_val), f"{_fmt_pct(m.get('expense_ratio'))} of inflow", _C_AMBER),
            ("Net Cash Surplus", _fmt_curr(prof_val), "Retained liquid buffer", _C_EMERALD if prof_val >= 0 else _C_CRIMSON),
            ("Savings & Retention %", _fmt_pct(margin_val), "Net surplus margin", _C_EMERALD if (margin_val or 0) >= 0 else _C_CRIMSON),
            ("Retained Savings", _fmt_curr(total_sav), "Committed investments", _C_COBALT),
            (
                "50/30/20 Budget Health",
                f"Needs {b_rule['needs']['pct']}%" if b_rule else "50/30/20 Plan",
                f"Wants {b_rule['wants']['pct']}% · Sav {b_rule['savings']['pct']}%" if b_rule else "Balanced budget",
                _C_EMERALD if (b_rule and b_rule["needs"]["pct"] <= 50) else _C_AMBER,
            ),
        ]
    else:
        kpis = [
            ("Gross Revenue", _fmt_curr(rev_val), f"{m.get('transactions', 0)} commercial entries", _C_COBALT),
            ("Operating Expenses (OPEX)", _fmt_curr(exp_val), f"{_fmt_pct(m.get('expense_ratio'))} expense ratio", _C_AMBER),
            ("Net Operating Profit (EBITDA)", _fmt_curr(prof_val), f"Net margin {_fmt_pct(margin_val)}", _C_EMERALD if prof_val >= 0 else _C_CRIMSON),
            ("Operating Margin %", _fmt_pct(margin_val), f"Target threshold: {margin_threshold:.0f}%", _C_EMERALD if (margin_val or 0) >= margin_threshold else _C_AMBER),
            ("Cost of Goods Sold (COGS)", _fmt_curr(float(m.get("cost") or 0.0)), f"Gross profit: {_fmt_curr(float(m.get('gross_profit') or 0.0))}", _C_COBALT),
            ("Expense Ratio & ROI", f"ROI: {_fmt_pct(m.get('roi'))}", f"Posture: {runway.get('status', 'Stable')}", _C_EMERALD),
        ]

    for idx, (label, val_str, sub_str, col) in enumerate(kpis):
        col_idx = idx % 3
        row_idx = idx // 3
        cx = MARGIN + (col_idx * (card_w + card_gap))
        cy = r1_y if row_idx == 0 else r2_y
        _draw_kpi_card(pdf, cx, cy, card_w, card_h, label, val_str, sub_str, accent_color=col)

    # 4. Top Contribution Breakdown Table
    table_top_y = r2_y - 20
    pdf.setFillColor(_C_PRIMARY)
    pdf.setFont("Helvetica-Bold", 10.5)
    dim_title = "Category Expense & Inflow Breakdown" if is_pers else f"Top {dim.title()} Profitability & Revenue Contribution"
    pdf.drawString(MARGIN, table_top_y, dim_title)
    pdf.setFillColor(_C_MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(PAGE_W - MARGIN, table_top_y, "Top 5 Ledger Entities")

    # Table Box
    tbl_y = table_top_y - 128
    tbl_h = 120
    pdf.setFillColor(_C_WHITE)
    pdf.setStrokeColor(_C_BORDER)
    pdf.roundRect(MARGIN, tbl_y, USABLE_W, tbl_h, 6, fill=1, stroke=1)

    # Table Header Row
    header_h = 22.0
    hdr_y = tbl_y + tbl_h - header_h
    pdf.setFillColor(_C_CARD_ALT)
    pdf.rect(MARGIN, hdr_y, USABLE_W, header_h, fill=1, stroke=0)
    pdf.setStrokeColor(_C_BORDER)
    pdf.line(MARGIN, hdr_y, PAGE_W - MARGIN, hdr_y)

    pdf.setFillColor(_C_SECONDARY)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(MARGIN + 12, hdr_y + 7, "ITEM / ENTITY NAME")
    pdf.drawRightString(MARGIN + 280, hdr_y + 7, "INFLOW / REVENUE" if is_pers else "REVENUE")
    pdf.drawRightString(MARGIN + 410, hdr_y + 7, "OUTFLOW / EXPENSES" if is_pers else "NET PROFIT")
    pdf.drawRightString(PAGE_W - MARGIN - 12, hdr_y + 7, "BUDGET SHARE" if is_pers else "MARGIN %")

    # Table Rows (5 rows)
    row_h = 19.0
    for r_i, r_data in enumerate(top_dims[:5]):
        ry = hdr_y - ((r_i + 1) * row_h)
        # zebra shading
        if r_i % 2 == 1:
            pdf.setFillColor(_C_CARD_BG)
            pdf.rect(MARGIN + 0.5, ry, USABLE_W - 1, row_h, fill=1, stroke=0)

        pdf.setStrokeColor(HexColor("#F0F0F2"))
        pdf.setLineWidth(0.5)
        pdf.line(MARGIN, ry, PAGE_W - MARGIN, ry)

        name = str(r_data.get(dim) or "Unassigned")
        if len(name) > 38:
            name = name[:36] + "…"
        rev_item = float(r_data.get("revenue") or 0.0)
        exp_item = float(r_data.get("expense") or 0.0)
        prof_item = float(r_data.get("profit") or 0.0)
        margin_item = r_data.get("margin")

        pdf.setFillColor(_C_PRIMARY)
        pdf.setFont("Helvetica", 8.5)
        pdf.drawString(MARGIN + 12, ry + 5.5, name)

        pdf.setFillColor(_C_SECONDARY)
        pdf.setFont("Helvetica", 8.5)
        if is_pers:
            pdf.drawRightString(MARGIN + 280, ry + 5.5, f"{currency} {rev_item:,.0f}" if rev_item > 0 else "—")
            pdf.drawRightString(MARGIN + 410, ry + 5.5, f"{currency} {exp_item:,.0f}")
            pct_share = (exp_item / exp_val * 100) if exp_val > 0 else 0.0
            pdf.drawRightString(PAGE_W - MARGIN - 12, ry + 5.5, f"{pct_share:.1f}%")
        else:
            pdf.drawRightString(MARGIN + 280, ry + 5.5, f"{currency} {rev_item:,.0f}")
            pdf.setFillColor(_C_EMERALD if prof_item >= 0 else _C_CRIMSON)
            pdf.drawRightString(MARGIN + 410, ry + 5.5, f"{currency} {prof_item:,.0f}")
            pdf.drawRightString(PAGE_W - MARGIN - 12, ry + 5.5, f"{margin_item:.1f}%" if margin_item is not None else "N/A")

    # 5. Strategic Decision Intelligence (3 Pillars)
    intel_top_y = tbl_y - 18
    pdf.setFillColor(_C_PRIMARY)
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawString(MARGIN, intel_top_y, "Executive Decision Intelligence (3-Pillar Analysis)")

    box_y = intel_top_y - 88
    box_h = 80
    pdf.setFillColor(_C_CARD_BG)
    pdf.setStrokeColor(_C_BORDER)
    pdf.roundRect(MARGIN, box_y, USABLE_W, box_h, 6, fill=1, stroke=1)

    # Accent bar on left edge
    pdf.setFillColor(_C_COBALT)
    pdf.roundRect(MARGIN, box_y, 4, box_h, 2, fill=1, stroke=0)

    pillars = (brief or {}).get("pillars", [])
    if len(pillars) >= 3:
        p_w = (USABLE_W - 20) / 3.0
        for p_idx, p_item in enumerate(pillars[:3]):
            px = MARGIN + 12 + (p_idx * p_w)
            pdf.setFillColor(_C_COBALT)
            pdf.setFont("Helvetica-Bold", 7.5)
            pdf.drawString(px, box_y + box_h - 15, str(p_item.get("step") or f"0{p_idx+1}").upper())

            pdf.setFillColor(_C_PRIMARY)
            pdf.setFont("Helvetica-Bold", 8.5)
            p_head = str(p_item.get("headline") or "")
            if len(p_head) > 28:
                p_head = p_head[:26] + "…"
            pdf.drawString(px, box_y + box_h - 28, p_head)

            pdf.setFillColor(_C_MUTED)
            pdf.setFont("Helvetica", 7.5)
            detail = str(p_item.get("detail") or "")
            # split into 2-3 lines
            words = detail.split()
            lines = []
            curr_line = []
            for w in words:
                if len(" ".join(curr_line + [w])) <= 34:
                    curr_line.append(w)
                else:
                    lines.append(" ".join(curr_line))
                    curr_line = [w]
                    if len(lines) >= 3:
                        break
            if curr_line and len(lines) < 3:
                lines.append(" ".join(curr_line))
            for l_idx, line_str in enumerate(lines[:3]):
                pdf.drawString(px, box_y + box_h - 42 - (l_idx * 10), line_str)

    # 6. Risk Governance & Cashflow Runway Cards
    gov_top_y = box_y - 18
    pdf.setFillColor(_C_PRIMARY)
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawString(MARGIN, gov_top_y, "Risk Governance & Liquidity Assessment")

    gov_card_w = (USABLE_W - card_gap) / 2.0
    gov_card_h = 60.0
    gov_y = gov_top_y - gov_card_h - 8

    # Left Card: Random Forest Risk Breakdown
    pdf.setFillColor(_C_WHITE)
    pdf.setStrokeColor(_C_BORDER)
    pdf.roundRect(MARGIN, gov_y, gov_card_w, gov_card_h, 6, fill=1, stroke=1)
    pdf.setFillColor(_C_PRIMARY)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(MARGIN + 12, gov_y + gov_card_h - 15, "Offline Random Forest ML Risk Decomposition")
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(_C_SECONDARY)
    tot_tx = max(1, m.get("transactions", 1))
    low_pct = (ms.get("low_risk", 0) / tot_tx) * 100
    mod_pct = (ms.get("moderate_risk", 0) / tot_tx) * 100
    high_pct = (ms.get("high_risk", 0) / tot_tx) * 100
    pdf.drawString(MARGIN + 12, gov_y + gov_card_h - 30, f"Low Risk (Normal): {ms.get('low_risk', 0):,} ({low_pct:.1f}%)")
    pdf.drawString(MARGIN + 12, gov_y + gov_card_h - 43, f"Moderate Risk: {ms.get('moderate_risk', 0):,} ({mod_pct:.1f}%)")
    pdf.drawString(MARGIN + 12, gov_y + gov_card_h - 55, f"High Risk / Anomalies: {ms.get('high_risk', 0):,} ({high_pct:.1f}%)")

    # Right Card: Cashflow Runway & Posture
    rx = MARGIN + gov_card_w + card_gap
    pdf.setFillColor(_C_WHITE)
    pdf.setStrokeColor(_C_BORDER)
    pdf.roundRect(rx, gov_y, gov_card_w, gov_card_h, 6, fill=1, stroke=1)
    pdf.setFillColor(_C_PRIMARY)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(rx + 12, gov_y + gov_card_h - 15, "Cash-Flow Runway & Liquidity Buffer")

    posture_text = runway.get("status", "Healthy Surplus (Self-Sustaining)")
    _draw_pill(pdf, rx + 12, gov_y + gov_card_h - 34, 180, 14, posture_text, _C_EMERALD_LIGHT, _C_EMERALD, font_size=7)

    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(_C_SECONDARY)
    avg_burn = float(runway.get("monthly_burn") or 0.0)
    pdf.drawString(rx + 12, gov_y + 12, f"Average Monthly Outflow: {currency} {avg_burn:,.2f}")

    # 7. Page 1 Footer
    pdf.setStrokeColor(_C_BORDER)
    pdf.setLineWidth(0.8)
    pdf.line(MARGIN, 38, PAGE_W - MARGIN, 38)
    pdf.setFillColor(_C_MUTED)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(MARGIN, 25, f"Confidential · Finance Pulse Analytics Offline Edge Intelligence Engine · Workspace: {user_name}")
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawRightString(PAGE_W - MARGIN, 25, "Page 1 of 2")

    # =========================================================================
    # PAGE 2: Executive Visual Analytics & Trend Decomposition
    # =========================================================================
    if df is not None and len(df) >= 2:
        cash_png = render_monthly_cashflow_png(df, currency=currency)
        seg_png = render_segment_profit_png(df, dimension=dim, currency=currency)

        if cash_png or seg_png:
            pdf.showPage()

            # Top Decorative Stripe
            pdf.setFillColor(_C_COBALT)
            pdf.rect(0, PAGE_H - 5, PAGE_W, 5, fill=1, stroke=0)

            # Header
            y2 = PAGE_H - 36
            pdf.setFillColor(_C_PRIMARY)
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(MARGIN, y2, "Finance Pulse Analytics — Executive Visual Analytics")
            pdf.setFillColor(_C_MUTED)
            pdf.setFont("Helvetica", 8.5)
            pdf.drawString(MARGIN, y2 - 16, f"Trend Decomposition, Monthly Cashflow Velocity & {dim.title()} Ranking | 100% Offline Intelligence")
            pdf.line(MARGIN, y2 - 24, PAGE_W - MARGIN, y2 - 24)

            # Top Chart Card (Monthly Cashflow Trajectory)
            top_chart_y = y2 - 380
            top_chart_h = 350
            pdf.setFillColor(_C_WHITE)
            pdf.setStrokeColor(_C_BORDER)
            pdf.roundRect(MARGIN, top_chart_y, USABLE_W, top_chart_h, 8, fill=1, stroke=1)

            pdf.setFillColor(_C_PRIMARY)
            pdf.setFont("Helvetica-Bold", 10.5)
            pdf.drawString(MARGIN + 16, top_chart_y + top_chart_h - 22, "Monthly Cashflow Velocity & Profit Trajectory")

            if cash_png:
                img_cash = ImageReader(io.BytesIO(cash_png))
                pdf.drawImage(
                    img_cash,
                    MARGIN + 12,
                    top_chart_y + 12,
                    width=USABLE_W - 24,
                    height=top_chart_h - 42,
                    preserveAspectRatio=True,
                )

            # Bottom Chart Card (Contribution Ranking)
            bot_chart_y = top_chart_y - 360
            bot_chart_h = 340
            pdf.setFillColor(_C_WHITE)
            pdf.setStrokeColor(_C_BORDER)
            pdf.roundRect(MARGIN, bot_chart_y, USABLE_W, bot_chart_h, 8, fill=1, stroke=1)

            pdf.setFillColor(_C_PRIMARY)
            pdf.setFont("Helvetica-Bold", 10.5)
            bot_title = f"Top {dim.title()} Net Profit & Spending Contribution Ranking ({currency})"
            pdf.drawString(MARGIN + 16, bot_chart_y + bot_chart_h - 22, bot_title)

            if seg_png:
                img_seg = ImageReader(io.BytesIO(seg_png))
                pdf.drawImage(
                    img_seg,
                    MARGIN + 12,
                    bot_chart_y + 12,
                    width=USABLE_W - 24,
                    height=bot_chart_h - 42,
                    preserveAspectRatio=True,
                )

            # Page 2 Footer
            pdf.setStrokeColor(_C_BORDER)
            pdf.setLineWidth(0.8)
            pdf.line(MARGIN, 38, PAGE_W - MARGIN, 38)
            pdf.setFillColor(_C_MUTED)
            pdf.setFont("Helvetica", 7.5)
            pdf.drawString(MARGIN, 25, f"Confidential · Finance Pulse Analytics Offline Edge Intelligence Engine · Workspace: {user_name}")
            pdf.setFont("Helvetica-Bold", 7.5)
            pdf.drawRightString(PAGE_W - MARGIN, 25, "Page 2 of 2")

    pdf.save()
    stream.seek(0)
    return stream.getvalue()
