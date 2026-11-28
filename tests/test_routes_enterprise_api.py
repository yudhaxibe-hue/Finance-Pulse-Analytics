"""End-to-end Flask route, security, offline API, and enterprise sample tests for v1.2.0."""
from __future__ import annotations

import io
import zipfile

from PIL import Image, ImageDraw
import pytest
from werkzeug.security import generate_password_hash

import app
from database.db import connect


def _register_user(client, name="Enterprise User", email="ent@example.com", password="strongpassword123"):
    resp = client.post(
        "/register",
        data={"name": name, "email": email, "password": password},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    return client


def _make_admin_client(email="secadmin@test.local", password="adminpassword123"):
    conn = connect()
    try:
        if not conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                ("Admin", email, generate_password_hash(password, method="pbkdf2:sha256"), "admin", "2026-01-01T00:00:00"),
            )
            conn.commit()
    finally:
        conn.close()
    admin = app.app.test_client()
    admin.post("/admin/login", data={"email": email, "password": password}, follow_redirects=True)
    return admin


class TestEnterpriseRoutesAndQuickEntry:
    def test_load_10k_enterprise_sample_route_and_filters(self, isolated_env):
        c = _register_user(app.app.test_client())
        res = c.post("/user/load-enterprise-sample", follow_redirects=True)
        assert res.status_code == 200
        assert b"10,000 enterprise transactions" in res.data

        dash = c.get("/user/dashboard")
        assert dash.status_code == 200
        assert b"Random Forest risk" in dash.data
        assert b"cash-flow runway" in dash.data.lower()

        filtered = c.get("/user/dashboard?year=2025&region=North")
        assert filtered.status_code == 200
        assert b"2025" in filtered.data

    def test_manual_transaction_entry_income_expense_and_validation(self, isolated_env):
        c = _register_user(app.app.test_client())

        # Valid income
        r1 = c.post(
            "/user/transaction",
            data={
                "txn_date": "2026-04-10",
                "flow_type": "income",
                "amount": "25000",
                "category": "Services",
                "product": "Retainer",
                "department": "Advisory",
                "region": "South",
                "vendor_name": "Acme Corp",
            },
            follow_redirects=True,
        )
        assert r1.status_code == 200
        assert b"Transaction added and scored via Random Forest" in r1.data

        # Valid expense
        r2 = c.post(
            "/user/transaction",
            data={"txn_date": "2026-04-11", "flow_type": "expense", "amount": "9000", "category": "Operations"},
            follow_redirects=True,
        )
        assert r2.status_code == 200

        # Invalid zero/negative amount
        r_bad = c.post(
            "/user/transaction",
            data={"txn_date": "2026-04-12", "flow_type": "expense", "amount": "0"},
            follow_redirects=True,
        )
        assert b"positive transaction amount" in r_bad.data

        # Invalid date
        r_date = c.post(
            "/user/transaction",
            data={"txn_date": "not-a-date", "flow_type": "income", "amount": "100"},
            follow_redirects=True,
        )
        assert b"valid transaction date" in r_date.data

    def test_institutional_single_amount_csv_end_to_end(self, isolated_env):
        c = _register_user(app.app.test_client())
        csv_data = (
            b"Entry_ID,Date,Fiscal_Year,Type,Category,Course_or_Dept,Paid_to_or_Received_from,Payment_Mode,Total_Amount_INR\n"
            b"E-1,2024-01-10,2024,Income,Tuition Fees,Computer Science,Student Batch,UPI,200000\n"
            b"E-2,2024-02-10,2024,Expense,Faculty Salary,Computer Science,Prof Kumar,NEFT,85000\n"
            b"E-3,2024-03-10,2024,Income,Grants,Physics,State Board,Bank Transfer,120000\n"
            b"E-4,2024-04-10,2024,Expense,Lab Upgrade,Physics,LabTech,Cheque,40000\n"
            b"E-5,2024-05-10,2024,Income,Tuition Fees,Mathematics,Student Batch,UPI,150000\n"
            b"E-6,2024-06-10,2024,Expense,Faculty Salary,Mathematics,Prof Rao,NEFT,60000\n"
        )
        prev = c.post(
            "/user/data",
            data={"file": (io.BytesIO(csv_data), "college_audit.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert prev.status_code == 200
        conf = c.post("/user/data", data={"confirm": "1"}, follow_redirects=True)
        assert b"6 rows imported successfully" in conf.data

        dash = c.get("/user/dashboard")
        assert b"470,000.00" in dash.data

        fc_rf = c.get("/user/forecasting?target=profit&horizon=6&model=rf")
        assert fc_rf.status_code == 200
        assert b"Random Forest Regressor" in fc_rf.data

        fc_ols = c.get("/user/forecasting?target=profit&horizon=6&model=ols")
        assert fc_ols.status_code == 200
        assert b"Linear trend regression" in fc_ols.data


class TestReceiptScanConfirmAndExports:
    def test_receipt_scan_validation_and_png_pdf_confirm_workflow(self, isolated_env):
        c = _register_user(app.app.test_client())

        # Missing file or disallowed extension -> 400 JSON
        no_file = c.post("/user/receipt-scan", data={}, headers={"Accept": "application/json"})
        assert no_file.status_code == 400

        bad_ext = c.post(
            "/user/receipt-scan",
            data={"document": (io.BytesIO(b"mz"), "bad.exe")},
            content_type="multipart/form-data",
            headers={"Accept": "application/json"},
        )
        assert bad_ext.status_code == 400

        # Valid PDF receipt scan
        from reportlab.pdfgen import canvas as pdf_canvas

        buf = io.BytesIO()
        cv = pdf_canvas.Canvas(buf)
        cv.drawString(72, 720, "Cloud Hosting Invoice")
        cv.drawString(72, 700, "Date: 2026-07-09")
        cv.drawString(72, 680, "Grand Total: INR 3400.00")
        cv.save()
        buf.seek(0)

        scan_res = c.post(
            "/user/receipt-scan",
            data={"document": (buf, "cloud_bill.pdf")},
            content_type="multipart/form-data",
            headers={"Accept": "application/json"},
        )
        assert scan_res.status_code == 200
        payload = scan_res.get_json()
        assert payload["ok"] is True
        assert payload["data"]["expense"] == pytest.approx(3400.0)
        assert payload["data"]["txn_date"] == "2026-07-09"

        # Valid PNG receipt scan
        img = Image.new("RGB", (320, 140), "white")
        ImageDraw.Draw(img).text((20, 40), "Total: INR 500", fill="black")
        ibuf = io.BytesIO()
        img.save(ibuf, format="PNG")
        ibuf.seek(0)
        png_res = c.post(
            "/user/receipt-scan",
            data={"document": (ibuf, "bill.png")},
            content_type="multipart/form-data",
            headers={"Accept": "application/json"},
        )
        assert png_res.status_code == 200
        assert png_res.get_json()["ok"] is True

        # Confirm scanned receipt into SQLite ledger
        conf = c.post(
            "/user/receipt-confirm",
            data={
                "date": "2026-07-09",
                "transaction_type": "Expense",
                "expense": "3400",
                "category": "Software",
                "product": "Cloud Hosting",
                "department": "Engineering",
                "vendor_name": "Cloud Vendor",
                "payment_method": "Corporate Card",
                "notes": "Verified scanned invoice",
            },
            follow_redirects=True,
        )
        assert conf.status_code == 200
        assert b"Receipt transaction confirmed" in conf.data

    def test_charts_pack_powerbi_kit_multipage_pdf_and_pii_masked_csv(self, isolated_env):
        c = _register_user(app.app.test_client())
        c.post("/user/load-enterprise-sample", follow_redirects=True)

        # Charts pack zip
        czip = c.get("/user/charts-pack.zip")
        assert czip.status_code == 200
        with zipfile.ZipFile(io.BytesIO(czip.data), "r") as zf:
            assert "01_monthly_cashflow.png" in zf.namelist()
            assert "04_random_forest_risk_audit.png" in zf.namelist()

        # Power BI Kit zip
        pzip = c.get("/user/powerbi-kit.zip")
        assert pzip.status_code == 200
        with zipfile.ZipFile(io.BytesIO(pzip.data), "r") as zf:
            assert {"powerbi_transactions.csv", "finance_pulse_powerquery.pq", "finance_pulse_measures.dax"}.issubset(zf.namelist())

        # Multi-page PDF report
        pdf = c.get("/user/report.pdf")
        assert pdf.status_code == 200
        assert pdf.data.startswith(b"%PDF")
        assert len(pdf.data) > 5000

        # Add PII entry & verify /user/export.csv masks PII when pii_masking=1
        c.post(
            "/user/transaction",
            data={
                "txn_date": "2026-08-01",
                "flow_type": "expense",
                "amount": "1200",
                "vendor_name": "secret.person@private.org",
                "notes": "PAN ABCDE1234F",
            },
        )
        csv_exp = c.get("/user/export.csv")
        assert csv_exp.status_code == 200
        assert b"secret.person@private.org" not in csv_exp.data
        assert b"ABCDE1234F" not in csv_exp.data


class TestCopilotEndpointsPowerBiApiAndAdminBackups:
    def test_session_copilot_api_and_mobile_bearer_apis(self, isolated_env):
        c = _register_user(app.app.test_client())

        # Empty question rejected 400
        assert c.post("/api/copilot/ask", json={"question": "   "}).status_code == 400

        # Personal budget question works out of the box
        ask_pers = c.post(
            "/api/copilot/ask",
            json={"question": "I earn 30k salary, spend 22k, save 8k — what should I do?", "language": "en"},
        )
        assert ask_pers.status_code == 200
        assert ask_pers.get_json()["tool"] == "personal_cashflow_advisor"

        # Mobile Bearer Token API authentication enforcement
        assert app.app.test_client().post("/api/v1/copilot/ask", json={"question": "summary"}).status_code == 401
        assert app.app.test_client().get("/api/v1/powerbi/feed").status_code == 401

        reg = app.app.test_client().post(
            "/api/v1/auth/register",
            json={"name": "API User", "email": "api@example.com", "password": "strongpassword123"},
        )
        token = reg.get_json()["token"]
        api_ask = app.app.test_client().post(
            "/api/v1/copilot/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "30k salary spend 22k save 8k risk?"},
        )
        assert api_ask.status_code == 200
        assert api_ask.get_json()["ok"] is True

        feed = app.app.test_client().get(
            "/api/v1/powerbi/feed?limit=10",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert feed.status_code == 200
        assert feed.get_json()["schema"] == "finance_pulse_powerbi_v1"

    def test_admin_backups_rbac_create_download_and_traversal_block(self, isolated_env):
        user = _register_user(app.app.test_client())
        assert user.get("/admin/backups").status_code == 403
        assert user.post("/admin/backups").status_code == 403

        admin = _make_admin_client()
        page = admin.get("/admin/backups")
        assert page.status_code == 200
        assert b"Database backups" in page.data

        created = admin.post("/admin/backups", data={"label": "audit_snapshot"}, follow_redirects=True)
        assert created.status_code == 200
        assert b"Verified SQLite backup" in created.data

        from database.db import list_backups

        bk = list_backups(limit=1)[0]
        dl = admin.get(f"/admin/backups/download/{bk['filename']}")
        assert dl.status_code == 200
        assert dl.data.startswith(b"SQLite format 3")

        # Traversal or non-matching filename returns 404
        assert admin.get("/admin/backups/download/..%2F..%2Fetc%2Fpasswd").status_code == 404
        assert admin.get("/admin/backups/download/invalid_name.txt").status_code == 404

    def test_account_availability_endpoint(self, isolated_env):
        c = app.app.test_client()

        # Empty email returns 400
        r_empty = c.get("/api/check-availability")
        assert r_empty.status_code == 400
        assert r_empty.get_json()["available"] is False

        # Malformed email
        r_invalid = c.get("/api/check-availability?email=notanemail")
        assert r_invalid.status_code == 200
        assert r_invalid.get_json()["status"] == "invalid"
        assert r_invalid.get_json()["available"] is False

        # Available email
        r_avail = c.get("/api/check-availability?email=unique_person@test.local")
        assert r_avail.status_code == 200
        assert r_avail.get_json()["status"] == "available"
        assert r_avail.get_json()["available"] is True

        # Register that email
        c.post(
            "/register",
            data={
                "name": "Unique User",
                "email": "unique_person@test.local",
                "password": "strongpassword123",
                "security_word": "quantum",
            },
            follow_redirects=True,
        )

        # Now it is taken
        r_taken = c.get("/api/check-availability?email=unique_person@test.local")
        assert r_taken.status_code == 200
        assert r_taken.get_json()["status"] == "taken"
        assert r_taken.get_json()["available"] is False

    def test_offline_security_word_password_recovery_flow(self, isolated_env):
        c = app.app.test_client()

        # 1. Register with a user-defined security recovery word
        email = "recover_me@test.local"
        reg = c.post(
            "/register",
            data={
                "name": "Recovery User",
                "email": email,
                "password": "old_password_123",
                "security_word": "BlueFalcon",
            },
            follow_redirects=True,
        )
        assert reg.status_code == 200

        # Log out
        c.get("/logout", follow_redirects=True)

        # 2. GET /forgot-password
        get_fp = c.get("/forgot-password")
        assert get_fp.status_code == 200
        assert b"Reset password offline" in get_fp.data

        # 3. Non-existent account
        r_none = c.post(
            "/forgot-password",
            data={
                "email": "unknown@test.local",
                "security_word": "BlueFalcon",
                "password": "new_password_123",
                "confirm_password": "new_password_123",
            },
            follow_redirects=True,
        )
        assert b"No active account found" in r_none.data

        # 4. Incorrect security word
        r_wrong_word = c.post(
            "/forgot-password",
            data={
                "email": email,
                "security_word": "WrongWord",
                "password": "new_password_123",
                "confirm_password": "new_password_123",
            },
            follow_redirects=True,
        )
        assert b"Incorrect security word" in r_wrong_word.data

        # 5. Mismatching confirmation password
        r_mismatch = c.post(
            "/forgot-password",
            data={
                "email": email,
                "security_word": "bluefalcon",
                "password": "new_password_123",
                "confirm_password": "different_pass_123",
            },
            follow_redirects=True,
        )
        assert b"confirmation do not match" in r_mismatch.data

        # 6. Correct security word & valid new password (case-insensitive recovery phrase)
        r_success = c.post(
            "/forgot-password",
            data={
                "email": email,
                "security_word": "bluefalcon",
                "password": "brand_new_secret_password_123",
                "confirm_password": "brand_new_secret_password_123",
            },
            follow_redirects=True,
        )
        assert r_success.status_code == 200
        assert b"password has been successfully reset" in r_success.data

        # 7. Old password no longer works
        old_login = c.post("/login", data={"email": email, "password": "old_password_123"}, follow_redirects=True)
        assert b"Invalid user email or password" in old_login.data

        # 8. New password logs in smoothly
        new_login = c.post("/login", data={"email": email, "password": "brand_new_secret_password_123"}, follow_redirects=True)
        assert new_login.status_code == 200
        assert b"Recovery User" in new_login.data or b"Dashboard" in new_login.data

    def test_admin_reset_user_password_and_security_status(self, isolated_env):
        user_c = _register_user(app.app.test_client(), email="managed@test.local")
        user_c.get("/logout")

        # Non-admin cannot invoke reset
        assert user_c.post("/admin/users/1/reset-password").status_code == 302

        admin = _make_admin_client()
        users_page = admin.get("/admin/users")
        assert users_page.status_code == 200
        assert b"Recovery" in users_page.data

        # Reset user password to temp password
        reset_res = admin.post("/admin/users/1/reset-password", follow_redirects=True)
        assert reset_res.status_code == 200
        assert b"ResetPass@2026" in reset_res.data

        # User logs in with ResetPass@2026
        login_res = app.app.test_client().post(
            "/login",
            data={"email": "ent@example.com", "password": "ResetPass@2026"},
            follow_redirects=True,
        )
        assert login_res.status_code == 200
        assert b"Dashboard" in login_res.data or b"Workspace" in login_res.data

    def test_three_pillar_and_chart_reporting_enhancements(self, isolated_env):
        c = _register_user(app.app.test_client())
        c.post("/user/load-enterprise-sample", follow_redirects=True)
        dash = c.get("/user/dashboard")
        assert dash.status_code == 200
        # 3-pillar unboxed classes and badges
        assert b"3-Pillar Decision Intelligence" in dash.data
        assert b"pillar-card" in dash.data
        # Enhanced Power BI surpassing controls
        assert b"Gross &amp; Net Profit/Loss" in dash.data
        assert b"btn-export-chart" in dash.data
        assert b"Cumulative Waterfall" in dash.data

    def test_receipt_discard_flow(self, isolated_env):
        c = _register_user(app.app.test_client())
        # Set dummy preview in session
        with c.session_transaction() as sess:
            sess["receipt_preview"] = {"filename": "test.png", "fields": {}}
        # Verify receipt preview exists
        with c.session_transaction() as sess:
            assert "receipt_preview" in sess
        # Discard receipt
        res = c.get("/user/receipt-discard", follow_redirects=True)
        assert res.status_code == 200
        # Verify session receipt_preview was cleared
        with c.session_transaction() as sess:
            assert "receipt_preview" not in sess

    def test_clear_workspace_and_replace_audit_switch_personal_to_hospital(self, isolated_env):
        c = _register_user(app.app.test_client())
        personal_csv = (
            b"Txn_ID,Date,Type,Category,Sub_Category,Description,Payee,Payment_Mode,Need_or_Want,Revenue_INR,Expenses_INR,Savings_INR\n"
            b"T1,2026-08-01,Income,Salary,Monthly Salary,Salary,Employer,Bank Transfer,Income,38000,0,0\n"
            b"T2,2026-08-02,Expense,Housing,PG Rent,PG rent,PG Owner,UPI,Need,0,7500,0\n"
            b"T3,2026-08-03,Expense,Food,Tea & Snacks,Tea + snacks,Tea Kadai,Cash,Want,0,60,0\n"
        )
        c.post("/user/data", data={"file": (io.BytesIO(personal_csv), "personal.csv"), "import_mode": "replace"}, content_type="multipart/form-data")
        c.post("/user/data", data={"confirm": "1", "import_mode": "replace"})
        d1 = c.get("/user/dashboard").data.decode("utf-8")
        assert "Audit Mode: Personal &amp; Household Ledger" in d1

        hospital_csv = (
            b"Date,Transaction_ID,Transaction_Type,Department,Product,Category,Region,Revenue,Expense,Cost,Payment_Method,Vendor_Name,Customer_Segment\n"
            b"2023-01-05,AIMS-0001,Revenue,Radiology & Imaging,MRI 3T Brain Scans,Diagnostic Services,Block A,779000,0,358340,Insurance Claim,N/A,Insurance Patients\n"
            b"2023-01-09,AIMS-0002,Revenue,MBBS & PG Medical College,MBBS Semester Fee,Tuition & Academic Fees,Campus,8550000,0,5985000,Bank Transfer,N/A,Medical Students\n"
            b"2023-01-27,AIMS-0004,Expense,Hospital Administration,Biomedical Waste Contract,Biomedical Waste Management,Wing B,0,62000,0,Bank Transfer,GreenLeaf,Internal Operations\n"
            b"2023-02-08,AIMS-0006,Revenue,MBBS & PG Medical College,PG Clinical Training Fee,Tuition & Academic Fees,Campus,6650000,0,4522000,Bank Transfer,N/A,PG Residents\n"
        )
        prev = c.post("/user/data", data={"file": (io.BytesIO(hospital_csv), "hospital.csv"), "import_mode": "replace"}, content_type="multipart/form-data", follow_redirects=True)
        prev_html = prev.data.decode("utf-8")
        assert "Audit type change detected" in prev_html
        c.post("/user/data", data={"confirm": "1", "import_mode": "replace"}, follow_redirects=True)
        d2 = c.get("/user/dashboard").data.decode("utf-8")
        assert "Audit Mode: Corporate P&amp;L" in d2
        assert "4 transactions" in d2

        clr = c.post("/user/data/clear", follow_redirects=True)
        assert clr.status_code == 200
        d3 = c.get("/user/dashboard").data.decode("utf-8")
        assert "No financial data has been imported yet" in d3
