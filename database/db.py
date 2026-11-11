import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from werkzeug.security import generate_password_hash
import config


def connect():
    db_path = Path(config.DATABASE)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 10000")
    except sqlite3.OperationalError:
        pass
    return conn


def get_journal_mode() -> str:
    conn = connect()
    try:
        row = conn.execute("PRAGMA journal_mode").fetchone()
        return str(row[0]).lower() if row else "unknown"
    finally:
        conn.close()


def _add_column(conn, table, definition):
    name = definition.split()[0]
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def initialize():
    conn = connect()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS imports (
      id INTEGER PRIMARY KEY, filename TEXT NOT NULL, imported_at TEXT NOT NULL,
      row_count INTEGER NOT NULL, excluded_count INTEGER DEFAULT 0, quality_json TEXT
    );
    CREATE TABLE IF NOT EXISTS financial_transactions (
      id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL, txn_date TEXT NOT NULL,
      transaction_id TEXT, transaction_type TEXT, category TEXT, product TEXT,
      department TEXT, region TEXT, revenue REAL NOT NULL DEFAULT 0,
      expense REAL NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0,
      quantity REAL, unit_price REAL, investment REAL NOT NULL DEFAULT 0, notes TEXT,
      FOREIGN KEY(import_id) REFERENCES imports(id)
    );
    CREATE INDEX IF NOT EXISTS idx_transactions_date ON financial_transactions(txn_date);
    CREATE INDEX IF NOT EXISTS idx_transactions_import ON financial_transactions(import_id);
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
      status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, last_activity_at TEXT
    );
    CREATE TABLE IF NOT EXISTS workspaces (
      id INTEGER PRIMARY KEY, owner_user_id INTEGER, name TEXT NOT NULL, created_at TEXT NOT NULL,
      FOREIGN KEY(owner_user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS audit_logs (
      id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL, detail TEXT,
      created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS scenarios (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, assumptions_json TEXT NOT NULL,
      result_json TEXT NOT NULL, created_at TEXT NOT NULL
    );
    ''')
    _add_column(conn, "imports", "workspace_id INTEGER")
    _add_column(conn, "imports", "file_type TEXT")
    _add_column(conn, "imports", "status TEXT NOT NULL DEFAULT 'imported'")

    # 26 enterprise fields + ML classification & anomaly columns (non-destructive upgrades)
    _add_column(conn, "financial_transactions", "workspace_id INTEGER")
    _add_column(conn, "financial_transactions", "fiscal_year INTEGER")
    _add_column(conn, "financial_transactions", "fiscal_quarter TEXT")
    _add_column(conn, "financial_transactions", "subcategory TEXT")
    _add_column(conn, "financial_transactions", "cost_center TEXT")
    _add_column(conn, "financial_transactions", "country TEXT")
    _add_column(conn, "financial_transactions", "channel TEXT")
    _add_column(conn, "financial_transactions", "payment_method TEXT")
    _add_column(conn, "financial_transactions", "currency_code TEXT")
    _add_column(conn, "financial_transactions", "customer_segment TEXT")
    _add_column(conn, "financial_transactions", "vendor_name TEXT")
    _add_column(conn, "financial_transactions", "tax_amount REAL NOT NULL DEFAULT 0")
    _add_column(conn, "financial_transactions", "discount_amount REAL NOT NULL DEFAULT 0")
    _add_column(conn, "financial_transactions", "risk_tier TEXT")
    _add_column(conn, "financial_transactions", "risk_score REAL")
    _add_column(conn, "financial_transactions", "predicted_category TEXT")
    _add_column(conn, "financial_transactions", "is_anomaly INTEGER NOT NULL DEFAULT 0")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_ws_date ON financial_transactions(workspace_id, txn_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_region ON financial_transactions(region, department)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_year ON financial_transactions(fiscal_year)")

    _add_column(conn, "scenarios", "workspace_id INTEGER")
    defaults = {
        "currency": "INR",
        "margin_threshold": "15",
        "anomaly_threshold": "1.5",
        "forecast_period": "6",
        "date_format": "%d %b %Y",
        "pii_masking": "1",
    }
    conn.executemany("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", defaults.items())

    # Backfill fiscal_year / fiscal_quarter for legacy records if unset
    conn.execute(
        """UPDATE financial_transactions
           SET fiscal_year = COALESCE(fiscal_year, CAST(substr(txn_date, 1, 4) AS INTEGER)),
               fiscal_quarter = COALESCE(fiscal_quarter,
                   CASE
                     WHEN CAST(substr(txn_date, 6, 2) AS INTEGER) BETWEEN 1 AND 3 THEN 'Q1'
                     WHEN CAST(substr(txn_date, 6, 2) AS INTEGER) BETWEEN 4 AND 6 THEN 'Q2'
                     WHEN CAST(substr(txn_date, 6, 2) AS INTEGER) BETWEEN 7 AND 9 THEN 'Q3'
                     ELSE 'Q4'
                   END)
           WHERE txn_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-*'
             AND (fiscal_year IS NULL OR fiscal_quarter IS NULL)"""
    )

    # Repair records imported by early versions that accidentally persisted
    # pandas' Series.prod method instead of the product column value.
    for row in conn.execute("SELECT id, product FROM financial_transactions WHERE product LIKE '<bound method Series.prod%' "):
        match = re.search(r"\nproduct\s+([^\n>]+)", row["product"])
        if match:
            conn.execute("UPDATE financial_transactions SET product=? WHERE id=?", (match.group(1).strip(), row["id"]))

    # Keep pre-portal records intact but segregated from every user workspace.
    legacy = conn.execute("SELECT id FROM workspaces WHERE name='Legacy / demo data'").fetchone()
    if not legacy and conn.execute("SELECT COUNT(*) FROM financial_transactions").fetchone()[0]:
        cur = conn.execute("INSERT INTO workspaces(owner_user_id,name,created_at) VALUES(NULL,?,?)", ("Legacy / demo data", datetime.utcnow().isoformat()))
        legacy_id = cur.lastrowid
        conn.execute("UPDATE imports SET workspace_id=? WHERE workspace_id IS NULL", (legacy_id,))
        conn.execute("UPDATE financial_transactions SET workspace_id=? WHERE workspace_id IS NULL", (legacy_id,))
        conn.execute("UPDATE scenarios SET workspace_id=? WHERE workspace_id IS NULL", (legacy_id,))

    if config.ADMIN_EMAIL and config.ADMIN_PASSWORD:
        admin_email = config.ADMIN_EMAIL.lower().strip()
        if not conn.execute("SELECT 1 FROM users WHERE email=?", (admin_email,)).fetchone():
            now = datetime.utcnow().isoformat()
            cur = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                ("System Administrator", admin_email, generate_password_hash(config.ADMIN_PASSWORD, method="pbkdf2:sha256"), "admin", now),
            )
            conn.execute("INSERT INTO workspaces(owner_user_id,name,created_at) VALUES(?,?,?)", (cur.lastrowid, "Administrator workspace", now))

    conn.commit()
    conn.close()


def create_backup(label: str = "manual", backup_dir: Optional[Path] = None) -> dict:
    """Create a hot, transaction-consistent SQLite backup snapshot using sqlite3.backup."""
    target_dir = Path(backup_dir or config.BACKUPS_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^A-Za-z0-9_-]", "_", (label or "manual").strip())[:32] or "manual"
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    out_path = target_dir / f"finance_pulse_{safe_label}_{stamp}.db"

    src = connect()
    dst = sqlite3.connect(out_path)
    try:
        src.backup(dst)
        dst.commit()
        check = dst.execute("PRAGMA quick_check").fetchone()[0]
        row_count = int(dst.execute("SELECT COUNT(*) FROM financial_transactions").fetchone()[0])
    finally:
        dst.close()
        src.close()

    return {
        "filename": out_path.name,
        "path": str(out_path),
        "size_bytes": out_path.stat().st_size,
        "integrity": check,
        "transactions": row_count,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


def list_backups(backup_dir: Optional[Path] = None, limit: Optional[int] = None) -> List[dict]:
    target_dir = Path(backup_dir or config.BACKUPS_DIR)
    if not target_dir.is_dir():
        return []
    items = []
    for f in sorted(target_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        st = f.stat()
        items.append({
            "filename": f.name,
            "path": str(f),
            "size_bytes": st.st_size,
            "modified_at": datetime.utcfromtimestamp(st.st_mtime).isoformat() + "Z",
        })
    if limit is not None:
        return items[:max(0, int(limit))]
    return items
