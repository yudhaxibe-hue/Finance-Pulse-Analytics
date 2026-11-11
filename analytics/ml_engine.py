"""100% offline scikit-learn Random Forest ML suite (risk scoring & category prediction)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import FunctionTransformer

import config

RISK_TIERS = ("Low Risk", "Moderate Risk", "High Risk")

_CATEGORY_PRIORS: List[Tuple[str, str, float, float]] = [
    ("Core Suite SaaS license renewal Enterprise subscription", "Software", 85000.0, 22000.0),
    ("Insight Pro AWS Cloud Azure GCP hosting bill invoice", "Software", 0.0, 42000.0),
    ("Cloud infrastructure Kubernetes GitHub Adobe seat license", "Software", 48000.0, 18000.0),
    ("Statutory audit advisory consulting compliance retainer", "Consulting", 52000.0, 28000.0),
    ("Legal counsel chartered accountant tax audit fees", "Consulting", 0.0, 35000.0),
    ("Support Plan SLA Enterprise Care implementation services", "Services", 41000.0, 20000.0),
    ("Managed Ops electricity internet broadband office rent water", "Operations", 0.0, 32000.0),
    ("Office stationery utilities courier logistics maintenance", "Operations", 0.0, 14000.0),
    ("Google Ads Meta campaign sponsorship admission marketing", "Marketing", 0.0, 45000.0),
    ("Facebook social media brand banner ads demand gen marketing", "Marketing", 0.0, 28000.0),
    ("Monthly teaching staff payroll salary stipend provident fund", "Payroll", 0.0, 95000.0),
    ("Teacher salary academic faculty wages employee compensation payroll", "Payroll", 0.0, 72000.0),
    ("Non-teaching administrative staff salary bonus payroll run", "Payroll", 0.0, 64000.0),
    ("Tuition fee Term 1 Term 2 examination fee student enrollment", "Tuition & Fees", 120000.0, 0.0),
    ("Airline flight hotel cab travel reimbursement accommodation", "Travel", 0.0, 18500.0),
    ("Classroom furniture computers projectors lab equipment capex", "Equipment & Capex", 0.0, 140000.0),
]


def model_artifact_path() -> Path:
    return Path(config.MODELS_DIR) / "finance_pulse_rf_models.joblib"


def _extract_risk_features(df: pd.DataFrame) -> np.ndarray:
    if df is None or df.empty:
        return np.zeros((0, 9), dtype=float)

    def _num(col: str) -> np.ndarray:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)
        return np.zeros(len(df), dtype=float)

    rev = _num("revenue")
    exp = _num("expense")
    cost = _num("cost")
    tax = _num("tax_amount")
    inv = _num("investment")

    dates = pd.to_datetime(df["txn_date"] if "txn_date" in df.columns else pd.Series([""] * len(df)), errors="coerce")
    months = dates.dt.month.fillna(6).to_numpy(dtype=float)
    quarters = ((months - 1) // 3) + 1.0

    # Relative scale ratio against median non-zero transaction disbursement / inflow
    pos_exp = exp[exp > 0]
    med_exp = float(np.median(pos_exp)) if len(pos_exp) else 1.0
    pos_rev = rev[rev > 0]
    med_rev = float(np.median(pos_rev)) if len(pos_rev) else 1.0

    exp_rel = np.where(exp > 0, exp / max(med_exp, 1.0), 0.0)
    rev_rel = np.where(rev > 0, rev / max(med_rev, 1.0), 0.0)

    denom_flow = np.maximum(rev, exp)
    exp_to_rev = np.where(rev > 0, np.clip(exp / np.maximum(rev, 1.0), 0.0, 5.0), np.where(exp > 0, np.clip(exp_rel, 0.5, 5.0), 0.0))
    margin_ratio = np.where(rev > 0, np.clip((rev - exp) / np.maximum(rev, 1.0), -3.0, 1.0), np.where(exp > 0, -0.5, 0.0))
    cogs_ratio = np.where(denom_flow > 0, np.clip(cost / np.maximum(denom_flow, 1.0), 0.0, 2.0), 0.0)
    tax_ratio = np.where(denom_flow > 0, np.clip(tax / np.maximum(denom_flow, 1.0), 0.0, 1.0), 0.0)

    return np.column_stack([
        np.log1p(rev),
        np.log1p(exp),
        exp_to_rev,
        margin_ratio,
        np.clip(exp_rel, 0.0, 20.0),
        np.clip(rev_rel, 0.0, 20.0),
        cogs_ratio,
        tax_ratio,
        np.where(inv > 0, 1.0, 0.0) * 0.25 + (quarters / 4.0),
    ])


def _derive_risk_labels(df: pd.DataFrame) -> np.ndarray:
    rev = pd.to_numeric(df["revenue"] if "revenue" in df.columns else pd.Series(0.0, index=df.index), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    exp = pd.to_numeric(df["expense"] if "expense" in df.columns else pd.Series(0.0, index=df.index), errors="coerce").fillna(0.0).to_numpy(dtype=float)

    pos_exp = exp[exp > 0]
    if len(pos_exp) >= 4:
        q1, q3 = np.percentile(pos_exp, [25, 75])
        exp_high_cut = float(q3 + 1.5 * (q3 - q1))
        exp_mod_cut = float(np.median(pos_exp) * 1.45)
    else:
        med = float(np.median(pos_exp)) if len(pos_exp) else 50000.0
        exp_high_cut = med * 2.5
        exp_mod_cut = med * 1.45

    labels = []
    for r, e in zip(rev, exp):
        if r > 0 and e > 0:
            margin = (r - e) / r
            if margin < 0.0 or e > exp_high_cut:
                labels.append("High Risk")
            elif margin < 0.15 or e > exp_mod_cut:
                labels.append("Moderate Risk")
            else:
                labels.append("Low Risk")
        elif e > 0 and r == 0:
            if e > exp_high_cut:
                labels.append("High Risk")
            elif e > exp_mod_cut:
                labels.append("Moderate Risk")
            else:
                labels.append("Low Risk")
        else:
            labels.append("Low Risk")
    return np.array(labels, dtype=object)


def _bootstrap_risk_dataset(n: int = 240) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    rows = []
    labels = []
    per_cls = n // 3
    for _ in range(per_cls):
        # Low Risk healthy dual + normal single transactions
        rev = rng.uniform(50000, 160000)
        exp = rev * rng.uniform(0.32, 0.72)
        rows.append((rev, exp, rev * 0.25, rev * 0.12, 0.0, int(rng.integers(1, 13))))
        labels.append("Low Risk")
    for _ in range(per_cls):
        # Moderate Risk compressed margin
        rev = rng.uniform(35000, 120000)
        exp = rev * rng.uniform(0.86, 0.99)
        rows.append((rev, exp, rev * 0.30, rev * 0.10, 0.0, int(rng.integers(1, 13))))
        labels.append("Moderate Risk")
    for _ in range(per_cls):
        # High Risk deficit or spend spike
        rev = rng.uniform(20000, 90000)
        exp = rev * rng.uniform(1.12, 2.35)
        rows.append((rev, exp, rev * 0.35, rev * 0.08, 5000.0, int(rng.integers(1, 13))))
        labels.append("High Risk")

    syn_df = pd.DataFrame({
        "revenue": [r[0] for r in rows],
        "expense": [r[1] for r in rows],
        "cost": [r[2] for r in rows],
        "tax_amount": [r[3] for r in rows],
        "investment": [r[4] for r in rows],
        "txn_date": [f"2025-{r[5]:02d}-15" for r in rows],
    })
    return _extract_risk_features(syn_df), np.array(labels, dtype=object)


def _compose_text(df: pd.DataFrame) -> List[str]:
    cols = ("product", "department", "vendor_name", "notes", "transaction_type", "subcategory", "payment_method")
    out = []
    for i in range(len(df)):
        parts = []
        row = df.iloc[i]
        for c in cols:
            if c in df.columns:
                val = row[c]
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    s = str(val).strip()
                    if s and s.lower() not in {"unspecified", "general", "none"}:
                        parts.append(s)
        out.append(" ".join(parts) if parts else "financial transaction")
    return out


def _select_text_col(frame: pd.DataFrame) -> List[str]:
    return frame["_ml_text"].tolist()


def _select_num_cols(frame: pd.DataFrame) -> np.ndarray:
    rev = pd.to_numeric(frame["revenue"] if "revenue" in frame.columns else pd.Series(0.0, index=frame.index), errors="coerce").fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)
    exp = pd.to_numeric(frame["expense"] if "expense" in frame.columns else pd.Series(0.0, index=frame.index), errors="coerce").fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)
    return np.column_stack([np.log1p(rev), np.log1p(exp), np.where(rev >= exp, 1.0, 0.0)])


def _build_category_pipeline() -> Pipeline:
    union = FeatureUnion([
        ("tfidf", Pipeline([
            ("sel", FunctionTransformer(_select_text_col, validate=False)),
            ("vec", TfidfVectorizer(max_features=320, ngram_range=(1, 2), lowercase=True)),
        ])),
        ("nums", FunctionTransformer(_select_num_cols, validate=False)),
    ])
    return Pipeline([
        ("features", union),
        ("clf", RandomForestClassifier(
            n_estimators=120,
            max_depth=14,
            min_samples_leaf=1,
            class_weight="balanced",
            random_state=42,
            n_jobs=1,
        )),
    ])


def _fit_risk_classifier(df: Optional[pd.DataFrame] = None) -> RandomForestClassifier:
    X_syn, y_syn = _bootstrap_risk_dataset()
    if df is not None and len(df) >= 8:
        X_df = _extract_risk_features(df)
        y_df = _derive_risk_labels(df)
        X_all = np.vstack([X_syn, X_df])
        y_all = np.concatenate([y_syn, y_df])
    else:
        X_all, y_all = X_syn, y_syn
    clf = RandomForestClassifier(
        n_estimators=120,
        max_depth=10,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=1,
    )
    clf.fit(X_all, y_all)
    return clf


def _fit_category_classifier(df: Optional[pd.DataFrame] = None) -> Pipeline:
    prior_rows = [
        {"_ml_text": txt, "revenue": r, "expense": e, "category": cat}
        for txt, cat, r, e in _CATEGORY_PRIORS
    ] * 3
    train_df = pd.DataFrame(prior_rows)
    if df is not None and not df.empty and "category" in df.columns:
        valid_cat = df[df["category"].notna() & (~df["category"].astype(str).str.strip().isin(["", "Uncategorized", "None"]))].copy()
        if len(valid_cat) >= 5:
            sample = valid_cat.head(2500).copy()
            sample["_ml_text"] = _compose_text(sample)
            sub = sample[["_ml_text", "revenue", "expense", "category"]].copy()
            train_df = pd.concat([train_df, sub], ignore_index=True)

    pipe = _build_category_pipeline()
    pipe.fit(train_df, train_df["category"].astype(str))
    return pipe


def train_and_save_models(df: Optional[pd.DataFrame] = None, persist_disk: bool = True) -> Dict[str, Any]:
    """Train offline Random Forest risk & category models and save bundle via joblib."""
    risk_clf = _fit_risk_classifier(df)
    cat_pipe = _fit_category_classifier(df)
    bundle = {
        "version": "1.2.0",
        "trained_at": datetime.utcnow().isoformat() + "Z",
        "row_count": 0 if df is None else int(len(df)),
        "risk_clf": risk_clf,
        "cat_pipe": cat_pipe,
        "feature_names": [
            "log_revenue", "log_expense", "expense_to_revenue", "margin_ratio",
            "expense_relative", "revenue_relative", "cogs_ratio", "tax_ratio", "calendar_investment",
        ],
    }
    saved_path = None
    if persist_disk:
        try:
            target = model_artifact_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(bundle, target, compress=3)
            saved_path = str(target)
        except OSError:
            saved_path = None
    bundle["artifact_path"] = saved_path
    return bundle


def score_transactions_risk(df: pd.DataFrame, clf: Optional[RandomForestClassifier] = None) -> pd.DataFrame:
    """Return copy with Random Forest `risk_tier` ('Low Risk'|'Moderate Risk'|'High Risk') & `risk_score` (0..100)."""
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    out = df.copy()
    model = clf or _fit_risk_classifier(out)
    X = _extract_risk_features(out)
    probs = model.predict_proba(X)
    classes = list(model.classes_)
    pred_tiers = model.predict(X)

    high_idx = classes.index("High Risk") if "High Risk" in classes else None
    mod_idx = classes.index("Moderate Risk") if "Moderate Risk" in classes else None
    high_p = probs[:, high_idx] if high_idx is not None else np.zeros(len(out))
    mod_p = probs[:, mod_idx] if mod_idx is not None else np.zeros(len(out))

    scores = np.clip(np.round((high_p * 100.0 + mod_p * 48.0), 1), 1.0, 99.9)
    out["risk_tier"] = pd.Series(pred_tiers, index=out.index, dtype=object)
    out["risk_score"] = pd.Series(scores, index=out.index, dtype="float64")
    return out


def predict_missing_categories(df: pd.DataFrame, pipe: Optional[Pipeline] = None) -> pd.Series:
    """Predict structured accounting categories offline with Random Forest + TF-IDF."""
    if df is None or df.empty:
        return pd.Series([], dtype=object)
    model = pipe or _fit_category_classifier(df)
    work = df.copy()
    work["_ml_text"] = _compose_text(work)
    preds = model.predict(work)
    return pd.Series(preds, index=df.index, dtype=object)


def enrich_transactions_df(df: pd.DataFrame, persist_models: bool = True) -> pd.DataFrame:
    """Apply Random Forest risk tiering, category inference, and IQR/ML anomaly tags."""
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    bundle = train_and_save_models(df, persist_disk=persist_models)
    out = score_transactions_risk(df, clf=bundle["risk_clf"])
    preds = predict_missing_categories(out, pipe=bundle["cat_pipe"])
    existing_cat = out["category"] if "category" in out.columns else pd.Series([None] * len(out), index=out.index)
    out["predicted_category"] = [
        str(cur).strip() if cur is not None and not (isinstance(cur, float) and pd.isna(cur)) and str(cur).strip() not in ("", "Uncategorized") else str(pred)
        for cur, pred in zip(existing_cat.tolist(), preds.tolist())
    ]

    # Mark statistical / Random Forest extreme outliers cleanly
    exp = pd.to_numeric(out.get("expense", 0.0), errors="coerce").fillna(0.0)
    rev = pd.to_numeric(out.get("revenue", 0.0), errors="coerce").fillna(0.0)
    anom = np.zeros(len(out), dtype=int)
    for ser in (exp, rev):
        pos = ser[ser > 0]
        if len(pos) >= 4:
            q1, q3 = pos.quantile(0.25), pos.quantile(0.75)
            cutoff = q3 + 1.5 * (q3 - q1)
            anom = np.where(ser > cutoff, 1, anom)
    out["is_anomaly"] = anom
    return out


def ml_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """Summarize offline Random Forest risk posture, feature drivers, and category intelligence."""
    if df is None or df.empty:
        return {
            "total": 0,
            "low_risk": 0,
            "moderate_risk": 0,
            "high_risk": 0,
            "high_risk_pct": 0.0,
            "high_risk_exposure": 0.0,
            "avg_risk_score": 0.0,
            "feature_importances": [],
            "model_saved": False,
        }

    scored = df.copy()
    has_precomputed = (
        "risk_tier" in scored.columns
        and "risk_score" in scored.columns
        and scored["risk_tier"].isin(RISK_TIERS).all()
        and scored["risk_score"].notna().all()
    )

    sample_for_imp = scored.iloc[::max(1, len(scored) // 2500)] if len(scored) > 2500 else scored
    risk_clf = _fit_risk_classifier(sample_for_imp)
    if not has_precomputed:
        scored = score_transactions_risk(scored, clf=risk_clf)

    tiers = scored["risk_tier"].astype(str)
    low_c = int((tiers == "Low Risk").sum())
    mod_c = int((tiers == "Moderate Risk").sum())
    high_c = int((tiers == "High Risk").sum())

    high_mask = tiers == "High Risk"
    high_exp = float(pd.to_numeric(scored.loc[high_mask, "expense"], errors="coerce").fillna(0.0).sum()) if "expense" in scored.columns else 0.0
    avg_score = round(float(pd.to_numeric(scored["risk_score"], errors="coerce").fillna(0.0).mean()), 1)

    feature_names = [
        "log_revenue", "log_expense", "expense_to_revenue", "margin_ratio",
        "expense_relative", "revenue_relative", "cogs_ratio", "tax_ratio", "calendar_investment",
    ]
    labels_pretty = {
        "log_revenue": "Revenue Scale",
        "log_expense": "Expense Scale",
        "expense_to_revenue": "Expense / Revenue Ratio",
        "margin_ratio": "Net Margin Ratio",
        "expense_relative": "Disbursement Multiple",
        "revenue_relative": "Inflow Multiple",
        "cogs_ratio": "COGS Intensity",
        "tax_ratio": "Tax Load Ratio",
        "calendar_investment": "Quarter & Capex Mix",
    }
    imp = sorted(
        [
            {"feature": labels_pretty.get(name, name), "importance": round(float(val * 100.0), 1)}
            for name, val in zip(feature_names, risk_clf.feature_importances_)
        ],
        key=lambda x: x["importance"],
        reverse=True,
    )

    return {
        "total": int(len(scored)),
        "low_risk": low_c,
        "moderate_risk": mod_c,
        "high_risk": high_c,
        "high_risk_pct": round(high_c / max(1, len(scored)) * 100.0, 1),
        "high_risk_exposure": round(high_exp, 2),
        "avg_risk_score": avg_score,
        "feature_importances": imp[:5],
        "model_saved": model_artifact_path().exists(),
    }
