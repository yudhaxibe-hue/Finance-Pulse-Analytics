import re
import sqlite3
from datetime import datetime
from pathlib import Path
from werkzeug.security import generate_password_hash
import config


def connect():
    db_path = Path(config.DATABASE)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
    _add_column(conn, "financial_transactions", "workspace_id INTEGER")
    _add_column(conn, "scenarios", "workspace_id INTEGER")
    defaults = {
        "currency": "INR",
        "margin_threshold": "15",
        "anomaly_threshold": "1.5",
        "forecast_period": "6",
        "date_format": "%d %b %Y",
    }
    conn.executemany("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", defaults.items())

    # Repair records imported by early versions that accidentally persisted
    # pandas' Series.prod method instead of the product column value.
    for row in conn.execute("SELECT id, product FROM financial_transactions WHERE product LIKE '<bound method Series.prod%' "):
        match = re.search(r"\nproduct\s+([^\n]+)", row["product"])
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
