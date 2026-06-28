"""Universal Ingest Brain (ROADMAP F09) — isolated feature package.

Self-contained on purpose: drop-in subpackage so the whole feature can be added
or removed without touching the existing ``services/ingest/`` autotrain staging
pipeline (different concern). Everything here is gated by
``flags.INGEST_BRAIN`` (default OFF) — with the flag off nothing in here runs and
the from-file ingest path is byte-identical to today.

Stages: DETECT → EXTRACT → PROFILE → UNDERSTAND → UNIFY → STORE+LEARN.
Built in phases (P1 messy-Excel+profile+preview · P2 PDF/Word/image · P3 unify).
"""
