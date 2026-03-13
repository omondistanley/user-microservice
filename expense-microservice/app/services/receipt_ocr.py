"""
Receipt OCR: run Tesseract on receipt image bytes and parse amount/date/merchant.
Requires tesseract-ocr installed on the system. Optional dependency.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _run_tesseract(image_bytes: bytes) -> Optional[str]:
    """Run tesseract on image bytes. Returns raw text or None if tesseract unavailable."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(image_bytes)
            path = f.name
        try:
            out = subprocess.run(
                ["tesseract", path, "stdout", "-l", "eng"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if out.returncode == 0 and out.stdout:
                return out.stdout.strip()
            return None
        finally:
            Path(path).unlink(missing_ok=True)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def is_tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _parse_amount(text: str) -> Optional[float]:
    """Extract first plausible total/amount from text (e.g. $12.34, 12.34, TOTAL 12.34)."""
    if not text:
        return None
    # Prefer line containing "total" or "amount" then number
    for pattern in [
        r"(?:total|amount|sum|balance)\s*[:\s]*\$?\s*([\d,]+\.?\d*)",
        r"\$\s*([\d,]+\.?\d*)",
        r"(?<!\d)([\d,]+\.\d{2})(?!\d)",
    ]:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            try:
                val = float(m.group(1).replace(",", ""))
                if 0 < val < 1e7:
                    return val
            except ValueError:
                continue
    return None


def _parse_date(text: str) -> Optional[str]:
    """Extract first plausible date (YYYY-MM-DD)."""
    if not text:
        return None
    for pattern in [
        r"(\d{4})-(\d{2})-(\d{2})",
        r"(\d{2})/(\d{2})/(\d{4})",
        r"(\d{2})-(\d{2})-(\d{4})",
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})",
    ]:
        m = re.search(pattern, text)
        if m:
            g = m.groups()
            if len(g) == 3:
                try:
                    if len(g[0]) == 4:  # YYYY-MM-DD
                        y, mo, d = int(g[0]), int(g[1]), int(g[2])
                    else:
                        mo, d, y = int(g[0]), int(g[1]), int(g[2])
                    if 1 <= mo <= 12 and 1 <= d <= 31 and 1990 <= y <= 2030:
                        return f"{y:04d}-{mo:02d}-{d:02d}"
                except (ValueError, IndexError):
                    continue
    return None


def _parse_merchant(text: str) -> Optional[str]:
    """Use first non-empty, non-number line as merchant/description (trimmed)."""
    if not text:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 2:
            continue
        if re.match(r"^[\d\s\$\.\,\-]+$", line):
            continue
        if line.upper().startswith(("TOTAL", "AMOUNT", "DATE", "SUB")):
            continue
        return line[:500]
    return None


def run_ocr(image_bytes: bytes) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Run Tesseract on image bytes and parse amount, date, merchant.
    Returns (raw_text, extracted_dict). extracted_dict has keys: amount, date, description.
    """
    raw = _run_tesseract(image_bytes)
    extracted: Dict[str, Any] = {}
    if raw:
        amount = _parse_amount(raw)
        if amount is not None:
            extracted["amount"] = amount
        date_str = _parse_date(raw)
        if date_str:
            extracted["date"] = date_str
        merchant = _parse_merchant(raw)
        if merchant:
            extracted["description"] = merchant
    extracted["diagnostics"] = {
        "tesseract_available": is_tesseract_available(),
        "raw_text_length": len(raw or ""),
        "field_count": len([k for k in extracted.keys() if k != "diagnostics"]),
    }
    return (raw, extracted)
