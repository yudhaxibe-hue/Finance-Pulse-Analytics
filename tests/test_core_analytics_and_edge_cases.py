"""Comprehensive unit & edge-case tests for optimization, intelligence, profitability, metrics, updater, and launcher."""
from __future__ import annotations

import pandas as pd
import pytest

import app_launcher
import config
import updater
from analytics.anomalies import detect as detect_anomalies
from analytics.financial_metrics import metrics, monthly, period_growth, safe_pct
from analytics.forecasting import forecast
from analytics.intelligence import (
    anomalies_narrative,
    dimension_narrative,
    forecast_narrative,
    ml_insights_narrative,
    overview_narrative,
)
from analytics.optimization import recommendations, scenario, segment_opportunities, target_margin_plan
from analytics.profitability import by_dimension
from data.importer import allowed, detect, normalize, persist, quality_report
from database.db import connect


class TestFinancialMetricsAndProfitabilityEdgeCases:
    def test_empty_dataframe_metrics_and_monthly(self):
        m = metrics(pd.DataFrame())
        assert m["transactions"] == 0
        assert m["revenue"] is None
        assert m["profit"] is None

        mon = monthly(pd.DataFrame())
        assert mon.empty
        assert list(mon.columns) == ["period", "revenue", "expense", "cost", "profit", "margin"]

    def test_monthly_coerces_string_dates_and_drops_invalid(self):
        df = pd.DataFrame({
            "txn_date": ["2025-01-10", "invalid-date", "2025-02-15"],
            "revenue": [1000.0, 9999.0, 2000.0],
            "expense": [400.0, 9999.0, 700.0],
            "cost": [100.0, 0.0, 200.0],
        })
        mon = monthly(df)
        assert len(mon) == 2
        assert mon["revenue"].sum() == pytest.approx(3000.0)

    def test_safe_pct_and_period_growth_edges(self):
        assert safe_pct(50, 0) is None
        assert safe_pct(25, 100) == 25.0
        assert period_growth(pd.Series([100.0])) is None
        assert period_growth(pd.Series([0.0, 100.0])) is None
        assert period_growth(pd.Series([100.0, 125.0])) == 25.0
        assert period_growth(pd.Series([200.0, 150.0])) == -25.0

    def test_by_dimension_handles_blank_missing_and_sorts_descending(self):
        df = pd.DataFrame({
            "product": ["", None, "Enterprise", "Starter"],
            "revenue": [100.0, 200.0, 5000.0, 800.0],
            "expense": [50.0, 120.0, 1500.0, 900.0],
            "cost": [10.0, 20.0, 500.0, 100.0],
        })
        rows = by_dimension(df, "product")
        assert rows[0]["product"] == "Enterprise"
        assert rows[-1]["product"] == "Starter"
        unassigned = next(r for r in rows if r["product"] == "Unassigned")
        assert unassigned["revenue"] == pytest.approx(300.0)
        assert by_dimension(pd.DataFrame(), "product") == []
        assert by_dimension(df, "nonexistent_col") == []


