"""F09 UNDERSTAND — LLM names each column's meaning + synonyms (Phase 3).

Takes the deterministic ColumnProfiles from PROFILE and asks a CHEAP model to
write a one-line ``meaning`` and a few ``synonyms`` per column, GROUNDED in the
profile (name, dtype, role, sample values) — never inventing data. Decoupled:
the caller passes an ``llm_inference(prompt) -> str`` callable (wired to the org
OpenRouter client at the route). No callable → passthrough (P1/P2 behavior).
NEVER raises. Output stays ``status=pending`` downstream (review-gated).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable, List, Optional

from app.services.ingest_brain.contract import ColumnProfile

logger = logging.getLogger(__name__)

_SYS = (
    "You label spreadsheet/table columns for a data catalog. For each column you "
    "are given its name, type, role, and up to 5 sample values. Return STRICT JSON "
    '{"columns":[{"name":<exact name>,"meaning":<≤12 words, plain>,'
    '"synonyms":[<≤3 alternates>]}]}. Ground every meaning in the name+samples; do '
    "NOT invent units or values you cannot see. Output ONLY the JSON object."
)
_MAX_COLS = 60          # cap prompt size / cost


def _prompt(profiles: List[ColumnProfile]) -> str:
    lines = []
    for p in profiles[:_MAX_COLS]:
        samp = ", ".join(str(s) for s in (p.sample_values or [])[:5])
        lines.append(f"- {p.name} | type={p.dtype} role={p.semantic_role} unit={p.unit or '-'} samples=[{samp}]")
    return f"{_SYS}\n\nCOLUMNS:\n" + "\n".join(lines) + "\n\nJSON:"


def _parse(text: str) -> Optional[dict]:
    try:
        t = re.sub(r"```[a-zA-Z]*", "", str(text)).replace("```", "").strip()
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if not m:
            return None
        return json.loads(re.sub(r",\s*([}\]])", r"\1", m.group(0)))
    except Exception:  # noqa: BLE001
        return None


def understand_columns(profiles: List[ColumnProfile], *,
                       llm_inference: Optional[Callable[[str], str]] = None) -> List[ColumnProfile]:
    """Enrich profiles in place with meaning + synonyms. NEVER raises."""
    if not profiles or llm_inference is None:
        return profiles
    try:
        obj = _parse(llm_inference(_prompt(profiles))) or {}
        by_name = {str(c.get("name", "")).strip().lower(): c for c in obj.get("columns", [])}
        for p in profiles:
            c = by_name.get(p.name.strip().lower())
            if not c:
                continue
            meaning = str(c.get("meaning", "")).strip()
            if meaning:
                p.meaning = meaning[:200]
            syns = [str(s).strip() for s in (c.get("synonyms") or []) if str(s).strip()]
            if syns:
                # merge with the heuristic synonyms from PROFILE, dedup
                merged = list(dict.fromkeys((p.synonyms or []) + syns))
                p.synonyms = merged[:6]
    except Exception:  # noqa: BLE001
        logger.exception("ingest_brain.understand_columns failed")
    return profiles
