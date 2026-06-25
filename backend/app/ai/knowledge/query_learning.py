"""Task 8 — live query-learning (flag HYBRID_QUERY_LEARNING).

Today only the TRAIN pass writes example SQL to the query library
(`auto_queries.generate_queries_for_studio` -> QueryLibraryItem). This module
ALSO learns from LIVE create_data runs:

  * On a create_data step SUCCESS, persist its working SQL/approach to the query
    library (`QueryLibraryItem`, born **pending** per the review-gate convention,
    `source='chat'`, tagged with the question + a `win` marker) so future similar
    questions can reuse it.
  * When the run FAILED on earlier attempts then SUCCEEDED on a retry, the
    corrected SQL is the positive example and the failed approach is recorded as a
    down-weighted NEGATIVE note (`StudioInstruction`, pending) so the planner can
    avoid the dead path. Negative notes need a studio (resolved from the report's
    `studio_id`); if the report isn't inside a studio we just skip the note.
  * `recall_learned_queries` injects the closest APPROVED learned queries back
    into the codegen prompt (reuse), mirroring how proven snippets are injected.

Everything is review-gated (born pending/approved-only on read) and fail-soft —
any error is swallowed so a successful turn is never broken. All gated on
`flags.QUERY_LEARNING`; nothing here runs when the flag is off.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Library rows we author from live runs are born pending (review gate). Only
# approved rows are ever recalled into context (approved-only invariant).
_LIVE_SOURCE = "chat"
_LIVE_STATUS_NEW = "pending"
_RECALL_STATUSES = ("approved",)
_MAX_RECALL = 3

# Golden-query promotion threshold: a learned query is promoted to golden once
# it has been verified this many times (thumbs-up OR repeated successful reuse).
_GOLDEN_THRESHOLD = 2


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9_]+", (text or "").lower()))


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _short(text: str, n: int = 60) -> str:
    t = (text or "").strip().replace("\n", " ")
    return t[:n]


def _pick_primary_sql(executed_queries: List[str]) -> Optional[str]:
    """Choose the most representative SQL from a run's executed queries.

    Heuristic: the longest SELECT-ish statement (the run's main query rather than
    a tiny probe). Returns None if nothing usable.
    """
    cands = [q for q in (executed_queries or []) if isinstance(q, str) and q.strip()]
    if not cands:
        return None
    selects = [q for q in cands if re.search(r"\bselect\b", q, re.IGNORECASE)]
    pool = selects or cands
    return max(pool, key=len)


async def _resolve_studio_id(db: AsyncSession, report) -> Optional[str]:
    """The studio this report lives in, or None. Best-effort."""
    try:
        sid = getattr(report, "studio_id", None)
        return str(sid) if sid else None
    except Exception:
        return None


async def capture_live_run(
    db: AsyncSession,
    *,
    organization_id: str,
    data_source_ids: List[str],
    report,
    question: str,
    executed_queries: List[str],
    generated_code: str,
    code_errors: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Persist a successful live run as a learned, review-gated positive example.

    Returns a small summary dict ({saved, negative_noted}). Never raises.
    """
    summary = {"saved": 0, "negative_noted": False}
    try:
        from app.models.query_library import QueryLibraryItem

        sql = _pick_primary_sql(executed_queries)
        if not sql or not data_source_ids:
            return summary
        ds_id = str(data_source_ids[0])
        # Stable, human-readable name keyed by the question so a re-ask UPSERTs the
        # same row instead of spamming the library.
        name = f"learned: {_short(question)}"
        had_failures = bool(code_errors)

        existing = (
            await db.execute(
                select(QueryLibraryItem).where(
                    QueryLibraryItem.organization_id == organization_id,
                    QueryLibraryItem.data_source_id == ds_id,
                    QueryLibraryItem.name == name,
                )
            )
        ).scalar_one_or_none()

        tags = ["learned", "win"]
        if had_failures:
            tags.append("corrected")
        desc = f"Learned from a live successful answer to: {question.strip()[:200]}"

        if existing is not None:
            existing.sql_text = sql
            existing.description = desc
            existing.source = _LIVE_SOURCE
            existing.tags = tags
            # Don't downgrade an already-approved row back to pending.
            if existing.status not in _RECALL_STATUSES:
                existing.status = _LIVE_STATUS_NEW
            # Golden promotion: this question was asked again and succeeded —
            # count as a positive verification signal (gated on GOLDEN_QUERIES).
            await promote_to_golden(db, item=existing, reason="reuse")
        else:
            db.add(
                QueryLibraryItem(
                    organization_id=organization_id,
                    data_source_id=ds_id,
                    name=name,
                    description=desc,
                    sql_text=sql,
                    tags=tags,
                    source=_LIVE_SOURCE,
                    status=_LIVE_STATUS_NEW,
                    run_count=0,
                )
            )
        await db.flush()
        summary["saved"] = 1

        # Fail-then-success: record the dead path as a down-weighted negative note
        # so the planner avoids it. Needs a studio (from report.studio_id).
        if had_failures:
            noted = await _record_negative_note(
                db, report=report, question=question, code_errors=code_errors,
            )
            summary["negative_noted"] = noted
    except Exception:
        logger.debug("query_learning.capture_live_run failed", exc_info=True)
    return summary


