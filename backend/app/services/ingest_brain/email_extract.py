"""F09 EXTRACT (email / HTML / EPUB) — Phase D, GPU-free.

HTML  → BeautifulSoup: every ``<table>`` becomes a RawTable (first row = header)
        and the visible page text (script/style stripped) becomes one ProseBlock.
EML   → stdlib ``email`` (policy.default): the HTML part feeds the HTML table
        logic; the plain-text body becomes a ProseBlock titled with the Subject.
EPUB  → ``ebooklib`` (MAY BE ABSENT): each document item's text becomes a
        ProseBlock (one per chapter, capped). Missing lib → a single note block.

Every reader is lazy-imported and fail-soft: a missing library or a parse error
returns ([], []) (or what it has) and is recorded as a note — never raises into
the ingest path.

Returns (list[RawTable], list[ProseBlock]).
"""
from __future__ import annotations

import logging
import re
from typing import Any, List, Tuple

from app.services.ingest_brain.contract import RawTable, ProseBlock

logger = logging.getLogger(__name__)

_ITEM_CAP = 50          # max EPUB items to ingest
_WS_RE = re.compile(r"\s+")


def _clean(v: Any) -> str:
    """Strip + collapse internal whitespace of a single cell/text value."""
    if v is None:
        return ""
    return _WS_RE.sub(" ", str(v).replace("\xa0", " ")).strip()


def _dedup_header(header: List[str]) -> List[str]:
    """De-duplicate (and backfill blank) header names, preserving order."""
    seen: dict[str, int] = {}
    out: List[str] = []
    for i, h in enumerate(header):
        name = _clean(h) or f"col_{i + 1}"
        if name in seen:
            seen[name] += 1
            out.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 0
            out.append(name)
    return out


def _grid_to_table(name: str, grid: List[List[Any]], source_file: str) -> RawTable | None:
    """Build a RawTable from a list-of-lists. Cleans cells, dedups header,
    pads ragged rows, requires >=2 rows (header + >=1 data). None if too small."""
    try:
        cleaned = [[_clean(c) for c in row] for row in grid if any(_clean(c) for c in row)]
        if len(cleaned) < 2:
            return None
        width = max(len(r) for r in cleaned)
        cleaned = [r + [""] * (width - len(r)) for r in cleaned]
        header = _dedup_header(cleaned[0])
        rows: List[List[Any]] = cleaned[1:]
        return RawTable(
            name=name,
            header=header,
            rows=rows,
            source_file=source_file,
            sheet=None,
            region_bbox=None,
            notes=[f"extracted {len(rows)} rows from <table>"],
        )
    except Exception as e:  # noqa: BLE001 — fail-soft
        logger.debug("_grid_to_table failed: %s", e)
        return None


def _tables_from_soup(soup: Any, source_file: str) -> List[RawTable]:
    """Pull every <table> in a BeautifulSoup tree into RawTables."""
    tables: List[RawTable] = []
    for ti, tbl in enumerate(soup.find_all("table"), 1):
        try:
            grid: List[List[Any]] = []
            for tr in tbl.find_all("tr"):
                cells = tr.find_all(["th", "td"])
                if not cells:
                    continue
                grid.append([c.get_text(separator=" ", strip=True) for c in cells])
            rt = _grid_to_table(f"{(source_file or 'html')}_table_{ti}", grid, source_file)
            if rt is not None:
                tables.append(rt)
        except Exception as e:  # noqa: BLE001 — fail-soft per table
            logger.debug("table %d parse failed: %s", ti, e)
            continue
    return tables


def _prose_from_soup(soup: Any, source_file: str, title: str) -> List[ProseBlock]:
    """Visible text of a BeautifulSoup tree → one ProseBlock (script/style removed)."""
    try:
        for bad in soup(["script", "style", "head", "meta", "link"]):
            bad.extract()
        text = _WS_RE.sub(" ", soup.get_text(separator=" ", strip=True)).strip()
        if not text:
            return []
        return [ProseBlock(title=title, body=text, source_file=source_file, page=None)]
    except Exception as e:  # noqa: BLE001 — fail-soft
        logger.debug("_prose_from_soup failed: %s", e)
        return []


