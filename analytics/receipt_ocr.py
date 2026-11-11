"""100% offline photo & PDF financial document extraction (no external AI keys)."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from analytics.privacy import mask_pii_text

_CATEGORY_KEYWORDS = {
    "Software": ("aws", "azure", "google cloud", "saas", "software", "license", "github", "adobe", "hosting", "cloud", "zoom"),
    "Consulting": ("consulting", "advisory", "audit", "legal", "retainer", "agency", "services"),
    "Operations": ("office", "utilities", "electricity", "rent", "internet", "broadband", "logistics", "shipping", "fuel"),
    "Travel": ("airline", "flight", "hotel", "uber", "ola", "cab", "rail", "travel", "boarding"),
    "Marketing": ("ads", "marketing", "campaign", "meta ads", "google ads", "promotion", "sponsorship"),
    "Payroll": ("salary", "payroll", "wages", "stipend", "bonus", "compensation"),
    "Groceries & Dining": ("restaurant", "cafe", "coffee", "mart", "supermarket", "dining", "food", "bakery", "swiggy", "zomato"),
}

_DATE_PATTERNS = [
    (re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+(20\d{2})\b", re.I), "dmony"),
    (re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})[\s,]+(20\d{2})\b", re.I), "mondy"),
]
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONEY_RE = re.compile(
    r"(?:INR|Rs\.?|USD|\$|EUR|€|GBP|£)?\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)(?![0-9])",
    re.I,
)


def _extract_date_iso(text: str) -> str:
    for pat, kind in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if kind == "ymd":
                dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            elif kind == "dmy":
                g1, g2, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
                day, month = (g1, g2) if g2 <= 12 else (g2, g1)
                dt = datetime(yr, month, day)
            elif kind == "dmony":
                dt = datetime(int(m.group(3)), _MONTH_MAP[m.group(2)[:3].lower()], int(m.group(1)))
            else:
                dt = datetime(int(m.group(3)), _MONTH_MAP[m.group(1)[:3].lower()], int(m.group(2)))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.utcnow().strftime("%Y-%m-%d")


def _extract_currency(text: str, default: str = "INR") -> str:
    upper = text.upper()
    if "USD" in upper or "$" in text:
        return "USD"
    if "EUR" in upper or "€" in text:
        return "EUR"
    if "GBP" in upper or "£" in text:
        return "GBP"
    if "INR" in upper or "RS" in upper or "₹" in text:
        return "INR"
    return default


def _extract_labeled_amount(lines: List[str], labels: Tuple[str, ...]) -> Optional[float]:
    candidates: List[float] = []
    for line in lines:
        low = line.lower()
        if any(lbl in low for lbl in labels):
            vals = [float(x.replace(",", "")) for x in _MONEY_RE.findall(line) if float(x.replace(",", "")) > 0]
            if vals:
                candidates.append(vals[-1])
    return max(candidates) if candidates else None


def parse_receipt_text(raw_text: str, filename: str = "") -> Dict[str, Any]:
    """Parse unstructured OCR or PDF text into a structured transaction preview."""
    lines = [ln.strip() for ln in (raw_text or "").splitlines() if ln.strip()]
    joined = "\n".join(lines)
    low = joined.lower()

    txn_date = _extract_date_iso(joined)
    currency = _extract_currency(joined)

    # Distinguish Sales/Invoice credit vs Expense/Receipt debit
    is_income = any(k in low for k in ("sales receipt", "payment received", "credit memo", "payout", "revenue", "salary credit", "payslip", "net pay"))
    tax_amt = _extract_labeled_amount(lines, ("gst", "vat", "tax", "cgst", "sgst")) or 0.0
    total_amt = _extract_labeled_amount(lines, ("grand total", "net total", "total amount", "amount paid", "amount due", "total expense", "total revenue", "balance due", "total", "net pay", "salary"))

    if total_amt is None:
        all_nums = []
        for ln in lines:
            if any(skip in ln.lower() for skip in ("phone", "tel", "gstin", "invoice #", "inv-", "date", "zip", "pin")):
                continue
            for token in _MONEY_RE.findall(ln):
                val = float(token.replace(",", ""))
                if 1.0 <= val <= 1e8:
                    all_nums.append(val)
        total_amt = max(all_nums) if all_nums else 0.0

    revenue = round(total_amt, 2) if is_income else 0.0
    expense = 0.0 if is_income else round(total_amt, 2)

    detected_cat = "Operations" if not is_income else "Sales"
    for cat, kws in _CATEGORY_KEYWORDS.items():
        if any(kw in low for kw in kws):
            detected_cat = cat
            break

    payment = "Bank Transfer"
    if any(k in low for k in ("visa", "mastercard", "card", "credit", "debit")):
        payment = "Corporate Card"
    elif any(k in low for k in ("upi", "gpay", "phonepe", "paytm")):
        payment = "UPI / Instant"
    elif "cash" in low:
        payment = "Cash"

    vendor = "Document Extract"
    for ln in lines[:5]:
        if len(ln) >= 3 and not re.match(r"^(invoice|receipt|tax|bill|date|total)\b", ln, re.I):
            vendor = ln[:80]
            break

    masked_vendor, red1 = mask_pii_text(vendor, enabled=True)
    snippet = " | ".join(lines[:6])[:240]
    masked_notes, red2 = mask_pii_text(f"Document OCR ({filename}): {snippet}" if snippet else f"Document OCR ({filename})", enabled=True)

    return {
        "txn_date": txn_date,
        "transaction_type": "Sale" if is_income else "Operating Expense",
        "category": detected_cat,
        "subcategory": "Scanned Document",
        "product": detected_cat,
        "department": "Finance" if is_income else ("Operations" if detected_cat == "Operations" else "General"),
        "region": "National",
        "vendor_name": masked_vendor,
        "payment_method": payment,
        "currency_code": currency,
        "revenue": revenue,
        "expense": expense,
        "cost": round(expense * 0.4, 2) if expense else 0.0,
        "tax_amount": round(tax_amt, 2),
        "notes": masked_notes,
        "raw_text": joined,
        "pii_redacted": red1 + red2,
        "confidence": 0.92 if lines and total_amt > 0 else (0.62 if lines else 0.25),
        "confidence_label": "High" if lines and total_amt > 0 else ("Partial" if lines else "Low"),
    }


def _ocr_macos_vision(image_path: Path) -> Tuple[str, str]:
    import Foundation
    import Vision

    url = Foundation.NSURL.fileURLWithPath_(str(image_path))
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesCPUOnly_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    ok, _err = handler.performRequests_error_([req], None)
    if not ok or not req.results():
        return "", "Apple Vision (no text)"
    lines = [str(obs.topCandidates_(1)[0].string()) for obs in req.results() if obs.topCandidates_(1)]
    return "\n".join(lines), "Apple Vision (on-device)"


def _ocr_tesseract(image_path: Path) -> Tuple[str, str]:
    exe = shutil.which("tesseract")
    if not exe:
        return "", ""
    proc = subprocess.run([exe, str(image_path), "stdout", "--psm", "6"], capture_output=True, text=True, timeout=10)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip(), "Tesseract CLI (local)"
    return "", ""


def _ocr_windows_winrt(image_path: Path) -> Tuple[str, str]:
    if not sys.platform.startswith("win"):
        return "", ""
    ps_script = (
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
        "$null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]; "
        "$null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]; "
        "$f=[Windows.Storage.StorageFile]::GetFileFromPathAsync($env:FP_OCR_IMG).GetAwaiter().GetResult(); "
        "$s=$f.OpenAsync([Windows.Storage.FileAccessMode]::Read).GetAwaiter().GetResult(); "
        "$d=[Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($s).GetAwaiter().GetResult(); "
        "$b=$d.GetSoftwareBitmapAsync().GetAwaiter().GetResult(); "
        "$e=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages(); "
        "if($e){($e.RecognizeAsync($b).GetAwaiter().GetResult()).Text}"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            env={"FP_OCR_IMG": str(image_path)},
            capture_output=True,
            text=True,
            timeout=12,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip(), "Windows Media OCR (on-device)"
    except Exception:
        pass
    return "", ""


def extract_document_details(file_path: Path) -> Dict[str, Any]:
    """Extract text & structured financial fields from a receipt photo or PDF completely offline."""
    path = Path(file_path)
    ext = path.suffix.lower()
    raw_text = ""
    engine = "Metadata fallback"
    warnings: List[str] = []

    if ext == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages[:8]]
            raw_text = "\n".join(p for p in pages if p.strip())
            engine = "PyPDF (local text)"
            if not raw_text.strip():
                warnings.append("PDF has no selectable text layer; fill or confirm amounts manually.")
        except Exception as exc:
            warnings.append(f"PDF read warning: {exc}")
    else:
        if sys.platform == "darwin":
            try:
                raw_text, engine = _ocr_macos_vision(path)
            except Exception as exc:
                warnings.append(f"Vision OCR unavailable: {exc}")
        if not raw_text and sys.platform.startswith("win"):
            raw_text, engine = _ocr_windows_winrt(path)
        if not raw_text:
            tess_text, tess_eng = _ocr_tesseract(path)
            if tess_text:
                raw_text, engine = tess_text, tess_eng
        if not raw_text:
            try:
                from PIL import Image

                with Image.open(path) as im:
                    info = {str(k): str(v) for k, v in (im.info or {}).items() if isinstance(v, (str, bytes))}
                    if info:
                        raw_text = "\n".join(f"{k}: {v}" for k, v in info.items())
                        engine = "Image metadata fallback"
            except Exception:
                pass
            if not raw_text:
                warnings.append("No text detected on this platform without Tesseract; review & enter amount below.")

    parsed = parse_receipt_text(raw_text, filename=path.name)
    parsed["ocr_engine"] = engine or "Manual review"
    parsed["warnings"] = warnings
    return parsed
