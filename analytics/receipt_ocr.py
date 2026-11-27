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
    "Healthcare": ("hospital", "clinic", "medical", "pharmacy", "doctor", "dr.", "medicine", "patient", "op bill", "ip bill", "lab", "diagnostic", "consultation", "speciality", "apollo", "medplus", "1mg"),
    "Education": ("college", "school", "university", "tuition", "semester", "exam fee", "stationery", "textbook"),
    "Software": ("aws", "azure", "google cloud", "saas", "software", "license", "github", "adobe", "hosting", "cloud", "zoom", "microsoft 365", "workspace"),
    "Utilities & Telecom": ("electricity", "water bill", "tneb", "bescom", "airtel", "jio", "broadband", "fibernet", "recharge", "gas bill", "internet"),
    "Travel": ("petrol", "diesel", "fuel", "hpcl", "bpcl", "iocl", "indian oil", "shell", "airline", "flight", "hotel", "uber", "ola", "rapido", "cab", "rail", "irctc", "metro", "fastag", "toll", "boarding"),
    "Groceries & Dining": ("restaurant", "cafe", "coffee", "mart", "supermarket", "kirana", "dining", "food", "bakery", "swiggy", "zomato", "blinkit", "zepto", "bigbasket", "dmart", "reliance fresh", "bakers", "bhavan", "mess", "tiffin", "biryani", "idli", "snacks", "lunch", "dinner", "breakfast"),
    "Shopping & Retail": ("amazon", "flipkart", "myntra", "apparel", "clothing", "electronics", "croma", "reliance digital", "pothys", "retail"),
    "Consulting": ("consulting", "advisory", "audit", "legal", "retainer", "agency", "services"),
    "Operations": ("office", "rent", "lease", "maintenance", "courier", "logistics", "shipping"),
    "Payroll": ("salary", "payroll", "wages", "stipend", "bonus", "compensation"),
}

_DATE_PATTERNS = [
    (re.compile(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})[-/\s]+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/\s,]+(20\d{2})\b", re.I), "dmony"),
    (re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/\s]+(\d{1,2})[-/\s,]+(20\d{2})\b", re.I), "mondy"),
]
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONEY_RE = re.compile(
    r"(?:INR|Rs\.?|USD|\$|EUR|€|GBP|£|₹)?\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)(?![0-9])",
    re.I,
)
_HAS_CURR_PREFIX_RE = re.compile(r"(?:INR|Rs\.?|USD|\$|EUR|€|GBP|£|₹)", re.I)


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


_SKIP_LINE_WORDS = (
    "phone", "tel", "mobile", "helpdesk", "+91", "gstin", "invoice #", "inv-",
    "date", "zip", "pin", "salai", "road", "street", "dist", "district", "nadu",
    "patient code", "visit id", "bill no", "reg no", "hsn", "sac", "fssai",
    "cin:", "pan:", "tan:", "order id", "txn id", "utr", "ref no",
)
_EXCLUDED_TOTAL_WORDS = (
    "sub total", "subtotal", "sub-total", "total qty", "total items", "total units",
    "total weight", "total savings", "total discount", "cash tendered", "tendered",
    "change due", "balance change", "mrp total",
)


def _is_pin_or_id(token: str, val: float, has_curr: bool = False) -> bool:
    if "." not in token and "," not in token and not has_curr:
        # Bare 5+ digit integers without decimals/currency are almost always PIN codes, HSN codes, invoice IDs, or phone numbers
        if len(token) >= 5:
            return True
    if "." not in token and "," not in token:
        if 100000 <= val <= 899999 and len(token) == 6:
            return True
        if len(token) >= 8:
            return True
    return False


def _extract_line_amounts(line: str) -> List[Tuple[float, bool]]:
    out: List[Tuple[float, bool]] = []
    for m in _MONEY_RE.finditer(line):
        tok = m.group(1)
        val = float(tok.replace(",", ""))
        prefix_slice = line[max(0, m.start() - 5):m.start() + 4]
        has_curr = bool(_HAS_CURR_PREFIX_RE.search(prefix_slice))
        if val > 0 and not _is_pin_or_id(tok, val, has_curr=has_curr):
            out.append((val, "." in tok or "," in tok or has_curr))
    return out


