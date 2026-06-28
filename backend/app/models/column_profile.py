"""ColumnProfile — durable per-column understanding (ROADMAP F09, Phase 1).

One row per profiled column of an ingested dataset: dtype, unit, null%,
cardinality, sample values (PII-masked), PII flag, semantic role, synonyms, the
LLM-written meaning (P3), and the cross-source ``maps_to`` link (P3). This is
what makes a dataset reusable anytime — the agent and the user both see a
column's meaning/unit/role/links, not a bare name.

No FK constraints by design (tracking/enrichment table — avoids the
delete-cascade coupling landmine, same convention as ``IngestBatch``). Scoped by
``organization_id`` + ``data_source_id`` + ``table_name`` + ``column_name``.
Written ``status='pending'`` and surfaced in the Knowledge Review gate before it
reaches the agent — never auto-trusted (mirrors knowledge_proposer discipline).
"""
from sqlalchemy import Column, String, Integer, Float, Boolean, JSON, Index

from app.models.base import BaseSchema


class ColumnProfile(BaseSchema):
    __tablename__ = "column_profiles"
    __table_args__ = (
        Index("ix_column_profiles_org_ds", "organization_id", "data_source_id"),
        Index("ix_column_profiles_table", "data_source_id", "table_name"),
    )

    organization_id = Column(String(36), nullable=False, index=True)
    data_source_id = Column(String(36), nullable=True)
    connection_table_id = Column(String(36), nullable=True)

    table_name = Column(String, nullable=True)
    column_name = Column(String, nullable=False)
    normalized_name = Column(String, nullable=True)

    dtype = Column(String(16), nullable=True)          # int | float | date | bool | text
    unit = Column(String(32), nullable=True)           # ₹ / % / kg / count
    null_pct = Column(Float, nullable=False, default=0.0, server_default="0")
    cardinality = Column(Integer, nullable=False, default=0, server_default="0")
    sample_values = Column(JSON, nullable=True)        # list[str], PII-masked
    pii_flag = Column(Boolean, nullable=False, default=False, server_default="false")
    semantic_role = Column(String(16), nullable=True)  # id | date | measure | category
    synonyms = Column(JSON, nullable=True)             # list[str]

    meaning = Column(String, nullable=True)            # LLM-written (UNDERSTAND, P3)
    maps_to = Column(String, nullable=True)            # canonical brain entity (UNIFY, P3)
    source_ref = Column(JSON, nullable=True)           # {source_file, sheet, col_index}

    # pending | approved | rejected — review gate (approved-only reaches the agent)
    status = Column(String(16), nullable=False, default="pending", server_default="pending")