async def _record_negative_note(
    db: AsyncSession, *, report, question: str, code_errors: List[Any]
) -> bool:
    """Write a pending StudioInstruction warning about a failed approach.

    Born `pending` (review gate) and only reaches the agent once a human flips it
    to `active`. No-op (returns False) when the report isn't inside a studio.
    """
    try:
        studio_id = await _resolve_studio_id(db, report)
        if not studio_id:
            return False
        from app.models.studio import StudioInstruction

        # code_errors is a list of (code, error_message) tuples from the executor.
        last_err = ""
        try:
            if code_errors:
                tail = code_errors[-1]
                last_err = str(tail[1] if isinstance(tail, (list, tuple)) and len(tail) > 1 else tail)
        except Exception:
            last_err = ""
        content = (
            f"AVOID (learned from a failed attempt) for questions like "
            f"\"{_short(question, 120)}\": a prior approach failed with: "
            f"{last_err[:240]}. Prefer the corrected query saved in the query "
            f"library for this question."
        )
        # De-dupe: don't pile identical pending notes for the same studio.
        existing = (
            await db.execute(
                select(StudioInstruction).where(
                    StudioInstruction.studio_id == studio_id,
                    StudioInstruction.content == content,
                    StudioInstruction.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                StudioInstruction(
                    studio_id=studio_id,
                    content=content,
                    source="auto",
                    status="pending",
                    score=-1.0,  # down-weighted negative
                )
            )
            await db.flush()
        return True
    except Exception:
        logger.debug("query_learning._record_negative_note failed", exc_info=True)
        return False


async def promote_to_golden(
    db: AsyncSession,
    *,
    item,
    reason: str = "verified",
) -> bool:
    """Increment verified_count on *item* and promote to golden when threshold met.

    Gated on flags.GOLDEN_QUERIES — when the flag is OFF this is an exact no-op
    (returns False immediately, touches no DB columns). When ON: increments
    `verified_count` and sets `is_golden=True` once verified_count reaches
    _GOLDEN_THRESHOLD. Never raises; fail-soft → returns False on error.

    Args:
        db:     Active async session; caller must commit/flush after.
        item:   A QueryLibraryItem ORM instance (already loaded in-session).
        reason: Informational tag (logged at DEBUG); e.g. 'thumbs-up' or 'reuse'.
    Returns:
        True if `is_golden` was flipped to True in this call; False otherwise.
    """
    try:
        from app.settings.hybrid_flags import flags
        if not flags.GOLDEN_QUERIES:
            return False

        # Safely access columns — guard against old rows that pre-date the migration
        # (columns would be None on models loaded before alembic ran).
        current_count = (getattr(item, "verified_count", None) or 0)
        current_golden = (getattr(item, "is_golden", None) or False)

        new_count = current_count + 1
        item.verified_count = new_count

        newly_golden = False
        if not current_golden and new_count >= _GOLDEN_THRESHOLD:
            item.is_golden = True
            newly_golden = True
            logger.debug(
                "query_learning: query '%s' promoted to golden (%s, verified_count=%d)",
                getattr(item, "name", "?"),
                reason,
                new_count,
            )
        else:
            logger.debug(
                "query_learning: query '%s' verified_count=%d reason=%s golden=%s",
                getattr(item, "name", "?"),
                new_count,
                reason,
                current_golden,
            )
        await db.flush()
        return newly_golden
    except Exception:
        logger.debug("query_learning.promote_to_golden failed", exc_info=True)
        return False


async def recall_learned_queries(
    db: AsyncSession,
    *,
    organization_id: str,
    data_source_ids: List[str],
    question: str,
    limit: int = _MAX_RECALL,
) -> List[Dict[str, str]]:
    """Return the closest APPROVED learned queries for reuse in the codegen prompt.

    Approved-only (review-gate invariant), scoped to the run's data sources,
    ranked by token-Jaccard between the stored description/name and the question.
    Returns [] on any error or when the flag is off.
    """
    try:
        from app.settings.hybrid_flags import flags
        if not flags.QUERY_LEARNING or not question or not data_source_ids:
            return []
        from app.models.query_library import QueryLibraryItem

        rows = (
            await db.execute(
                select(QueryLibraryItem).where(
                    QueryLibraryItem.organization_id == organization_id,
                    QueryLibraryItem.data_source_id.in_([str(d) for d in data_source_ids]),
                    QueryLibraryItem.status.in_(list(_RECALL_STATUSES)),
                    QueryLibraryItem.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        if not rows:
            return []
        scored = []
        for r in rows:
            score = max(
                _jaccard(question, r.description or ""),
                _jaccard(question, r.name or ""),
            )
            if score > 0.0:
                scored.append((score, r))

        # Golden queries rank first when the flag is ON. The golden tiebreak is
        # a boolean key (True > False in descending sort), so within the same
        # relevance band golden rows bubble up. When GOLDEN_QUERIES is OFF the
        # sort key is identical to the original (score-only), preserving existing
        # behaviour byte-for-byte.
        from app.settings.hybrid_flags import flags as _gflags
        if _gflags.GOLDEN_QUERIES:
            scored.sort(
                key=lambda t: (t[0], bool(getattr(t[1], "is_golden", False))),
                reverse=True,
            )
        else:
            scored.sort(key=lambda t: t[0], reverse=True)

        out: List[Dict[str, str]] = []
        for _, r in scored[: max(0, int(limit))]:
            out.append({
                "name": r.name or "",
                "description": r.description or "",
                "sql": r.sql_text or "",
            })
        return out
    except Exception:
        logger.debug("query_learning.recall_learned_queries failed", exc_info=True)
        return []


def render_learned_queries_block(items: List[Dict[str, str]]) -> str:
    """Render recalled learned queries as a codegen-prompt reuse block.

    Empty string when there is nothing to inject (so the prompt is byte-identical
    when the flag is off / nothing matches).
    """
    if not items:
        return ""
    parts = ["<learned_queries>"]
    for it in items:
        parts.append(
            f"-- {it.get('name','')}: {it.get('description','')}\n{it.get('sql','')}"
        )
    parts.append("</learned_queries>")
    return "\n".join(parts)
