"""F09 UNIFY — match columns across ALL org sources → join candidates (Phase 3).

The flagship idea: a column in a newly-dropped file (``salesA.cust_id``) is
matched to a column the org already has (``crmC.customer``) even though they came
from different files in different formats — so the brain proposes the join. This
is pure-Python (difflib on normalized names + value-sample overlap), so it is
deterministic and testable with no DB/LLM. Proposals are review-gated downstream.

Public:
    unify_columns(new_profiles, existing_columns, *, min_conf=0.55) -> list[JoinCandidate]

``existing_columns`` items are plain dicts (fetched from the column_profiles
table by the caller):
    {"ref": "crmC.customer", "normalized_name": "customer",
     "semantic_role": "id", "sample_values": ["1001","1002", ...]}
"""
from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any, Dict, List

from app.services.ingest_brain.contract import ColumnProfile, JoinCandidate

logger = logging.getLogger(__name__)

# Only id/category columns are sane join keys; never join on a free measure.
_JOINABLE_ROLES = {"id", "category"}


def _name_sim(a: str, b: str) -> float:
    a, b = (a or "").lower(), (b or "").lower()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # reward shared tokens (cust_id ~ customer_id) on top of raw ratio
    base = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.replace("-", "_").split("_")), set(b.replace("-", "_").split("_"))
    tok = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    return max(base, 0.5 * base + 0.5 * tok)


def _value_overlap(sa: List[Any], sb: List[Any]) -> float:
    va = {str(x).strip().lower() for x in (sa or []) if str(x).strip()}
    vb = {str(x).strip().lower() for x in (sb or []) if str(x).strip()}
    if not va or not vb:
        return 0.0
    return len(va & vb) / min(len(va), len(vb))


def unify_columns(new_profiles: List[ColumnProfile],
                  existing_columns: List[Dict[str, Any]],
                  *, min_conf: float = 0.55) -> List[JoinCandidate]:
    """Propose cross-source joins between this file's columns and the org's.

    Confidence = blend of name similarity and value-sample overlap, with a small
    boost when both sides are id-role. NEVER raises. Returns best match per new
    column above ``min_conf``.
    """
    out: List[JoinCandidate] = []
    try:
        for p in new_profiles:
            if p.semantic_role not in _JOINABLE_ROLES:
                continue
            left_ref = f"{(p.source_ref or {}).get('sheet') or p.normalized_name}.{p.name}"
            best = None
            for ex in existing_columns:
                if ex.get("semantic_role") not in _JOINABLE_ROLES:
                    continue
                name_s = _name_sim(p.normalized_name, ex.get("normalized_name", ""))
                val_s = _value_overlap(p.sample_values, ex.get("sample_values", []))
                conf = 0.6 * name_s + 0.4 * val_s
                if p.semantic_role == "id" and ex.get("semantic_role") == "id":
                    conf = min(1.0, conf + 0.1)
                if best is None or conf > best[0]:
                    best = (conf, ex, name_s, val_s)
            if best and best[0] >= min_conf:
                conf, ex, name_s, val_s = best
                reason = []
                if name_s >= 0.6:
                    reason.append("similar name")
                if val_s >= 0.3:
                    reason.append(f"{int(val_s*100)}% value overlap")
                out.append(JoinCandidate(
                    left_ref=left_ref, right_ref=ex.get("ref", ex.get("normalized_name", "")),
                    confidence=round(conf, 2), reason=" + ".join(reason) or "name match"))
    except Exception:  # noqa: BLE001
        logger.exception("ingest_brain.unify_columns failed")
    return out
