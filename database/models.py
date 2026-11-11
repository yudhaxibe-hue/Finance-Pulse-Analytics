"""SQLAlchemy 2.x ORM definitions & WAL-safe engine helpers mirroring SQLite storage."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

import config


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    last_activity_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)


class ImportRecord(Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    imported_at: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="imported", nullable=False)


class FinancialTransaction(Base):
    """26-field enterprise financial transaction schema + ML enrichment metadata."""

    __tablename__ = "financial_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(Integer, ForeignKey("imports.id"), nullable=False)
    workspace_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    txn_date: Mapped[str] = mapped_column(String(32), nullable=False)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    transaction_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    fiscal_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fiscal_quarter: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    product: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    cost_center: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    channel: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    currency_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    customer_segment: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    expense: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    investment: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_tier: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_category: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    assumptions_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


def get_sqlalchemy_engine(db_path: Optional[Path] = None):
    target = Path(db_path or config.DATABASE)
    target.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{target}", future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    return engine


def inspect_schema_summary(db_path: Optional[Path] = None) -> Dict[str, List[str]]:
    engine = get_sqlalchemy_engine(db_path)
    try:
        insp = inspect(engine)
        return {tbl: [col["name"] for col in insp.get_columns(tbl)] for tbl in insp.get_table_names()}
    finally:
        engine.dispose()
