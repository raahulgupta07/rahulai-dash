from sqlalchemy import Column, String, Text, Integer, JSON, ForeignKey, Index

from app.models.base import BaseSchema


class ResultCacheEntry(BaseSchema):
    """Task 7 — deterministic create_data result cache (flag HYBRID_RESULT_CACHE).

    One row per (organization, report, cache_key). The cache_key is a SHA-256 of
    (normalized question text + the report's per-source row-count *watermark
    signature*). When the data behind the report is unchanged the watermark
    signature is stable, so re-asking the SAME question produces the SAME key and
    HITS — and we serve `result_json` WITHOUT re-running codegen + execution. A
    re-train / new upload bumps a source's profile watermark, the signature
    changes, the key changes, and the entry naturally MISSES so the result is
    rebuilt once (the stale row is simply never read again).

    `result_json` stores the formatted widget payload (columns/rows/info) plus the
    title/data_model/view/generated_code needed to recreate the create_data
    artifacts on a hit. Additive table — does not touch dash core. Inert unless
    the flag is on (nothing reads or writes this table otherwise).
    """

    __tablename__ = "result_cache_entries"

    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    report_id = Column(String(36), ForeignKey("reports.id"), nullable=True, index=True)

    # SHA-256 hex of (normalized_question + '|' + watermark_signature).
    cache_key = Column(String(64), nullable=False, index=True)

    # Echoed for debugging / invalidation visibility (not used for matching).
    question_norm = Column(Text, nullable=False, default="")
    watermark_sig = Column(String(64), nullable=False, default="")

    # The stored deliverable: {title, generated_code, formatted, data_model, view}.
    result_json = Column(JSON, nullable=False, default=dict)

    hit_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_result_cache_lookup", "organization_id", "cache_key"),
    )

    def __repr__(self) -> str:
        return f"<ResultCacheEntry(org={self.organization_id}, key={self.cache_key[:8]}…, hits={self.hit_count})>"