class TestOptimizationEngine:
    def test_scenario_zero_revenue_returns_none_margin(self):
        base = {"revenue": 0.0, "expenses": 100.0, "profit": -100.0}
        res = scenario(base, revenue_change=10, expense_change=-20)
        assert res["expenses"] == pytest.approx(80.0)
        assert res["profit"] == pytest.approx(-80.0)
        assert res["margin"] is None

    def test_recommendations_surfaces_cost_pressure_low_margin_and_high_ratio(self):
        df = pd.DataFrame({
            "txn_date": pd.to_datetime(["2025-01-10", "2025-02-10"]),
            "product": ["Alpha", "Alpha"],
            "revenue": [1000.0, 1000.0],
            "expense": [600.0, 1200.0],
            "cost": [200.0, 200.0],
            "investment": [0.0, 0.0],
        })
        recs = recommendations(df, margin_threshold=20.0)
        titles = {r["title"] for r in recs}
        assert "Cost pressure" in titles
        assert "Low-margin product" in titles
        assert "High expense ratio" in titles

    def test_target_margin_plan_edges_achieved_invalid_and_clamping(self):
        assert target_margin_plan({"revenue": 0.0, "expenses": 50.0, "profit": -50.0}, 20.0) is None
        achieved = target_margin_plan({"revenue": 1000.0, "expenses": 600.0, "profit": 400.0, "margin": 40.0}, 25.0)
        assert achieved["already_achieved"] is True
        assert achieved["expense_cut_amount"] == 0.0
        assert achieved["revenue_lift_amount"] == 0.0

        clamped = target_margin_plan({"revenue": 1000.0, "expenses": 900.0, "profit": 100.0, "margin": 10.0}, 150.0)
        assert clamped["target_margin"] == 95.0

    def test_segment_opportunities_unrecovered_spend_and_top8_limit(self):
        assert segment_opportunities(pd.DataFrame()) == []
        df = pd.DataFrame({
            "product": [f"P{i}" for i in range(10)],
            "department": [f"D{i}" for i in range(10)],
            "category": ["Software"] * 10,
            "region": ["North"] * 10,
            "revenue": [0.0] + [1000.0 * (i + 1) for i in range(9)],
            "expense": [500.0] + [300.0 * (i + 1) for i in range(9)],
            "cost": [100.0] * 10,
        })
        opps = segment_opportunities(df, margin_threshold=15.0)
        assert len(opps) <= 8
        assert opps == sorted(opps, key=lambda x: x["impact"], reverse=True)
        # Ensure zero-revenue positive-expense segment generates Eliminate unrecovered spend somewhere on full list
        small = df.iloc[:1].copy()
        s_opps = segment_opportunities(small, margin_threshold=15.0)
        assert any(o["opportunity"] == "Eliminate unrecovered spend" for o in s_opps)


class TestIntelligenceNarrativesEdgeCases:
    def test_narratives_return_none_on_empty_inputs(self):
        empty = pd.DataFrame()
        assert overview_narrative(empty, []) is None
        assert dimension_narrative(empty, "product", []) is None
        assert anomalies_narrative(empty, []) is None
        assert forecast_narrative({}, "revenue", 6) is None
        assert ml_insights_narrative({}, {}) is None

    def test_anomalies_narrative_clean_and_revenue_spike_branches(self):
        clean_df = pd.DataFrame({
            "txn_date": pd.date_range("2025-01-01", periods=5, freq="MS"),
            "category": ["Sales"] * 5,
            "revenue": [1000.0, 1020.0, 1010.0, 1030.0, 1005.0],
            "expense": [400.0, 410.0, 405.0, 415.0, 408.0],
            "cost": [100.0] * 5,
            "investment": [0.0] * 5,
        })
        b_clean = anomalies_narrative(clean_df, [], 1.5, "USD")
        assert "0 statistical outliers" in b_clean["pillars"][1]["headline"]

        rev_spike_df = clean_df.copy()
        rev_spike_df.loc[4, "revenue"] = 95000.0
        flags = detect_anomalies(rev_spike_df, 1.5)
        b_spike = anomalies_narrative(rev_spike_df, flags, 1.5, "INR")
        assert "recurring ex-spike profit" in b_spike["pillars"][2]["headline"]

    def test_forecast_narrative_ols_vs_rf_and_ml_insights_narrative(self):
        dates4 = pd.date_range("2025-01-01", periods=4, freq="MS")
        df4 = pd.DataFrame({"txn_date": dates4, "revenue": [100, 120, 140, 160], "expense": [50, 60, 70, 80], "cost": [20]*4})
        res4 = forecast(df4, "revenue", 3)
        b4 = forecast_narrative(res4, "revenue", 3, "INR")
        assert "linear trend" in b4["pillars"][0]["headline"]

        dates8 = pd.date_range("2025-01-01", periods=8, freq="MS")
        df8 = pd.DataFrame({"txn_date": dates8, "revenue": [1000 + i * 100 for i in range(8)], "expense": [500] * 8, "cost": [200] * 8})
        res8 = forecast(df8, "revenue", 4)
        b8 = forecast_narrative(res8, "revenue", 4, "INR")
        assert "Random Forest" in b8["pillars"][0]["headline"]

        ml_b = ml_insights_narrative(
            {"total": 50, "high_risk": 5, "moderate_risk": 10, "low_risk": 35, "high_risk_exposure": 12000.0, "feature_importances": [{"feature": "Expense Ratio", "importance": 55.0}]},
            {"status": "Healthy Surplus", "recent_monthly_net": 5000.0, "runway_months": None},
            "INR",
        )
        assert "50 entries" in ml_b["pillars"][0]["headline"]
        assert "5 High Risk" in ml_b["pillars"][1]["headline"]


