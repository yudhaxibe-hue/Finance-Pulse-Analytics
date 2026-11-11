"""Tests for Offline AI Financial Copilot across all 13 tools, EN/Tamil/Hindi, Personal Advisor, and PII safety."""
from __future__ import annotations

import pandas as pd
import pytest

from analytics.copilot import answer_question, detect_language


def _copilot_ledger() -> pd.DataFrame:
    dates = pd.date_range("2024-01-10", periods=16, freq="MS")
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "txn_date": d.strftime("%Y-%m-%d"),
            "transaction_id": f"TX-{i + 1:03d}",
            "transaction_type": "Sale",
            "category": "Software" if i % 2 == 0 else "Services",
            "product": "Core Suite" if i % 2 == 0 else "Support Plan",
            "department": "Product" if i % 2 == 0 else "Customer Success",
            "region": "North" if i % 3 == 0 else "South",
            "vendor_name": "Apex Cloud Ltd" if i % 2 == 0 else "Meridian Advisors",
            "payment_method": "UPI" if i % 2 == 0 else "NEFT",
            "revenue": 120000.0 + i * 3500.0,
            "expense": 55000.0 + i * 1200.0 + (260000.0 if i == 15 else 0.0),
            "cost": 22000.0,
            "investment": 5000.0 if i % 4 == 0 else 0.0,
            "risk_tier": "High Risk" if i == 15 else ("Moderate Risk" if i % 5 == 0 else "Low Risk"),
            "risk_score": 88.5 if i == 15 else 24.0,
        })
    return pd.DataFrame(rows)


class TestCopilotLanguagesAndRouting:
    @pytest.mark.parametrize(
        "query,explicit,expected",
        [
            ("What is total revenue?", "auto", "en"),
            ("வருவாய் மற்றும் லாபம் எவ்வளவு", "auto", "ta"),
            ("en sambalam 30k selavu 22k enna seiya vendum", "auto", "ta"),
            ("मेरी सैलरी 30000 है खर्च 22000 क्या करें", "auto", "hi"),
            ("meri salary 30k hai kharcha 22k bachat 8k kya karu", "auto", "hi"),
            ("Predict next 6 months", "ta", "ta"),
            ("Predict next 6 months", "hi", "hi"),
        ],
    )
    def test_language_detection(self, query, explicit, expected):
        assert detect_language(query, explicit) == expected

    def test_empty_workspace_returns_onboarding_guidance(self):
        res = answer_question("Show overview summary", pd.DataFrame(), currency="INR")
        assert res["ok"] is True
        assert res["tool"] == "empty_workspace"
        assert "No financial dataset" in res["answer"]

    def test_personal_cashflow_advisor_works_without_ledger_en_ta_hi(self):
        for lang_code, prompt in [
            ("en", "I am a salaried person earning 30k salary, spending 22k and remaining 8k, what should I do and what is the risk?"),
            ("ta", "என் சம்பளம் 30000 செலவு 22000 மீதி 8000 என்ன செய்ய வேண்டும் ஆபத்து"),
            ("hi", "मेरी सैलरी 30000 है खर्च 22000 बचत 8000 क्या करें और जोखिम क्या है"),
        ]:
            res = answer_question(prompt, pd.DataFrame(), currency="INR")
            assert res["ok"] is True
            assert res["tool"] == "personal_cashflow_advisor"
            assert res["language"] == lang_code
            assert len(res["actions"]) == 3
            assert len(res["metrics"]) == 4

    @pytest.mark.parametrize(
        "salary_q,expected_tag",
        [
            ("salary 50000 expense 55000 zero savings what risk?", "Critical Risk"),
            ("salary 40k spend 36k save 4k risk factor", "Elevated Risk"),
            ("salary 100k spend 78k save 22k plan", "Moderate Risk"),
        ],
    )
    def test_personal_advisor_risk_tiers(self, salary_q, expected_tag):
        res = answer_question(salary_q, pd.DataFrame(), currency="INR")
        assert res["tool"] == "personal_cashflow_advisor"
        risk_metric = next(m["value"] for m in res["metrics"] if "Risk" in m["label"])
        assert expected_tag in risk_metric


