import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
from werkzeug.security import generate_password_hash

import app
import config
from analytics.anomalies import detect as detect_anomalies
from analytics.financial_metrics import metrics, monthly, period_growth
from analytics.forecasting import forecast
from analytics.intelligence import anomalies_narrative, dimension_narrative, forecast_narrative, overview_narrative
from analytics.optimization import recommendations, scenario, segment_opportunities, target_margin_plan
from analytics.profitability import by_dimension
from data.importer import detect, normalize, quality_report
from database.db import connect, initialize


class IsolatedDBTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_db = config.DATABASE
        self._orig_upload = config.UPLOAD_FOLDER
        config.DATABASE = Path(self._tmpdir.name) / "test.db"
        config.UPLOAD_FOLDER = Path(self._tmpdir.name) / "uploads"
        initialize()
        app.app.config["TESTING"] = True

    def tearDown(self):
        config.DATABASE = self._orig_db
        config.UPLOAD_FOLDER = self._orig_upload
        self._tmpdir.cleanup()


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "revenue": [1000.0],
            "expense": [600.0],
            "cost": [400.0],
            "investment": [200.0],
        })

    def test_profit_and_margin(self):
        result = metrics(self.df)
        self.assertEqual(result["profit"], 400)
        self.assertEqual(result["margin"], 40)
        self.assertEqual(result["gross_profit"], 600)

    def test_scenario(self):
        result = scenario(metrics(self.df), 10, -5)
        self.assertEqual(result["revenue"], 1100)
        self.assertEqual(result["expenses"], 570)
        self.assertEqual(result["profit"], 530)

    def test_target_margin_plan_and_segment_opportunities(self):
        plan = target_margin_plan({"revenue": 1000.0, "expenses": 600.0, "profit": 400.0, "margin": 40.0}, 50.0)
        self.assertIsNotNone(plan)
        self.assertEqual(plan["expense_cut_pct"], -16.7)
        self.assertEqual(plan["revenue_lift_pct"], 20.0)
        self.assertEqual(plan["breakeven_revenue"], 600.0)

        df = pd.DataFrame({
            "product": ["Free", "Core"],
            "department": ["Support", "Product"],
            "category": ["Services", "Software"],
            "region": ["South", "North"],
            "revenue": [100.0, 900.0],
            "expense": [95.0, 400.0],
            "cost": [10.0, 150.0],
        })
        opps = segment_opportunities(df, margin_threshold=15.0)
        self.assertTrue(len(opps) > 0)
        self.assertEqual(opps[0]["impact"], 50.0)
        self.assertEqual(opps[0]["opportunity"], "Scale high-margin volume (+10%)")
        self.assertTrue(any(o["segment"] == "Free" and "15.0%" in o["opportunity"] for o in opps))

    def test_zero_revenue_dimension_margin_is_none(self):
        df = pd.DataFrame({
            "product": ["Free", "Paid"],
            "revenue": [0.0, 100.0],
            "expense": [50.0, 40.0],
            "cost": [0.0, 20.0],
        })
        rows = {r["product"]: r for r in by_dimension(df, "product")}
        self.assertIsNone(rows["Free"]["margin"])
        self.assertEqual(rows["Paid"]["margin"], 60.0)

    def test_anomalies_handles_nan_category(self):
        df = pd.DataFrame({
            "txn_date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01", "2024-05-01"]),
            "category": ["Ops", "Ops", "Ops", "Ops", float("nan")],
            "revenue": [100.0, 105.0, 102.0, 98.0, 101.0],
            "expense": [50.0, 52.0, 49.0, 51.0, 500.0],
        })
        flags = detect_anomalies(df)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["entity"], "Uncategorized")
        self.assertIn("threshold", flags[0])

    def test_intelligence_narratives_cover_what_happened_and_could_happen(self):
        df = pd.DataFrame({
            "txn_date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01", "2024-05-01"]),
            "product": ["Core", "Core", "Addon", "Core", "Addon"],
            "department": ["Sales", "Sales", "Support", "Sales", "Support"],
            "category": ["Software", "Software", "Services", "Software", "Services"],
            "region": ["North", "North", "South", "North", "South"],
            "revenue": [1000.0, 1100.0, 300.0, 1200.0, 400.0],
            "expense": [400.0, 440.0, 290.0, 450.0, 950.0],
            "cost": [200.0, 220.0, 100.0, 230.0, 120.0],
            "investment": [100.0, 0.0, 0.0, 0.0, 0.0],
        })
        m_df = monthly(df)
        s_rows = m_df.assign(period=m_df.period.dt.strftime("%Y-%m")).to_dict("records")
        ov = overview_narrative(df, s_rows, 15.0, "INR")
        self.assertEqual([p["step"] for p in ov["pillars"]], ["01 · What it is", "02 · What happened", "03 · What could have happened"])

        prod_rows = by_dimension(df, "product")
        dim_b = dimension_narrative(df, "product", prod_rows, 15.0, "INR")
        self.assertIn("Core", dim_b["pillars"][1]["headline"])

        flags = detect_anomalies(df, 1.5)
        anom_b = anomalies_narrative(df, flags, 1.5, "INR")
        self.assertIn("outlier", anom_b["pillars"][1]["headline"].lower())

        fc = forecast(df, "revenue", 3)
        fc_b = forecast_narrative(fc, "revenue", 3, "INR")
        self.assertEqual(fc_b["pillars"][2]["step"], "03 · What could happen")


