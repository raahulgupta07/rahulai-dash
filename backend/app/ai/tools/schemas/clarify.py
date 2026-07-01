from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ClarifyQuestion(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        description="The question shown to the user. Keep it concise.",
    )
    options: Optional[list[str]] = Field(
        None,
        description=(
            "Clickable answer choices rendered as selectable chips. "
            "Omit for free-form text input. "
            "Include an 'Other…' entry when the list may not be exhaustive."
        ),
    )


class ClarifyInput(BaseModel):
    """Input schema for the clarify tool.

    Each entry in ``questions`` becomes an interactive form row: a chip-picker
    when ``options`` is supplied, a text field otherwise. All questions are
    shown at once; the user submits all answers in a single reply.
    """

    questions: list[ClarifyQuestion] = Field(
        ...,
        min_length=1,
        description="One or more questions to ask the user before proceeding.",
    )
    context: Optional[str] = Field(
        None,
        description="Brief internal note about why clarification is needed (not shown to the user).",
    )

    @field_validator("questions", mode="before")
    @classmethod
    def _coerce_questions(cls, v):
        """Weak models sometimes emit ``questions`` as plain strings (or objects
        keyed ``question``/``label`` instead of ``text``). Coerce each entry to
        the ``{text, options}`` shape and drop empties so the UI never renders an
        unlabeled, dead-end box. Kept lenient — validation of the coerced dicts
        (incl. the ``text`` min_length) still runs afterward."""
        if not isinstance(v, list):
            return v
        out = []
        for item in v:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    out.append({"text": text})
            elif isinstance(item, dict):
                text = (item.get("text") or item.get("question") or item.get("label") or "")
                if isinstance(text, str) and text.strip():
                    out.append({**item, "text": text.strip()})
            else:
                out.append(item)
        return out


class ClarifyOutput(BaseModel):
    """Output schema for the clarify tool."""

    status: str = Field(
        default="awaiting_response",
        description="Status of the clarification request.",
    )
