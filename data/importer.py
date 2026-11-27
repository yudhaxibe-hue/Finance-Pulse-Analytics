import json
import re
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from werkzeug.utils import secure_filename
import config
from database.db import connect

CANONICAL = {
    "date": ["date", "sales date", "transaction date", "txn date", "txn_date", "entry date", "posting date"],
    "revenue": [
        "revenue", "total revenue", "gross revenue", "net revenue", "sales", "total sales",
        "income", "total income", "gross income", "net income", "earnings", "receipts", "turnover",
    ],
    "expense": [
        "expense", "expenses", "total expense", "total expenses", "spend", "spending",
        "expenditure", "operating expense", "operating cost", "operating costs", "total spend",
        "total spending", "disbursement", "disbursements", "overhead",
    ],
    "credit": ["credit", "credit amount", "cr", "cr amount", "deposit", "receipt", "inflow"],
    "debit": ["debit", "debit amount", "dr", "dr amount", "withdrawal", "payment", "outflow"],
    "amount": [
        "total_amount_inr", "total amount inr", "total_amount", "total amount",
        "amount", "amount inr", "amount_inr", "transaction amount", "transaction_amount",
        "txn amount", "txn_amount", "net amount", "net_amount", "gross amount", "gross_amount",
        "total", "value",
    ],
    "cost": ["cost", "cogs", "cost of goods sold"],
    "investment": ["investment", "capex", "savings", "rd", "sip"],
    "tax_amount": ["tax amount", "tax_amount", "tax", "gst", "vat"],
    "discount_amount": ["discount amount", "discount_amount", "discount"],
    "quantity": ["quantity", "qty", "units"],
    "unit_price": ["unit price", "unit_price", "unit amount inr", "unit_amount_inr", "unit amount", "price", "rate"],
    "transaction_id": [
        "transaction id", "transaction_id", "txn id", "txn_id", "tx id", "tx_id",
        "entry id", "entry_id", "voucher no", "receipt no", "reference", "ref no", "invoice id", "id",
    ],
    "transaction_type": ["transaction type", "transaction_type", "type", "entry type", "dr/cr", "cr/dr", "flow"],
    "fiscal_year": ["fiscal year", "fiscal_year", "year", "fy"],
    "fiscal_quarter": ["fiscal quarter", "fiscal_quarter", "quarter"],
    "category": ["category", "segment", "account head"],
    "subcategory": ["subcategory", "sub category", "sub_category", "nature", "account nature"],
    "product": ["product", "item description", "item_description", "item", "service", "particulars"],
    "department": ["department", "dept", "unit", "business unit", "course or dept", "course_or_dept", "course"],
    "cost_center": ["cost center", "cost_center"],
    "region": ["region", "location", "building or location", "building_or_location", "branch", "site"],
    "country": ["country", "nation"],
    "channel": ["channel", "sales channel"],
    "payment_method": ["payment method", "payment_method", "payment mode", "payment_mode", "mode", "payment"],
    "currency_code": ["currency", "currency code", "currency_code"],
    "customer_segment": [
        "customer segment", "customer_segment", "client segment",
        "need or want", "need_or_want", "need want", "budget type", "budget category", "classification",
    ],
    "vendor_name": [
        "vendor name", "vendor_name", "vendor", "merchant", "party",
        "paid to or received from", "paid_to_or_received_from", "payee", "payor", "counterparty",
    ],
    "notes": ["notes", "note", "description", "remarks", "remark", "memo", "narration"],
}
REQUIRED = {"date", "revenue", "expense"}

TEXT_FIELDS = (
    "transaction_id",
    "transaction_type",
    "fiscal_quarter",
    "category",
    "subcategory",
    "product",
    "department",
    "cost_center",
    "region",
    "country",
    "channel",
    "payment_method",
    "currency_code",
    "customer_segment",
    "vendor_name",
    "notes",
)
NUMERIC_FIELDS = ("revenue", "expense", "cost", "tax_amount", "discount_amount", "quantity", "unit_price", "investment")

_EXPENSE_WORDS = {
    "expense", "expenses", "debit", "dr", "payment", "payments", "outflow",
    "withdrawal", "spend", "spending", "cost", "purchase", "payout", "expenditure", "paid",
    "salary", "salaries", "payroll", "maintenance", "rent", "utility", "utilities",
    "refund", "reimbursement",
}
_INCOME_WORDS = {
    "income", "credit", "cr", "receipt", "receipts", "revenue", "sale", "sales",
    "deposit", "inflow", "earning", "earnings", "contribution", "grant", "fee", "fees",
    "interest", "received",
}


