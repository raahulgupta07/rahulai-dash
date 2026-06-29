"""F09 Ingest Brain (Phase B) — OpenRouter vision client.

Builds a fail-soft, sync ``vision_infer(image_bytes, prompt) -> str`` callable
that sends an image (PNG/JPEG) to the org's OpenRouter vision model and returns
the model's text reply. The callable is passed into the ingest pipeline so that
scanned PDFs / images can be turned into table rows.

LLM is OpenRouter-only. We resolve the org's provider via ``LLMService``, then
call OpenRouter's OpenAI-compatible chat completions endpoint directly with the
``openai`` SDK (the shared text-only LLM client cannot send images).

Everything here is fully fail-soft: any error yields ``None`` (from the builder)
or ``""`` (from the callable). Nothing in this module raises.
"""

from __future__ import annotations

import base64
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Cheap, strong-OCR vision model; vision-to-JSON needs no tool-calling.
DEFAULT_VISION_MODEL: str = "google/gemini-3.1-flash-lite"

_OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"


async def build_vision_infer(
    db,
    organization,
    *,
    model: str = DEFAULT_VISION_MODEL,
) -> Optional[Callable[[bytes, str], str]]:
    """Build a sync vision-inference callable for ``organization``.

    Resolves the org's OpenRouter provider and returns a fail-soft callable
    ``vision_infer(image_bytes, prompt) -> str``. Returns ``None`` if no
    provider can be found or anything goes wrong (caller then skips vision).

    The returned callable closes over the api_key + model and performs no DB
    access.
    """
    try:
        from app.services.llm_service import LLMService

        provider = await LLMService()._find_openrouter_provider(db, organization)
        if provider is None:
            logger.info("build_vision_infer: no OpenRouter provider found; skipping vision")
            return None

        api_key = provider.decrypt_credentials()[0]
        if not api_key:
            logger.info("build_vision_infer: provider has no api_key; skipping vision")
            return None
    except Exception:
        logger.exception("build_vision_infer: failed to resolve OpenRouter provider")
        return None

    model_slug = model or DEFAULT_VISION_MODEL

    def vision_infer(image_bytes: bytes, prompt: str) -> str:
        """Send ``image_bytes`` + ``prompt`` to the vision model; return text or ""."""
        try:
            from openai import OpenAI

            b64 = base64.b64encode(image_bytes).decode("ascii")
            client = OpenAI(api_key=api_key, base_url=_OPENROUTER_BASE_URL)
            resp = client.chat.completions.create(
                model=model_slug,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"},
                            },
                        ],
                    }
                ],
                max_tokens=2000,
            )
            return resp.choices[0].message.content or ""
        except Exception:
            logger.exception("vision_infer: vision inference call failed")
            return ""

    return vision_infer
