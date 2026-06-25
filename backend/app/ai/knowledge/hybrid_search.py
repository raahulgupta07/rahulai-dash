"""Hybrid full-text search over the knowledge_search_index table (P8 scaffold).

Gated by flags.SEMANTIC_SEARCH (default OFF).  When OFF callers receive [] and
this module is a no-op.  When ON it combines:

  1. PostgreSQL full-text rank (ts_rank / to_tsquery on the pre-built ``tsv``
     column) — gives BM25-ish relevance using the existing PG machinery.
  2. Token-Jaccard fallback — the same ``normalize_question / _tokens / _jaccard``
     idiom used by ``app.ai.brain.query_cache_store`` and
     ``app.ai.context.builders.skill_context_builder``.  Applied as a secondary
     scorer when PG FTS is unavailable (SQLite dev) or when the tsvector column
     is null for a row.
  3. Reciprocal Rank Fusion (RRF, k=60) — merges the two ranked lists into a
     single score without needing score normalization.

There is NO embedder in the image (vectorless design).  The ``embedding``
(vector) column added by hybridsearch1 is reserved for a future wave when an
embedder is provisioned; it is never read or written here.

Usage (from a caller, once wired into the agent prompt — later wave)::

    from app.settings.hybrid_flags import flags
    from app.ai.knowledge.hybrid_search import hybrid_search

    if flags.SEMANTIC_SEARCH:
        hits = await hybrid_search(db, org_id=org_id, query=user_question, k=5)
        # hits: list of dicts with keys: id, kind, ref_id, title, body, score
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

log = logging.getLogger(__name__)

# Reciprocal Rank Fusion constant (standard k=60 from the original RRF paper).
_RRF_K = 60

# Maximum rows fetched from each ranked list before merging.
_FETCH_LIMIT = 50


# ---------------------------------------------------------------------------
# Internal helpers (token-Jaccard, mirrors query_cache_store / skill_context_builder)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Normalize + tokenize exactly like query_cache_store._tokens."""
    # Re-use the shared helpers when available; fall back to inline impl so
    # this module stays importable even in minimal test environments.
    try:
        from app.ai.brain.query_cache_store import normalize_question, _tokens  # noqa: WPS433
        return _tokens(normalize_question(text))
    except Exception:
        import re
        _WS = re.compile(r"\s+")
        words = _WS.sub(" ", text.strip().lower()).split()
        # Minimal stop-word list (mirrors query_cache_store._STOP)
        _STOP = {"a", "an", "the", "is", "of", "in", "on", "at", "to", "for",
                 "and", "or", "but", "not", "with", "by"}
        return {w for w in words if w and w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _rrf_score(rank: int, k: int = _RRF_K) -> float:
    """Reciprocal Rank Fusion score for a result at 1-based ``rank``."""
    return 1.0 / (k + rank)


# ---------------------------------------------------------------------------
# PG full-text search (dialect-gated)
# ---------------------------------------------------------------------------

async def _pg_fts_rank(
    db: Any,
    org_id: str,
    query: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """Return rows ranked by ts_rank (PG-only).

    Returns [] on any error or when not on PostgreSQL.
    """
    from sqlalchemy import text as sa_text  # noqa: WPS433

    sql = sa_text(
        """
        SELECT
            id,
            kind,
            ref_id,
            title,
            body,
            ts_rank(tsv, plainto_tsquery('english', :q)) AS fts_score
        FROM knowledge_search_index
        WHERE
            org_id = :org_id
            AND deleted_at IS NULL
            AND tsv @@ plainto_tsquery('english', :q)
        ORDER BY fts_score DESC
        LIMIT :lim
        """
    )
    try:
        result = await db.execute(sql, {"q": query, "org_id": org_id, "lim": limit})
        rows = result.fetchall()
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "ref_id": r.ref_id,
                "title": r.title or "",
                "body": r.body or "",
            }
            for r in rows
        ]
    except Exception as exc:
        log.debug("hybrid_search: PG FTS failed (%s), falling back", exc)
        return []


# ---------------------------------------------------------------------------
# Token-Jaccard fallback (dialect-agnostic)
# ---------------------------------------------------------------------------

