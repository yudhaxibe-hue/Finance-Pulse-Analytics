"""Tests for offline Random Forest risk/category models, RF Regressor forecasting, IsolationForest anomalies, and runway math."""
from __future__ import annotations

import pandas as pd
import pytest

from analytics.anomalies import detect as detect_anomalies
from analytics.financial_metrics import compute_cashflow_runway
from analytics.forecasting import forecast
from analytics.ml_engine import (
    _extract_risk_features,
    enrich_transactions_df,
    ml_summary,
    model_artifact_path,
    predict_missing_categories,
    score_transactions_risk,
    train_and_save_models,
)
from data.importer import detect, normalize
from data.sample_data import build_enterprise_10k_dataframe


def _monthly_fixture(months: int = 12) -> pd.DataFrame:
    dates = pd.date_range("2024-01-15", periods=months, freq="MS")
    return pd.DataFrame({
        "txn_date": dates.strftime("%Y-%m-%d"),
        "category": ["Software" if i % 2 == 0 else "Services" for i in range(months)],
        "product": ["Core Suite"] * months,
        "department": ["Product"] * months,
        "region": ["North"] * months,
        "revenue": [50000.0 + i * 2500.0 + (4000.0 if i % 4 == 0 else 0.0) for i in range(months)],
        "expense": [26000.0 + i * 1100.0 for i in range(months)],
        "cost": [10000.0] * months,
        "investment": [2000.0 if i % 3 == 0 else 0.0 for i in range(months)],
    })


class TestRandomForestMlEngine:
    def test_train_and_save_models_persists_joblib(self, isolated_env):
        df = _monthly_fixture(12)
        bundle = train_and_save_models(df, persist_disk=True)
        assert bundle["artifact_path"] is not None
        assert model_artifact_path().is_file()
        assert bundle["row_count"] == 12

    def test_extract_risk_features_handles_minimal_and_empty_df(self):
        assert _extract_risk_features(pd.DataFrame()).shape == (0, 9)
        minimal = pd.DataFrame({"revenue": [1000.0, 0.0], "expense": [400.0, 500.0]})
        feats = _extract_risk_features(minimal)
        assert feats.shape == (2, 9)

    def test_score_transactions_risk_separates_healthy_and_deficit(self):
        df = pd.DataFrame([
            {"txn_date": "2025-01-10", "revenue": 100000.0, "expense": 25000.0, "cost": 10000.0},
            {"txn_date": "2025-02-10", "revenue": 25000.0, "expense": 85000.0, "cost": 12000.0},
        ])
        scored = score_transactions_risk(df)
        assert set(["risk_tier", "risk_score"]).issubset(scored.columns)
        assert scored.iloc[0]["risk_tier"] in ("Low Risk", "Moderate Risk")
        assert scored.iloc[1]["risk_tier"] in ("Moderate Risk", "High Risk")
        assert 1.0 <= float(scored.iloc[0]["risk_score"]) <= 99.9
        assert float(scored.iloc[1]["risk_score"]) > float(scored.iloc[0]["risk_score"])

    @pytest.mark.parametrize(
        "product,department,notes,rev,exp,expected_cat",
        [
            ("Teacher Salary", "Academics", "Monthly faculty payroll stipend", 0.0, 75000.0, "Payroll"),
            ("AWS Cloud Hosting", "Engineering", "Cloud Kubernetes production bill", 0.0, 42000.0, "Software"),
            ("Google Ads", "Growth", "Admission search campaign marketing", 0.0, 35000.0, "Marketing"),
            ("Statutory Audit", "Finance", "Chartered accountant advisory fee", 0.0, 28000.0, "Consulting"),
            ("Student Tuition Fee", "Registrar", "Term 1 examination enrollment fee", 140000.0, 0.0, "Tuition & Fees"),
            ("Flight & Hotel", "Field Sales", "Domestic travel airline reimbursement", 0.0, 18000.0, "Travel"),
            ("Lab Equipment", "Infrastructure", "Desktop computers and projectors capex", 0.0, 150000.0, "Equipment & Capex"),
        ],
    )
    def test_predict_missing_categories_offline_classifier(self, product, department, notes, rev, exp, expected_cat):
        row = pd.DataFrame([{
            "product": product,
            "department": department,
            "notes": notes,
            "revenue": rev,
            "expense": exp,
        }])
        preds = predict_missing_categories(row)
        assert preds.iloc[0] == expected_cat

    def test_enrich_and_ml_summary_on_large_enterprise_dataset(self, isolated_env):
        raw = build_enterprise_10k_dataframe(n_rows=1000, seed=7)
        ent, _ = normalize(raw, detect(raw.columns))
        enriched = enrich_transactions_df(ent, persist_models=True)
        assert len(enriched) == 1000
        assert set(enriched["risk_tier"].unique()).issubset({"Low Risk", "Moderate Risk", "High Risk"})
        assert "predicted_category" in enriched.columns
        assert enriched["is_anomaly"].isin([0, 1]).all()

        summary = ml_summary(enriched)
        assert summary["total"] == 1000
        assert summary["low_risk"] + summary["moderate_risk"] + summary["high_risk"] == 1000
        assert len(summary["feature_importances"]) == 5
        assert summary["model_saved"] is True

    def test_ml_summary_empty_dataframe(self):
        res = ml_summary(pd.DataFrame())
        assert res["total"] == 0
        assert res["high_risk"] == 0
        assert res["feature_importances"] == []


