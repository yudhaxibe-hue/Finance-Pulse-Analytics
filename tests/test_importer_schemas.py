"""Tests for universal CSV/XLSX/JSON ingestion, 4 accounting layouts, and 10k sample generator."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from data.importer import detect, normalize, quality_report, read_file
from data.sample_data import build_enterprise_10k_dataframe


AUDIT_UPLOAD_CSV = Path(
    "/Users/yudha/.gemini/antigravity/brain/2901c475-c5b3-4429-9c1f-e5b675e35d08/.user_uploaded/media_1794380201493_ed0470d9.csv"
)


class TestFourAccountingLayouts:
    def test_layout_a_dual_revenue_expense(self):
        raw = pd.DataFrame({
            "Sales Date": ["2025-01-10", "2025-02-15"],
            "Revenue": ["₹1,25,000.50", "85000"],
            "Expense": ["INR 45,000", "40000"],
            "Product": ["Core Suite", "Insight Pro"],
            "Department": ["Product", "Services"],
        })
        mapping = detect(raw.columns)
        cleaned, excluded = normalize(raw, mapping)
        assert excluded == 0
        assert len(cleaned) == 2
        assert cleaned.iloc[0]["revenue"] == pytest.approx(125000.50)
        assert cleaned.iloc[0]["expense"] == pytest.approx(45000.0)

    def test_dual_layout_excludes_negative_values(self):
        raw = pd.DataFrame({
            "Date": ["2025-01-10", "2025-01-11", "2025-01-12"],
            "Revenue": [1000.0, -50.0, 2000.0],
            "Expense": [400.0, 10.0, -25.0],
        })
        cleaned, excluded = normalize(raw, detect(raw.columns))
        assert len(cleaned) == 1
        assert excluded == 2

    @pytest.mark.parametrize(
        "txn_type,raw_amt,exp_rev,exp_exp",
        [
            ("Expense", "15000", 0.0, 15000.0),
            ("Debit", "9200.50", 0.0, 9200.50),
            ("Maintenance", "INR 4,500", 0.0, 4500.0),
            ("Salary", "68000", 0.0, 68000.0),
            ("Withdrawal", "1200", 0.0, 1200.0),
            ("Income", "250000", 250000.0, 0.0),
            ("Credit", "54000", 54000.0, 0.0),
            ("Tuition Fee", "75000", 75000.0, 0.0),
            ("Grant Receipt", "180000", 180000.0, 0.0),
            ("Deposit", "30000", 30000.0, 0.0),
        ],
    )
    def test_layout_b_single_amount_plus_type(self, txn_type, raw_amt, exp_rev, exp_exp):
        raw = pd.DataFrame({
            "Transaction Date": ["2025-03-14"],
            "Transaction Type": [txn_type],
            "Total Amount INR": [raw_amt],
            "Account Head": ["Campus Ledger"],
        })
        mapping = detect(raw.columns)
        cleaned, excluded = normalize(raw, mapping)
        assert excluded == 0
        assert len(cleaned) == 1
        assert cleaned.iloc[0]["revenue"] == pytest.approx(exp_rev)
        assert cleaned.iloc[0]["expense"] == pytest.approx(exp_exp)

    def test_layout_c_credit_debit_bank_statement(self):
        raw = pd.DataFrame({
            "Posting Date": ["2025-04-01", "2025-04-02"],
            "Credit": ["85000", ""],
            "Debit": ["0", "₹22,500"],
            "Description": ["Client Retainer", "Cloud Hosting"],
        })
        mapping = detect(raw.columns)
        cleaned, excluded = normalize(raw, mapping)
        assert excluded == 0
        assert cleaned["revenue"].sum() == pytest.approx(85000.0)
        assert cleaned["expense"].sum() == pytest.approx(22500.0)

    def test_layout_d_signed_amount_without_type_column(self):
        raw = pd.DataFrame({
            "Date": ["2025-05-01", "2025-05-02", "2025-05-03"],
            "Amount": ["40000", "-12500", "(7500)"],
        })
        mapping = detect(raw.columns)
        cleaned, excluded = normalize(raw, mapping)
        assert excluded == 0
        assert cleaned.iloc[0]["revenue"] == pytest.approx(40000.0)
        assert cleaned.iloc[1]["expense"] == pytest.approx(12500.0)
        assert cleaned.iloc[2]["expense"] == pytest.approx(7500.0)

    def test_institutional_college_audit_schema_headers(self):
        raw = pd.DataFrame({
            "Entry_ID": ["AUD-01", "AUD-02"],
            "Date": ["2012-01-15", "2012-02-20"],
            "Fiscal_Year": [2012, 2012],
            "Type": ["Income", "Expense"],
            "Category": ["Tuition Fees", "Faculty Salaries"],
            "Nature": ["Academic", "Payroll"],
            "Course_or_Dept": ["Computer Science", "Computer Science"],
            "Building_or_Location": ["Main Block", "Main Block"],
            "Item_Description": ["Semester Fees", "Professor Salary"],
            "Paid_to_or_Received_from": ["Students Batch 2012", "Dr. Rao"],
            "Payment_Mode": ["Bank Transfer", "NEFT"],
            "Total_Amount_INR": [320000.0, 95000.0],
        })
        mapping = detect(raw.columns)
        cleaned, excluded = normalize(raw, mapping)
        assert excluded == 0
        assert len(cleaned) == 2
        assert cleaned.iloc[0]["revenue"] == pytest.approx(320000.0)
        assert cleaned.iloc[1]["expense"] == pytest.approx(95000.0)
        assert cleaned.iloc[0]["department"] == "Computer Science"
        assert cleaned.iloc[1]["vendor_name"] == "Dr. Rao"

    def test_real_green_valley_audit_csv_if_available(self):
        if not AUDIT_UPLOAD_CSV.is_file():
            pytest.skip("Local benchmark audit CSV not present in CI")
        raw = read_file(AUDIT_UPLOAD_CSV)
        mapping = detect(raw.columns)
        cleaned, excluded = normalize(raw, mapping)
        assert len(cleaned) == 2161
        assert excluded == 0
        assert cleaned["revenue"].sum() > 754_000_000
        assert cleaned["expense"].sum() > 727_000_000


class TestDatesCurrenciesFilesAndQuality:
    @pytest.mark.parametrize(
        "date_str,expected",
        [
            ("2025-07-04", "2025-07-04"),
            ("2025/07/04", "2025-07-04"),
            ("14-08-2025", "2025-08-14"),
            ("Jan 19, 2025", "2025-01-19"),
        ],
    )
    def test_date_format_normalization(self, date_str, expected):
        raw = pd.DataFrame({"Date": [date_str], "Revenue": [100], "Expense": [50]})
        cleaned, excluded = normalize(raw, detect(raw.columns))
        assert excluded == 0
        assert cleaned.iloc[0]["txn_date"].strftime("%Y-%m-%d") == expected

    def test_invalid_date_and_garbage_amount_handling(self):
        raw = pd.DataFrame({
            "Date": ["not-a-date", "2025-06-01"],
            "Revenue": ["$1,000.00", "--"],
            "Expense": ["100", "250.50"],
        })
        report = quality_report(raw, detect(raw.columns))
        assert report["invalid_dates"] == 1
        cleaned, excluded = normalize(raw, detect(raw.columns))
        assert len(cleaned) == 1
        assert excluded == 1
        assert cleaned.iloc[0]["expense"] == pytest.approx(250.50)

    def test_detect_missing_required_date_flagged_and_excluded(self):
        raw = pd.DataFrame({"Product": ["A"], "Revenue": [100], "Expense": [50]})
        mapping = detect(raw.columns)
        assert "date" not in mapping
        report = quality_report(raw, mapping)
        assert "date" in report["missing_required"]
        cleaned, excluded = normalize(raw, mapping)
        assert len(cleaned) == 0
        assert excluded == 1

    def test_detect_missing_financial_amount_columns_flagged(self):
        raw = pd.DataFrame({"Date": ["2025-01-01"], "Product": ["A"]})
        mapping = detect(raw.columns)
        report = quality_report(raw, mapping)
        assert "revenue" in report["missing_required"]
        assert "expense" in report["missing_required"]

    def test_read_file_csv_xlsx_json_and_unsupported(self, tmp_path):
        csv_p = tmp_path / "a.csv"
        csv_p.write_text("Date,Revenue,Expense\n2025-01-01,100,40\n", encoding="utf-8")
        assert len(read_file(csv_p)) == 1

        xlsx_p = tmp_path / "b.xlsx"
        pd.DataFrame([{"Date": "2025-01-02", "Revenue": 200, "Expense": 80}]).to_excel(xlsx_p, index=False)
        assert len(read_file(xlsx_p)) == 1

        json_list_p = tmp_path / "c.json"
        json_list_p.write_text(json.dumps([{"Date": "2025-01-03", "Revenue": 300, "Expense": 90}]), encoding="utf-8")
        assert len(read_file(json_list_p)) == 1

        json_wrap_p = tmp_path / "d.json"
        json_wrap_p.write_text(json.dumps({"transactions": [{"Date": "2025-01-04", "Revenue": 400, "Expense": 100}]}), encoding="utf-8")
        assert len(read_file(json_wrap_p)) == 1

        bad_p = tmp_path / "e.exe"
        bad_p.write_text("nope", encoding="utf-8")
        with pytest.raises(ValueError):
            read_file(bad_p)

    def test_quality_report_duplicate_ids_and_rows(self):
        raw = pd.DataFrame({
            "Date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "Transaction ID": ["T-1", "T-1", ""],
            "Category": ["Ops", "", None],
            "Revenue": [100, 200, 300],
            "Expense": [50, 60, 70],
        })
        rep = quality_report(raw, detect(raw.columns))
        assert rep["duplicate_ids"] == 1
        assert rep["rows"] == 3
        assert rep["empty_rows"] == 0


class TestEnterprise10kSample:
    def test_10k_shape_columns_and_determinism(self):
        df1 = build_enterprise_10k_dataframe(n_rows=10000, seed=42)
        df2 = build_enterprise_10k_dataframe(n_rows=10000, seed=42)
        assert len(df1) == 10000
        assert len(df1.columns) >= 24
        for col in ("Date", "Revenue", "Expense", "Category", "Product", "Department", "Region", "Vendor Name", "Payment Method"):
            assert col in df1.columns
        assert df1["Revenue"].isna().sum() == 0
        assert df1["Expense"].isna().sum() == 0
        assert df1["Revenue"].sum() == pytest.approx(df2["Revenue"].sum())

    def test_10k_normalizes_through_importer_zero_exclusions(self):
        raw = build_enterprise_10k_dataframe(n_rows=10000, seed=42)
        mapping = detect(raw.columns)
        cleaned, excluded = normalize(raw, mapping)
        assert len(cleaned) == 10000
        assert excluded == 0
        assert set(cleaned["fiscal_year"].dropna().astype(int).unique()) >= {2023, 2024, 2025, 2026}
