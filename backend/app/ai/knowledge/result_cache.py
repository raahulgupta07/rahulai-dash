"""Task 7 — deterministic create_data result cache (flag HYBRID_RESULT_CACHE).

For STATIC data, re-asking the same question rebuilds the dataframe and re-runs
LLM codegen — pure waste. This module caches a create_data result keyed by:

    cache_key = sha256( normalized_question + '|' + watermark_signature )

where the *watermark signature* is the sha256 of the sorted per-table
row-count watermarks (`DataSourceTable.metadata_json["_profile_watermark"]
["row_count"]`, the same value the train/profiling pipeline writes — see
`app/routes/column_profile.py`) across every data source pinned to the report.
Train / new-upload bumps a table's row_count -> the signature changes -> the key
changes -> the entry naturally MISSES -> the result is rebuilt once. We therefore
NEVER serve a stale entry: a different watermark is a different key.

Everything here is best-effort and fail-soft — any error returns "no cache" so
the normal create_data path runs. Nothing in this module imports or touches the
agent loop; the create_data tool calls `lookup` before planning and `store`
after a successful build, both gated on `flags.RESULT_CACHE`.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Must match app/routes/column_profile.py _WATERMARK_KEY.
_WATERMARK_KEY = "_profile_watermark"


def normalize_question(text: str) -> str:
    """Lowercase, collapse whitespace, strip trailing punctuation.

    Deterministic and conservative — two prompts that differ only in casing /
    spacing / a trailing '?' collapse to the same key; anything else stays
    distinct so we never cross-serve different questions.
    """
    if not text:
        return ""
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = t.strip(" \t\r\n?.!")
    return t


async def compute_watermark_signature(
    db: AsyncSession, data_source_ids: List[str]
) -> str:
    """SHA-256 of the sorted (table_id, row_count) watermarks for these sources.

    Reads the SAME per-table watermark the profiling pipeline writes. A source
    with no profiled watermark contributes nothing (its tables just don't appear
    in the signature) — so a never-trained report still gets a stable, if coarse,
    signature. Returns "" on any error (caller treats "" as "do not cache").
    """
    if not data_source_ids:
        return ""
    try:
        from app.models.datasource_table import DataSourceTable

        rows = (
            await db.execute(
                select(DataSourceTable).where(
                    DataSourceTable.datasource_id.in_(list(data_source_ids)),
                    DataSourceTable.deleted_at.is_(None),
                )
            )
        ).scalars().all()

        parts: List[str] = []
        for tbl in rows:
            rc = _read_row_count(tbl)
            # Include EVERY active table id so adding/removing a table also moves
            # the signature; row_count may be None (never profiled) -> 'n'.
            parts.append(f"{tbl.id}:{'n' if rc is None else int(rc)}")
        parts.sort()
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return digest
    except Exception:
        logger.debug("result_cache: watermark signature failed", exc_info=True)
        return ""


def _read_row_count(tbl) -> Optional[int]:
    """Per-table row_count watermark, or None if absent/unreadable.

    Falls back to the legacy `no_rows` column when no profile watermark exists,
    so even an un-trained source contributes a (coarse) row-count signal.
    """
    try:
        meta = getattr(tbl, "metadata_json", None)
        if isinstance(meta, dict):
            wm = meta.get(_WATERMARK_KEY)
            if isinstance(wm, dict) and wm.get("row_count") is not None:
                return int(wm["row_count"])
    except Exception:
        pass
    try:
        nr = getattr(tbl, "no_rows", None)
        return int(nr) if nr is not None else None
    except Exception:
        return None


def make_cache_key(question: str, watermark_sig: str) -> str:
    """Deterministic SHA-256 cache key. Empty when uncacheable (no signature)."""
    qn = normalize_question(question)
    if not qn or not watermark_sig:
        return ""
    return hashlib.sha256(f"{qn}|{watermark_sig}".encode("utf-8")).hexdigest()


async def lookup(
    db: AsyncSession,
    *,
    organization_id: str,
    cache_key: str,
) -> Optional[Dict[str, Any]]:
    """Return a stored `result_json` on a HIT (and bump hit_count), else None.

    Fail-soft: any error returns None so create_data falls through to a rebuild.
    The matching watermark is already baked into `cache_key`, so a HIT is, by
    construction, never stale.
    """
    if not cache_key:
        return None
    try:
        from app.models.result_cache import ResultCacheEntry

        row = (
            await db.execute(
                select(ResultCacheEntry).where(
                    ResultCacheEntry.organization_id == organization_id,
                    ResultCacheEntry.cache_key == cache_key,
                    ResultCacheEntry.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        payload = row.result_json
        if not isinstance(payload, dict) or not payload:
            return None
        try:
            row.hit_count = (row.hit_count or 0) + 1
            await db.flush()
        except Exception:
            pass
        return payload
    except Exception:
        logger.debug("result_cache: lookup failed", exc_info=True)
        return None


async def store(
    db: AsyncSession,
    *,
    organization_id: str,
    report_id: Optional[str],
    cache_key: str,
    question: str,
    watermark_sig: str,
    result_json: Dict[str, Any],
) -> bool:
    """UPSERT a result cache entry by (org, cache_key). Returns True on write.

    Never raises — a cache write must never break a successful create_data turn.
    """
    if not cache_key or not isinstance(result_json, dict) or not result_json:
        return False
    try:
        from app.models.result_cache import ResultCacheEntry

        existing = (
            await db.execute(
                select(ResultCacheEntry).where(
                    ResultCacheEntry.organization_id == organization_id,
                    ResultCacheEntry.cache_key == cache_key,
                    ResultCacheEntry.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.result_json = result_json
            existing.question_norm = normalize_question(question)
            existing.watermark_sig = watermark_sig
            existing.report_id = report_id
        else:
            db.add(
                ResultCacheEntry(
                    organization_id=organization_id,
                    report_id=report_id,
                    cache_key=cache_key,
                    question_norm=normalize_question(question),
                    watermark_sig=watermark_sig,
                    result_json=result_json,
                    hit_count=0,
                )
            )
        await db.flush()
        return True
    except Exception:
        logger.debug("result_cache: store failed", exc_info=True)
        return False
