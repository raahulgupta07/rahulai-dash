"""Session Summary — one cheap-LLM roll-up across ALL turns of a report.

After a report has accumulated several chat turns, this synthesizer gathers the
report's COMPLETED turns (each user question + the answer text + the F10
``sense_making`` decision if present) plus the artifacts the report produced
(dashboards / slide decks / Excel workbooks), and makes ONE small-model LLM call
to fold them into a single structured summary that is pinned in the Outputs panel.

Public surface
--------------
    async def build_session_summary(db, *, report, organization, user, model) -> dict | None

Returns the summary dict (shape below) or ``None`` when there is nothing to
summarise (no completed turns) or on ANY error. NEVER raises.

JSON contract (frontend reads this verbatim)
--------------------------------------------
    {
      "headline": str,
      "decision": {"verb": "Watch|Act|Hold", "confidence": "high|medium|low",
                   "text": str} | null,
      "key_findings": [str, ...],          # <= 6, deduped
      "produced": [{"type": "dashboard|slides|excel|answer", "title": str,
                    "status": str}],
      "next_steps": [str, ...],            # <= 4
      "generated_from": {"completion_count": int, "last_completion_id": str|null,
                         "generated_at": None}   # route stamps generated_at
    }

Design rules (mirror ``sense_maker`` / ``followups`` EXACTLY)
------------------------------------------------------------
- Cheap tier: ONE small-model inference via dash's one-shot wrapper
  ``LLM(model, usage_session_maker=async_session_maker).inference(prompt,
  usage_scope="session_summary")`` (SYNC -> run in a worker thread).
- Grounding: only summarise what is actually in the turns/artifacts; the prompt
  forbids invented numbers; findings are deduped and tightly capped.
- Fail-soft: any exception -> ``None`` (logged at WARNING, never re-raised).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.settings.logging_config import get_logger

logger = get_logger(__name__)

# Bounds (cheap tier — keep the prompt small + the output tight).
_MAX_TURNS = 24          # newest turns fed to the LLM
_MAX_ARTIFACTS = 20
_MAX_ANSWER_CHARS = 1200  # per-turn answer truncation
_MAX_QUESTION_CHARS = 400
_MAX_FINDINGS = 6
_MAX_NEXT_STEPS = 4

_VALID_VERBS = {"Watch", "Act", "Hold"}
_VALID_CONF = {"high", "medium", "low"}
# Artifact mode -> produced.type bucket.
_MODE_TO_TYPE = {"page": "dashboard", "slides": "slides", "excel": "excel"}


def _clean(s: Any) -> str:
    return str(s).strip() if s is not None else ""


def _content(obj: Any) -> str:
    """Pull a 'content' string from a JSON column (dict | str | other)."""
    try:
        if isinstance(obj, dict):
            return str(obj.get("content") or "")
        if isinstance(obj, str):
            return obj
    except Exception:
        pass
    return ""


def _strip_fences(text: str) -> str:
    """Strip ```json ... ``` / ``` ... ``` fences a model may wrap output in."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """Tolerant JSON-object parse: strip fences, fall back to outermost {...}."""
    s = _strip_fences(raw or "")
    if not s:
        return None
    if not s.startswith("{"):
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start:end + 1]
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _sense_making_brief(sm: Any) -> Optional[Dict[str, Any]]:
    """Compact a turn's stored ``sense_making`` card into a small dict for the prompt."""
    if not isinstance(sm, dict):
        return None
    headline = sm.get("headline") if isinstance(sm.get("headline"), dict) else {}
    findings = sm.get("findings") if isinstance(sm.get("findings"), list) else []
    brief: Dict[str, Any] = {}
    htext = _clean(headline.get("text"))
    if htext:
        brief["headline"] = htext
        sev = _clean(headline.get("severity"))
        if sev:
            brief["severity"] = sev
    fbits: List[str] = []
    for f in findings[:3]:
        if not isinstance(f, dict):
            continue
        what = _clean(f.get("what"))
        nw = f.get("now_what") if isinstance(f.get("now_what"), dict) else {}
        action = _clean(nw.get("action"))
        if what and action:
            fbits.append(f"{what} -> {action}")
        elif what:
            fbits.append(what)
    if fbits:
        brief["findings"] = fbits
    return brief or None


