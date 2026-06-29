"""F09 EXTRACT (scanned / image) — GPU-free via OpenRouter vision (Phase 2).

ONLY pages with no text layer reach this module (DETECT routes born-digital to
CPU libs). Each page/image is rendered to PNG and sent to an OpenRouter
vision-capable model that returns table rows as JSON. Results are cached by
content hash so a re-dropped file never re-pays the vision cost.

Decoupled by design: the caller passes a ``vision_infer(image_bytes, prompt)``
callable (wired to the org's OpenRouter provider at the route layer, same
pattern excel_reader uses for its LLM rescue). With no callable → returns ([],
[]) and a note; nothing breaks. NEVER raises.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any, Callable, List, Optional, Tuple

from app.services.ingest_brain.contract import RawTable, ProseBlock

logger = logging.getLogger(__name__)

_VISION_PROMPT = (
    "You are reading a scanned document image. Extract any TABLE you see as "
    "strict JSON: {\"tables\":[{\"name\":str,\"header\":[str],\"rows\":[[cell,...]]}],"
    "\"text\":str}. Use the visible column headers. If there is no table, return "
    "an empty tables array and put the readable text in \"text\". Output ONLY the "
    "JSON object, no prose, no code fences. Never invent values you cannot see."
)
_MAX_PAGES = 15            # cap vision spend per document


def _render_pages_to_png(path: str, ext: str) -> List[bytes]:
    """Render a scanned PDF (or pass an image) to a list of PNG byte blobs."""
    out: List[bytes] = []
    try:
        if ext in ("png", "jpg", "jpeg", "tiff", "bmp", "webp"):
            with open(path, "rb") as f:
                out.append(f.read())
            return out
        # PDF → page images via PyMuPDF (no GPU)
        import fitz
        doc = fitz.open(path)
        try:
            for page in list(doc)[:_MAX_PAGES]:
                pix = page.get_pixmap(dpi=150)
                out.append(pix.tobytes("png"))
        finally:
            doc.close()
    except Exception:  # noqa: BLE001
        logger.exception("vision render failed for %s", path)
    return out


def _parse_json(text: str) -> Optional[dict]:
    try:
        t = re.sub(r"```[a-zA-Z]*", "", str(text)).replace("```", "").strip()
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if not m:
            return None
        blob = re.sub(r",\s*([}\]])", r"\1", m.group(0))
        obj = json.loads(blob)
        return obj if isinstance(obj, dict) else None
    except Exception:  # noqa: BLE001
        return None


def extract_vision(
    path: str, ext: str, *, filename: str = "",
    vision_infer: Optional[Callable[[bytes, str], str]] = None,
    content_hash: str = "",
    cache_lookup: Optional[Callable[[str], Any]] = None,
    cache_save: Optional[Callable[[str, Any], None]] = None,
) -> Tuple[List[RawTable], List[ProseBlock]]:
    """Scanned/image → tables + prose via vision. NEVER raises.

    Returns ([], [ProseBlock(note)]) when no vision callable is supplied so the
    caller can still surface "needs vision — not configured" in the preview.
    """
    if vision_infer is None:
        return [], [ProseBlock(title=filename or "scanned",
                               body="(scanned/image file — vision extraction not configured)",
                               source_file=filename)]

    # cache hit?
    if cache_lookup and content_hash:
        try:
            cached = cache_lookup(content_hash)
            if cached:
                return _from_payload(cached, filename)
        except Exception:  # noqa: BLE001
            pass

    tables: List[RawTable] = []
    prose: List[ProseBlock] = []
    payload_pages: List[dict] = []
    try:
        pages = _render_pages_to_png(path, ext)
        for pi, png in enumerate(pages, 1):
            try:
                raw = vision_infer(png, _VISION_PROMPT)
                obj = _parse_json(raw) or {}
                payload_pages.append(obj)
                for ti, t in enumerate(obj.get("tables", []) or []):
                    header = [str(h) for h in (t.get("header") or [])]
                    rows = [[c for c in r] for r in (t.get("rows") or [])]
                    if header and rows:
                        tables.append(RawTable(
                            name=t.get("name") or f"scan_p{pi}_t{ti+1}",
                            header=header, rows=rows, source_file=filename,
                            sheet=f"page_{pi}", notes=[f"vision-extracted, page {pi}"]))
                txt = (obj.get("text") or "").strip()
                if txt:
                    prose.append(ProseBlock(title=f"{filename} — page {pi}", body=txt,
                                            source_file=filename, page=pi))
            except Exception:  # noqa: BLE001 — skip bad page
                logger.exception("vision page %s failed", pi)
                continue
        if cache_save and content_hash:
            try:
                cache_save(content_hash, {"pages": payload_pages})
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        logger.exception("extract_vision failed for %s", path)
    return tables, prose


def _from_payload(cached: Any, filename: str) -> Tuple[List[RawTable], List[ProseBlock]]:
    tables: List[RawTable] = []
    prose: List[ProseBlock] = []
    try:
        for pi, obj in enumerate(cached.get("pages", []), 1):
            for ti, t in enumerate(obj.get("tables", []) or []):
                header = [str(h) for h in (t.get("header") or [])]
                rows = [[c for c in r] for r in (t.get("rows") or [])]
                if header and rows:
                    tables.append(RawTable(name=t.get("name") or f"scan_p{pi}_t{ti+1}",
                                           header=header, rows=rows, source_file=filename,
                                           sheet=f"page_{pi}", notes=[f"vision (cached), page {pi}"]))
            txt = (obj.get("text") or "").strip()
            if txt:
                prose.append(ProseBlock(title=f"{filename} — page {pi}", body=txt,
                                        source_file=filename, page=pi))
    except Exception:  # noqa: BLE001
        pass
    return tables, prose