class ImporterTests(unittest.TestCase):
    def test_normalize_and_quality_report_handle_missing_ids(self):
        frame = pd.DataFrame({
            "Sales Date": ["2024-01-05", "bad-date", "2024-02-10"],
            "Sales": [500, 300, 700],
            "Expense": [200, 100, -5],
            "Transaction ID": [None, None, "TX-3"],
        })
        mapping = detect(frame.columns)
        report = quality_report(frame, mapping)
        self.assertEqual(report["duplicate_ids"], 0)
        self.assertEqual(report["invalid_dates"], 1)
        cleaned, excluded = normalize(frame, mapping)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(excluded, 2)
        self.assertIsNone(cleaned.iloc[0]["transaction_id"])


class AuthPersistenceTests(IsolatedDBTestCase):
    def test_load_or_create_secret_key_persists_across_calls(self):
        secret_path = Path(self._tmpdir.name) / ".flask_secret"
        first = config.load_or_create_secret_key(secret_path)
        second = config.load_or_create_secret_key(secret_path)
        self.assertEqual(first, second)
        self.assertTrue(secret_path.exists())
        self.assertTrue(len(first) >= 20)

    def test_register_page_clears_stale_user_session(self):
        conn = connect()
        try:
            user_id = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                ("Stale User", "stale@example.com", "hash", "user", "2026-01-01T00:00:00"),
            ).lastrowid
            conn.commit()
        finally:
            conn.close()

        client = app.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
        response = client.get("/register")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Create your account", response.data)
        with client.session_transaction() as session:
            self.assertNotIn("user_id", session)


