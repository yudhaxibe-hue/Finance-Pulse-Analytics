import json
from datetime import datetime
import pandas as pd
from werkzeug.utils import secure_filename
import config
from database.db import connect

CANONICAL = {
    "date": ["date", "sales date", "transaction date", "txn date", "txn_date"],
    "transaction_id": ["transaction id", "transaction_id", "id", "invoice id"],
    "transaction_type": ["transaction type", "type"],
    "category": ["category", "segment"],
    "product": ["product", "item"],
    "department": ["department", "dept"],
    "region": ["region", "location"],
    "revenue": ["revenue", "sales", "income", "amount"],
    "expense": ["expense", "expenses", "cost"],
    "cost": ["cost", "cogs", "cost of goods sold"],
    "quantity": ["quantity", "qty"],
    "unit_price": ["unit price", "price"],
    "investment": ["investment"],
    "notes": ["notes", "note", "description"],
}
REQUIRED = {"date", "revenue", "expense"}


def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS


def read_file(path):
    ext = path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path)
    if ext == ".xlsx":
        return pd.read_excel(path)
    if ext == ".json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported file type: {ext}")


def detect(columns):
    lowered = {str(c).strip().lower(): c for c in columns}
    mapping = {}
    for target, aliases in CANONICAL.items():
        for alias in aliases:
            if alias in lowered:
                mapping[target] = lowered[alias]
                break
    return mapping


def quality_report(frame, mapping):
    missing = sorted(REQUIRED - set(mapping))
    date_bad = 0
    numeric_bad = 0
    if "date" in mapping:
        date_bad = int(pd.to_datetime(frame[mapping["date"]], errors="coerce").isna().sum())
    for col in ("revenue", "expense", "cost"):
        if col in mapping:
            numeric_bad += int(pd.to_numeric(frame[mapping[col]], errors="coerce").isna().sum())
    duplicates = 0
    if "transaction_id" in mapping:
        non_null_ids = frame[mapping["transaction_id"]].dropna()
        duplicates = int(non_null_ids.duplicated().sum())
    return {
        "rows": len(frame),
        "empty_rows": int(frame.isna().all(axis=1).sum()),
        "invalid_dates": date_bad,
        "invalid_numbers": numeric_bad,
        "duplicate_ids": duplicates,
        "missing_required": missing,
    }


def _clean_text(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def normalize(frame, mapping, exclude_invalid=True):
    out = pd.DataFrame(index=frame.index)
    for field in CANONICAL:
        out[field] = frame[mapping[field]] if field in mapping else None
    out["txn_date"] = pd.to_datetime(out.pop("date"), errors="coerce")
    for field in ("revenue", "expense", "cost", "quantity", "unit_price", "investment"):
        out[field] = pd.to_numeric(out[field], errors="coerce").fillna(0.0)
    for field in ("transaction_id", "transaction_type", "category", "product", "department", "region", "notes"):
        out[field] = pd.Series([_clean_text(v) for v in out[field]], index=out.index, dtype=object)
    valid = out.txn_date.notna() & (out.revenue >= 0) & (out.expense >= 0)
    excluded = int((~valid).sum())
    return (out[valid].copy() if exclude_invalid else out), excluded


def persist(frame, filename, report, excluded, workspace_id):
    conn = connect()
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"
    cur = conn.execute(
        "INSERT INTO imports(filename,imported_at,row_count,excluded_count,quality_json,workspace_id,file_type,status) VALUES(?,?,?,?,?,?,?,?)",
        (filename, datetime.utcnow().isoformat(), len(frame), excluded, json.dumps(report), workspace_id, file_ext, "imported"),
    )
    import_id = cur.lastrowid
    rows = []
    text = lambda value: None if value is None or pd.isna(value) else str(value)
    number = lambda value: None if value is None or pd.isna(value) else float(value)
    for _, r in frame.iterrows():
        rows.append((
            import_id,
            workspace_id,
            r["txn_date"].strftime("%Y-%m-%d"),
            text(r["transaction_id"]),
            text(r["transaction_type"]),
            text(r["category"]),
            text(r["product"]),
            text(r["department"]),
            text(r["region"]),
            number(r["revenue"]),
            number(r["expense"]),
            number(r["cost"]),
            number(r["quantity"]),
            number(r["unit_price"]),
            number(r["investment"]),
            text(r["notes"]),
        ))
    conn.executemany(
        """INSERT INTO financial_transactions(
            import_id,workspace_id,txn_date,transaction_id,transaction_type,category,
            product,department,region,revenue,expense,cost,quantity,unit_price,investment,notes
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return import_id


def save_upload(file, workspace_id):
    config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    name = secure_filename(file.filename)
    path = config.UPLOAD_FOLDER / f"workspace_{workspace_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{name}"
    file.save(path)
    return path