class TestImporterAndUpdaterAndLauncherEdgeCases:
    @pytest.mark.parametrize(
        "filename,ok",
        [("ledger.csv", True), ("audit.xlsx", True), ("dump.json", True), ("script.sh", False), ("noext", False)],
    )
    def test_allowed_extensions(self, filename, ok):
        assert allowed(filename) is ok

    def test_currency_indian_rupee_symbol_and_persist_without_ml(self, isolated_env):
        raw = pd.DataFrame({
            "Date": ["2025-03-01", ""],
            "Type": ["Debit", "Credit"],
            "Total Amount INR": ["Rs. 12,500", "INR 30,000"],
            "Category": ["Ops", "Sales"],
        })
        rep = quality_report(raw, detect(raw.columns))
        assert rep["invalid_dates"] == 1
        cleaned, excluded = normalize(raw, detect(raw.columns))
        assert len(cleaned) == 1
        assert cleaned.iloc[0]["expense"] == pytest.approx(12500.0)

        imp_id = persist(cleaned, "no_ml.csv", rep, excluded, workspace_id=1, enrich_ml=False)
        conn = connect()
        try:
            row = conn.execute("SELECT risk_tier, expense FROM financial_transactions WHERE import_id=?", (imp_id,)).fetchone()
            assert row["risk_tier"] == "Unclassified"
            assert row["expense"] == pytest.approx(12500.0)
        finally:
            conn.close()

    @pytest.mark.parametrize(
        "raw_url,expected",
        [
            ("https://example.com/", "https://example.com"),
            ("example.org/sync", "https://example.org/sync"),
            ("http://192.168.1.10:8080/", "http://192.168.1.10:8080"),
            ("javascript:alert(1)", None),
            ("data:text/html,hi", None),
            ("file:///etc/passwd", None),
            ("   ", None),
            (None, None),
        ],
    )
    def test_normalize_http_url_security(self, raw_url, expected):
        assert updater.normalize_http_url(raw_url) == expected

    @pytest.mark.parametrize(
        "lv,lb,rv,rb,expected",
        [
            ("1.1.0", 2, "1.2.0", 16, True),
            ("1.2.0", 16, "1.2.0", 16, False),
            ("1.2.0", 16, "1.1.0", 16, False),
            ("1.2.0", 16, "1.3.0", None, True),
            ("1.2.0", 16, "1.1.9", None, False),
        ],
    )
    def test_is_update_available_semver_and_build(self, lv, lb, rv, rb, expected):
        assert updater.is_update_available(lv, lb, rv, rb) is expected

    def test_sync_override_and_manifest_parsing(self, isolated_env):
        ok_bad, val_bad = updater.set_sync_override("javascript:alert(1)")
        assert ok_bad is False
        assert val_bad is None

        ok_set, val_set = updater.set_sync_override("https://sync.financepulse.local/")
        assert ok_set is True
        assert val_set == "https://sync.financepulse.local"
        assert updater.get_sync_config()["mode"] == "Manual override"

        ok_clr, _ = updater.set_sync_override("")
        assert ok_clr is True
        assert updater.get_sync_config()["override_url"] == ""

        parsed = updater.parse_manifest_dict({
            "version": "1.9.0",
            "build_number": 99,
            "sync_server_url": "https://central.example.com/",
            "release_notes": "Enterprise release",
        })
        assert parsed["update_available"] is True
        assert parsed["sync_server_url"] == "https://central.example.com"

    def test_app_launcher_cli_and_admin_bootstrap(self, isolated_env):
        assert app_launcher.normalize_start_path("", admin_mode=False) == "/"
        assert app_launcher.normalize_start_path("", admin_mode=True) == "/admin/login"
        assert app_launcher.normalize_start_path("user/data", admin_mode=False) == "/user/data"
        assert app_launcher.resolve_remote_url("finance.local", "/admin/login") == "https://finance.local/admin/login"
        assert app_launcher.find_free_port("127.0.0.1") > 0

        parsed_cli = app_launcher.parse_args(["--headless", "--admin", "--port", "9100", "-psn_0_98765"])
        assert parsed_cli.headless is True
        assert parsed_cli.admin is True
        assert parsed_cli.port == 9100

        # Invalid admin creation
        assert app_launcher.create_admin_account_cli("bad-email", "password123", "A") == 1
        assert app_launcher.create_admin_account_cli("ok@test.local", "short", "A") == 1
        # Valid admin creation & subsequent update
        assert app_launcher.create_admin_account_cli("cliadmin@test.local", "StrongPass123", "CLI Admin") == 0
        assert app_launcher.create_admin_account_cli("cliadmin@test.local", "StrongPass456", "CLI Admin v2") == 0

    def test_windows_chromium_app_window_fallback(self, isolated_env, monkeypatch, tmp_path):
        fake_edge = tmp_path / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        fake_edge.parent.mkdir(parents=True)
        fake_edge.write_text("", encoding="utf-8")
        monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path))

        assert app_launcher._find_windows_chromium_app_browser() == str(fake_edge)

        launched_cmds = []
        closed = []

        class FakeProc:
            def wait(self):
                return 0

            def poll(self):
                return 0

            def terminate(self):
                pass

        # Simulate window staying open >= 2s before closing cleanly
        ticks = iter([100.0, 105.0])
        monkeypatch.setattr(app_launcher.time, "monotonic", lambda: next(ticks))
        import subprocess
        monkeypatch.setattr(subprocess, "Popen", lambda cmd: (launched_cmds.append(cmd), FakeProc())[1])

        ok = app_launcher._open_chromium_app_window(
            "http://127.0.0.1:5000/",
            storage_dir=isolated_env / "webview_user",
            on_close_callback=lambda: closed.append(True),
        )
        assert ok is True
        assert closed == [True]
        assert launched_cmds and launched_cmds[0][0] == str(fake_edge)
        assert "--app=http://127.0.0.1:5000/" in launched_cmds[0]
        assert any(arg.startswith("--user-data-dir=") for arg in launched_cmds[0])