class TestForecastingEngine:
    def test_short_series_returns_insufficient_data_error(self):
        df = _monthly_fixture(3)
        res = forecast(df, target="revenue", horizon=6)
        assert "error" in res
        assert res["forecast"] == []

    def test_five_period_series_falls_back_to_ols(self):
        df = _monthly_fixture(5)
        res = forecast(df, target="profit", horizon=6, model_type="auto")
        assert res["model"] == "Linear trend regression"
        assert res["model_code"] == "ols"
        assert len(res["forecast"]) == 6
        assert "r2" in res["accuracy"]

    def test_twelve_period_uses_random_forest_regressor_with_confidence_bands(self):
        df = _monthly_fixture(14)
        res = forecast(df, target="revenue", horizon=6, model_type="auto")
        assert res["model"] == "Random Forest Regressor"
        assert res["model_code"] == "random_forest"
        assert len(res["forecast"]) == 6
        assert len(res["feature_importances"]) >= 4
        for pt in res["forecast"]:
            assert pt["low"] <= pt["value"] <= pt["high"]
            assert "ols_baseline" in pt

    def test_explicit_ols_override_on_long_series(self):
        df = _monthly_fixture(12)
        res = forecast(df, target="expense", horizon=9, model_type="ols")
        assert res["model_code"] == "ols"
        assert len(res["forecast"]) == 9

    @pytest.mark.parametrize("target", ["revenue", "expense", "profit"])
    def test_forecast_targets_and_horizon_clamping(self, target):
        df = _monthly_fixture(10)
        res = forecast(df, target=target, horizon=12)
        assert len(res["forecast"]) == 12
        assert res["accuracy"]["mae"] >= 0


class TestHybridAnomaliesAndRunway:
    def test_hybrid_iqr_and_isolation_forest_flags_planted_outlier(self):
        df = _monthly_fixture(18)
        df.loc[17, "expense"] = 950000.0
        flags = detect_anomalies(df, multiplier=1.5)
        assert len(flags) >= 1
        top = flags[0]
        assert top["type"] == "Expense"
        assert top["value"] == pytest.approx(950000.0)
        assert "z_score" in top and "isolation_score" in top
        assert "Isolation Forest" in top["method"] or "Statistical IQR" in top["method"]

    def test_clean_series_returns_empty_anomalies(self):
        df = pd.DataFrame({
            "txn_date": pd.date_range("2025-01-01", periods=10, freq="MS").strftime("%Y-%m-%d"),
            "category": ["Ops"] * 10,
            "revenue": [1000.0 + i for i in range(10)],
            "expense": [500.0 + i for i in range(10)],
        })
        assert detect_anomalies(df, multiplier=1.5) == []

    def test_cashflow_runway_surplus_watch_and_critical_modes(self):
        # Empty -> No data
        assert compute_cashflow_runway(pd.DataFrame())["status"] == "No data"

        # Healthy Surplus (Self-Sustaining)
        surplus_df = _monthly_fixture(6)
        rw_good = compute_cashflow_runway(surplus_df)
        assert "Healthy Surplus" in rw_good["status"]
        assert rw_good["runway_months"] is None
        assert rw_good["recent_monthly_net"] > 0

        # Watch / Burning down positive accumulated reserve across recent 6 months
        burn_df = pd.DataFrame({
            "txn_date": [
                "2025-01-10", "2025-02-10", "2025-03-10",
                "2025-04-10", "2025-05-10", "2025-06-10",
                "2025-07-10", "2025-08-10", "2025-09-10",
            ],
            "revenue": [120000, 120000, 120000, 20000, 20000, 20000, 20000, 20000, 20000],
            "expense": [10000, 10000, 10000, 40000, 40000, 40000, 40000, 40000, 40000],
        })
        rw_watch = compute_cashflow_runway(burn_df)
        assert rw_watch["recent_monthly_net"] < 0
        assert rw_watch["runway_months"] > 0
        assert any(tok in rw_watch["status"] for tok in ("Watch", "Stable Buffer", "Critical"))

        # Critical with zero reserve
        red_df = pd.DataFrame({
            "txn_date": ["2025-01-10", "2025-02-10", "2025-03-10"],
            "revenue": [10000, 10000, 10000],
            "expense": [50000, 50000, 50000],
        })
        rw_crit = compute_cashflow_runway(red_df)
        assert "Critical Runway" in rw_crit["status"]
        assert rw_crit["runway_months"] == 0.0