async def _jaccard_rank(
    db: Any,
    org_id: str,
    query: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """Fetch all index rows for the org and rank by token-Jaccard.

    Fails soft to [] on any error.
    """
    from sqlalchemy import text as sa_text  # noqa: WPS433

    sql = sa_text(
        """
        SELECT id, kind, ref_id, title, body
        FROM knowledge_search_index
        WHERE org_id = :org_id AND deleted_at IS NULL
        LIMIT :lim
        """
    )
    try:
        result = await db.execute(sql, {"org_id": org_id, "lim": limit})
        rows = result.fetchall()
    except Exception as exc:
        log.debug("hybrid_search: Jaccard fetch failed (%s)", exc)
        return []

    if not rows:
        return []

    q_toks = _tokenize(query)
    if not q_toks:
        return []

    scored: list[tuple[float, dict]] = []
    for r in rows:
        candidate = f"{r.title or ''} {r.body or ''}"
        score = _jaccard(q_toks, _tokenize(candidate))
        if score > 0.0:
            scored.append((score, {
                "id": r.id,
                "kind": r.kind,
                "ref_id": r.ref_id,
                "title": r.title or "",
                "body": r.body or "",
            }))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [item for _, item in scored[:limit]]


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion merge
# ---------------------------------------------------------------------------

def _rrf_merge(
    list_a: List[Dict[str, Any]],
    list_b: List[Dict[str, Any]],
    k: int,
) -> List[Dict[str, Any]]:
    """Merge two ranked lists using Reciprocal Rank Fusion.

    Each list is ranked 1…N; the final score is the sum of RRF scores from
    each list a hit appears in.  Items only in one list still get their RRF
    contribution from that list.
    """
    scores: dict[str, float] = {}
    meta: dict[str, dict] = {}

    for rank, item in enumerate(list_a, start=1):
        iid = item["id"]
        scores[iid] = scores.get(iid, 0.0) + _rrf_score(rank, k)
        meta[iid] = item

    for rank, item in enumerate(list_b, start=1):
        iid = item["id"]
        scores[iid] = scores.get(iid, 0.0) + _rrf_score(rank, k)
        if iid not in meta:
            meta[iid] = item

    merged = sorted(scores.keys(), key=lambda iid: scores[iid], reverse=True)
    return [
        {**meta[iid], "score": round(scores[iid], 6)}
        for iid in merged
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def hybrid_search(
    db: Any,
    *,
    org_id: str,
    query: str,
    k: int = 5,
) -> List[Dict[str, Any]]:
    """Search the knowledge_search_index for ``query`` and return the top-k hits.

    Gated by flags.SEMANTIC_SEARCH — returns [] immediately when the flag is OFF
    so callers need no extra guard.

    Algorithm:
        1. PG full-text rank (ts_rank via ``tsv`` GIN index) — fast on PG.
        2. Token-Jaccard fallback (re-uses the C4 idiom from query_cache_store).
        3. Reciprocal Rank Fusion merge of both lists.

    Returns a list of dicts:
        {id, kind, ref_id, title, body, score}
    sorted descending by RRF score.  Returns [] on any error (fail-soft).
    """
    from app.settings.hybrid_flags import flags  # local import: stays dep-free

    if not flags.SEMANTIC_SEARCH:
        return []

    if not query or not org_id:
        return []

    fetch_limit = max(k * 3, _FETCH_LIMIT)

    try:
        fts_hits, jaccard_hits = [], []

        # Run both rankers; each is individually fail-soft
        try:
            fts_hits = await _pg_fts_rank(db, org_id, query, fetch_limit)
        except Exception as exc:
            log.debug("hybrid_search: PG FTS ranker error (%s)", exc)

        try:
            jaccard_hits = await _jaccard_rank(db, org_id, query, fetch_limit)
        except Exception as exc:
            log.debug("hybrid_search: Jaccard ranker error (%s)", exc)

        merged = _rrf_merge(fts_hits, jaccard_hits, k=_RRF_K)
        return merged[:k]

    except Exception as exc:
        log.warning("hybrid_search: unexpected error (%s); returning []", exc, exc_info=True)
        return []
