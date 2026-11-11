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