class TestAllThirteenTools:
    def test_tool_1_overview_kpis_en_ta_hi(self):
        df = _copilot_ledger()
        for lang, expected_char in [("en", "revenue"), ("ta", "வருவாய்"), ("hi", "राजस्व")]:
            res = answer_question("Give me overall executive summary", df, currency="INR", language=lang)
            assert res["tool"] == "overview_kpis"
            assert expected_char.lower() in res["answer"].lower()
            assert len(res["metrics"]) >= 4

    def test_tool_2_future_prediction_targets_and_horizons(self):
        df = _copilot_ledger()
        for q in (
            "Predict next 6 months revenue",
            "Forecast next 12 months expenses",
            "Predict next 3 months profit",
        ):
            res = answer_question(q, df, currency="INR")
            assert res["tool"] == "future_prediction"
            assert res["ok"] is True
            assert len(res["metrics"]) >= 3

    def test_tool_2_localized_tamil_and_hindi(self):
        df = _copilot_ledger()
        ta = answer_question("அடுத்த 6 மாத வருவாய் கணிப்பு", df, language="ta")
        hi = answer_question("अगले 6 माह का लाभ अनुमान बताएं", df, language="hi")
        assert ta["tool"] == "future_prediction"
        assert hi["tool"] == "future_prediction"
        assert "கணிப்பு" in ta["answer"]
        assert "अनुमान" in hi["answer"]

    def test_tool_3_cashflow_runway(self):
        res = answer_question("What is our cashflow runway?", _copilot_ledger(), currency="INR")
        assert res["tool"] == "cashflow_runway"
        assert any("Runway" in m["label"] for m in res["metrics"])

    @pytest.mark.parametrize(
        "q,dim_word",
        [
            ("Which product generated highest profit?", "Product"),
            ("Compare performance by department", "Department"),
            ("Rank regions by net profit", "Region"),
            ("Which category performed best?", "Category"),
        ],
    )
    def test_tool_4_segment_ranking(self, q, dim_word):
        res = answer_question(q, _copilot_ledger(), currency="INR")
        assert res["tool"] == "segment_ranking"
        assert dim_word in res["title"]

    def test_tool_5_anomaly_audit(self):
        res = answer_question("Show expense anomalies and IQR outliers", _copilot_ledger(), currency="INR")
        assert res["tool"] == "anomaly_audit"
        assert "outlier" in res["answer"].lower()

    def test_tool_6_ml_risk_audit(self):
        res = answer_question("Show Random Forest risk score and high risk entries", _copilot_ledger(), currency="INR")
        assert res["tool"] == "ml_risk_audit"
        assert "High Risk" in res["answer"]

    def test_tool_7_margin_optimizer(self):
        res = answer_question("How can I hit 45% target margin?", _copilot_ledger(), currency="INR")
        assert res["tool"] == "margin_optimizer"
        assert "45.0%" in res["title"]

    def test_tool_8_what_if_handles_negative_drop_keywords(self):
        res = answer_question("What if revenue grows 15% and expenses drop 10%?", _copilot_ledger(), currency="INR")
        assert res["tool"] == "what_if_simulation"
        assert "+15%" in res["title"]
        assert "-10%" in res["title"]

    def test_tool_9_period_growth_summary(self):
        res = answer_question("Compare month over month growth vs previous month", _copilot_ledger(), currency="INR")
        assert res["tool"] == "period_growth_summary"
        assert "MoM" in res["title"]

    def test_tool_10_date_or_year_filter_found_missing_and_extremes(self):
        df = _copilot_ledger()
        r_2024 = answer_question("Show performance in year 2024", df, currency="INR")
        assert r_2024["tool"] == "date_or_year_filter"
        assert "2024" in r_2024["title"]

        r_missing = answer_question("Show performance in year 2099", df, currency="INR")
        assert "No ledger entries matched calendar year 2099" in r_missing["answer"]

        r_peak = answer_question("Which was our peak month vs worst month?", df, currency="INR")
        assert "Peak Month" in {m["label"] for m in r_peak["metrics"]}

    def test_tool_11_vendor_or_payment_audit(self):
        res = answer_question("Which vendor did we pay the most and what payment mode?", _copilot_ledger(), currency="INR")
        assert res["tool"] == "vendor_or_payment_audit"
        assert len(res["metrics"]) >= 2

    def test_tool_12_dataset_and_audit_status(self):
        res = answer_question("How many rows are imported and dataset schema status?", _copilot_ledger(), filename_meta="test.csv")
        assert res["tool"] == "dataset_and_audit_status"
        assert "16 validated transactions" in res["answer"]

    def test_pii_redacted_before_processing(self):
        res = answer_question("Show summary for ceo@secret.org card 4532123456789012", _copilot_ledger())
        assert "ceo@secret.org" not in str(res)
        assert "4532123456789012" not in str(res)