class EndToEndWorkflowTests(IsolatedDBTestCase):
    def _register_and_import_csv(self, client, email="alice@example.com", csv_bytes=None):
        resp = client.post(
            "/register",
            data={"name": "Alice", "email": email, "password": "strongpassword123"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        if csv_bytes is None:
            csv_bytes = (
                b"Date,Product,Department,Category,Region,Revenue,Expense,Cost,Investment\n"
                b"2024-01-10,Core,Engineering,Software,North,1000,400,200,100\n"
                b"2024-02-10,Core,Engineering,Software,North,1200,450,220,0\n"
                b"2024-03-10,FreeTier,Support,Services,South,0,100,0,0\n"
                b"2024-04-10,Core,Engineering,Software,North,1400,500,250,0\n"
                b"2024-05-10,Core,Engineering,Software,North,1600,1800,300,0\n"
            )
        preview = client.post(
            "/user/data",
            data={"file": (io.BytesIO(csv_bytes), "sample.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(preview.status_code, 200)
        self.assertIn(b"Detected column mapping", preview.data)
        confirm = client.post("/user/data", data={"confirm": "1"}, follow_redirects=True)
        self.assertEqual(confirm.status_code, 200)
        self.assertIn(b"imported successfully", confirm.data)

    def test_full_user_workflow_and_isolation(self):
        alice = app.app.test_client()
        self._register_and_import_csv(alice, "alice@example.com")

        # Dashboard and date-range empty-result state keep filter visible
        dash = alice.get("/user/dashboard")
        self.assertEqual(dash.status_code, 200)
        self.assertIn(b"5,200.00", dash.data)
        empty_range = alice.get("/user/dashboard?start=2025-01-01&end=2025-02-01")
        self.assertEqual(empty_range.status_code, 200)
        self.assertIn(b"No matching transactions", empty_range.data)
        self.assertIn(b"Clear date filter", empty_range.data)

        # Analysis views never render literal 'nan' for zero-revenue margin
        products = alice.get("/user/analytics/products")
        self.assertEqual(products.status_code, 200)
        self.assertNotIn(b">nan<", products.data.lower())
        regions = alice.get("/user/analytics/regions")
        self.assertEqual(regions.status_code, 200)
        self.assertIn(b"North", regions.data)

        # Forecasting & optimization scenario history
        fc = alice.get("/user/forecasting?target=profit&horizon=6")
        self.assertEqual(fc.status_code, 200)
        self.assertIn(b"Linear trend regression", fc.data)

        opt = alice.post(
            "/user/optimization",
            data={"name": "Cut Costs", "revenue_change": "5", "expense_change": "-10"},
            follow_redirects=True,
        )
        self.assertEqual(opt.status_code, 200)
        self.assertIn(b"Saved scenarios", opt.data)
        self.assertIn(b"Cut Costs", opt.data)

        # CSV and PDF exports
        csv_resp = alice.get("/user/export.csv")
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn(b"Core", csv_resp.data)
        pdf_resp = alice.get("/user/report.pdf")
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertTrue(pdf_resp.data.startswith(b"%PDF"))

        # JSON upload works consistently with config.ALLOWED_EXTENSIONS
        json_payload = json.dumps([
            {"Date": "2024-06-10", "Product": "Addon", "Revenue": 800, "Expense": 300}
        ]).encode("utf-8")
        jprev = alice.post(
            "/user/data",
            data={"file": (io.BytesIO(json_payload), "more.json")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(jprev.status_code, 200)
        self.assertIn(b"Detected column mapping", jprev.data)
        jconf = alice.post("/user/data", data={"confirm": "1"}, follow_redirects=True)
        self.assertIn(b"1 rows imported successfully", jconf.data)

        # Second user workspace is isolated and cannot access /admin
        bob = app.app.test_client()
        bob.post(
            "/register",
            data={"name": "Bob", "email": "bob@example.com", "password": "strongpassword123"},
            follow_redirects=True,
        )
        bob_dash = bob.get("/user/dashboard")
        self.assertIn(b"No financial data has been imported yet", bob_dash.data)
        self.assertEqual(bob.get("/admin/dashboard").status_code, 403)

    def test_admin_user_counts_do_not_multiply_across_imports(self):
        user_client = app.app.test_client()
        self._register_and_import_csv(user_client, "multi@example.com")
        # Second import into same workspace
        csv2 = b"Date,Revenue,Expense\n2024-07-01,200,100\n2024-07-02,300,150\n"
        user_client.post(
            "/user/data",
            data={"file": (io.BytesIO(csv2), "second.csv")},
            content_type="multipart/form-data",
        )
        user_client.post("/user/data", data={"confirm": "1"})

        # Create admin user and sign in
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                ("Admin", "admin@test.local", generate_password_hash("adminpass123", method="pbkdf2:sha256"), "admin", "2026-01-01T00:00:00"),
            )
            conn.commit()
        finally:
            conn.close()

        admin_client = app.app.test_client()
        admin_client.post("/admin/login", data={"email": "admin@test.local", "password": "adminpass123"})
        users_page = admin_client.get("/admin/users")
        self.assertEqual(users_page.status_code, 200)
        # 2 datasets and 7 total records (not 2*7 = 14)
        self.assertIn(b"<td>2</td><td>7</td>", users_page.data.replace(b"\r", b"").replace(b"\n", b"").replace(b" ", b""))

        # Admin settings validation rejects bad values and persists valid ones
        bad_settings = admin_client.post(
            "/admin/settings",
            data={"currency": "USD", "margin_threshold": "abc", "anomaly_threshold": "1.5", "forecast_period": "6", "date_format": "%Y-%m-%d"},
            follow_redirects=True,
        )
        self.assertIn(b"Enter valid numeric settings", bad_settings.data)
        good_settings = admin_client.post(
            "/admin/settings",
            data={"currency": "USD", "margin_threshold": "12.5", "anomaly_threshold": "2.0", "forecast_period": "9", "date_format": "%Y-%m-%d"},
            follow_redirects=True,
        )
        self.assertIn(b"System settings saved.", good_settings.data)

    def test_xlsx_upload_and_portal_switch(self):
        client = app.app.test_client()
        client.post(
            "/register",
            data={"name": "Carol", "email": "carol@example.com", "password": "strongpassword123"},
            follow_redirects=True,
        )
        buf = io.BytesIO()
        pd.DataFrame([{"Date": "2024-01-15", "Product": "Suite", "Revenue": 2500, "Expense": 900}]).to_excel(buf, index=False)
        buf.seek(0)
        prev = client.post(
            "/user/data",
            data={"file": (buf, "report.xlsx")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(prev.status_code, 200)
        self.assertIn(b"Detected column mapping", prev.data)
        conf = client.post("/user/data", data={"confirm": "1"}, follow_redirects=True)
        self.assertIn(b"1 rows imported successfully", conf.data)

        # Visiting /admin/login while signed in as a user clears the user session
        admin_page = client.get("/admin/login")
        self.assertEqual(admin_page.status_code, 200)
        self.assertIn(b"Administrator sign in", admin_page.data)
        with client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_all_portal_routes_and_static_assets_render_cleanly(self):
        # Verify public routes, health endpoint, exact title & offline static design system assets
        anon = app.app.test_client()
        for path in ("/", "/register", "/login", "/admin/login", "/health", "/static/css/app.css", "/static/css/portal.css", "/static/css/forecast.css", "/static/js/ui.js", "/static/js/chart.umd.min.js", "/static/favicon.svg"):
            with anon.get(path) as res:
                self.assertEqual(res.status_code, 200, f"Failed GET {path}")

        with anon.get("/health") as health_res:
            payload = health_res.get_json()
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["title"], config.APP_TITLE)

        with anon.get("/") as landing:
            self.assertIn(b"Financial clarity, computed locally.", landing.data)
            self.assertIn(config.APP_TITLE.encode("utf-8"), landing.data)
            self.assertIn(b"canvas-skeleton", landing.data)
            self.assertNotIn(b"eyebrow", landing.data)

        # Register user, import CSV, verify all analytical routes
        user_client = app.app.test_client()
        self._register_and_import_csv(user_client, "routes@example.com")
        for path in (
            "/user/dashboard",
            "/user/analytics/overview",
            "/user/analytics/products",
            "/user/analytics/departments",
            "/user/analytics/categories",
            "/user/analytics/regions",
            "/user/analytics/anomalies",
            "/user/forecasting",
            "/user/optimization",
            "/user/optimization?target_margin=75",
            "/user/data",
        ):
            with user_client.get(path) as res:
                self.assertEqual(res.status_code, 200, f"Failed GET {path}")
                self.assertIn(b"ui.js", res.data)
                self.assertNotIn(b"cdn.jsdelivr.net", res.data)
                if path.startswith("/user/analytics/"):
                    self.assertIn(b"01 \xc2\xb7 What it is", res.data)
                    self.assertIn(b"02 \xc2\xb7 What happened", res.data)

        # Admin routes including audit trail & user suspension governance
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                ("Admin2", "admin2@test.local", generate_password_hash("adminpass123", method="pbkdf2:sha256"), "admin", "2026-01-01T00:00:00"),
            )
            conn.commit()
            route_user_id = conn.execute("SELECT id FROM users WHERE email='routes@example.com'").fetchone()["id"]
        finally:
            conn.close()
        admin_client = app.app.test_client()
        admin_client.post("/admin/login", data={"email": "admin2@test.local", "password": "adminpass123"})
        for path in ("/admin/dashboard", "/admin/users", "/admin/datasets", "/admin/audit", "/admin/audit?category=imports", "/admin/settings"):
            with admin_client.get(path) as res:
                self.assertEqual(res.status_code, 200, f"Failed GET {path}")
                self.assertIn(config.APP_TITLE.encode("utf-8"), res.data)

        # Suspend user -> blocks login -> reactivate user -> restores login
        with admin_client.post(f"/admin/users/{route_user_id}/status", follow_redirects=True) as suspend_res:
            self.assertEqual(suspend_res.status_code, 200)
            self.assertIn(b"suspended", suspend_res.data)
        suspended_login = app.app.test_client().post(
            "/login",
            data={"email": "routes@example.com", "password": "strongpassword123"},
            follow_redirects=True,
        )
        self.assertIn(b"Invalid user email or password.", suspended_login.data)
        admin_client.post(f"/admin/users/{route_user_id}/status", follow_redirects=True)
        with admin_client.get("/admin/audit") as audit_res:
            self.assertIn(b"user status changed", audit_res.data)


class LauncherAndPackagingTests(IsolatedDBTestCase):
    def test_launcher_loopback_health_and_paths(self):
        import app_launcher

        self.assertEqual(app_launcher.normalize_start_path("", admin_mode=False), "/")
        self.assertEqual(app_launcher.normalize_start_path("", admin_mode=True), "/admin/login")
        self.assertEqual(
            app_launcher.resolve_remote_url("https://finance.example.com/", "/admin/login"),
            "https://finance.example.com/admin/login",
        )

        port = app_launcher.find_free_port("127.0.0.1")
        self.assertGreater(port, 0)
        srv = app_launcher.FlaskServerThread(app.app, "127.0.0.1", port)
        srv.start()
        try:
            ready = app_launcher.wait_for_server("127.0.0.1", port, expected_title=config.APP_TITLE, timeout_sec=8.0)
            self.assertTrue(ready)
        finally:
            srv.stop()

    def test_sample_fallback_writable_data_dir_and_icons_exist(self):
        from data.sample_data import generate

        orig_sample = config.SAMPLE_FOLDER
        orig_data = config.DATA_DIR
        try:
            config.DATA_DIR = Path(self._tmpdir.name) / "appdata"
            # Simulate unwritable bundle path across macOS, Linux, and Windows by nesting under a regular file
            blocker = Path(self._tmpdir.name) / "readonly_blocker"
            blocker.write_text("file", encoding="utf-8")
            config.SAMPLE_FOLDER = blocker / "sample_data"
            out_path = generate()
            self.assertTrue(out_path.exists())
            self.assertIn("appdata", str(out_path))
        finally:
            config.SAMPLE_FOLDER = orig_sample
            config.DATA_DIR = orig_data

        assets = config.BASE_DIR / "packaging" / "assets"
        for fname in ("icon_1024.png", "finance_pulse.icns", "finance_pulse.ico"):
            fpath = assets / fname
            self.assertTrue(fpath.exists(), f"Missing icon asset {fpath}")
            self.assertGreater(fpath.stat().st_size, 1024)


class SyncAndUpdaterTests(IsolatedDBTestCase):
    def setUp(self):
        super().setUp()
        self._orig_data_dir = config.DATA_DIR
        self._orig_manifest_url = config.UPDATE_MANIFEST_URL
        self._orig_default_sync = config.DEFAULT_SYNC_URL
        config.DATA_DIR = Path(self._tmpdir.name) / "appdata"
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.DEFAULT_SYNC_URL = ""
        import updater
        updater._SYNC_RUNTIME["tokens"].clear()
        updater._SYNC_RUNTIME["last_sync_at"] = ""
        updater._SYNC_RUNTIME["last_sync_ok"] = None
        updater._SYNC_RUNTIME["last_sync_error"] = ""

    def tearDown(self):
        config.DATA_DIR = self._orig_data_dir
        config.UPDATE_MANIFEST_URL = self._orig_manifest_url
        config.DEFAULT_SYNC_URL = self._orig_default_sync
        super().tearDown()

    def test_updater_semver_url_and_manifest_parsing(self):
        import updater

        self.assertEqual(updater.parse_semver("1.2.10+45"), (1, 2, 10))
        self.assertTrue(updater.is_update_available("1.1.0", 2, "1.1.0", 12))
        self.assertFalse(updater.is_update_available("1.1.0", 12, "1.1.0", 12))
        self.assertFalse(updater.is_update_available("1.2.0", 2, "1.1.0", 2))
        self.assertTrue(updater.is_update_available("1.1.0", 2, "1.2.0", None))

        self.assertEqual(updater.normalize_http_url("https://example.com/"), "https://example.com")
        self.assertEqual(updater.normalize_http_url("sync.example.com"), "https://sync.example.com")
        self.assertIsNone(updater.normalize_http_url("javascript:alert(1)"))
        self.assertIsNone(updater.normalize_http_url("file:///etc/passwd"))
        self.assertIsNone(updater.normalize_http_url("   "))

        self.assertTrue(updater._is_self_url("http://127.0.0.1:8000", 8000))
        self.assertFalse(updater._is_self_url("http://127.0.0.1:9000", 8000))

        parsed = updater.parse_manifest_dict({
            "version": "1.5.0",
            "build_number": 99,
            "sync_server_url": "https://hub.example.com/",
            "macos": {"version": "1.5.0", "build_number": 99, "url": "https://hub.example.com/mac.zip", "sha256": "ABCD"},
            "windows": {"version": "1.5.0", "build_number": 99, "url": "https://hub.example.com/win.zip", "sha256": "EF01"},
        })
        self.assertTrue(parsed["update_available"])
        self.assertEqual(parsed["sync_server_url"], "https://hub.example.com")
        self.assertEqual(parsed["latest_build"], 99)

        ok, norm = updater.set_sync_override("http://192.168.1.55:8000/")
        self.assertTrue(ok)
        self.assertEqual(norm, "http://192.168.1.55:8000")
        self.assertEqual(updater.get_sync_config()["mode"], "Manual override")
        ok_bad, _ = updater.set_sync_override("javascript:alert(1)")
        self.assertFalse(ok_bad)
        updater.set_sync_override("")
        self.assertEqual(updater.get_sync_config()["mode"], "Offline local")

    def test_update_check_over_http_populates_manifest_sync_and_state(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import updater

        payload = {
            "version": "9.9.0",
            "build_number": 999,
            "sync_server_url": "https://sync.financepulse.example",
            "macos": {"version": "9.9.0", "build_number": 999, "url": "https://sync.financepulse.example/mac.zip", "sha256": "00" * 32},
            "windows": {"version": "9.9.0", "build_number": 999, "url": "https://sync.financepulse.example/win.zip", "sha256": "00" * 32},
        }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        srv = HTTPServer(("127.0.0.1", 0), Handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            config.UPDATE_MANIFEST_URL = f"http://127.0.0.1:{srv.server_port}/version.json"
            status = updater.check_for_updates(timeout=3.0)
            self.assertTrue(status["checked"])
            self.assertEqual(status["error"], "")
            self.assertTrue(status["update_available"])
            self.assertEqual(status["latest_build"], 999)
            self.assertEqual(updater.get_sync_config()["effective_url"], "https://sync.financepulse.example")
            self.assertEqual(updater.get_sync_config()["mode"], "Automatic manifest")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_download_desktop_update_refreshes_stale_cached_sha(self):
        import hashlib
        from unittest.mock import patch
        import updater

        archive_bytes = b"PK\x03\x04finance-pulse-v120-archive-payload"
        fresh_sha = hashlib.sha256(archive_bytes).hexdigest()
        stale_sha = "8ce256abafa9" + "0" * 52

        dl_dir = Path(self._tmpdir.name) / "dl"
        dl_dir.mkdir(parents=True, exist_ok=True)
        config.UPDATE_MANIFEST_URL = "https://updates.example.test/version.json"

        with updater._STATE_LOCK:
            updater._UPDATE_CACHE["download_url"] = "https://updates.example.test/pkg.zip"
            updater._UPDATE_CACHE["sha256"] = stale_sha
            updater._UPDATE_CACHE["asset_name"] = "pkg.zip"

        fresh_manifest = json.dumps({
            "version": "1.2.0",
            "build_number": 999,
            "macos": {
                "version": "1.2.0",
                "build_number": 999,
                "url": "https://updates.example.test/pkg.zip",
                "sha256": fresh_sha,
            },
            "windows": {
                "version": "1.2.0",
                "build_number": 999,
                "url": "https://updates.example.test/pkg.zip",
                "sha256": fresh_sha,
            },
            "linux": {
                "version": "1.2.0",
                "build_number": 999,
                "url": "https://updates.example.test/pkg.zip",
                "sha256": fresh_sha,
            },
        }).encode("utf-8")

        class FakeResp:
            def __init__(self, body: bytes):
                self._bio = io.BytesIO(body)
                self.status = 200

            def read(self, n=-1):
                return self._bio.read(n)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.endswith("version.json"):
                return FakeResp(fresh_manifest)
            return FakeResp(archive_bytes)

        with patch.object(updater, "_download_dir", return_value=dl_dir), patch(
            "urllib.request.urlopen", side_effect=fake_urlopen
        ):
            res = updater.download_desktop_update()

        self.assertEqual(res["download_status"], "ready")
        self.assertEqual(res["download_error"], "")
        self.assertTrue(Path(res["download_path"]).is_file())

    def test_sync_api_auth_import_dedup_and_admin_visibility(self):
        client = app.app.test_client()

        # CORS preflight on /api/v1/auth/register & /health
        opt = client.options("/api/v1/auth/register")
        self.assertEqual(opt.status_code, 204)
        self.assertEqual(opt.headers.get("Access-Control-Allow-Origin"), "*")

        # Register validation & creation
        bad_reg = client.post("/api/v1/auth/register", json={"name": "A", "email": "bad", "password": "123"})
        self.assertEqual(bad_reg.status_code, 400)

        reg = client.post(
            "/api/v1/auth/register",
            json={"name": "Mobile Mia", "email": "mia@example.com", "password": "secret12", "platform": "android"},
        )
        self.assertEqual(reg.status_code, 201)
        reg_json = reg.get_json()
        self.assertTrue(reg_json["ok"])
        token = reg_json["token"]

        # Idempotent re-register with matching password returns 200; mismatch returns 409
        re_reg = client.post(
            "/api/v1/auth/register",
            json={"name": "Mobile Mia", "email": "mia@example.com", "password": "secret12", "platform": "android"},
        )
        self.assertEqual(re_reg.status_code, 200)
        conflict = client.post(
            "/api/v1/auth/register",
            json={"name": "Mobile Mia", "email": "mia@example.com", "password": "wrongpassword", "platform": "android"},
        )
        self.assertEqual(conflict.status_code, 409)

        # Login & tampered token rejection
        login_res = client.post("/api/v1/auth/login", json={"email": "mia@example.com", "password": "secret12"})
        self.assertEqual(login_res.status_code, 200)
        self.assertEqual(client.get("/api/v1/sync/status").status_code, 401)
        self.assertEqual(
            client.get("/api/v1/sync/status", headers={"Authorization": "Bearer tampered.token.val"}).status_code,
            401,
        )

        # Sync import using Android txn_date payload & idempotency dedup
        sample_rows = [
            {
                "txn_date": "2025-01-10",
                "product": "Insight Pro",
                "department": "Engineering",
                "category": "SaaS",
                "region": "North",
                "revenue": 2500.0,
                "expense": 900.0,
                "cost": 300.0,
                "investment": 50.0,
            },
            {
                "txn_date": "2025-02-10",
                "product": "Core Suite",
                "department": "Sales",
                "category": "Enterprise",
                "region": "West",
                "revenue": 1500.0,
                "expense": 600.0,
                "cost": 200.0,
                "investment": 0.0,
            },
        ]
        imp1 = client.post(
            "/api/v1/sync/import",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "filename": "android_ledger.csv",
                "client_import_id": "mob-dedup-001",
                "platform": "android",
                "rows": sample_rows,
            },
        )
        self.assertEqual(imp1.status_code, 201)
        self.assertEqual(imp1.get_json()["rows_imported"], 2)

        # Second identical POST with same client_import_id must deduplicate
        imp2 = client.post(
            "/api/v1/sync/import",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "filename": "android_ledger.csv",
                "client_import_id": "mob-dedup-001",
                "platform": "android",
                "rows": sample_rows,
            },
        )
        self.assertEqual(imp2.status_code, 200)
        self.assertTrue(imp2.get_json()["duplicate"])

        st = client.get("/api/v1/sync/status", headers={"Authorization": f"Bearer {token}"}).get_json()
        self.assertEqual(st["datasets"], 1)
        self.assertEqual(st["records"], 2)

        # Create admin via loopback /admin/setup & verify admin portal shows synced mobile records
        self.assertIn(b"Set up administrator account", client.get("/admin/login").data)
        setup_res = client.post(
            "/admin/setup",
            data={"name": "Owner Admin", "email": "owner@financepulse.local", "password": "ownerpassword123"},
            follow_redirects=True,
        )
        self.assertEqual(setup_res.status_code, 200)
        self.assertIn(b"Admin Portal", setup_res.data)
        self.assertIn(b"Mobile Mia", client.get("/admin/users").data)
        self.assertIn(b"android_ledger.csv", client.get("/admin/datasets").data)

        # Once admin exists, /admin/setup is permanently locked (403)
        self.assertEqual(client.get("/admin/setup").status_code, 403)
        self.assertEqual(
            client.post("/admin/setup", data={"name": "X", "email": "x@x.com", "password": "password123"}).status_code,
            403,
        )

    def test_security_boundaries_loopback_vs_proxied_and_operator_sync(self):
        client = app.app.test_client()

        # Simulate external proxied visitor (e.g. cloudflared tunnel) trying first-time /admin/setup -> must be 403
        proxied_setup = client.get("/admin/setup", headers={"X-Forwarded-For": "203.0.113.5"})
        self.assertEqual(proxied_setup.status_code, 403)
        cf_setup = client.get("/admin/setup", headers={"CF-Connecting-IP": "198.51.100.2"})
        self.assertEqual(cf_setup.status_code, 403)

        # Simulated remote unauthenticated visitor cannot access /api/system/operator-sync -> 403
        remote_op = client.get("/api/system/operator-sync", environ_base={"REMOTE_ADDR": "198.51.100.7"})
        self.assertEqual(remote_op.status_code, 403)
        proxied_op = client.post(
            "/api/system/operator-sync",
            headers={"X-Forwarded-For": "198.51.100.7"},
            json={"action": "save_override", "url": "https://evil.example"},
        )
        self.assertEqual(proxied_op.status_code, 403)

        # Genuine local operator on loopback CAN read/save/clear sync override
        op_get = client.get("/api/system/operator-sync")
        self.assertEqual(op_get.status_code, 200)
        self.assertTrue(op_get.get_json()["ok"])

        bad_op = client.post("/api/system/operator-sync", json={"action": "save_override", "url": "javascript:1"})
        self.assertEqual(bad_op.status_code, 400)

        save_op = client.post(
            "/api/system/operator-sync",
            json={"action": "save_override", "url": "https://central.financepulse.local"},
        )
        self.assertEqual(save_op.status_code, 200)
        self.assertEqual(save_op.get_json()["override_url"], "https://central.financepulse.local")

        clear_op = client.post("/api/system/operator-sync", json={"action": "clear_override"})
        self.assertEqual(clear_op.status_code, 200)
        self.assertEqual(clear_op.get_json()["override_url"], "")

    def test_end_to_end_mirror_sync_across_live_http_server(self):
        import time
        import app_launcher
        import updater

        port = app_launcher.find_free_port("127.0.0.1")
        srv = app_launcher.FlaskServerThread(app.app, "127.0.0.1", port)
        srv.start()
        try:
            self.assertTrue(app_launcher.wait_for_server("127.0.0.1", port, expected_title=config.APP_TITLE, timeout_sec=8.0))
            base_url = f"http://127.0.0.1:{port}"
            ok, _ = updater.set_sync_override(base_url)
            self.assertTrue(ok)

            # Mirror signup + immediate dataset queue concurrently (no race condition)
            updater.mirror_auth_event("register", "Mirror User", "mirror@example.com", "strongpass123")
            updater.mirror_dataset_import(
                "mirror@example.com",
                "desktop_sync.csv",
                "desk-sync-e2e-001",
                [{
                    "date": "2025-05-01",
                    "product": "Enterprise",
                    "department": "Finance",
                    "category": "SaaS",
                    "region": "APAC",
                    "revenue": 4200.0,
                    "expense": 1200.0,
                    "cost": 400.0,
                    "investment": 100.0,
                }],
            )

            deadline = time.time() + 6.0
            records_cnt = 0
            while time.time() < deadline:
                updater.flush_sync_outbox()
                conn = connect()
                try:
                    records_cnt = conn.execute("SELECT COUNT(*) FROM financial_transactions").fetchone()[0]
                finally:
                    conn.close()
                if records_cnt == 1 and updater.get_sync_config()["queue_count"] == 0:
                    break
                time.sleep(0.15)

            self.assertEqual(records_cnt, 1)
            self.assertEqual(updater.get_sync_config()["queue_count"], 0)
            self.assertTrue((config.DATA_DIR / "sync_tokens.json").is_file())
        finally:
            srv.stop()


if __name__ == "__main__":
    unittest.main()