def _norm_header(col) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(col).strip().lower()).strip()


def _parse_numeric_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    def _clean_num(val):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        s = str(val).strip()
        if not s or s.lower() in {"nan", "none", "null", "n/a", "-", "--"}:
            return None
        neg = s.startswith("(") and s.endswith(")")
        if neg:
            s = s[1:-1].strip()
        s = re.sub(r"(?i)\b(?:INR|Rs\.?|USD|EUR|GBP|AUD|CAD)(?=\s|[0-9₹$€£,(]|$)", "", s)
        s = re.sub(r"[₹$€£,\s]", "", s)
        if not s:
            return None
        try:
            num = float(s)
            return -abs(num) if neg else num
        except ValueError:
            return None

    return pd.Series([_clean_num(v) for v in series], index=series.index, dtype="float64")


def _parse_dates(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    bad_mask = parsed.isna() & series.notna()
    if bad_mask.any():
        try:
            fallback = pd.to_datetime(series[bad_mask], errors="coerce", format="mixed", dayfirst=True)
            parsed = parsed.copy()
            parsed.loc[bad_mask] = fallback
        except Exception:
            pass
    return parsed


def _classify_txn_type(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "unknown"
    raw = str(value).strip().lower()
    if not raw:
        return "unknown"
    words = set(re.sub(r"[^a-z]+", " ", raw).split())
    if words & _EXPENSE_WORDS:
        return "expense"
    if words & _INCOME_WORDS:
        return "income"
    return "unknown"


def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS


def column_fingerprint(columns) -> str:
    import hashlib
    normed = "|".join(_norm_header(c) for c in columns if str(c).strip())
    return hashlib.sha256(normed.encode("utf-8")).hexdigest()[:16]


def _auto_promote_header(df: pd.DataFrame) -> pd.DataFrame:
    """Skip bank statement or Excel title banner rows (first 15 rows) to locate true header row."""
    if df is None or df.empty or len(df) < 2:
        return df
    unnamed_ratio = sum(1 for c in df.columns if str(c).startswith("Unnamed:")) / max(1, len(df.columns))
    initial_map = detect(df.columns)
    has_req = ("date" in initial_map) and any(k in initial_map for k in ("revenue", "expense", "credit", "debit", "amount"))
    if unnamed_ratio < 0.4 and has_req:
        return df

    best_idx = None
    best_score = 0
    scan_limit = min(15, len(df) - 1)
    for idx in range(scan_limit):
        row_vals = [str(v).strip() if pd.notna(v) and str(v).strip() else f"Col_{j}" for j, v in enumerate(df.iloc[idx].tolist())]
        non_empty = sum(1 for v in df.iloc[idx].tolist() if pd.notna(v) and str(v).strip())
        if non_empty < 2:
            continue
        cand_map = detect(row_vals)
        score = len(cand_map) * 10 + non_empty
        if ("date" in cand_map) and any(k in cand_map for k in ("revenue", "expense", "credit", "debit", "amount")):
            score += 50
        if score > best_score:
            best_score = score
            best_idx = idx

    if best_idx is not None and best_score >= 25:
        new_cols = []
        seen = {}
        for j, v in enumerate(df.iloc[best_idx].tolist()):
            name = str(v).strip() if pd.notna(v) and str(v).strip() else f"Column_{j+1}"
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 0
            new_cols.append(name)
        promoted = df.iloc[best_idx + 1:].copy().reset_index(drop=True)
        promoted.columns = new_cols
        return promoted
    return df


def read_file(path):
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".csv":
        return _auto_promote_header(pd.read_csv(path))
    if ext == ".xlsx":
        return _auto_promote_header(pd.read_excel(path))
    if ext == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for key in ("transactions", "records", "rows", "data", "entries", "ledger"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        if isinstance(payload, list):
            return pd.json_normalize(payload)
        return pd.read_json(path)
    raise ValueError(f"Unsupported file type: {ext}")


_CURRENCY_SUFFIX_RE = re.compile(r"\b(?:inr|usd|eur|gbp|aed|sgd|aud|cad|jpy|rs|rupees|dollars)\b$", re.IGNORECASE)


def infer_mapping_from_content(frame: pd.DataFrame, mapping: dict) -> dict:
    """Infer missing date/amount/category/notes columns by inspecting sample cell values."""
    if frame is None or frame.empty:
        return mapping
    out = dict(mapping)
    used = set(out.values())
    sample = frame.head(40)

    # 1. Infer date if missing
    if "date" not in out:
        for col in frame.columns:
            if col in used:
                continue
            s = sample[col].dropna()
            if len(s) < 2:
                continue
            # Skip pure small integers or pure numeric amounts
            if pd.api.types.is_numeric_dtype(s):
                continue
            str_s = s.astype(str).str.strip()
            if str_s.str.match(r"^-?\d+(\.\d+)?$").mean() > 0.5:
                continue
            parsed = _parse_dates(str_s)
            if parsed.notna().mean() >= 0.70:
                out["date"] = col
                used.add(col)
                break

    # 2. Infer amount/revenue/expense if all are missing
    has_amt = any(k in out for k in ("revenue", "expense", "credit", "debit", "amount"))
    if not has_amt:
        num_cands = []
        for col in frame.columns:
            if col in used:
                continue
            s = sample[col].dropna()
            if len(s) < 2:
                continue
            parsed = _parse_numeric_series(s)
            if parsed.notna().mean() >= 0.75:
                # Avoid serial/ID numbers (1, 2, 3, 4...)
                vals = parsed.dropna().tolist()
                if len(vals) >= 4 and vals == list(range(int(vals[0]), int(vals[0]) + len(vals))):
                    continue
                num_cands.append((col, parsed.dropna()))

        if len(num_cands) == 1:
            out["amount"] = num_cands[0][0]
            used.add(num_cands[0][0])
        elif len(num_cands) >= 2:
            # Heuristic: if one has negative/smaller frequent values or two columns represent cr/dr
            out["revenue"] = num_cands[0][0]
            out["expense"] = num_cands[1][0]
            used.add(num_cands[0][0])
            used.add(num_cands[1][0])

    # 3. Infer category and notes if missing
    if "category" not in out or "notes" not in out:
        text_cands = []
        for col in frame.columns:
            if col in used:
                continue
            s = sample[col].dropna().astype(str).str.strip()
            s = s[s != ""]
            if len(s) < 2:
                continue
            if _parse_numeric_series(s).notna().mean() > 0.7:
                continue
            uniq_ratio = s.nunique() / max(1, len(s))
            text_cands.append((col, uniq_ratio, s.str.len().mean()))

        if "category" not in out and text_cands:
            # Prefer lower cardinality short labels for category
            cat_cand = min(text_cands, key=lambda x: (x[1], x[2]))
            if cat_cand[1] <= 0.65:
                out["category"] = cat_cand[0]
                used.add(cat_cand[0])
                text_cands = [c for c in text_cands if c[0] != cat_cand[0]]

        if "notes" not in out and text_cands:
            # Prefer longer descriptive text for notes
            note_cand = max(text_cands, key=lambda x: (x[2], x[1]))
            out["notes"] = note_cand[0]
            used.add(note_cand[0])

    return out


def detect(columns, frame=None):
    lowered = {str(c).strip().lower(): c for c in columns}
    normalized = {}
    currency_stripped = {}
    for c in columns:
        key = _norm_header(c)
        if key and key not in normalized:
            normalized[key] = c
        stripped = _CURRENCY_SUFFIX_RE.sub("", key).strip()
        if stripped and stripped not in currency_stripped:
            currency_stripped[stripped] = c

    mapping = {}
    used_cols = set()
    for target, aliases in CANONICAL.items():
        matched = None
        for alias in aliases:
            col = lowered.get(alias)
            if col is not None and col not in used_cols:
                matched = col
                break
        if matched is None:
            for alias in aliases:
                col = normalized.get(_norm_header(alias))
                if col is not None and col not in used_cols:
                    matched = col
                    break
        if matched is None:
            for alias in aliases:
                col = currency_stripped.get(_norm_header(alias))
                if col is not None and col not in used_cols:
                    matched = col
                    break
        if matched is not None:
            mapping[target] = matched
            used_cols.add(matched)

    if frame is not None:
        mapping = infer_mapping_from_content(frame, mapping)
    return mapping


def quality_report(frame, mapping):
    missing = []
    if "date" not in mapping:
        missing.append("date")
    has_dual = "revenue" in mapping or "expense" in mapping
    has_crdr = "credit" in mapping or "debit" in mapping
    has_single = "amount" in mapping
    if not (has_dual or has_crdr or has_single):
        if "expense" not in mapping and "debit" not in mapping:
            missing.append("expense")
        if "revenue" not in mapping and "credit" not in mapping:
            missing.append("revenue")
    missing = sorted(missing)

    date_bad = 0
    numeric_bad = 0
    if "date" in mapping:
        date_bad = int(_parse_dates(frame[mapping["date"]]).isna().sum())
    for col in ("revenue", "expense", "credit", "debit", "amount", "cost", "tax_amount", "discount_amount"):
        if col in mapping:
            raw_series = frame[mapping[col]]
            parsed_num = _parse_numeric_series(raw_series)
            if col in ("revenue", "expense", "amount"):
                numeric_bad += int(parsed_num.isna().sum())
            else:
                non_empty = raw_series.notna() & (raw_series.astype(str).str.strip() != "")
                numeric_bad += int((parsed_num.isna() & non_empty).sum())
    duplicates = 0
    if "transaction_id" in mapping:
        non_null_ids = frame[mapping["transaction_id"]].dropna()
        duplicates = int(non_null_ids.duplicated().sum())
    return {
        "rows": len(frame),
        "detected_fields": len(mapping),
        "empty_rows": int(frame.isna().all(axis=1).sum()),
        "invalid_dates": date_bad,
        "invalid_numbers": numeric_bad,
        "duplicate_ids": duplicates,
        "missing_required": missing,
    }


def _clean_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def normalize(frame, mapping, exclude_invalid=True):
    out = pd.DataFrame(index=frame.index)
    out["txn_date"] = _parse_dates(frame[mapping["date"]]) if "date" in mapping else pd.NaT

    for field in TEXT_FIELDS:
        if field in mapping:
            out[field] = pd.Series([_clean_text(v) for v in frame[mapping[field]]], index=frame.index, dtype=object)
        else:
            out[field] = None

    raw_rev = _parse_numeric_series(frame[mapping["revenue"]]).fillna(0.0) if "revenue" in mapping else None
    raw_exp = _parse_numeric_series(frame[mapping["expense"]]).fillna(0.0) if "expense" in mapping else None
    raw_cr = _parse_numeric_series(frame[mapping["credit"]]).fillna(0.0) if "credit" in mapping else None
    raw_dr = _parse_numeric_series(frame[mapping["debit"]]).fillna(0.0) if "debit" in mapping else None
    raw_amt = _parse_numeric_series(frame[mapping["amount"]]).fillna(0.0) if "amount" in mapping else None

    if raw_rev is not None or raw_exp is not None:
        out["revenue"] = raw_rev if raw_rev is not None else pd.Series(0.0, index=frame.index)
        out["expense"] = raw_exp if raw_exp is not None else pd.Series(0.0, index=frame.index)
    elif raw_cr is not None or raw_dr is not None:
        cr_vals = raw_cr if raw_cr is not None else pd.Series(0.0, index=frame.index)
        dr_vals = raw_dr if raw_dr is not None else pd.Series(0.0, index=frame.index)
        out["revenue"] = np.where(cr_vals >= 0, cr_vals, 0.0)
        out["expense"] = np.where(dr_vals < 0, np.abs(dr_vals), np.where(cr_vals < 0, np.abs(cr_vals), dr_vals))
    elif raw_amt is not None:
        ttype_series = out["transaction_type"].tolist() if "transaction_type" in out else [None] * len(frame)
        revs = []
        exps = []
        for amt_val, ttype in zip(raw_amt.tolist(), ttype_series):
            kind = _classify_txn_type(ttype)
            if kind == "expense":
                revs.append(0.0)
                exps.append(abs(float(amt_val)))
            elif kind == "income":
                if amt_val >= 0:
                    revs.append(float(amt_val))
                    exps.append(0.0)
                else:
                    revs.append(0.0)
                    exps.append(abs(float(amt_val)))
            else:
                if amt_val >= 0:
                    revs.append(float(amt_val))
                    exps.append(0.0)
                else:
                    revs.append(0.0)
                    exps.append(abs(float(amt_val)))
        out["revenue"] = pd.Series(revs, index=frame.index, dtype="float64")
        out["expense"] = pd.Series(exps, index=frame.index, dtype="float64")
    else:
        out["revenue"] = raw_rev if raw_rev is not None else 0.0
        out["expense"] = raw_exp if raw_exp is not None else 0.0

    for field in ("cost", "tax_amount", "discount_amount", "quantity", "unit_price", "investment"):
        if field in mapping:
            out[field] = _parse_numeric_series(frame[mapping[field]]).fillna(0.0)
        else:
            out[field] = 0.0

    raw_fy = _parse_numeric_series(frame[mapping["fiscal_year"]]) if "fiscal_year" in mapping else pd.Series(np.nan, index=frame.index)
    derived_fy = out["txn_date"].dt.year
    out["fiscal_year"] = raw_fy.fillna(derived_fy)

    derived_q = np.where(
        out["txn_date"].notna(),
        "Q" + (((out["txn_date"].dt.month.fillna(1).astype(int) - 1) // 3) + 1).astype(str),
        None,
    )
    out["fiscal_quarter"] = [
        fq if fq else dq
        for fq, dq in zip(out["fiscal_quarter"].tolist(), derived_q.tolist())
    ]

    valid = out.txn_date.notna() & (out.revenue >= 0) & (out.expense >= 0)
    excluded = int((~valid).sum())
    cleaned = out[valid].copy() if exclude_invalid else out.copy()
    if not cleaned.empty:
        cleaned["fiscal_year"] = cleaned["fiscal_year"].astype(int)
    return cleaned, excluded


def persist(frame, filename, report, excluded, workspace_id, enrich_ml: bool = True):
    enriched = frame.copy()
    if enrich_ml and not enriched.empty:
        try:
            from analytics.ml_engine import enrich_transactions_df

            enriched = enrich_transactions_df(enriched)
        except Exception:
            pass

    for col, default in (("risk_tier", "Unclassified"), ("risk_score", 0.0), ("predicted_category", None), ("is_anomaly", 0)):
        if col not in enriched:
            enriched[col] = default

    conn = connect()
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"
    cur = conn.execute(
        "INSERT INTO imports(filename,imported_at,row_count,excluded_count,quality_json,workspace_id,file_type,status) VALUES(?,?,?,?,?,?,?,?)",
        (filename, datetime.utcnow().isoformat(), len(enriched), excluded, json.dumps(report), workspace_id, file_ext, "imported"),
    )
    import_id = cur.lastrowid

    def _t(value):
        return None if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)

    def _f(value):
        return 0.0 if value is None or (isinstance(value, float) and pd.isna(value)) else float(value)

    rows = [
        (
            import_id,
            workspace_id,
            r_txn_date.strftime("%Y-%m-%d"),
            _t(r_tid),
            _t(r_ttype),
            None if pd.isna(r_fy) else int(r_fy),
            _t(r_fq),
            _t(r_cat),
            _t(r_sub),
            _t(r_prod),
            _t(r_dept),
            _t(r_cc),
            _t(r_reg),
            _t(r_ctry),
            _t(r_chan),
            _t(r_pm),
            _t(r_curr),
            _t(r_cseg),
            _t(r_vend),
            _f(r_rev),
            _f(r_exp),
            _f(r_cost),
            _f(r_tax),
            _f(r_disc),
            _f(r_qty),
            _f(r_up),
            _f(r_inv),
            _t(r_notes),
            _t(r_rtier),
            _f(r_rscore),
            _t(r_pcat),
            int(bool(r_anom)),
        )
        for (
            r_txn_date, r_tid, r_ttype, r_fy, r_fq, r_cat, r_sub, r_prod, r_dept, r_cc,
            r_reg, r_ctry, r_chan, r_pm, r_curr, r_cseg, r_vend, r_rev, r_exp, r_cost,
            r_tax, r_disc, r_qty, r_up, r_inv, r_notes, r_rtier, r_rscore, r_pcat, r_anom,
        ) in zip(
            enriched["txn_date"], enriched["transaction_id"], enriched["transaction_type"],
            enriched["fiscal_year"], enriched["fiscal_quarter"], enriched["category"],
            enriched["subcategory"], enriched["product"], enriched["department"],
            enriched["cost_center"], enriched["region"], enriched["country"],
            enriched["channel"], enriched["payment_method"], enriched["currency_code"],
            enriched["customer_segment"], enriched["vendor_name"], enriched["revenue"],
            enriched["expense"], enriched["cost"], enriched["tax_amount"],
            enriched["discount_amount"], enriched["quantity"], enriched["unit_price"],
            enriched["investment"], enriched["notes"], enriched["risk_tier"],
            enriched["risk_score"], enriched["predicted_category"], enriched["is_anomaly"],
        )
    ]

    conn.executemany(
        """INSERT INTO financial_transactions(
            import_id,workspace_id,txn_date,transaction_id,transaction_type,
            fiscal_year,fiscal_quarter,category,subcategory,product,department,cost_center,
            region,country,channel,payment_method,currency_code,customer_segment,vendor_name,
            revenue,expense,cost,tax_amount,discount_amount,quantity,unit_price,investment,notes,
            risk_tier,risk_score,predicted_category,is_anomaly
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
