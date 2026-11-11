"""Tests for Matplotlib/Seaborn visuals, Power BI Ready Kit exports, and offline Photo/PDF Receipt OCR."""
from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest
from PIL import Image, ImageDraw

from analytics.forecasting import forecast
from analytics.powerbi import POWERBI_COLUMNS, build_powerbi_feed, build_powerbi_kit_zip, prepare_powerbi_dataframe
from analytics.receipt_ocr import extract_document_details, parse_receipt_text
from analytics.visuals import (
    build_charts_zip,
    render_forecast_png,
    render_monthly_cashflow_png,
    render_risk_distribution_png,
    render_segment_profit_png,
)


def _sample_df() -> pd.DataFrame:
    dates = pd.date_range("2025-01-10", periods=10, freq="MS")
    return pd.DataFrame({
        "txn_date": dates.strftime("%Y-%m-%d"),
        "transaction_id": [f"TX-{i+1}" for i in range(10)],
        "transaction_type": ["Sale"] * 10,
        "category": ["Software", "Consulting"] * 5,
        "product": ["Core Suite", "Advisory"] * 5,
        "department": ["Product", "Services"] * 5,
        "region": ["North", "South"] * 5,
        "vendor_name": ["Alice alice@secret.com" if i == 0 else f"Vendor {i}" for i in range(10)],
        "payment_method": ["UPI"] * 10,
        "revenue": [80000.0 + i * 3000.0 for i in range(10)],
        "expense": [42000.0 + i * 1000.0 for i in range(10)],
        "cost": [15000.0] * 10,
        "investment": [2000.0] * 10,
        "risk_tier": ["High Risk" if i == 9 else "Low Risk" for i in range(10)],
        "risk_score": [82.0 if i == 9 else 19.0 for i in range(10)],
        "predicted_category": ["Software", "Consulting"] * 5,
        "is_anomaly": [1 if i == 9 else 0 for i in range(10)],
        "notes": ["Call +91 9876543210 PAN ABCDE1234F" if i == 0 else "Standard entry" for i in range(10)],
    })


class TestVisualsCharts:
    def test_empty_df_renders_none_cleanly(self):
        empty = pd.DataFrame()
        assert render_monthly_cashflow_png(empty) is None
        assert render_segment_profit_png(empty) is None
        assert render_risk_distribution_png(empty) is None
        assert render_forecast_png({}) is None

    def test_render_individual_pngs_have_valid_png_signature(self):
        df = _sample_df()
        png_sig = b"\x89PNG\r\n\x1a\n"
        for img_bytes in (
            render_monthly_cashflow_png(df, "INR"),
            render_segment_profit_png(df, "product", "INR"),
            render_risk_distribution_png(df, "INR"),
            render_forecast_png(forecast(df, "revenue", 6), "revenue", "INR"),
        ):
            assert img_bytes is not None
            assert img_bytes.startswith(png_sig)
            assert len(img_bytes) > 5000

    def test_build_charts_zip_packages_all_five_charts_and_readme(self):
        raw_zip = build_charts_zip(_sample_df(), currency="USD", horizon=6)
        with zipfile.ZipFile(io.BytesIO(raw_zip), "r") as zf:
            names = set(zf.namelist())
            for expected in (
                "01_monthly_cashflow.png",
                "02_top_product_profitability.png",
                "03_top_department_profitability.png",
                "04_random_forest_risk_audit.png",
                "05_revenue_forecast_band.png",
                "README_Charts.txt",
            ):
                assert expected in names


