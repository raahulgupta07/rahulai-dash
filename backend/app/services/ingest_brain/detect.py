"""F09 DETECT — sniff file type + probe for a text layer (Phase 2).

Routing rule (design §3): born-digital → CPU library; only scanned/image (no
text layer) → OpenRouter vision. This module decides which. NEVER raises.
"""
from __future__ import annotations

import logging
import os

from app.services.ingest_brain.contract import SourceDoc

logger = logging.getLogger(__name__)

_SPREADSHEET = {"xlsx", "xlsm", "csv", "tsv", "txt"}
_LEGACY_XL = {"xls", "xlsb"}                 # old Excel → xlrd / pyxlsb path (P-E)
_DOC = {"docx", "pptx"}
_IMAGE = {"png", "jpg", "jpeg", "tiff", "bmp", "webp"}
_EMAIL = {"eml", "html", "htm", "epub"}      # email / web / ebook (P-D)

# A digital PDF page usually yields plenty of characters; a scanned one yields ~0.
_TEXT_LAYER_MIN_CHARS = 40


def _pdf_has_text_layer(path: str) -> bool:
    """True if the PDF carries an extractable text layer (born-digital)."""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:3]:           # sample first pages only
                txt = (page.extract_text() or "").strip()
                if len(txt) >= _TEXT_LAYER_MIN_CHARS:
                    return True
        return False
    except Exception:  # noqa: BLE001 — try PyMuPDF, else assume scanned
        try:
            import fitz
            doc = fitz.open(path)
            try:
                for page in list(doc)[:3]:
                    if len((page.get_text() or "").strip()) >= _TEXT_LAYER_MIN_CHARS:
                        return True
            finally:
                doc.close()
        except Exception:  # noqa: BLE001
            logger.exception("pdf text-layer probe failed for %s", path)
        return False


def detect(path: str, filename: str) -> SourceDoc:
    """Classify an uploaded file into a SourceDoc with a parser route."""
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    size = 0
    try:
        size = os.path.getsize(path)
    except OSError:
        pass

    if ext in _SPREADSHEET:
        kind, has_text = "spreadsheet", True
    elif ext in _LEGACY_XL:
        kind, has_text = "legacy_excel", True
    elif ext in _EMAIL:
        kind, has_text = "email", True
    elif ext in _DOC:
        kind, has_text = "doc", True
    elif ext in _IMAGE:
        kind, has_text = "image", False           # always vision
    elif ext == "pdf":
        has_text = _pdf_has_text_layer(path)
        kind = "text_pdf" if has_text else "scanned_pdf"
    else:
        kind, has_text = "unknown", True

    return SourceDoc(path=path, filename=filename, ext=ext, kind=kind,
                     has_text_layer=has_text, size_bytes=size)
