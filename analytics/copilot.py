"""100% Offline Multilingual AI Financial Copilot (English, Tamil, Hindi + SQLite Tools)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline

from .anomalies import detect as detect_anomalies
from .financial_metrics import compute_cashflow_runway, metrics, monthly, period_growth
from .forecasting import forecast
from .ml_engine import ml_summary, score_transactions_risk
from .optimization import scenario, segment_opportunities, target_margin_plan
from .privacy import mask_pii_text
from .profitability import by_dimension

# Training utterances for offline TF-IDF + RandomForestClassifier intent routing (EN + TA + HI)
_INTENT_SAMPLES: List[Tuple[str, str]] = [
    # 1. overview_kpis
    ("give me executive summary total revenue profit margin roi", "overview_kpis"),
    ("what is total revenue and operating expense net profit", "overview_kpis"),
    ("how is the business performing overall summary", "overview_kpis"),
    ("motham varuvai selavu labam enna summary", "overview_kpis"),
    ("வருவாய் செலவு லாபம் மொத்தம் எவ்வளவு", "overview_kpis"),
    ("kul kamai kharcha munafa kitna hai report", "overview_kpis"),
    ("राजस्व खर्च और शुद्ध लाभ कितना है", "overview_kpis"),

    # 2. future_prediction
    ("predict next 6 months future forecast revenue profit projection", "future_prediction"),
    ("what is the future prediction for next year", "future_prediction"),
    ("forecast expense trajectory 12 months random forest", "future_prediction"),
    ("ethirkala kanippu adutha 6 maatham revenue forecast", "future_prediction"),
    ("எதிர்கால கணிப்பு அடுத்த மாத வருவாய்", "future_prediction"),
    ("bhavishya prediction agle 6 mahine munafa forecast", "future_prediction"),
    ("भविष्य का पूर्वानुमान अगले महीने का लाभ", "future_prediction"),

    # 3. cashflow_runway
    ("what is our cashflow runway burn rate net monthly cash", "cashflow_runway"),
    ("how many months of cash buffer survival runway do we have", "cashflow_runway"),
    ("runway savings rate liquidity reserve", "cashflow_runway"),
    ("kaiyil ulla panam ethanai maatham thaangum runway", "cashflow_runway"),
    ("cash runway kitne mahine chalega liquidity", "cashflow_runway"),

    # 4. segment_ranking
    ("which product department category region made the highest profit", "segment_ranking"),
    ("top and worst performing departments branches products", "segment_ranking"),
    ("compare segments breakdown by region and product", "segment_ranking"),
    ("entha department product athiga labam rank", "segment_ranking"),
    ("कौन सा विभाग या उत्पाद सबसे अधिक लाभ में है", "segment_ranking"),
    ("kaunsa product ya department sabse zyada profit mein hai", "segment_ranking"),

    # 5. anomaly_audit
    ("show anomalies outliers suspicious spikes expenses", "anomaly_audit"),
    ("which transactions exceeded iqr isolation forest cutoff", "anomaly_audit"),
    ("athiga selavu spike outlier irukka", "anomaly_audit"),
    ("कहाँ असामान्य खर्च या आउटलायर है", "anomaly_audit"),
    ("koi unusual kharcha ya anomaly flag hua kya", "anomaly_audit"),

    # 6. ml_risk_audit
    ("show random forest risk score high risk transactions", "ml_risk_audit"),
    ("what are the risk factors in my ledger data", "ml_risk_audit"),
    ("risk tier classification high moderate low exposure", "ml_risk_audit"),
    ("aabathu risk score enna high risk", "ml_risk_audit"),
    ("जोखिम स्कोर और हाई रिस्क लेनदेन दिखाएं", "ml_risk_audit"),

    # 7. margin_optimizer
    ("how do i reach 25 percent target profit margin optimization", "margin_optimizer"),
    ("break even revenue cost cut required target margin", "margin_optimizer"),
    ("margin athigarikka enna seiya vendum optimization", "margin_optimizer"),
    ("target margin badhane ke liye kharcha kitna kam karein", "margin_optimizer"),

    # 8. what_if_simulation
    ("what if revenue grows 15 percent and expenses drop 10 percent", "what_if_simulation"),
    ("simulate +20% sales and -5% spend scenario", "what_if_simulation"),
    ("agar kamai 10% badhe aur kharcha 5% ghate", "what_if_simulation"),

    # 9. period_growth_summary
    ("month over month growth comparison latest month vs previous", "period_growth_summary"),
    ("recent month growth percentage revenue vs expense", "period_growth_summary"),
    ("indha maatham growth poana maatham compare", "period_growth_summary"),
    ("pichle mahine se is mahine growth kitni hui", "period_growth_summary"),

    # 10. date_or_year_filter
    ("show performance for year 2024 2025 2026 best month worst month", "date_or_year_filter"),
    ("which year had highest profit peak month trough month", "date_or_year_filter"),
    ("2025 varusham la ethu best month", "date_or_year_filter"),
    ("किस साल या महीने में सबसे ज्यादा मुनाफा हुआ", "date_or_year_filter"),

    # 11. vendor_or_payment_audit
    ("top vendors suppliers parties payment method upi bank transfer cheque", "vendor_or_payment_audit"),
    ("who did we pay the most vendor analysis payment mode", "vendor_or_payment_audit"),
    ("yaaruku athiga panam koduthom vendor payment mode", "vendor_or_payment_audit"),
    ("sabse zyada kis vendor ko payment gaya hai", "vendor_or_payment_audit"),

    # 12. personal_cashflow_advisor
    ("i am a salaried person earning 30k salary spending 22k saving 8k what should i do risk factor", "personal_cashflow_advisor"),
    ("salary 30000 expenses 22000 rest 8000 investment emergency plan risk", "personal_cashflow_advisor"),
    ("monthly income 50k spend 35k how to invest remaining 15k safe plan", "personal_cashflow_advisor"),
    ("en sambalam 30k selavu 22k meedhi 8k enna seiya vendum aabathu", "personal_cashflow_advisor"),
    ("என் சம்பளம் 30000 செலவு 22000 மீதி 8000 என்ன செய்ய வேண்டும் ஆபத்து", "personal_cashflow_advisor"),
    ("meri salary 30k hai kharcha 22k bachat 8k kya karna chahiye risk factor kya hai", "personal_cashflow_advisor"),
    ("मेरी सैलरी 30000 है खर्च 22000 बचत 8000 क्या करें और जोखिम क्या है", "personal_cashflow_advisor"),

    # 13. dataset_and_audit_status
    ("how many records rows dataset schema columns imported", "dataset_and_audit_status"),
    ("check data quality missing categories duplicates database status", "dataset_and_audit_status"),
    ("ethanai rows import aagiyullathu dataset status", "dataset_and_audit_status"),
    ("kitne records aur columns import hue hain database status", "dataset_and_audit_status"),
]

_TOOL_ROUTER: Optional[Pipeline] = None


def _get_router() -> Pipeline:
    global _TOOL_ROUTER
    if _TOOL_ROUTER is None:
        texts = [t for t, _ in _INTENT_SAMPLES]
        labels = [lbl for _, lbl in _INTENT_SAMPLES]
        pipe = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), analyzer="char_wb", min_df=1)),
            ("rf", RandomForestClassifier(n_estimators=140, random_state=42, n_jobs=1)),
        ])
        pipe.fit(texts, labels)
        _TOOL_ROUTER = pipe
    return _TOOL_ROUTER


def detect_language(question: str, explicit_lang: str = "auto") -> str:
    if explicit_lang in {"en", "ta", "hi"}:
        return explicit_lang
    q = question or ""
    if re.search(r"[\u0B80-\u0BFF]", q):
        return "ta"
    if re.search(r"[\u0900-\u097F]", q):
        return "hi"
    low = q.lower()
    if any(w in low for w in ("sambalam", "selavu", "varuvai", "labam", "semippu", "ethirkala", "aabathu", "enna", "ethanai", "vendum")):
        return "ta"
    if any(w in low for w in ("kamai", "kharcha", "bachat", "munafa", "bhavishya", "kitna", "kya karu", "chahiye", "meri salary", "khatra")):
        return "hi"
    return "en"


def _money(val: Optional[float], curr: str = "INR") -> str:
    if val is None:
        return "N/A"
    sign = "-" if val < 0 else ""
    return f"{sign}{curr} {abs(float(val)):,.0f}"


def _parse_money_token(num_str: str, suffix: str) -> float:
    base = float(num_str.replace(",", ""))
    suf = (suffix or "").lower()
    if suf == "k":
        return base * 1_000.0
    if suf in {"l", "lac", "lakh", "lakhs"}:
        return base * 100_000.0
    if suf in {"m", "mn"}:
        return base * 1_000_000.0
    if suf in {"cr", "crore"}:
        return base * 10_000_000.0
    return base


def _extract_personal_budget(question: str) -> Optional[Tuple[float, float, float]]:
    q = (question or "").strip()
    low = q.lower()
    has_personal_cue = any(w in low for w in (
        "salary", "salaried", "paycheck", "take home", "earn", "getting",
        "sambalam", "सैलरी", "वेतन", "संबलम", "சம்பளம்", "spend", "selavu", "kharcha", "बचत", "சேமிப்பு",
    ))
    pat = re.compile(
        r"(?:inr|rs\.?|₹|\$)?\s*([0-9]{1,3}(?:,[0-9]{2,3})+|[0-9]+(?:\.[0-9]+)?)\s*(k|l|lac|lakh|lakhs|m|mn|cr|crore)?\b",
        re.IGNORECASE,
    )
    amounts: List[Tuple[float, str]] = []
    for m in pat.finditer(q):
        val = _parse_money_token(m.group(1), m.group(2) or "")
        # Ignore small numbers like percentages or years unless scaled (k/l/m)
        if not m.group(2) and (1900 <= val <= 2099 or val < 500):
            continue
        ctx = low[max(0, m.start() - 24):min(len(low), m.end() + 24)]
        amounts.append((val, ctx))

    if len(amounts) < 2 or not has_personal_cue:
        return None

    salary = None
    spend = None
    save = None
    for val, ctx in amounts:
        if salary is None and any(k in ctx for k in ("salary", "earn", "income", "get", "sambalam", "वेतन", "सैलरी", "சம்பளம்")):
            salary = val
        elif spend is None and any(k in ctx for k in ("spend", "spent", "expense", "kharcha", "selavu", "खर्च", "செலவு")):
            spend = val
        elif save is None and any(k in ctx for k in ("rest", "save", "saving", "remaining", "left", "bachat", "semippu", "meedhi", "बचत", "மீதி")):
            save = val

    vals_sorted = sorted([a[0] for a in amounts], reverse=True)
    if salary is None:
        salary = vals_sorted[0]
    if spend is None:
        others = [v for v in vals_sorted if abs(v - salary) > 1e-6]
        if others:
            spend = others[0]
    if salary is None or spend is None or salary <= 0:
        return None
    if save is None:
        save = max(0.0, salary - spend)
    return salary, spend, save


def _pick_tool(question: str) -> str:
    low = (question or "").lower()
    if _extract_personal_budget(question) is not None:
        return "personal_cashflow_advisor"
    if any(w in low for w in ("what if", "simulate", "what-if", "agar ")) and re.search(r"[+-]?\d+\s*%", low):
        return "what_if_simulation"
    if any(w in low for w in ("predict", "forecast", "projection", "future", "ethirkala", "kanippu", "bhavishya", "कணிப்பு", "கணிப்பு", "भविष्य")):
        return "future_prediction"
    if any(w in low for w in ("runway", "burn rate", "months buffer", "survival")):
        return "cashflow_runway"
    if any(w in low for w in ("anomal", "outlier", "iqr", "isolation forest", "spike")):
        return "anomaly_audit"
    if any(w in low for w in ("risk tier", "high risk", "risk score", "random forest risk")):
        return "ml_risk_audit"
    if any(w in low for w in ("target margin", "break-even", "breakeven", "optimiz")):
        return "margin_optimizer"
    if any(w in low for w in ("vendor", "supplier", "party", "payment mode", "payment method", "upi", "cheque")):
        return "vendor_or_payment_audit"
    if any(w in low for w in ("product", "department", "region", "category", "segment", "branch", "course")):
        return "segment_ranking"
    if re.search(r"\b20\d{2}\b", low) or any(w in low for w in ("best month", "worst month", "peak month")):
        return "date_or_year_filter"
    if any(w in low for w in ("how many rows", "how many records", "dataset status", "schema", "quality")):
        return "dataset_and_audit_status"

    router = _get_router()
    return str(router.predict([question or "overview summary"])[0])


def _localized_prefix(lang: str) -> Dict[str, str]:
    if lang == "ta":
        return {
            "advice_tag": "நடைமுறைத் திட்டம்",
            "salary_title": "தனிநபர் சம்பளம் & ஆபத்து பகுப்பாய்வு",
            "forecast_title": "Random Forest எதிர்கால கணிப்பு",
            "overview_title": "நிதி சுருக்கம் (SQLite)",
        }
    if lang == "hi":
        return {
            "advice_tag": "कार्य योजना",
            "salary_title": "व्यक्तिगत वेतन और जोखिम सलाहकार",
            "forecast_title": "Random Forest भविष्य पूर्वानुमान",
            "overview_title": "वित्तीय सारांश (SQLite)",
        }
    return {
        "advice_tag": "Action Plan",
        "salary_title": "Personal Cash-Flow & Risk Plan",
        "forecast_title": "Random Forest Future Projection",
        "overview_title": "Executive Ledger Summary",
    }


def _answer_personal_advisor(salary: float, spend: float, save: float, curr: str, lang: str) -> Dict[str, Any]:
    net = salary - spend
    savings_rate = round((net / salary) * 100.0, 1) if salary > 0 else 0.0
    spend_ratio = round((spend / salary) * 100.0, 1) if salary > 0 else 0.0
    emergency_3m = spend * 3.0
    emergency_6m = spend * 6.0
    months_to_6m = round(emergency_6m / max(1.0, save), 1) if save > 0 else None

    # Score through offline Random Forest risk classifier for consistent risk quantification
    sample_row = pd.DataFrame([{
        "txn_date": pd.Timestamp.utcnow().strftime("%Y-%m-%d"),
        "revenue": salary,
        "expense": spend,
        "cost": spend * 0.4,
        "tax_amount": 0.0,
        "investment": save,
    }])
    scored = score_transactions_risk(sample_row)
    rf_tier = str(scored.iloc[0]["risk_tier"])
    rf_score = float(scored.iloc[0]["risk_score"])

    if net <= 0:
        risk_label = "Critical Risk (Zero Surplus)"
    elif savings_rate < 15.0:
        risk_label = f"Elevated Risk ({savings_rate:.1f}% savings)"
    elif savings_rate < 25.0:
        risk_label = f"Moderate Risk ({savings_rate:.1f}% savings)"
    else:
        risk_label = f"{rf_tier} ({savings_rate:.1f}% savings)"

    alloc_emerg = round(save * 0.50)
    alloc_invest = round(save * 0.35)
    alloc_shield = max(0.0, round(save - alloc_emerg - alloc_invest))
    year1_corpus = round(save * 12.0)
    # 3-year projection: 50% liquid @ 6.5% + 50% SIP @ 11% annual compounded monthly
    r_liq, r_sip = 0.065 / 12.0, 0.11 / 12.0
    half_s = save * 0.5
    fv_3y = round(
        half_s * (((1 + r_liq) ** 36 - 1) / r_liq)
        + half_s * (((1 + r_sip) ** 36 - 1) / r_sip)
    )

    if lang == "ta":
        answer = (
            f"மாதச் சம்பளம் {_money(salary, curr)} இல் {_money(spend, curr)} ({spend_ratio:.1f}%) செலவு செய்து "
            f"{_money(save, curr)} ({savings_rate:.1f}%) சேமிப்பது நல்ல தொடக்கம் (RF Risk: {risk_label}). "
            f"ஆனால் 6 மாத அவசர நிதி ({_money(emergency_6m, curr)}) சேரும் வரை வருமானத் தடை மற்றும் மருத்துவச் செலவு ஆபத்து அதிகம்."
        )
        actions = [
            f"1. அவசர நிதி (50% = {_money(alloc_emerg, curr)}/மாதம்): {_money(emergency_3m, curr)} (3 மாதச் செலவு) சேரும் வரை Liquid Fund / Sweep FD-ல் சேமிக்கவும்.",
            f"2. வளர்ச்சி முதலீடு (35% = {_money(alloc_invest, curr)}/மாதம்): முதல் 3 மாத Buffer உருவான பின் Index / SIP தொடங்கவும் (3 ஆண்டில் ~{_money(fv_3y, curr)}).",
            f"3. பாதுகாப்பு & செலவு வரம்பு (15% = {_money(alloc_shield, curr)}/மாதம்): Health / Term காப்பீடு எடுத்து செலவை {curr} {int(spend * 0.9):,} கீழ் வைக்கவும்.",
        ]
    elif lang == "hi":
        answer = (
            f"{_money(salary, curr)} मासिक सैलरी में {_money(spend, curr)} ({spend_ratio:.1f}%) खर्च के बाद "
            f"{_money(save, curr)} ({savings_rate:.1f}% बचत दर) एक स्वस्थ आधार है (RF Risk: {risk_label})। "
            f"मुख्य जोखिम: बिना {_money(emergency_6m, curr)} इमरजेंसी फंड (6 माह खर्च) के नौकरी ब्रेक या मेडिकल खर्च सीधे बजट बिगाड़ सकता है।"
        )
        actions = [
            f"1. इमरजेंसी बफर (50% = {_money(alloc_emerg, curr)}/माह): पहले 3-6 माह के खर्च ({_money(emergency_3m, curr)}–{_money(emergency_6m, curr)}) के लिए Liquid Fund / RD में डालें।",
            f"2. लॉन्ग-टर्म SIP (35% = {_money(alloc_invest, curr)}/माह): 1 माह बफर के बाद डायवर्सिफाइड Index SIP शुरू करें (3 साल में ~{_money(fv_3y, curr)} संभावित)।",
            f"3. रिस्क शील्ड (15% = {_money(alloc_shield, curr)}/माह): टर्म व हेल्थ बीमा रखें और +10% खर्च वृद्धि (जो बचत को {_money(max(0.0, net - spend*0.10), curr)} तक घटा देगी) से बचें।",
        ]
    else:
        answer = (
            f"Saving {_money(save, curr)} on {_money(salary, curr)} salary ({savings_rate:.1f}% savings rate, "
            f"{spend_ratio:.1f}% expense ratio) clears the 20% baseline (RF score: {rf_score:.0f}/100 · {risk_label}). "
            f"Primary risk factor: zero liquid cushion covers <1 month if income pauses, and +10% expense creep ({_money(spend * 0.1, curr)}/mo) cuts monthly savings by {(spend * 0.1 / max(1.0, save)) * 100:.0f}%."
        )
        actions = [
            f"1. Build Emergency Runway (50% = {_money(alloc_emerg, curr)}/mo): Park in Liquid Fund / Sweep FD until 3–6 months of spend ({_money(emergency_3m, curr)}–{_money(emergency_6m, curr)}) is covered (~{months_to_6m or 'N/A'} mo full pace).",
            f"2. Compound Growth SIP (35% = {_money(alloc_invest, curr)}/mo): Automate low-cost index/recurring investments once 1 month buffer sits aside (~{_money(fv_3y, curr)} projected 3-yr total).",
            f"3. Insurance & Spend Guardrail (15% = {_money(alloc_shield, curr)}/mo): Fund health/term protection first so one medical bill never liquidates your {_money(year1_corpus, curr)}/yr savings.",
        ]

    return {
        "ok": True,
        "tool": "personal_cashflow_advisor",
        "language": lang,
        "model": "Offline Random Forest Risk & Budget Engine",
        "title": _localized_prefix(lang)["salary_title"],
        "answer": answer,
        "metrics": [
            {"label": "Monthly Surplus", "value": f"{_money(save, curr)} ({savings_rate:.1f}%)"},
            {"label": "RF Risk Factor", "value": risk_label},
            {"label": "6-Month Target Buffer", "value": _money(emergency_6m, curr)},
            {"label": "3-Year Projected Wealth", "value": _money(fv_3y, curr)},
        ],
        "actions": actions,
        "suggestions": [
            "Predict next 6 months for my workspace ledger",
            "What if expenses drop by 10%?",
            "Show high-risk transactions",
        ],
    }


def answer_question(
    question: str,
    df: Optional[pd.DataFrame],
    currency: str = "INR",
    margin_threshold: float = 15.0,
    anomaly_multiplier: float = 1.5,
    language: str = "auto",
    filename_meta: Optional[str] = None,
) -> Dict[str, Any]:
    """Answer user questions grounded strictly in active SQLite data + offline Random Forest ML."""
    clean_q, _ = mask_pii_text((question or "").strip(), enabled=True)
    lang = detect_language(str(clean_q), language)
    tool = _pick_tool(str(clean_q))

    # Personal advisor works even when enterprise ledger is empty!
    if tool == "personal_cashflow_advisor":
        parsed = _extract_personal_budget(str(clean_q))
        if parsed:
            return _answer_personal_advisor(parsed[0], parsed[1], parsed[2], currency, lang)

    if df is None or df.empty:
        return {
            "ok": True,
            "tool": "empty_workspace",
            "language": lang,
            "model": "Offline SQLite Copilot",
            "title": "Workspace Ready",
            "answer": (
                "No financial dataset is loaded in this workspace yet. Upload a CSV/XLSX/JSON ledger or load the "
                "10,000-record enterprise sample — or ask a personal cashflow question like: "
                "'I earn 30k salary and spend 22k, what should I do with 8k and what is the risk?'"
            ),
            "metrics": [],
            "actions": [
                "Upload your ledger CSV or scan a receipt photo in Data Import",
                "Try asking: 30k salary, 22k spend, 8k savings — what is my risk plan?",
            ],
            "suggestions": [
                "I earn 30k salary, spend 22k, save 8k — what should I do and what is the risk?",
            ],
        }

    m = metrics(df)
    rev = float(m["revenue"] or 0.0)
    exp = float(m["expenses"] or 0.0)
    prof = float(m["profit"] or 0.0)
    margin = m["margin"]

    if tool == "future_prediction":
        low = str(clean_q).lower()
        target = "expense" if any(w in low for w in ("expense", "spend", "cost", "kharcha", "selavu")) else ("profit" if any(w in low for w in ("profit", "surplus", "net", "labam", "munafa")) else "revenue")
        h_match = re.search(r"\b(\d{1,2})\s*(?:month|months|mo|माह|மாத)\b", low)
        horizon = max(3, min(24, int(h_match.group(1)))) if h_match else 6
        fc = forecast(df, target=target, horizon=horizon)
        if fc.get("error"):
            return {
                "ok": True,
                "tool": tool,
                "language": lang,
                "model": "Offline Forecasting Engine",
                "title": "Forecast Unavailable",
                "answer": fc["error"],
                "metrics": [{"label": "Current Profit", "value": _money(prof, currency)}],
                "actions": [],
                "suggestions": ["Give me overview summary", "Show top segments"],
            }
        fc_rows = fc["forecast"]
        cum_fc = sum(r["value"] for r in fc_rows)
        end_row = fc_rows[-1]
        acc = fc["accuracy"]
        top_drv = fc.get("feature_importances", [{}])[0]
        if lang == "ta":
            ans = (
                f"{fc['model']} அடிப்படையில் அடுத்த {horizon} மாத {target} கணிப்பு: "
                f"{end_row['period']} இல் {_money(end_row['value'], currency)} (மொத்தம் {_money(cum_fc, currency)}). "
                f"வரலாற்றுப் பிழை MAE {_money(acc['mae'], currency)}."
            )
        elif lang == "hi":
            ans = (
                f"{fc['model']} के अनुसार अगले {horizon} माह का {target} अनुमान {end_row['period']} में "
                f"{_money(end_row['value'], currency)} (कुल {_money(cum_fc, currency)}) है। ऐतिहासिक MAE: {_money(acc['mae'], currency)}।"
            )
        else:
            ans = (
                f"{fc['model']} projects next {horizon} months of {target} reaching {_money(end_row['value'], currency)} "
                f"by {end_row['period']} (range {_money(end_row.get('low'), currency)} to {_money(end_row.get('high'), currency)}). "
                f"Cumulative {horizon}-month total: {_money(cum_fc, currency)}; primary driver: {top_drv.get('feature', 'Trend Index')} ({top_drv.get('importance', 0)}%)."
            )
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": fc["model"],
            "title": _localized_prefix(lang)["forecast_title"],
            "answer": ans,
            "metrics": [
                {"label": f"{horizon}M Cumulative {target.title()}", "value": _money(cum_fc, currency)},
                {"label": f"End ({end_row['period']})", "value": _money(end_row["value"], currency)},
                {"label": "Historical MAE", "value": _money(acc["mae"], currency)},
                {"label": "MAPE / R²", "value": f"{acc['mape'] or 'N/A'}% · {acc.get('r2', 'N/A')}"},
            ],
            "actions": [
                "Inspect Confidence Band & Drivers inside Forecasting",
                "Run Target-Margin Optimization to lift projected trajectory",
            ],
            "suggestions": ["What is our cashflow runway?", "Which department leads profit?", "Any expense anomalies?"],
        }

    if tool == "cashflow_runway":
        rw = compute_cashflow_runway(df)
        runway_val = f"{rw['runway_months']} mo" if rw["runway_months"] is not None else "Self-Sustaining"
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": "Offline Runway Analyzer",
            "title": "Cash-Flow Runway & Burn Check",
            "answer": (
                f"Status is {rw['status']} across {rw['months']} monthly periods. Recent monthly revenue averages "
                f"{_money(rw['recent_monthly_revenue'], currency)} vs. {_money(rw['recent_monthly_expense'], currency)} "
                f"expense (net {_money(rw['recent_monthly_net'], currency)}/mo)."
            ),
            "metrics": [
                {"label": "Runway", "value": runway_val},
                {"label": "Recent Monthly Net", "value": _money(rw["recent_monthly_net"], currency)},
                {"label": "Savings Rate", "value": f"{rw['savings_rate_pct']}%" if rw["savings_rate_pct"] is not None else "N/A"},
                {"label": "Cumulative Buffer", "value": _money(rw["cash_reserve"], currency)},
            ],
            "actions": ["Trim low-margin expenses if savings rate is below 15%"],
            "suggestions": ["Predict next 6 months profit", "Show Random Forest risk tiers"],
        }

    if tool == "segment_ranking":
        low = str(clean_q).lower()
        dim = "department" if any(k in low for k in ("dept", "department", "course", "unit", "विभाग")) else (
            "region" if any(k in low for k in ("region", "location", "branch", "city")) else (
                "category" if "categor" in low else "product"
            )
        )
        rows = by_dimension(df, dim)
        if not rows:
            return {"ok": True, "tool": tool, "language": lang, "model": "SQLite Aggregator", "title": "Segments", "answer": "No segment data found.", "metrics": [], "actions": [], "suggestions": []}
        top_r = rows[0]
        low_r = rows[-1]
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": "Offline SQLite Dimensional Ranker",
            "title": f"Top & Bottom {dim.title()}s",
            "answer": (
                f"Across {len(rows)} {dim}(s), '{top_r[dim]}' led with {_money(top_r['profit'], currency)} profit "
                f"({top_r['margin'] if top_r['margin'] is not None else 'N/A'}% margin). "
                f"Lowest net contributor was '{low_r[dim]}' at {_money(low_r['profit'], currency)}."
            ),
            "metrics": [
                {"label": f"Top {dim.title()}", "value": str(top_r[dim])[:26]},
                {"label": "Leader Profit", "value": _money(top_r["profit"], currency)},
                {"label": f"Lowest {dim.title()}", "value": str(low_r[dim])[:26]},
                {"label": "Laggard Profit", "value": _money(low_r["profit"], currency)},
            ],
            "actions": [f"Review cost allocations or pricing on '{low_r[dim]}'"],
            "suggestions": ["Compare Regions", "Show anomaly audit", "Target 25% profit margin plan"],
        }

    if tool == "anomaly_audit":
        flags = detect_anomalies(df, multiplier=anomaly_multiplier)
        if not flags:
            return {
                "ok": True,
                "tool": tool,
                "language": lang,
                "model": "IQR + Isolation Forest Detector",
                "title": "Anomaly Audit Clean",
                "answer": f"Zero outliers flagged across {len(df):,} rows at {anomaly_multiplier}× IQR sensitivity.",
                "metrics": [{"label": "Screened Rows", "value": f"{len(df):,}"}],
                "actions": [],
                "suggestions": ["Show Random Forest risk breakdown"],
            }
        top_f = flags[0]
        exp_cnt = sum(1 for f in flags if f["type"] == "Expense")
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": "Hybrid IQR + Isolation Forest",
            "title": "Outlier & Anomaly Audit",
            "answer": (
                f"Flagged {len(flags):,} outlier entries ({exp_cnt} expense, {len(flags) - exp_cnt} revenue). "
                f"Largest spike: {top_f['date']} in '{top_f['entity']}' ({top_f['type']} of {_money(top_f['value'], currency)} vs cutoff {_money(top_f['threshold'], currency)})."
            ),
            "metrics": [
                {"label": "Total Flagged", "value": f"{len(flags):,}"},
                {"label": "Expense Spikes", "value": f"{exp_cnt:,}"},
                {"label": "Peak Outlier", "value": _money(top_f["value"], currency)},
                {"label": "Method", "value": str(top_f.get("method", "IQR"))},
            ],
            "actions": [f"Verify voucher/supporting bill for {top_f['date']} ({top_f['entity']})"],
            "suggestions": ["Run Random Forest risk breakdown", "Predict next 6 months expenses"],
        }

    if tool == "ml_risk_audit":
        ms = ml_summary(df)
        top_drv = ms["feature_importances"][0]["feature"] if ms["feature_importances"] else "Expense / Revenue Ratio"
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": "Random Forest Classifier (Offline)",
            "title": "Random Forest Transaction Risk Audit",
            "answer": (
                f"Evaluated {ms['total']:,} ledger entries locally: {ms['high_risk']:,} High Risk ({ms['high_risk_pct']}%), "
                f"{ms['moderate_risk']:,} Moderate Risk, and {ms['low_risk']:,} Low Risk. "
                f"Top Random Forest risk driver: {top_drv}."
            ),
            "metrics": [
                {"label": "High Risk Entries", "value": f"{ms['high_risk']:,} ({ms['high_risk_pct']}%)"},
                {"label": "High-Risk Exposure", "value": _money(ms["high_risk_exposure"], currency)},
                {"label": "Moderate / Low", "value": f"{ms['moderate_risk']:,} / {ms['low_risk']:,}"},
                {"label": "Mean Risk Score", "value": f"{ms['avg_risk_score']} / 100"},
            ],
            "actions": ["Audit High Risk disbursements and inspect Anomaly Surveillance tab"],
            "suggestions": ["Show top anomalies", "Predict next 6 months profit"],
        }

    if tool == "margin_optimizer":
        t_match = re.search(r"(\d+(?:\.\d+)?)\s*%", str(clean_q))
        target_m = float(t_match.group(1)) if t_match else max(margin_threshold, 25.0)
        plan = target_margin_plan(m, target_m)
        opps = segment_opportunities(df, margin_threshold)
        if not plan:
            return {"ok": True, "tool": tool, "language": lang, "model": "Optimization Solver", "title": "Margin Plan", "answer": "Positive revenue is required to compute a target margin plan.", "metrics": [], "actions": [], "suggestions": []}
        top_opp = opps[0] if opps else None
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": "Deterministic Target-Margin Solver",
            "title": f"Target {plan['target_margin']:.1f}% Margin Plan",
            "answer": (
                f"Current net margin is {plan['current_margin']:.2f}%. To reach {plan['target_margin']:.1f}%, either cut expenses by "
                f"{abs(plan['expense_cut_pct']):.1f}% ({_money(plan['expense_cut_amount'], currency)}) OR expand revenue by "
                f"+{plan['revenue_lift_pct']:.1f}% ({_money(plan['revenue_lift_amount'], currency)})."
            ),
            "metrics": [
                {"label": "Target Margin", "value": f"{plan['target_margin']:.1f}%"},
                {"label": "Required Cost Cut", "value": f"{plan['expense_cut_pct']:.1f}%"},
                {"label": "Or Revenue Lift", "value": f"+{plan['revenue_lift_pct']:.1f}%"},
                {"label": "Break-Even Revenue", "value": _money(plan["breakeven_revenue"], currency)},
            ],
            "actions": ([f"Top segment lever: {top_opp['dimension']} '{top_opp['segment']}' ({top_opp['opportunity']}, +{_money(top_opp['impact'], currency)})"] if top_opp else []),
            "suggestions": ["What if revenue +10% and expense -5%?", "Predict next 6 months profit"],
        }

    if tool == "what_if_simulation":
        q_str = str(clean_q)
        matches = list(re.finditer(r"([+-]?\d+(?:\.\d+)?)\s*%", q_str))
        signed_pcts: List[float] = []
        for m_pct in matches:
            val = float(m_pct.group(1))
            prefix_ctx = q_str[max(0, m_pct.start() - 22):m_pct.start()].lower()
            if val > 0 and not m_pct.group(1).startswith("+") and any(k in prefix_ctx for k in ("drop", "cut", "reduce", "decrease", "down", "lower", "trim", "less", "ghat", "kurai")):
                val = -val
            signed_pcts.append(val)
        rev_chg = signed_pcts[0] if len(signed_pcts) >= 1 else 10.0
        exp_chg = signed_pcts[1] if len(signed_pcts) >= 2 else -5.0
        sim = scenario(m, revenue_change=rev_chg, expense_change=exp_chg)
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": "Scenario Stress Engine",
            "title": f"What-If ({rev_chg:+.0f}% Rev, {exp_chg:+.0f}% Exp)",
            "answer": (
                f"Simulating {rev_chg:+.1f}% revenue and {exp_chg:+.1f}% expenses shifts projected profit from "
                f"{_money(prof, currency)} to {_money(sim['profit'], currency)} (delta {_money(sim['profit_change'], currency)}, margin {sim['margin']}%)."
            ),
            "metrics": [
                {"label": "Projected Revenue", "value": _money(sim["revenue"], currency)},
                {"label": "Projected Expense", "value": _money(sim["expenses"], currency)},
                {"label": "Projected Profit", "value": _money(sim["profit"], currency)},
                {"label": "Profit Impact", "value": _money(sim["profit_change"], currency)},
            ],
            "actions": [],
            "suggestions": ["What is break-even for 25% margin?", "Predict next 6 months revenue"],
        }

    if tool == "period_growth_summary":
        mon = monthly(df)
        if len(mon) < 2:
            return {"ok": True, "tool": tool, "language": lang, "model": "Monthly Aggregator", "title": "Period Growth", "answer": "At least 2 monthly periods are needed for MoM comparison.", "metrics": [], "actions": [], "suggestions": []}
        rg = period_growth(mon["revenue"])
        eg = period_growth(mon["expense"])
        last_p = mon["period"].iloc[-1].strftime("%Y-%m")
        prev_p = mon["period"].iloc[-2].strftime("%Y-%m")
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": "SQLite Monthly Growth Analyzer",
            "title": f"MoM Growth ({prev_p} → {last_p})",
            "answer": (
                f"In {last_p}, revenue shifted {rg if rg is not None else 'N/A'}% and expenses shifted "
                f"{eg if eg is not None else 'N/A'}% vs. {prev_p}. Latest monthly profit closed at {_money(float(mon['profit'].iloc[-1]), currency)}."
            ),
            "metrics": [
                {"label": f"{last_p} Revenue", "value": _money(float(mon["revenue"].iloc[-1]), currency)},
                {"label": f"{last_p} Expense", "value": _money(float(mon["expense"].iloc[-1]), currency)},
                {"label": "Revenue MoM", "value": f"{rg:+.1f}%" if rg is not None else "N/A"},
                {"label": "Expense MoM", "value": f"{eg:+.1f}%" if eg is not None else "N/A"},
            ],
            "actions": [],
            "suggestions": ["Predict next 6 months", "Which year performed best?"],
        }

    if tool == "date_or_year_filter":
        yr_m = re.search(r"\b(20\d{2})\b", str(clean_q))
        work = df.copy()
        work["_yr"] = pd.to_datetime(work["txn_date"], errors="coerce").dt.year
        if yr_m:
            yr = int(yr_m.group(1))
            sub = work[work["_yr"] == yr]
            if sub.empty:
                return {"ok": True, "tool": tool, "language": lang, "model": "SQLite Year Filter", "title": f"Year {yr}", "answer": f"No ledger entries matched calendar year {yr}.", "metrics": [], "actions": [], "suggestions": []}
            sm = metrics(sub)
            return {
                "ok": True,
                "tool": tool,
                "language": lang,
                "model": "SQLite Year Filter",
                "title": f"Fiscal Year {yr} Breakdown",
                "answer": f"In {yr} ({sm['transactions']:,} transactions), revenue totaled {_money(sm['revenue'], currency)} vs. {_money(sm['expenses'], currency)} expenses, yielding {_money(sm['profit'], currency)} net profit ({sm['margin']}% margin).",
                "metrics": [
                    {"label": f"{yr} Revenue", "value": _money(sm["revenue"], currency)},
                    {"label": f"{yr} Expense", "value": _money(sm["expenses"], currency)},
                    {"label": f"{yr} Net Profit", "value": _money(sm["profit"], currency)},
                    {"label": "Transactions", "value": f"{sm['transactions']:,}"},
                ],
                "actions": [],
                "suggestions": ["Show overview summary", "Top departments"],
            }
        mon = monthly(work)
        best_r = mon.loc[mon["profit"].idxmax()]
        worst_r = mon.loc[mon["profit"].idxmin()]
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": "SQLite Period Extreme Finder",
            "title": "Peak vs. Softest Periods",
            "answer": (
                f"Peak monthly net performance occurred in {best_r['period'].strftime('%Y-%m')} ({_money(float(best_r['profit']), currency)}) "
                f"and softest net occurred in {worst_r['period'].strftime('%Y-%m')} ({_money(float(worst_r['profit']), currency)})."
            ),
            "metrics": [
                {"label": "Peak Month", "value": best_r["period"].strftime("%Y-%m")},
                {"label": "Peak Profit", "value": _money(float(best_r["profit"]), currency)},
                {"label": "Softest Month", "value": worst_r["period"].strftime("%Y-%m")},
                {"label": "Softest Profit", "value": _money(float(worst_r["profit"]), currency)},
            ],
            "actions": [],
            "suggestions": ["Predict next 6 months profit"],
        }

    if tool == "vendor_or_payment_audit":
        v_col = "vendor_name" if "vendor_name" in df.columns and df["vendor_name"].notna().any() else "category"
        p_col = "payment_method" if "payment_method" in df.columns and df["payment_method"].notna().any() else None
        top_exp_v = (
            df[df["expense"] > 0]
            .assign(_v=df[v_col].fillna("Unspecified").astype(str))
            .groupby("_v")["expense"]
            .sum()
            .sort_values(ascending=False)
        )
        lead_v = str(top_exp_v.index[0]) if not top_exp_v.empty else "N/A"
        lead_v_amt = float(top_exp_v.iloc[0]) if not top_exp_v.empty else 0.0
        top_pm = "N/A"
        if p_col:
            pm_counts = df[p_col].dropna().astype(str).value_counts()
            if not pm_counts.empty:
                top_pm = f"{pm_counts.index[0]} ({pm_counts.iloc[0]:,})"
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": "SQLite Counterparty & Payment Audit",
            "title": "Vendor & Payment Channel Audit",
            "answer": f"Highest cumulative expenditure payee is '{lead_v}' at {_money(lead_v_amt, currency)}. Primary settlement channel: {top_pm}.",
            "metrics": [
                {"label": "Top Payee / Head", "value": lead_v[:28]},
                {"label": "Disbursed", "value": _money(lead_v_amt, currency)},
                {"label": "Primary Mode", "value": top_pm},
            ],
            "actions": [],
            "suggestions": ["Show top anomalies", "Check Random Forest risk exposure"],
        }

    if tool == "dataset_and_audit_status":
        dmin = pd.to_datetime(df["txn_date"], errors="coerce").min()
        dmax = pd.to_datetime(df["txn_date"], errors="coerce").max()
        span = f"{dmin.strftime('%Y-%m-%d')} to {dmax.strftime('%Y-%m-%d')}" if pd.notna(dmin) and pd.notna(dmax) else "N/A"
        missing_cats = int(df["category"].isna().sum()) if "category" in df.columns else 0
        return {
            "ok": True,
            "tool": tool,
            "language": lang,
            "model": "SQLite Storage Diagnostics",
            "title": "Workspace Dataset Health",
            "answer": (
                f"Active SQLite ledger holds {len(df):,} validated transactions spanning {span}"
                + (f" ({filename_meta})" if filename_meta else "")
                + f". Unlabeled categories: {missing_cats:,} (auto-classified by Random Forest on import)."
            ),
            "metrics": [
                {"label": "Transactions", "value": f"{len(df):,}"},
                {"label": "Date Span", "value": span},
                {"label": "Columns", "value": str(len(df.columns))},
                {"label": "Missing Categories", "value": f"{missing_cats:,}"},
            ],
            "actions": [],
            "suggestions": ["Give me overview summary", "Predict next 6 months revenue"],
        }

    # Default: overview_kpis (EN / TA / HI)
    if lang == "ta":
        ans = (
            f"செயலில் உள்ள {len(df):,} பதிவுகளில் மொத்த வருவாய் {_money(rev, currency)}, "
            f"செலவு {_money(exp, currency)}, நிகர லாபம் {_money(prof, currency)} ({margin}% லாப விகிதம்)."
        )
    elif lang == "hi":
        ans = (
            f"कुल {len(df):,} लेनदेन में राजस्व {_money(rev, currency)}, खर्च {_money(exp, currency)} और "
            f"शुद्ध लाभ {_money(prof, currency)} ({margin}% मार्जिन) दर्ज है।"
        )
    else:
        ans = (
            f"Across {len(df):,} ledger records, revenue reached {_money(rev, currency)} vs. {_money(exp, currency)} expenses, "
            f"delivering {_money(prof, currency)} net profit ({margin if margin is not None else 'N/A'}% margin)."
        )

    return {
        "ok": True,
        "tool": "overview_kpis",
        "language": lang,
        "model": "Offline SQLite Intelligence",
        "title": _localized_prefix(lang)["overview_title"],
        "answer": ans,
        "metrics": [
            {"label": "Total Revenue", "value": _money(rev, currency)},
            {"label": "Operating Expense", "value": _money(exp, currency)},
            {"label": "Net Profit", "value": _money(prof, currency)},
            {"label": "Profit Margin", "value": f"{margin}%" if margin is not None else "N/A"},
        ],
        "actions": [],
        "suggestions": [
            "Predict next 6 months profit",
            "What is our cashflow runway?",
            "Show top anomalies & high-risk entries",
        ],
    }
