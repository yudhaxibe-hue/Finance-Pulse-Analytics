"""Tests for SQLite WAL mode, SQLAlchemy 2.x ORM, hot backups, and deterministic PII masking."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

import config
from analytics.privacy import mask_dataframe_pii, mask_email, mask_pii_text
from database.db import connect, create_backup, get_journal_mode, initialize, list_backups
from database.models import FinancialTransaction, Workspace, get_sqlalchemy_engine, inspect_schema_summary


class TestDatabaseWalAndOrm:
    def test_sqlite_wal_mode_enabled(self, isolated_env):
        assert get_journal_mode() == "wal"

    def test_sqlalchemy_schema_summary_contains_all_tables_and_33_tx_cols(self, isolated_env):
        summary = inspect_schema_summary(config.DATABASE)
        for tbl in ("users", "workspaces", "imports", "financial_transactions", "settings", "audit_logs", "scenarios"):
            assert tbl in summary
        tx_cols = set(summary["financial_transactions"])
        assert len(tx_cols) >= 33
        for col in (
            "workspace_id", "fiscal_year", "fiscal_quarter", "subcategory",
            "cost_center", "country", "channel", "payment_method", "currency_code",
            "customer_segment", "vendor_name", "tax_amount", "discount_amount",
            "risk_tier", "risk_score", "predicted_category", "is_anomaly",
        ):
            assert col in tx_cols

    def test_sqlalchemy_orm_round_trip(self, isolated_env):
        from sqlalchemy import func, select
        from sqlalchemy.orm import Session

        conn = connect()
        try:
            imp_id = conn.execute(
                "INSERT INTO imports(filename,imported_at,row_count) VALUES(?,?,?)",
                ("orm.csv", "2026-01-01T00:00:00", 1),
            ).lastrowid
            ws_id = conn.execute(
                "INSERT INTO workspaces(name,created_at) VALUES(?,?)",
                ("ORM Workspace", "2026-01-01T00:00:00"),
            ).lastrowid
            conn.commit()
        finally:
            conn.close()

        engine = get_sqlalchemy_engine(config.DATABASE)
        try:
            with Session(engine) as session:
                tx = FinancialTransaction(
                    import_id=imp_id,
                    workspace_id=ws_id,
                    txn_date="2026-02-10",
                    category="Software",
                    product="Core Suite",
                    department="Engineering",
                    region="North",
                    revenue=5500.0,
                    expense=1800.0,
                    cost=600.0,
                    risk_tier="Low Risk",
                    risk_score=14.2,
                )
                session.add(tx)
                session.commit()

                total_cnt = session.execute(select(func.count(FinancialTransaction.id))).scalar_one()
                ws_name = session.execute(select(Workspace.name).where(Workspace.id == ws_id)).scalar_one()
                assert total_cnt == 1
                assert ws_name == "ORM Workspace"
        finally:
            engine.dispose()

    def test_initialize_repairs_legacy_rows_and_backfills_fiscal_periods(self, isolated_env):
        conn = connect()
        try:
            imp_id = conn.execute(
                "INSERT INTO imports(filename,imported_at,row_count) VALUES(?,?,?)",
                ("legacy.csv", "2025-01-01T00:00:00", 1),
            ).lastrowid
            conn.execute(
                "INSERT INTO financial_transactions(import_id,txn_date,product,revenue,expense) VALUES(?,?,?,?,?)",
                (imp_id, "2025-11-15", "<bound method Series.prod\nproduct   AlphaSuite>", 1000.0, 400.0),
            )
            conn.commit()
        finally:
            conn.close()

        initialize()
        conn = connect()
        try:
            row = conn.execute("SELECT product, fiscal_year, fiscal_quarter, workspace_id FROM financial_transactions").fetchone()
            assert row["product"] == "AlphaSuite"
            assert row["fiscal_year"] == 2025
            assert row["fiscal_quarter"] == "Q4"
            assert row["workspace_id"] is not None
        finally:
            conn.close()


class TestHotBackups:
    def test_create_backup_verifies_sqlite_integrity_and_listing(self, isolated_env):
        info = create_backup(label="Pre Release !@#")
        bpath = Path(info["path"])
        assert bpath.is_file()
        assert info["integrity"] == "ok"
        assert info["size_bytes"] > 0
        assert ".." not in bpath.name and "/" not in bpath.name

        # Verify actual SQLite quick_check on backup file independently
        bconn = sqlite3.connect(bpath)
        try:
            assert bconn.execute("PRAGMA quick_check").fetchone()[0].lower() == "ok"
        finally:
            bconn.close()

        items = list_backups(limit=10)
        assert len(items) >= 1
        assert items[0]["filename"] == info["filename"]

    def test_backup_sanitizes_path_traversal_label(self, isolated_env):
        info = create_backup(label="../../etc/passwd")
        assert Path(info["path"]).parent.resolve() == Path(config.BACKUPS_DIR).resolve()
        assert "/" not in info["filename"]


class TestPiiMasking:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("alice@example.com", "a***e@example.com"),
            ("ab@corp.in", "a*@corp.in"),
            ("x@y.co", "*@y.co"),
            ("plain_text", "plain_text"),
            ("", ""),
        ],
    )
    def test_mask_email(self, raw, expected):
        assert mask_email(raw) == expected

    @pytest.mark.parametrize(
        "secret_input,must_not_contain",
        [
            ("Contact admin@financepulse.io for refund", "admin@financepulse.io"),
            ("PAN ABCDE1234F verified", "ABCDE1234F"),
            ("Tax SSN 123-45-6789 filed", "123-45-6789"),
            ("Paid via card 4532 1234 5678 9012", "4532 1234 5678 9012"),
            ("Call +91 98765 43210 on arrival", "98765 43210"),
            ("Auth header Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sig", "eyJhbGci"),
        ],
    )
    def test_mask_pii_text_redacts_sensitive_patterns(self, secret_input, must_not_contain):
        cleaned, cnt = mask_pii_text(secret_input, enabled=True)
        assert cnt >= 1
        assert must_not_contain not in cleaned

    def test_mask_pii_disabled_or_none_preserves_original(self):
        raw = "alice@example.com"
        assert mask_pii_text(raw, enabled=False) == (raw, 0)
        assert mask_pii_text(None, enabled=True) == (None, 0)
        assert mask_pii_text("   ", enabled=True) == ("   ", 0)

    def test_mask_dataframe_pii_redacts_targeted_columns_only(self):
        df = pd.DataFrame([
            {
                "product": "Core Suite",
                "vendor_name": "John Doe john.doe@vendor.com",
                "notes": "Call 9876543210 PAN ABCDE1234F",
                "transaction_id": "TX-101",
            },
            {
                "product": "Support Plan",
                "vendor_name": None,
                "notes": "Clean ledger memo",
                "transaction_id": "TX-102",
            },
        ])
        masked, redactions = mask_dataframe_pii(df, enabled=True)
        assert redactions >= 3
        assert "john.doe@vendor.com" not in str(masked.iloc[0]["vendor_name"])
        assert "ABCDE1234F" not in str(masked.iloc[0]["notes"])
        assert masked.iloc[1]["product"] == "Support Plan"

        unmasked, zero_red = mask_dataframe_pii(df, enabled=False)
        assert zero_red == 0
        assert unmasked.iloc[0]["vendor_name"] == "John Doe john.doe@vendor.com"