async def _gather_turns(db, report_id: str) -> (List[Dict[str, Any]], int, Optional[str]):
    """Return (turns, completion_count, last_completion_id).

    A turn = a successful SYSTEM completion (the answer, ``completion['content']``
    + optional ``sense_making``) paired with its question (the nearest prior
    ``role='user'`` row by ``turn_index``). ``completion_count`` / ``last_completion_id``
    describe the report's current latest SYSTEM completion for staleness checks.
    """
    from app.models.completion import Completion

    rows = (
        await db.execute(
            select(Completion)
            .where(Completion.report_id == report_id)
            .order_by(Completion.turn_index.asc())
        )
    ).scalars().all()

    # Map user-side questions by turn_index for cheap pairing.
    user_q: Dict[Any, str] = {}
    for c in rows:
        if getattr(c, "role", None) == "user":
            q = _content(getattr(c, "prompt", None))
            if q:
                user_q[getattr(c, "turn_index", None)] = q

    def _nearest_question(turn_index: Any) -> str:
        # Exact turn first, else the nearest prior user turn.
        if turn_index in user_q:
            return user_q[turn_index]
        best = ""
        best_ti = None
        for ti, q in user_q.items():
            try:
                if ti is not None and turn_index is not None and ti <= turn_index:
                    if best_ti is None or ti > best_ti:
                        best_ti, best = ti, q
            except Exception:
                continue
        return best

    turns: List[Dict[str, Any]] = []
    completion_count = 0
    last_completion_id: Optional[str] = None
    for c in rows:
        if getattr(c, "role", None) == "user":
            continue
        comp = getattr(c, "completion", None)
        answer = _content(comp)
        # Only count "completed" answer turns with real content.
        if getattr(c, "status", None) != "success" or not answer:
            continue
        completion_count += 1
        last_completion_id = str(getattr(c, "id", "") or "") or last_completion_id
        question = _nearest_question(getattr(c, "turn_index", None))
        sm = comp.get("sense_making") if isinstance(comp, dict) else None
        turns.append({
            "question": _clean(question)[:_MAX_QUESTION_CHARS],
            "answer": answer[:_MAX_ANSWER_CHARS],
            "decision": _sense_making_brief(sm),
        })

    return turns, completion_count, last_completion_id


async def _gather_artifacts(db, report_id: str) -> List[Dict[str, str]]:
    """Return [{type, title, status}] for the report's artifacts (newest first)."""
    try:
        from app.models.artifact import Artifact

        rows = (
            await db.execute(
                select(Artifact)
                .where(Artifact.report_id == report_id)
                .order_by(Artifact.created_at.desc())
            )
        ).scalars().all()
    except Exception:
        return []

    out: List[Dict[str, str]] = []
    for a in rows[:_MAX_ARTIFACTS]:
        mode = _clean(getattr(a, "mode", "")) or "page"
        out.append({
            "type": _MODE_TO_TYPE.get(mode, "dashboard"),
            "title": _clean(getattr(a, "title", "")) or "Untitled",
            "status": _clean(getattr(a, "status", "")) or "completed",
        })
    return out


def _build_prompt(report_title: str, turns: List[Dict[str, Any]],
                  artifacts: List[Dict[str, str]]) -> str:
    turns_s = json.dumps(turns, ensure_ascii=False, default=str)[:9000]
    arts_s = json.dumps(artifacts, ensure_ascii=False, default=str)[:2000]
    return (
        "You are a senior data analyst writing a SESSION SUMMARY that sits pinned "
        "above the outputs of a multi-turn analytics conversation. Roll up the "
        "whole session into ONE tight, decision-oriented summary.\n\n"
        f"REPORT TITLE:\n{report_title or '(untitled)'}\n\n"
        "TURNS (each: the user's question, the answer they got, and an optional "
        "decision card already computed from the real data):\n"
        f"{turns_s}\n\n"
        "ARTIFACTS PRODUCED (dashboards / slide decks / Excel workbooks):\n"
        f"{arts_s}\n\n"
        "RULES:\n"
        "- Output STRICT JSON only. No markdown, no prose, no code fences.\n"
        "- GROUND everything in the turns/artifacts above. NEVER invent numbers, "
        "metrics, or facts that are not present in the material.\n"
        "- DEDUPE findings across turns; merge repeats into one. Keep at most 6 "
        "key_findings and at most 4 next_steps. Be concrete and brief.\n"
        "- 'decision' summarises the session's overall call. verb is one of "
        "Watch|Act|Hold; confidence is one of high|medium|low. If the turns carry "
        "no decision signal, set 'decision' to null.\n"
        "- 'produced' should reflect the ARTIFACTS list (type one of "
        "dashboard|slides|excel; use 'answer' only for a notable text answer with "
        "no artifact). Echo each artifact's real title and status.\n\n"
        "Return JSON EXACTLY matching this shape:\n"
        '{"headline":"","decision":{"verb":"Watch","confidence":"medium","text":""},'
        '"key_findings":[""],"produced":[{"type":"dashboard","title":"","status":""}],'
        '"next_steps":[""]}'
    )