class TestPowerBiKit:
    def test_prepare_powerbi_dataframe_schema_and_pii_masking(self):
        df = _sample_df()
        masked = prepare_powerbi_dataframe(df, currency="INR", mask_pii=True)
        assert list(masked.columns) == POWERBI_COLUMNS
        assert len(masked) == 10
        assert "alice@secret.com" not in str(masked.iloc[0]["Vendor Name"])
        assert "ABCDE1234F" not in str(masked.iloc[0]["Notes"])
        assert masked.iloc[0]["Net Profit"] == pytest.approx(38000.0)

        raw = prepare_powerbi_dataframe(df, currency="INR", mask_pii=False)
        assert "alice@secret.com" in str(raw.iloc[0]["Vendor Name"])

    def test_empty_powerbi_dataframe_returns_exact_columns(self):
        out = prepare_powerbi_dataframe(pd.DataFrame())
        assert list(out.columns) == POWERBI_COLUMNS
        assert len(out) == 0

    def test_build_powerbi_kit_zip_contents(self):
        raw = build_powerbi_kit_zip(_sample_df(), currency="INR", mask_pii=True)
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
            names = set(zf.namelist())
            assert {"powerbi_transactions.csv", "finance_pulse_powerquery.pq", "finance_pulse_measures.dax", "README_PowerBI.txt"}.issubset(names)
            csv_text = zf.read("powerbi_transactions.csv").decode("utf-8")
            assert "ML Risk Tier" in csv_text
            assert "alice@secret.com" not in csv_text

    def test_build_powerbi_feed_respects_limit(self):
        feed = build_powerbi_feed(_sample_df(), limit=3, mask_pii=True)
        assert feed["ok"] is True
        assert feed["count"] == 3
        assert len(feed["rows"]) == 3


class TestOfflineReceiptOcr:
    @pytest.mark.parametrize(
        "raw_text,exp_date,exp_curr,exp_cat,is_inc",
        [
            ("AWS Cloud Invoice\nDate: 2026-03-14\nTotal Amount: $1,250.00\nPaid via Card", "2026-03-14", "USD", "Software", False),
            ("Salary Credit Payslip\nDate: 01/04/2026\nNet Pay: INR 45,000.00\nBank Transfer", "2026-04-01", "INR", "Payroll", True),
            ("IndiGo Airlines Ticket\n15 Feb 2026\nGrand Total: €420.50\nFlight booking", "2026-02-15", "EUR", "Travel", False),
            ("Statutory Legal Advisory\nJan 22, 2026\nAmount Paid: £980\nRetainer fees", "2026-01-22", "GBP", "Consulting", False),
        ],
    )
    def test_parse_receipt_text_dates_currencies_and_categories(self, raw_text, exp_date, exp_curr, exp_cat, is_inc):
        parsed = parse_receipt_text(raw_text, filename="doc.png")
        assert parsed["txn_date"] == exp_date
        assert parsed["currency_code"] == exp_curr
        assert parsed["category"] == exp_cat
        if is_inc:
            assert parsed["revenue"] > 0 and parsed["expense"] == 0.0
        else:
            assert parsed["expense"] > 0 and parsed["revenue"] == 0.0

    def test_parse_receipt_redacts_pii_and_extracts_tax(self):
        txt = "Apex Stores\nCall +91 98765 43210 Email bill@apex.io\nGST: INR 180\nGrand Total: INR 1180\nPaid via UPI"
        parsed = parse_receipt_text(txt, filename="bill.jpg")
        assert parsed["tax_amount"] == pytest.approx(180.0)
        assert parsed["expense"] == pytest.approx(1180.0)
        assert parsed["payment_method"] == "UPI / Instant"
        assert "bill@apex.io" not in parsed["vendor_name"]
        assert parsed["pii_redacted"] >= 1

    def test_extract_document_details_from_local_pdf_and_png(self, tmp_path):
        # 1. Valid crisp PNG receipt image
        img = Image.new("RGB", (520, 220), "white")
        draw = ImageDraw.Draw(img)
        draw.text((24, 24), "ACME CLOUD SAAS", fill="black")
        draw.text((24, 64), "Date: 2026-05-12", fill="black")
        draw.text((24, 104), "Grand Total: INR 4850.00", fill="black")
        img_path = tmp_path / "receipt.png"
        img.save(img_path)

        png_res = extract_document_details(img_path)
        assert "ocr_engine" in png_res
        assert "confidence" in png_res

        # 2. Valid local multi-line PDF generated via reportlab (guaranteed local selectable text!)
        from reportlab.pdfgen import canvas as pdf_canvas

        pdf_path = tmp_path / "invoice.pdf"
        c = pdf_canvas.Canvas(str(pdf_path))
        c.drawString(72, 720, "Apex Software License Invoice")
        c.drawString(72, 700, "Date: 2026-06-18")
        c.drawString(72, 680, "Grand Total: INR 9500.00")
        c.save()

        pdf_res = extract_document_details(pdf_path)
        assert pdf_res["ocr_engine"].startswith("PyPDF")
        assert pdf_res["txn_date"] == "2026-06-18"
        assert pdf_res["expense"] == pytest.approx(9500.0)
