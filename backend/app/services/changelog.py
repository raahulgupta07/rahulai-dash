"""Changelog service — parse the hybrid "What's new" changelog (read-only, pure).

Source of truth: ``CHANGELOG_HYBRID.md`` at the repo root (created by the parent,
never by this module). ``VERSION_HYBRID`` at the repo root holds the current
semver.

Everything here is defensive: malformed markdown is skipped, a missing file
yields an empty list, and **nothing raises**. Callers (the read-only route)
can treat any failure as "no changelog".

Strict header format (newest entry on top):

    ## v1.2.0 — Intelligence Layer — 8 capabilities  (2026-06-25)
    - bullet one
    - bullet two

The title may itself contain " — " (em dash). Rule: the FIRST ``v<semver> — ``
prefix is the version, the LAST ``(YYYY-MM-DD)`` is the date, and the title is
everything in between.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# repo root = up from backend/app/services/changelog.py
#   .../changelog.py -> services -> app -> backend -> <repo root>
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
_CHANGELOG_PATH = os.path.join(_REPO_ROOT, "CHANGELOG_HYBRID.md")
_VERSION_PATH = os.path.join(_REPO_ROOT, "VERSION_HYBRID")

# Header: "## v1.2.0 — <title>  (2026-06-25)"
# - version: first "v<semver>" token after "## "
# - the rest (title + date) captured greedily, date pulled out separately so a
#   title containing " — " or even "(...)" survives.
_HEADER_RE = re.compile(r"^##\s+v(?P<version>\d+(?:\.\d+){0,3})\s+—\s+(?P<rest>.*\S)\s*$")
# Last (YYYY-MM-DD) in the line.
_DATE_RE = re.compile(r"\((?P<date>\d{4}-\d{2}-\d{2})\)\s*$")


def parse_changelog(md_text: str) -> list[dict]:
    """Parse changelog markdown → list of entries in file order (newest first).

    Each entry: ``{"version","title","date","features":[...],"details":[...]}``.

    Bullet convention:
      * **Top-level** bullets (``- ``, no leading indent) are *user-facing* and
        land in ``features`` — keep these plain-language for the "What's new"
        popover.
      * **Indented** bullets (any leading whitespace before ``- ``/``* ``) are
        *technical detail* and land in ``details`` — shown only on the full
        ``/changelog`` page, hidden from the popover.

    Malformed entries are skipped; never raises.
    """
    entries: list[dict] = []
    if not md_text or not isinstance(md_text, str):
        return entries

    current: dict | None = None
    try:
        for raw in md_text.splitlines():
            line = raw.rstrip()
            m = _HEADER_RE.match(line.strip())
            if m:
                # flush previous
                if current is not None:
                    entries.append(current)
                version = m.group("version")
                rest = m.group("rest").strip()
                date = ""
                dm = _DATE_RE.search(rest)
                if dm:
                    date = dm.group("date")
                    # title = rest with the trailing "(date)" removed
                    title = rest[: dm.start()].strip()
                    # strip trailing whitespace/dashes left over
                    title = title.rstrip(" —-").strip()
                else:
                    title = rest
                current = {
                    "version": version,
                    "title": title,
                    "date": date,
                    "features": [],
                    "details": [],
                }
                continue

            if current is None:
                continue
            indented = line[:1].isspace()  # leading whitespace = technical detail
            stripped = line.lstrip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                text = stripped[2:].strip()
                if text:
                    (current["details"] if indented else current["features"]).append(text)

        if current is not None:
            entries.append(current)
    except Exception as e:  # noqa: BLE001 — never raise
        logger.warning("parse_changelog failed: %s", e)
        return []

    return entries


def load_changelog() -> list[dict]:
    """Read + parse CHANGELOG_HYBRID.md from the repo root. Missing → []."""
    try:
        with open(_CHANGELOG_PATH, "r", encoding="utf-8") as fh:
            return parse_changelog(fh.read())
    except FileNotFoundError:
        return []
    except Exception as e:  # noqa: BLE001
        logger.warning("load_changelog failed: %s", e)
        return []


def current_version() -> str:
    """Current semver from VERSION_HYBRID; fall back to top changelog entry, else 0.0.0."""
    try:
        with open(_VERSION_PATH, "r", encoding="utf-8") as fh:
            v = fh.read().strip()
            if v:
                return v
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("current_version read failed: %s", e)

    entries = load_changelog()
    if entries:
        return entries[0].get("version") or "0.0.0"
    return "0.0.0"


def _semver_tuple(v: str | None) -> tuple[int, int, int, int]:
    """Parse a semver-ish string into a 4-int tuple (padded). Defensive on junk."""
    if not v or not isinstance(v, str):
        return (0, 0, 0, 0)
    parts = v.strip().lstrip("v").split(".")
    out: list[int] = []
    for p in parts[:4]:
        try:
            out.append(int(re.sub(r"[^0-9].*$", "", p) or "0"))
        except Exception:  # noqa: BLE001
            out.append(0)
    while len(out) < 4:
        out.append(0)
    return tuple(out[:4])  # type: ignore[return-value]


def entries_after(entries: list[dict], last_seen_version: str | None) -> list[dict]:
    """Entries strictly newer than ``last_seen_version`` (semver compare).

    If ``last_seen_version`` is None/empty → every entry is unseen.
    Never raises.
    """
    if not entries:
        return []
    if not last_seen_version:
        return list(entries)
    try:
        seen = _semver_tuple(last_seen_version)
        return [e for e in entries if _semver_tuple(e.get("version")) > seen]
    except Exception as e:  # noqa: BLE001
        logger.warning("entries_after failed: %s", e)
        return list(entries)
