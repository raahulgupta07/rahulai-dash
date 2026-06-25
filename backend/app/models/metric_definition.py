from sqlalchemy import Boolean, Column, Float, Numeric, String, Text, ForeignKey, Index, DateTime
from sqlalchemy.orm import relationship

from app.models.base import BaseSchema


class MetricDefinition(BaseSchema):
    """A named business metric for a data source (Phase-1 Metrics Catalog).

    Maps a human metric name -> a free-text definition -> a SQL calculation
    (`sql_calc`) that can be test-run read-only against the data source. One row
    per (organization, data_source, name). Additive — does not touch dash core.
    """
    __tablename__ = 'metric_definitions'
    # Bi-temporal: multiple versions per logical key may coexist (prior versions
    # carry invalid_at). Uniqueness on the CURRENT row only is enforced by the
    # partial unique index `uq_metric_def_current` (migration bitemp2, PG-only).
    # Here we keep a plain non-unique lookup index on the key.
    __table_args__ = (
        Index('ix_metric_def_name', 'organization_id', 'data_source_id', 'name'),
    )

    organization_id = Column(String(36), ForeignKey('organizations.id'), nullable=False, index=True)
    data_source_id = Column(String(36), ForeignKey('data_sources.id'), nullable=False, index=True)
    name = Column(String, nullable=False)

    definition = Column(Text, nullable=False, default='')
    table_ref = Column(String, nullable=False, default='')
    sql_calc = Column(Text, nullable=False, default='')
    owner = Column(String, nullable=True)
    status = Column(String(50), nullable=False, default='draft')

    # --- verified metrics (HYBRID_VERIFIED_METRICS) -------------------------
    # is_locked: when True and VERIFIED_METRICS is ON, resolve_metric executes
    # sql_calc read-only to obtain the authoritative live value instead of
    # returning the static definition only. OFF-flag rows treat this as False.
    is_locked = Column(Boolean, nullable=False, default=False, server_default="false")
    # last_value: the most recently computed scalar from sql_calc (nullable —
    # populated on first locked resolve; NULL until the first execution).
    last_value = Column(Numeric, nullable=True)
    # last_value_at: timestamp of the last successful locked execution.
    last_value_at = Column(DateTime, nullable=True)

    # --- bi-temporal (HYBRID_BITEMPORAL) -----------------------------------
    valid_at = Column(DateTime, nullable=True)
    invalid_at = Column(DateTime, nullable=True)
    superseded_by = Column(String(36), nullable=True)

    # Relationships
    organization = relationship("Organization")
    data_source = relationship("DataSource")
