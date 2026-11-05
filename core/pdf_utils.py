import os
import re
from decimal import Decimal, InvalidOperation


def _find_tessdata():
    """
    Work out where the Tesseract language files ('tessdata' folder) live,
    so OCR works even if TESSDATA_PREFIX was never set in Windows.
    Priority: Django setting > env var > common install locations.
    """
    # 1) Allow overriding from settings.py: TESSDATA_PREFIX = r"C:\Program Files\Tesseract-OCR\tessdata"
    try:
        from django.conf import settings
        configured = getattr(settings, "TESSDATA_PREFIX", None)
        if configured and os.path.isdir(configured):
            return configured
    except Exception:
        pass

    # 2) Environment variable, if already set on the machine
    env_path = os.environ.get("TESSDATA_PREFIX")
    if env_path and os.path.isdir(env_path):
        return env_path

    # 3) Common default install locations
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tessdata",
        r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/local/share/tessdata",
        "/opt/homebrew/share/tessdata",
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c

    return None


def extract_fee_summary(pdf_path):
    """
    Uses only PyMuPDF – no Poppler required.
    Falls back to OCR if the PDF has no text layer.
    """
    import pymupdf  # or fitz

    text = ""
    used_ocr = False
    error = None

    try:
        doc = pymupdf.open(pdf_path)

        # First try normal text extraction
        for page in doc:
            text += page.get_text() + "\n"

        # If almost no text → do OCR page by page
        if len(text.strip()) < 80:
            used_ocr = True
            text = ""
            tessdata = _find_tessdata()
            if tessdata is None:
                doc.close()
                return {
                    "total_fees": None,
                    "fees_paid": None,
                    "outstanding": None,
                    "raw_text": "",
                    "error": (
                        "This PDF has no selectable text (it's a scanned image), so it needs "
                        "OCR to be read, but Tesseract OCR isn't installed on this server. "
                        "Install Tesseract and either set TESSDATA_PREFIX to its 'tessdata' "
                        "folder, or add TESSDATA_PREFIX to settings.py."
                    ),
                    "used_ocr": used_ocr,
                }
            for page in doc:
                # This uses Tesseract under the hood
                tp = page.get_textpage_ocr(dpi=300, full=True, tessdata=tessdata)
                text += page.get_text(textpage=tp) + "\n"

        doc.close()
    except Exception as e:
        return {
            "total_fees": None,
            "fees_paid": None,
            "outstanding": None,
            "raw_text": "",
            "error": str(e),
            "used_ocr": used_ocr
        }

    if not text.strip():
        return {
            "total_fees": None,
            "fees_paid": None,
            "outstanding": None,
            "raw_text": "",
            "error": "No text extracted (even with OCR). Is Tesseract installed?",
            "used_ocr": used_ocr
        }

    raw = text
    # IMPORTANT: strip thousands-separator commas WITHOUT turning them into a
    # space first. "31,766.00" must become "31766.00", not "31 766.00" —
    # the old version replaced any run of commas/whitespace with a single
    # space, which chopped numbers like "31,766.00" into "31" + "766.00"
    # and made every amount below get parsed as just "31".
    clean = text.replace(",", "")
    clean = re.sub(r"\s+", " ", clean)
    clean_upper = clean.upper()

    outstanding = total_fees = fees_paid = None

    # Outstanding
    due_patterns = [
        r"DUE TO US[:\s]*R?\s*([\d]+(?:\.\d{1,2})?)",
        r"AMOUNT DUE[:\s]*R?\s*([\d]+(?:\.\d{1,2})?)",
        r"BALANCE DUE[:\s]*R?\s*([\d]+(?:\.\d{1,2})?)",
        r"OUTSTANDING BALANCE[:\s]*R?\s*([\d]+(?:\.\d{1,2})?)",
        r"OUTSTANDING[:\s]*R?\s*([\d]+(?:\.\d{1,2})?)",
    ]
    for p in due_patterns:
        m = re.search(p, clean_upper, re.DOTALL)
        if m:
            try:
                outstanding = Decimal(m.group(1))
                break
            except:
                pass

    if outstanding is None:
        pos = clean_upper.find("DUE TO US")
        if pos != -1:
            after = clean_upper[pos:pos+400]
            for num in re.findall(r"([\d]+(?:\.\d{1,2})?)", after):
                try:
                    val = Decimal(num)
                    if val > 50:
                        outstanding = val
                        break
                except:
                    continue

    # Paid
    for p in [r"TOTAL CREDITS?[:\s]*R?\s*([\d]+(?:\.\d{1,2})?)",
              r"TOTAL PAID[:\s]*R?\s*([\d]+(?:\.\d{1,2})?)"]:
        m = re.search(p, clean_upper)
        if m:
            try:
                fees_paid = abs(Decimal(m.group(1)))
                break
            except:
                pass

    # Total fees
    for p in [r"TOTAL DEBITS?[:\s]*R?\s*([\d]+(?:\.\d{1,2})?)",
              r"TOTAL FEES?[:\s]*R?\s*([\d]+(?:\.\d{1,2})?)"]:
        m = re.search(p, clean_upper)
        if m:
            try:
                total_fees = Decimal(m.group(1))
                break
            except:
                pass

    # Fallbacks
    if outstanding and fees_paid and not total_fees:
        total_fees = outstanding + fees_paid
    if total_fees and outstanding and not fees_paid:
        fees_paid = total_fees - outstanding
    if outstanding and not total_fees and not fees_paid:
        total_fees = outstanding
        fees_paid = Decimal("0.00")

    return {
        "total_fees": total_fees,
        "fees_paid": fees_paid,
        "outstanding": outstanding,
        "raw_text": raw[-2500:],
        "error": error,
        "used_ocr": used_ocr
    }