class TestAdditionalCoverageAndEnterpriseGuards:
    def test_anomaly_detector_small_and_multiplier_sensitivity(self):
        assert detect_anomalies(pd.DataFrame()) == []
        tiny = pd.DataFrame({"txn_date": ["2025-01-01", "2025-02-01"], "revenue": [100.0, 200.0], "expense": [50.0, 60.0]})
        assert detect_anomalies(tiny) == []

        dates = pd.date_range("2025-01-01", periods=10, freq="MS")
        df = pd.DataFrame({
            "txn_date": dates,
            "category": ["Ops"] * 10,
            "revenue": [1000.0] * 10,
            "expense": [400.0, 410.0, 420.0, 405.0, 415.0, 402.0, 408.0, 412.0, 425.0, 580.0],
        })
        loose = detect_anomalies(df, multiplier=3.0)
        tight = detect_anomalies(df, multiplier=1.0)
        assert len(tight) >= len(loose)

    @pytest.mark.parametrize(
        "num_str,suf,expected",
        [
            ("30", "k", 30_000.0),
            ("2.5", "lakh", 250_000.0),
            ("1.2", "lac", 120_000.0),
            ("1.5", "cr", 15_000_000.0),
            ("2", "mn", 2_000_000.0),
            ("45,000", "", 45_000.0),
        ],
    )
    def test_copilot_indian_scale_suffix_parser(self, num_str, suf, expected):
        from analytics.copilot import _parse_money_token

        assert _parse_money_token(num_str, suf) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "prompt,expected_tool",
        [
            ("en sambalam 30k selavu 22k meedhi 8k enna seiya vendum", "personal_cashflow_advisor"),
            ("meri salary 50k hai kharcha 35k bachat 15k risk factor kya hai", "personal_cashflow_advisor"),
            ("Show anomaly spikes and IQR outliers", "anomaly_audit"),
            ("What is our break-even revenue and target 30% margin?", "margin_optimizer"),
            ("Show top vendor and UPI payment method", "vendor_or_payment_audit"),
            ("How many rows are imported in this dataset?", "dataset_and_audit_status"),
        ],
    )
    def test_copilot_intent_router_coverage(self, prompt, expected_tool):
        from analytics.copilot import answer_question

        df = pd.DataFrame({
            "txn_date": pd.date_range("2025-01-01", periods=6, freq="MS").strftime("%Y-%m-%d"),
            "category": ["Ops"] * 6,
            "product": ["Core"] * 6,
            "department": ["Eng"] * 6,
            "region": ["North"] * 6,
            "vendor_name": ["CloudCo"] * 6,
            "payment_method": ["UPI"] * 6,
            "revenue": [10000.0] * 6,
            "expense": [4000.0] * 6,
            "cost": [2000.0] * 6,
            "investment": [500.0] * 6,
        })
        res = answer_question(prompt, df)
        assert res["ok"] is True
        assert res["tool"] == expected_tool

    def test_all_analytics_views_and_health_version_match(self, isolated_env):
        import app

        c = app.app.test_client()
        health = c.get("/health").get_json()
        assert health["status"] == "ok"
        assert health["version"] == config.APP_VERSION == "1.2.0"

        c.post("/register", data={"name": "ViewTester", "email": "vt@example.com", "password": "strongpassword123"})
        c.post("/user/load-enterprise-sample")
        for view_name in ("overview", "products", "departments", "categories", "regions", "anomalies"):
            resp = c.get(f"/user/analytics/{view_name}")
            assert resp.status_code == 200
        fc = c.get("/user/forecasting?target=expense&horizon=12")
        assert fc.status_code == 200

    def test_update_banner_present_on_landing_and_auth_and_install_guard(self, isolated_env):
        import app

        c = app.app.test_client()
        for route in ("/", "/login", "/register", "/admin/login"):
            resp = c.get(route)
            assert resp.status_code == 200
            assert b'id="desktopUpdateBanner"' in resp.data
            assert b'id="btnDesktopInstallUpdate"' in resp.data

        # External proxied client must be blocked from triggering local install-update
        blocked = c.post("/api/system/install-update", headers={"X-Forwarded-For": "203.0.113.10"})
        assert blocked.status_code == 403

    def test_desktop_updater_zip_safety_targets_and_self_install(self, isolated_env, monkeypatch, tmp_path):
        import hashlib
        import subprocess
        import zipfile
        from pathlib import Path

        assert updater.is_safe_zip_member("FinancePulseAnalytics/FinancePulseAnalytics.exe") is True
        assert updater.is_safe_zip_member("../outside.txt") is False
        assert updater.is_safe_zip_member("/etc/passwd") is False
        assert updater.is_safe_zip_member("C:\\Windows\\system32\\cmd.exe") is False

        # Unfrozen source mode never self-overwrites repo files
        monkeypatch.delattr(updater.sys, "frozen", raising=False)
        assert updater.detect_desktop_install_target()["can_self_install"] is False

        # Protect custom FinancePulseAdmin.app from overwriting itself with user bundle
        monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
        monkeypatch.setattr(updater.sys, "platform", "darwin")
        admin_exe = tmp_path / "FinancePulseAdmin.app" / "Contents" / "MacOS" / "FinancePulseAdmin"
        admin_exe.parent.mkdir(parents=True)
        admin_exe.write_text("", encoding="utf-8")
        monkeypatch.setattr(updater.sys, "executable", str(admin_exe))
        admin_target = updater.detect_desktop_install_target()
        assert admin_target["can_self_install"] is False
        assert admin_target["mode"] == "custom_admin_bundle"

        # Valid Windows install script avoids parenthesized IF blocks
        win_script = updater._build_windows_apply_script(
            4242,
            tmp_path / "staged",
            tmp_path / "Program Files (x86)" / "FinancePulseAnalytics",
            "FinancePulseAnalytics.exe",
            tmp_path / "staging",
        )
        assert "robocopy" in win_script
        assert "FinancePulseAnalytics.exe" in win_script

        # Valid macOS frozen FinancePulseAnalytics.app swap with verified ZIP
        user_app = tmp_path / "FinancePulseAnalytics.app"
        user_exe = user_app / "Contents" / "MacOS" / "FinancePulseAnalytics"
        user_exe.parent.mkdir(parents=True)
        user_exe.write_text("#!/bin/sh\necho old\n", encoding="utf-8")
        monkeypatch.setattr(updater.sys, "executable", str(user_exe))
        user_target = updater.detect_desktop_install_target()
        assert user_target["can_self_install"] is True
        assert user_target["mode"] == "macos_app_swap"

        zip_path = tmp_path / "FinancePulseAnalytics-macOS-unsigned.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("FinancePulseAnalytics.app/Contents/Info.plist", "<plist/>")
            zf.writestr("FinancePulseAnalytics.app/Contents/MacOS/FinancePulseAnalytics", "new-bin")

        # Tampered SHA-256 must fail before extracting
        with updater._STATE_LOCK:
            updater._UPDATE_CACHE["download_status"] = "ready"
            updater._UPDATE_CACHE["download_path"] = str(zip_path)
            updater._UPDATE_CACHE["sha256"] = "0" * 64
        bad_res = updater.install_desktop_update(trigger_shutdown=False)
        assert bad_res["ok"] is False
        assert "SHA-256 verification failed" in bad_res["message"]

        # Re-create ZIP cleanly with matching SHA-256 and mock Popen to verify apply script launch
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("FinancePulseAnalytics.app/Contents/Info.plist", "<plist/>")
            zf.writestr("FinancePulseAnalytics.app/Contents/MacOS/FinancePulseAnalytics", "new-bin")
        good_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        with updater._STATE_LOCK:
            updater._UPDATE_CACHE["download_status"] = "ready"
            updater._UPDATE_CACHE["download_path"] = str(zip_path)
            updater._UPDATE_CACHE["sha256"] = good_sha

        spawned = []
        real_popen = subprocess.Popen

        def selective_popen(cmd, **kw):
            if cmd and cmd[0] == "/bin/sh":
                spawned.append(cmd)
                return None
            return real_popen(cmd, **kw)

        monkeypatch.setattr(subprocess, "Popen", selective_popen)
        ok_res = updater.install_desktop_update(trigger_shutdown=False)
        assert ok_res["ok"] is True
        assert ok_res["restarting"] is True
        assert ok_res["install_status"] == "restarting"
        assert spawned and spawned[0][0] == "/bin/sh"
        assert (Path(config.DATA_DIR) / "apply_update.sh").is_file()
        assert (Path(config.DATA_DIR) / "update_staging" / "FinancePulseAnalytics.app").is_dir()