def _extract_labeled_amount(lines: List[str], labels: Tuple[str, ...], sum_matches: bool = False, exclude: Tuple[str, ...] = ()) -> Optional[float]:
    candidates: List[float] = []
    for idx, line in enumerate(lines):
        low = line.lower()
        if exclude and any(ex in low for ex in exclude):
            continue
        if any(lbl in low for lbl in labels):
            vals = _extract_line_amounts(line)
            if vals:
                candidates.append(vals[-1][0])
            else:
                # Look ahead up to 6 lines for columnar OCR layouts (label block followed by value block)
                for look in range(idx + 1, min(len(lines), idx + 7)):
                    cand_line = lines[look]
                    if any(skip in cand_line.lower() for skip in _SKIP_LINE_WORDS):
                        continue
                    look_vals = [v for v, is_fmt in _extract_line_amounts(cand_line) if is_fmt]
                    if look_vals:
                        candidates.append(look_vals[-1])
                        break
    if not candidates:
        return None
    return round(sum(candidates), 2) if sum_matches else max(candidates)


def _extract_tax_amount(lines: List[str]) -> float:
    cgst = _extract_labeled_amount(lines, ("cgst",), sum_matches=True)
    sgst = _extract_labeled_amount(lines, ("sgst",), sum_matches=True)
    igst = _extract_labeled_amount(lines, ("igst",), sum_matches=True)
    if cgst or sgst or igst:
        return round((cgst or 0.0) + (sgst or 0.0) + (igst or 0.0), 2)
    return _extract_labeled_amount(lines, ("service tax", "gst", "vat", "tax"), exclude=("tax invoice", "gstin", "taxable", "before tax")) or 0.0


def parse_receipt_text(raw_text: str, filename: str = "") -> Dict[str, Any]:
    """Parse unstructured OCR or PDF text into a structured transaction preview."""
    lines = [ln.strip() for ln in (raw_text or "").splitlines() if ln.strip()]
    joined = "\n".join(lines)
    low = joined.lower()

    txn_date = _extract_date_iso(joined)
    currency = _extract_currency(joined)

    # Distinguish Sales/Invoice credit vs Expense/Receipt debit (use word boundary for 'net pay' so 'net payable' isn't matched)
    is_income = (
        any(k in low for k in ("sales receipt", "payment received", "credit memo", "payout", "salary credit", "salary slip", "payslip", "credited to"))
        or bool(re.search(r"\bnet pay\b", low))
    )
    tax_amt = _extract_tax_amount(lines)

    # Strict tiered total matching: final payable total beats subtotal / cash tendered
    total_amt = _extract_labeled_amount(
        lines,
        ("grand total", "net payable", "amount payable", "net amount", "net total", "total payable", "invoice total", "bill total", "total amount", "amount due", "balance due"),
        exclude=_EXCLUDED_TOTAL_WORDS,
    )
    if total_amt is None:
        total_amt = _extract_labeled_amount(
            lines,
            ("amount paid", "total due", "total", "net pay", "salary"),
            exclude=_EXCLUDED_TOTAL_WORDS,
        )

    if total_amt is None:
        decimal_nums = []
        all_nums = []
        for ln in lines:
            if any(skip in ln.lower() for skip in _SKIP_LINE_WORDS):
                continue
            for val, is_fmt in _extract_line_amounts(ln):
                if 1.0 <= val <= 1e7:
                    all_nums.append(val)
                    if is_fmt:
                        decimal_nums.append(val)
        total_amt = max(decimal_nums) if decimal_nums else (max(all_nums) if all_nums else 0.0)

    if total_amt > 0 and tax_amt >= total_amt * 0.5:
        tax_amt = 0.0

    revenue = round(total_amt, 2) if is_income else 0.0
    expense = 0.0 if is_income else round(total_amt, 2)

    detected_cat = "Operations" if not is_income else "Sales"
    for cat, kws in _CATEGORY_KEYWORDS.items():
        if any(kw in low for kw in kws):
            detected_cat = cat
            break
    if detected_cat == "Operations" and any(k in low for k in ("upi transaction id", "google pay", "phonepe", "paytm", "paid to", "sent to")):
        detected_cat = "UPI Transfer"

    payment = "Bank Transfer"
    if any(k in low for k in ("upi", "gpay", "google pay", "phonepe", "paytm", "bhim")):
        payment = "UPI / Instant"
    elif any(k in low for k in ("visa", "mastercard", "rupay", "amex", "credit card", "debit card", "card")):
        payment = "Card"
    elif "cash" in low:
        payment = "Cash"

    vendor = "Document Extract"
    for ln in lines[:8]:
        if len(ln) >= 3 and not re.match(r"^(tax invoice|invoice|receipt|bill of supply|cash memo|retail invoice|welcome to|gstin|cin|pan|bill|date|total|page)\b", ln, re.I):
            cleaned_v = re.sub(r"^(?:to|paid to|from)\s*[:\-]?\s+", "", ln, flags=re.I).strip()
            vendor = (cleaned_v or ln)[:80]
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
