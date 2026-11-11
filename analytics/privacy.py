"""Deterministic PII detection and redaction for notes, vendors, exports, and Copilot outputs."""
from __future__ import annotations

import re
from typing import Iterable, Tuple

import pandas as pd

_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-])([A-Za-z0-9._%+-]*)(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){12,19}\b")
_PHONE_RE = re.compile(r"(?:(?<=\s)|^)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3,5}\)?[\s.-]?)\d{3,5}[\s.-]?\d{4}\b")
_PAN_RE = re.compile(r"\b([A-Z]{5})(\d{4})([A-Z])\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-(\d{4})\b")
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{10,}", re.IGNORECASE)


def mask_email(email: str) -> str:
    raw = (email or "").strip()
    if "@" not in raw:
        return raw
    local, domain = raw.split("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    elif len(local) == 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + ("*" * min(4, len(local) - 2)) + local[-1]
    return f"{masked_local}@{domain}"


def mask_pii_text(text: object, enabled: bool = True) -> Tuple[object, int]:
    """Return (masked_text, redaction_count) while preserving non-string / empty values cleanly."""
    if not enabled or text is None:
        return text, 0
    raw = str(text)
    if not raw.strip():
        return raw, 0

    count = 0

    def _sub_email(match: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)}***{match.group(3)}"

    def _sub_pan(match: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)[:2]}***{match.group(2)[-1:]}{match.group(3)}"

    def _sub_ssn(match: re.Match) -> str:
        nonlocal count
        count += 1
        return f"***-**-{match.group(1)}"

    def _sub_card(match: re.Match) -> str:
        nonlocal count
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < 12 or len(digits) > 19:
            return match.group(0)
        count += 1
        return f"****-****-{digits[-4:]}"

    def _sub_phone(match: re.Match) -> str:
        nonlocal count
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < 10 or len(digits) > 13:
            return match.group(0)
        count += 1
        return f"+***-***-{digits[-4:]}"

    def _sub_bearer(match: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)}[REDACTED]"

    out = _BEARER_RE.sub(_sub_bearer, raw)
    out = _EMAIL_RE.sub(_sub_email, out)
    out = _PAN_RE.sub(_sub_pan, out)
    out = _SSN_RE.sub(_sub_ssn, out)
    out = _CARD_RE.sub(_sub_card, out)
    out = _PHONE_RE.sub(_sub_phone, out)
    return out, count


def mask_dataframe_pii(
    df: pd.DataFrame,
    columns: Iterable[str] = ("notes", "vendor_name", "transaction_id", "product"),
    enabled: bool = True,
) -> Tuple[pd.DataFrame, int]:
    if not enabled or df is None or df.empty:
        return df, 0
    masked = df.copy()
    total_redactions = 0
    for col in columns:
        if col not in masked.columns:
            continue
        new_vals = []
        for val in masked[col].tolist():
            if val is None or (isinstance(val, float) and pd.isna(val)):
                new_vals.append(val)
            else:
                cleaned, cnt = mask_pii_text(val, enabled=True)
                total_redactions += cnt
                new_vals.append(cleaned)
        masked[col] = pd.Series(new_vals, index=masked.index, dtype=object)
    return masked, total_redactions