def extract_html(path: str, *, filename: str = "") -> Tuple[List[RawTable], List[ProseBlock]]:
    """HTML file → <table> RawTables + one visible-text ProseBlock. NEVER raises."""
    try:
        from bs4 import BeautifulSoup  # lazy import (lib `bs4` installed)

        with open(path, "rb") as fh:
            raw = fh.read()
        soup = BeautifulSoup(raw, "html.parser")
        src = filename or path
        # parse tables BEFORE prose (prose extraction mutates the tree).
        tables = _tables_from_soup(soup, src)
        prose = _prose_from_soup(soup, src, title=(filename or "HTML document"))
        return tables, prose
    except Exception as e:  # noqa: BLE001 — fail-soft
        logger.warning("extract_html failed for %s: %s", filename or path, e)
        return [], []


def extract_eml(path: str, *, filename: str = "") -> Tuple[List[RawTable], List[ProseBlock]]:
    """.eml file → tables from the HTML part + a ProseBlock titled by Subject. NEVER raises."""
    try:
        from email import message_from_binary_file
        from email.policy import default as default_policy

        with open(path, "rb") as fh:
            msg = message_from_binary_file(fh, policy=default_policy)

        src = filename or path
        subject = _clean(msg.get("subject", "")) or (filename or "Email")

        html_body: str = ""
        text_body: str = ""
        try:
            html_part = msg.get_body(preferencelist=("html",))
            if html_part is not None:
                html_body = html_part.get_content() or ""
        except Exception as e:  # noqa: BLE001
            logger.debug("eml html part failed: %s", e)
        try:
            text_part = msg.get_body(preferencelist=("plain",))
            if text_part is not None:
                text_body = text_part.get_content() or ""
        except Exception as e:  # noqa: BLE001
            logger.debug("eml plain part failed: %s", e)

        tables: List[RawTable] = []
        prose: List[ProseBlock] = []

        if html_body:
            try:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(html_body, "html.parser")
                tables = _tables_from_soup(soup, src)
                if not text_body:
                    text_body = _WS_RE.sub(
                        " ", soup.get_text(separator=" ", strip=True)
                    ).strip()
            except Exception as e:  # noqa: BLE001
                logger.debug("eml html parse failed: %s", e)

        body = _clean(text_body)
        if body:
            prose.append(ProseBlock(title=subject, body=body, source_file=src, page=None))

        return tables, prose
    except Exception as e:  # noqa: BLE001 — fail-soft
        logger.warning("extract_eml failed for %s: %s", filename or path, e)
        return [], []


def extract_epub(path: str, *, filename: str = "") -> Tuple[List[RawTable], List[ProseBlock]]:
    """.epub file → one ProseBlock per chapter/item (capped). NEVER raises.

    ``ebooklib`` may be absent → degrades to a single note ProseBlock.
    """
    src = filename or path
    try:
        try:
            import ebooklib  # noqa: F401 — may be absent
            from ebooklib import epub
        except Exception as imp_err:  # noqa: BLE001 — optional dependency
            logger.info("ebooklib not installed (%s); epub support disabled", imp_err)
            return [], [
                ProseBlock(
                    title=(filename or "EPUB document"),
                    body="epub support not installed",
                    source_file=src,
                    page=None,
                )
            ]

        try:
            from bs4 import BeautifulSoup
        except Exception:  # noqa: BLE001
            BeautifulSoup = None  # type: ignore[assignment]

        book = epub.read_epub(path)
        prose: List[ProseBlock] = []
        count = 0
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            if count >= _ITEM_CAP:
                break
            try:
                content = item.get_content() or b""
                if BeautifulSoup is not None:
                    soup = BeautifulSoup(content, "html.parser")
                    for bad in soup(["script", "style"]):
                        bad.extract()
                    text = _WS_RE.sub(
                        " ", soup.get_text(separator=" ", strip=True)
                    ).strip()
                else:
                    text = _WS_RE.sub(
                        " ", content.decode("utf-8", "ignore")
                    ).strip()
                if not text:
                    continue
                count += 1
                title = _clean(getattr(item, "get_name", lambda: "")()) or f"Chapter {count}"
                prose.append(
                    ProseBlock(title=title, body=text, source_file=src, page=count)
                )
            except Exception as e:  # noqa: BLE001 — fail-soft per item
                logger.debug("epub item parse failed: %s", e)
                continue

        return [], prose
    except Exception as e:  # noqa: BLE001 — fail-soft
        logger.warning("extract_epub failed for %s: %s", filename or path, e)
        return [], []
