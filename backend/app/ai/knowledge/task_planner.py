"""Task Plan — one cheap-LLM, Claude-TodoWrite-style outline at the START of a run.

When the ``HYBRID_AGENT_PLAN`` flag is on, the agent makes ONE small-model call at
run start that, given the user's prompt plus a brief data-schema context, returns a
short high-level plan (3-5 imperative steps). The plan is emitted once as a
``CompletionBlock`` (``source_type='plan'``) so the frontend can render it as a
numbered checklist; it is purely additive UI context and never alters the loop.

Public surface
--------------
    async def build_task_plan(db, *, user_message, organization, user, model,
                              data_context="") -> list[dict]

Returns a list of ``{"title": str, "status": "pending"}`` (<= 5) or ``[]`` when
there is nothing to plan or on ANY error. NEVER raises.

Design rules (mirror ``session_summary`` / ``sense_maker`` EXACTLY)
------------------------------------------------------------------
- Cheap tier: ONE small-model inference via dash's one-shot wrapper
  ``LLM(model, usage_session_maker=async_session_maker).inference(prompt,
  usage_scope="task_plan")`` (SYNC -> run in a worker thread).
- Defensive parse: strip code fences, ``json.loads``, clamp to 5 titles, each
  trimmed to <= ~8 words.
- Fail-soft: any exception -> ``[]`` (logged at WARNING, never re-raised).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from app.settings.logging_config import get_logger

logger = get_logger(__name__)

_MIN_TASKS = 1
_MAX_TASKS = 5
_MAX_TITLE_WORDS = 8
_MAX_TITLE_CHARS = 80
_MAX_DATA_CONTEXT_CHARS = 2500
_MAX_QUESTION_CHARS = 1200


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
        obj = json.loads(s, strict=False)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _clean_title(s: Any) -> str:
    """Normalise a single task title: collapse whitespace, clamp words + chars."""
    t = re.sub(r"\s+", " ", str(s or "")).strip()
    # Drop any leading list numbering the model may have added ("1. ", "- ").
    t = re.sub(r"^[\-\*\d]+[\.\)]?\s+", "", t)
    if not t:
        return ""
    words = t.split(" ")
    if len(words) > _MAX_TITLE_WORDS:
        t = " ".join(words[:_MAX_TITLE_WORDS])
    if len(t) > _MAX_TITLE_CHARS:
        t = t[:_MAX_TITLE_CHARS].rstrip()
    return t


def _coerce_tasks(parsed: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Pull ``{"tasks":[{"title":...}, ...]}`` into a clamped, deduped list."""
    if not isinstance(parsed, dict):
        return []
    raw_tasks = parsed.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    out: List[Dict[str, str]] = []
    seen = set()
    for item in raw_tasks:
        if isinstance(item, dict):
            title = _clean_title(item.get("title"))
        else:
            title = _clean_title(item)
        if not title:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "status": "pending"})
        if len(out) >= _MAX_TASKS:
            break
    return out


def _build_prompt(user_message: str, data_context: str) -> str:
    q = (user_message or "").strip()[:_MAX_QUESTION_CHARS]
    ctx = (data_context or "").strip()[:_MAX_DATA_CONTEXT_CHARS]
    ctx_block = f"\n\nAvailable data (schema excerpt):\n{ctx}\n" if ctx else "\n"
    return (
        "You are an analytics agent about to answer a user's request. Before you "
        "start, outline a SHORT high-level plan of the steps you will take, like a "
        "to-do checklist.\n\n"
        f"User request:\n{q}\n"
        f"{ctx_block}\n"
        "Rules:\n"
        "- Output 3 to 5 steps (fewer only if the request is trivial).\n"
        "- Each step is a short imperative title, at most 8 words.\n"
        "- Describe WHAT you'll do (e.g. 'Pull monthly revenue by region', "
        "'Build trend dashboard'), not generic filler.\n"
        "- Do NOT invent specific numbers or findings; this is a plan, not an answer.\n"
        "- Respond with STRICT JSON only, no prose, no code fences:\n"
        '{"tasks":[{"title":"..."},{"title":"..."},{"title":"..."}]}'
    )


async def build_task_plan(
    db,
    *,
    user_message: str,
    organization,
    user=None,
    model=None,
    data_context: str = "",
) -> List[Dict[str, str]]:
    """Build a 3-5 item task plan for a run. Returns the list or ``[]``.

    NEVER raises — any error returns ``[]`` (logged at WARNING).
    """
    try:
        q = (user_message or "").strip()
        if not q:
            return []

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
            logger.warning("task_plan: no model available for org %s",
                           getattr(organization, "id", "?"))
            return []

        prompt = _build_prompt(q, data_context)

        def _infer() -> str:
            from app.ai.llm.llm import LLM
            from app.dependencies import async_session_maker

            return LLM(model, usage_session_maker=async_session_maker).inference(
                prompt, usage_scope="task_plan"
            )

        raw = await asyncio.to_thread(_infer)
        tasks = _coerce_tasks(_parse_json(raw or ""))
        if len(tasks) < _MIN_TASKS:
            return []
        return tasks
    except Exception:
        logger.warning("task_plan: build_task_plan failed", exc_info=True)
        return []
