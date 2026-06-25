"""Agent Templates services (HYBRID_AGENT_TEMPLATES, default OFF).

Turn a smart Studio into a portable, data-agnostic *template* (markdown +
frontmatter + manifest) — and back again. See ``docs/PLAN_AGENT_TEMPLATES.md``.

This package is purely additive and never run unless ``flags.AGENT_TEMPLATES``
is on. ``exporter`` (Phase 1) is the studio -> template direction.
"""