def _coerce_decision(d: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(d, dict):
        return None
    text = _clean(d.get("text"))
    verb = _clean(d.get("verb")).capitalize()
    conf = _clean(d.get("confidence")).lower()
    if verb not in _VALID_VERBS:
        verb = "Watch"
    if conf not in _VALID_CONF:
        conf = "low"
    if not text:
        return None
    return {"verb": verb, "confidence": conf, "text": text}


def _dedupe_strings(items: Any, cap: int) -> List[str]:
    out: List[str] = []
    seen: set = set()
    if not isinstance(items, list):
        return out
    for it in items:
        s = _clean(it.get("text") if isinstance(it, dict) else it)
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= cap:
            break
    return out


def _coerce_produced(items: Any, artifacts: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if isinstance(items, list):
        for it in items:
            if not isinstance(it, dict):
                continue
            typ = _clean(it.get("type")).lower()
            if typ not in ("dashboard", "slides", "excel", "answer"):
                typ = "answer"
            title = _clean(it.get("title")) or "Untitled"
            status = _clean(it.get("status")) or "completed"
            out.append({"type": typ, "title": title, "status": status})
    # Fall back to the real artifact list if the model produced nothing usable.
    if not out and artifacts:
        out = [dict(a) for a in artifacts]
    return out[:_MAX_ARTIFACTS]


async def build_session_summary(db, *, report, organization, user, model) -> Optional[Dict[str, Any]]:
    """Build a cached session summary for a report. Returns the dict or None.

    NEVER raises — any error returns ``None`` (logged at WARNING).
    """
    try:
        report_id = str(getattr(report, "id", "") or "")
        if not report_id:
            return None

        turns, completion_count, last_completion_id = await _gather_turns(db, report_id)
        if not turns:
            # Nothing completed yet — nothing to summarise.
            return None
        # Feed only the newest N turns to keep the prompt cheap.
        fed_turns = turns[-_MAX_TURNS:]
        artifacts = await _gather_artifacts(db, report_id)

        # Resolve the cheap/small model if the caller didn't hand one in.
        if model is None:
            try:
                from app.services.llm_service import LLMService
                model = await LLMService().get_default_model(
                    db, organization, user, is_small=True
                )
            except Exception:
                model = None
        if model is None:
            logger.warning("session_summary: no model available for org %s",
                           getattr(organization, "id", "?"))
            return None

        report_title = _clean(getattr(report, "title", ""))
        prompt = _build_prompt(report_title, fed_turns, artifacts)

        def _infer() -> str:
            from app.ai.llm.llm import LLM
            from app.dependencies import async_session_maker

            return LLM(model, usage_session_maker=async_session_maker).inference(
                prompt, usage_scope="session_summary"
            )

        raw = await asyncio.to_thread(_infer)
        parsed = _parse_json(raw or "")
        if not parsed:
            return None

        result: Dict[str, Any] = {
            "headline": _clean(parsed.get("headline")),
            "decision": _coerce_decision(parsed.get("decision")),
            "key_findings": _dedupe_strings(parsed.get("key_findings"), _MAX_FINDINGS),
            "produced": _coerce_produced(parsed.get("produced"), artifacts),
            "next_steps": _dedupe_strings(parsed.get("next_steps"), _MAX_NEXT_STEPS),
        }

        # Provenance marker — the route stamps ``generated_at`` (ISO string).
        result["generated_from"] = {
            "completion_count": completion_count,
            # alias for the FE card's scope sub-header (reads `turn_count`)
            "turn_count": completion_count,
            "last_completion_id": last_completion_id,
            "generated_at": None,
        }
        return result
    except Exception:
        logger.warning("session_summary: build_session_summary failed", exc_info=True)
        return None


async def latest_completion_marker(db, report_id: str) -> Dict[str, Any]:
    """Return ``{completion_count, last_completion_id}`` for the report's CURRENT
    latest SYSTEM completion — used by the GET route to compute staleness.

    Fail-soft: returns zero/None on any error.
    """
    try:
        _turns, count, last_id = await _gather_turns(db, str(report_id))
        return {"completion_count": count, "last_completion_id": last_id}
    except Exception:
        logger.warning("session_summary: latest_completion_marker failed", exc_info=True)
        return {"completion_count": 0, "last_completion_id": None}
