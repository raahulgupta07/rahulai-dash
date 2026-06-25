"""Agent Template frontmatter parser — defensive, never-raise (read-only, pure).

Mirrors the changelog-service idiom (``app/services/changelog.py``): malformed
input degrades to safe defaults, **nothing raises**.

An Agent Template is a markdown document with a leading ``---`` frontmatter block
followed by plain-markdown body sections. The frontmatter is the binding
contract + metadata; ``manifest`` (the JSON column on ``AgentTemplate``) is the
parsed mirror of it.

Frontmatter contract (shallow YAML-ish — scalars, inline lists ``[a, b]`` and a
list-of-dicts for ``requires_columns``)::

    ---
    name: Retail Sales Analyst
    version: 1.0.0
    author: Jane Doe
    domain: [retail, sales]
    requires_columns:
      - role: TEMPORAL
        as: order_date
      - role: MEASURE
        as: revenue
    uses_skills: [cohort_analysis, rfm]
    example_questions: ["Top products last quarter?", "MoM revenue trend?"]
    ---
    ## Rules
    - ...

PyYAML is used when importable (checked at import time); otherwise a tiny
hand-rolled parser handles the shallow format above. Either path is wrapped so a
failure falls back to ``{}`` / safe defaults.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

try:  # PyYAML is present in the venv, but never depend on it hard.
    import yaml as _yaml  # type: ignore
except Exception:  # noqa: BLE001
    _yaml = None  # fall back to the hand-rolled parser


# A leading "---\n ... \n---" block. DOTALL so the body spans newlines.
_FM_RE = re.compile(r"^\s*---\s*\n(?P<fm>.*?)\n---\s*\n?(?P<body>.*)$", re.DOTALL)


def _empty_manifest() -> dict[str, Any]:
    return {
        "name": "",
        "version": "",
        "author": "",
        "domain": [],
        "requires_columns": [],
        "uses_skills": [],
        "example_questions": [],
        "body": "",
    }


def _coerce_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _coerce_str_list(v: Any) -> list[str]:
    """Anything → list[str]. Scalars become a 1-element list; junk → []."""
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, (list, tuple)):
        out: list[str] = []
        for item in v:
            s = _coerce_str(item)
            if s:
                out.append(s)
        return out
    s = _coerce_str(v)
    return [s] if s else []


def _coerce_requires_columns(v: Any) -> list[dict[str, str]]:
    """Normalize requires_columns → list of ``{role, as}`` (both strings)."""
    out: list[dict[str, str]] = []
    if not isinstance(v, (list, tuple)):
        return out
    for item in v:
        if not isinstance(item, dict):
            continue
        role = _coerce_str(item.get("role"))
        as_ = _coerce_str(item.get("as"))
        if role or as_:
            out.append({"role": role, "as": as_})
    return out


# ---------------------------------------------------------------------------
# Hand-rolled YAML-ish parser (fallback when PyYAML is unavailable)
# ---------------------------------------------------------------------------

def _parse_inline_list(raw: str) -> list[str]:
    """``[a, "b c", 'd']`` → ['a', 'b c', 'd']. Defensive on quoting/commas."""
    inner = raw.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    items: list[str] = []
    for part in inner.split(","):
        p = part.strip()
        if not p:
            continue
        if (p[0] == p[-1]) and p[0] in ("'", '"') and len(p) >= 2:
            p = p[1:-1]
        p = p.strip()
        if p:
            items.append(p)
    return items


def _unquote(raw: str) -> str:
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1].strip()
    return s


def _hand_parse_frontmatter(fm: str) -> dict[str, Any]:
    """Tiny YAML-ish reader for the shallow template frontmatter.

    Handles: ``key: scalar``, ``key: [inline, list]``, and a list-of-dicts under
    ``requires_columns`` (``- role: X`` / ``as: Y`` indented bullets).
    """
    data: dict[str, Any] = {}
    lines = fm.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        i += 1
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        if not key:
            continue

        if rest == "":
            # block value: either a "- ..." list (possibly list-of-dicts) on
            # following indented lines, or nothing.
            block: list[Any] = []
            cur: dict[str, str] | None = None
            while i < n:
                nxt = lines[i]
                nstr = nxt.strip()
                # stop when we hit a non-indented new key (col 0, has ':')
                if nstr and not nxt.startswith((" ", "\t")) and not nstr.startswith("-"):
                    break
                i += 1
                if not nstr or nstr.startswith("#"):
                    continue
                if nstr.startswith("- "):
                    item = nstr[2:].strip()
                    if ":" in item:  # "- role: TEMPORAL"
                        cur = {}
                        ik, _, iv = item.partition(":")
                        cur[ik.strip()] = _unquote(iv)
                        block.append(cur)
                    else:  # "- plain_value"
                        cur = None
                        block.append(_unquote(item))
                elif ":" in nstr and cur is not None:
                    # continuation of the current dict ("  as: order_date")
                    ik, _, iv = nstr.partition(":")
                    cur[ik.strip()] = _unquote(iv)
                # else: ignore stray line
            data[key] = block
        elif rest.startswith("["):
            data[key] = _parse_inline_list(rest)
        else:
            data[key] = _unquote(rest)
    return data


def _yaml_parse_frontmatter(fm: str) -> dict[str, Any]:
    loaded = _yaml.safe_load(fm)  # type: ignore[union-attr]
    if not isinstance(loaded, dict):
        return {}
    return loaded


def parse_frontmatter(md_text: str) -> dict[str, Any]:
    """Parse a template's md+frontmatter → manifest dict (+ ``body``).

    Returns keys: name, version, author, domain (list), requires_columns
    (list[{role, as}]), uses_skills (list), example_questions (list), body (str).
    Never raises — malformed input yields ``_empty_manifest()`` (with whatever
    body could be recovered).
    """
    manifest = _empty_manifest()
    if not md_text or not isinstance(md_text, str):
        return manifest

    try:
        m = _FM_RE.match(md_text)
        if not m:
            # No frontmatter block — treat the whole thing as body.
            manifest["body"] = md_text.strip()
            return manifest

        fm = m.group("fm") or ""
        manifest["body"] = (m.group("body") or "").strip()

        raw: dict[str, Any] = {}
        if _yaml is not None:
            try:
                raw = _yaml_parse_frontmatter(fm)
            except Exception as e:  # noqa: BLE001
                logger.warning("parse_frontmatter: yaml failed, hand-rolling: %s", e)
                raw = {}
        if not raw:
            raw = _hand_parse_frontmatter(fm)

        if isinstance(raw, dict):
            manifest["name"] = _coerce_str(raw.get("name"))
            manifest["version"] = _coerce_str(raw.get("version"))
            manifest["author"] = _coerce_str(raw.get("author"))
            manifest["domain"] = _coerce_str_list(raw.get("domain"))
            manifest["requires_columns"] = _coerce_requires_columns(raw.get("requires_columns"))
            manifest["uses_skills"] = _coerce_str_list(raw.get("uses_skills"))
            manifest["example_questions"] = _coerce_str_list(raw.get("example_questions"))
    except Exception as e:  # noqa: BLE001 — never raise
        logger.warning("parse_frontmatter failed: %s", e)
        return _empty_manifest()

    return manifest


def validate_manifest(m: dict) -> tuple[bool, list[str]]:
    """Basic manifest sanity checks. Returns ``(ok, problems)``. Never raises."""
    problems: list[str] = []
    try:
        if not isinstance(m, dict):
            return False, ["manifest is not an object"]

        if not _coerce_str(m.get("name")):
            problems.append("name is required")
        if not _coerce_str(m.get("version")):
            problems.append("version is required")
        else:
            ver = _coerce_str(m.get("version"))
            if not re.match(r"^\d+(?:\.\d+){0,3}", ver):
                problems.append(f"version '{ver}' is not semver-like")

        rc = m.get("requires_columns")
        if rc is not None and not isinstance(rc, list):
            problems.append("requires_columns must be a list")
        elif isinstance(rc, list):
            for idx, entry in enumerate(rc):
                if not isinstance(entry, dict):
                    problems.append(f"requires_columns[{idx}] is not an object")
                    continue
                if not _coerce_str(entry.get("role")):
                    problems.append(f"requires_columns[{idx}] missing 'role'")
                if not _coerce_str(entry.get("as")):
                    problems.append(f"requires_columns[{idx}] missing 'as'")
    except Exception as e:  # noqa: BLE001
        logger.warning("validate_manifest failed: %s", e)
        return False, ["validation error"]

    return (len(problems) == 0), problems
