"""Mixture of Agents (MoA) — flag-gated peer-consult layer.

Sidecar feature. Several cheap, fast, *diverse-lab* models look at one hard
question IN PARALLEL and each return a short analysis (NO tools, analysis-only).
Their analyses are folded into a single "peer analyses" context block that the
real aggregator (AgentV2 planner, e.g. glm-5.2) reads before it plans + calls
tools. Only the aggregator ever touches the data or builds artifacts — exactly
the diagram: "several models look at the problem, one writes the answer".

Design rules (mirror sense_maker.py / auto_model.py):
- Reuses the org's existing OpenRouter provider + the shared ``LLM`` client.
  No new HTTP client, no new credentials.
- Fully fail-soft: ANY error in a single consult is swallowed and that voice
  is dropped; a total failure returns an empty list. NEVER raises. With the
  feature flag OFF the caller never imports this path, so behaviour is byte-
  identical to today.
- Consults run analysis-only (no tools) with a tight token budget, in parallel
  via ``asyncio.gather(asyncio.to_thread(...))`` so the panel costs ~one round.

Public surface
--------------
    DEFAULT_PANEL: list[str]          # config B consult models (OpenRouter slugs)
    DEFAULT_AGGREGATOR: str           # writer/tool-caller model slug
    async def consult(db, organization, question, *, context="", models=None,
                      usage_scope="mixture_of_agents") -> list[dict]
    def build_peer_block(analyses) -> str
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# --- Config B (chosen panel) ------------------------------------------------
# Diverse labs + one US lens. Cheap, fast, good reasoning. Analysis-only here.
DEFAULT_PANEL: List[str] = [
    "deepseek/deepseek-v4-pro",      # DeepSeek  (CN) — best value reasoning
    "minimax/minimax-m3",            # MiniMax   (CN) — fast agentic
    "qwen/qwen3.7-plus",             # Alibaba   (CN) — strong reasoning
    "google/gemini-3.1-flash-lite",  # Google    (US) — different-lab lens
]
# The writer + tool-caller. Holds all peer analyses (1M ctx), near-frontier.
DEFAULT_AGGREGATOR: str = "z-ai/glm-5.2"

# Short label per slug for the peer block / UI.
_LABELS = {
    "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
    "minimax/minimax-m3": "MiniMax M3",
    "qwen/qwen3.7-plus": "Qwen3.7 Plus",
    "google/gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    "z-ai/glm-5.2": "GLM 5.2",
}

# Analysis-only system framing. The consult model must NOT answer with tools or
# invent data — it reasons about HOW to approach the question.
_ANALYSIS_SYS = (
    "You are one expert advisor on a panel. You do NOT have database access and "
    "you do NOT call tools. Another agent will execute the work. Your job: read "
    "the user's analytics question (and any schema/context) and give a SHORT, "
    "high-signal analysis of how to approach it. Cover: (1) what the user really "
    "wants, (2) the key metrics / dimensions / grain to use, (3) the SQL or "
    "aggregation strategy and any join/grain/edge-case traps, (4) what to show "
    "(chart types / dashboard widgets / slide story) if relevant, (5) risks or "
    "things a careless analyst would get wrong. Be concrete and brief — at most "
    "~180 words, plain text, no preamble, no markdown headers. Do NOT fabricate "
    "numbers; you have not seen the data."
)

_MAX_CONSULT_WORDS_HINT = 180

# A slow/cold consult model must never stall the panel — gather waits for the
# slowest. Cap each consult; a model over budget is dropped (ok=False, timeout).
_CONSULT_TIMEOUT_S = 20.0

# Aggregator framing — the ONE model that writes the answer, informed by peers.
_AGG_SYS = (
    "You are a senior data/business analyst. Answer the user's question clearly, "
    "concretely, and in a decision-useful way. Several expert advisor models have "
    "already reviewed the question (analysis only — they did not see the data). "
    "Use their perspectives: take the consensus, weigh disagreements, and avoid "
    "the traps they flag. Write the final answer yourself — be specific about the "
    "metrics, the method (e.g. SQL/aggregation/grain), and what to show or do."
)


def _label(slug: str) -> str:
    return _LABELS.get(slug, slug.split("/")[-1])


def _build_consult_prompt(question: str, context: str) -> str:
    ctx = (context or "").strip()
    ctx_block = f"\n\nSCHEMA / CONTEXT:\n{ctx[:6000]}\n" if ctx else "\n"
    return (
        f"{_ANALYSIS_SYS}\n\n"
        f"USER QUESTION:\n{(question or '').strip()}\n"
        f"{ctx_block}"
        "\nYour analysis (<= ~180 words, plain text):"
    )


def _transient_model(slug: str, provider: Any, organization: Any):
    """Build an in-memory LLMModel bound to the org's OpenRouter provider.

    Not persisted — only ``model_id`` + ``provider`` are read by ``LLM``.
    """
    from app.models.llm_model import LLMModel

    return LLMModel(
        name=_label(slug),
        model_id=slug,
        is_custom=True,
        provider=provider,
        provider_id=getattr(provider, "id", None),
        organization_id=getattr(organization, "id", None),
    )


async def _consult_one(slug: str, prompt: str, provider: Any, organization: Any,
                       usage_scope: str) -> Dict[str, Any]:
    """Run ONE consult model. Fail-soft → dict with ok=False on any error."""
    started = time.monotonic()
    try:
        from app.ai.llm.llm import LLM
        from app.dependencies import async_session_maker

        model = _transient_model(slug, provider, organization)

        def _infer() -> str:
            return LLM(model, usage_session_maker=async_session_maker).inference(
                prompt, usage_scope=usage_scope, should_record=True
            )

        text = await asyncio.wait_for(
            asyncio.to_thread(_infer), timeout=_CONSULT_TIMEOUT_S
        )
        ms = int((time.monotonic() - started) * 1000)
        analysis = (text or "").strip()
        if not analysis:
            return {"model": slug, "label": _label(slug), "ok": False,
                    "analysis": "", "ms": ms, "error": "empty response"}
        return {"model": slug, "label": _label(slug), "ok": True,
                "analysis": analysis, "ms": ms}
    except asyncio.TimeoutError:
        ms = int((time.monotonic() - started) * 1000)
        logger.warning("MoA consult timed out for %s after %ss", slug, _CONSULT_TIMEOUT_S)
        return {"model": slug, "label": _label(slug), "ok": False,
                "analysis": "", "ms": ms, "error": f"timeout >{int(_CONSULT_TIMEOUT_S)}s"}
    except Exception as exc:  # noqa: BLE001 — fail-soft per voice
        ms = int((time.monotonic() - started) * 1000)
        logger.warning("MoA consult failed for %s: %s", slug, exc)
        return {"model": slug, "label": _label(slug), "ok": False,
                "analysis": "", "ms": ms, "error": str(exc)[:200]}


async def consult(db, organization, question: str, *, context: str = "",
                  models: Optional[List[str]] = None,
                  usage_scope: str = "mixture_of_agents") -> List[Dict[str, Any]]:
    """Consult the panel in parallel. Returns one dict per model (ok True/False).

    NEVER raises. Returns [] if the org has no OpenRouter provider.
    """
    try:
        from app.services.llm_service import LLMService

        provider = await LLMService()._find_openrouter_provider(db, organization)
        if provider is None:
            logger.warning("MoA: no OpenRouter provider for org %s; skipping consult",
                           getattr(organization, "id", "?"))
            return []

        panel = models or DEFAULT_PANEL
        prompt = _build_consult_prompt(question, context)

        results = await asyncio.gather(
            *[_consult_one(slug, prompt, provider, organization, usage_scope)
              for slug in panel],
            return_exceptions=True,
        )
        out: List[Dict[str, Any]] = []
        for r in results:
            if isinstance(r, dict):
                out.append(r)
            else:  # an exception leaked despite _consult_one's guard
                logger.warning("MoA consult task raised: %s", r)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("MoA consult layer failed: %s", exc)
        return []


async def aggregate(db, organization, question: str, *, peer_block: str = "",
                    context: str = "", model: str = DEFAULT_AGGREGATOR,
                    usage_scope: str = "mixture_of_agents") -> Dict[str, Any]:
    """Run the aggregator model to WRITE the final answer.

    With ``peer_block`` empty this is the plain single-model baseline; with the
    peer block it is the MoA answer. Same model both ways → an honest A/B of the
    *peer-analyses* lift. Returns {text, ms, ok}. NEVER raises.
    """
    started = time.monotonic()
    try:
        from app.services.llm_service import LLMService
        from app.ai.llm.llm import LLM
        from app.dependencies import async_session_maker

        provider = await LLMService()._find_openrouter_provider(db, organization)
        if provider is None:
            return {"text": "", "ms": 0, "ok": False, "error": "no OpenRouter provider"}

        ctx = (context or "").strip()
        ctx_block = f"\n\nSCHEMA / CONTEXT:\n{ctx[:6000]}\n" if ctx else "\n"
        peer = (peer_block or "").strip()
        peer_section = f"\n{peer}\n" if peer else "\n"
        prompt = (
            f"{_AGG_SYS}\n\n"
            f"USER QUESTION:\n{(question or '').strip()}\n"
            f"{ctx_block}"
            f"{peer_section}"
            "\nFinal answer:"
        )
        m = _transient_model(model, provider, organization)

        def _infer() -> str:
            return LLM(m, usage_session_maker=async_session_maker).inference(
                prompt, usage_scope=usage_scope, should_record=True
            )

        text = await asyncio.to_thread(_infer)
        ms = int((time.monotonic() - started) * 1000)
        return {"text": (text or "").strip(), "ms": ms, "ok": bool((text or "").strip()),
                "model": model, "label": _label(model)}
    except Exception as exc:  # noqa: BLE001
        ms = int((time.monotonic() - started) * 1000)
        logger.warning("MoA aggregate failed: %s", exc)
        return {"text": "", "ms": ms, "ok": False, "error": str(exc)[:200]}


def build_peer_block(analyses: List[Dict[str, Any]]) -> str:
    """Format successful analyses into a context block for the aggregator.

    Returns "" when no voice succeeded (caller then behaves as if OFF).
    """
    good = [a for a in (analyses or []) if a.get("ok") and a.get("analysis")]
    if not good:
        return ""
    lines: List[str] = [
        "PEER ANALYSES — several independent expert models reviewed this question "
        "(analysis only; none saw the data or ran tools). Use their perspectives "
        "to plan a better answer: take the consensus, weigh the disagreements, and "
        "catch traps they flag. You are the only one that executes.",
        "",
    ]
    for i, a in enumerate(good, 1):
        lines.append(f"[Advisor {i} — {a.get('label', a.get('model'))}]")
        lines.append(a["analysis"].strip())
        lines.append("")
    return "\n".join(lines).strip()
