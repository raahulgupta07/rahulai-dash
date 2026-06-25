from sqlalchemy import Boolean, Column, String, Text, Integer, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import BaseSchema


class QueryLibraryItem(BaseSchema):
    """A saved, named, proven SQL query for a data source (Phase-3 Query Library).

    Org-shared library of reusable SELECT queries (name -> sql_text) that can be
    run read-only against the data source. `source` records provenance
    ('manual' | 'chat' | 'promoted') and `run_count` tracks reuse. One row per
    (organization, data_source, name). Additive — does not touch dash core.
    """
    __tablename__ = 'query_library_items'
    __table_args__ = (
        UniqueConstraint(
            'organization_id', 'data_source_id', 'name',
            name='uq_query_library_item_org_ds_name',
        ),
    )

    organization_id = Column(String(36), ForeignKey('organizations.id'), nullable=False, index=True)
    data_source_id = Column(String(36), ForeignKey('data_sources.id'), nullable=False, index=True)
    name = Column(String, nullable=False)

    description = Column(Text, nullable=False, default='')
    sql_text = Column(Text, nullable=False, default='')
    tags = Column(JSON, nullable=False, default=list)
    source = Column(String(50), nullable=False, default='manual')
    run_count = Column(Integer, nullable=False, default=0)
    owner = Column(String, nullable=True)
    status = Column(String(50), nullable=False, default='draft')

    # Golden Query Promotion (flag HYBRID_GOLDEN_QUERIES).
    # A row becomes golden when it has been repeatedly verified as correct
    # (verified_count >= threshold OR a thumbs-up fires on it). Golden rows
    # are surfaced first in the codegen recall block.  Both columns default
    # to their false/0 equivalents so existing rows are unaffected on upgrade.
    is_golden = Column(Boolean, nullable=False, default=False, server_default='false')
    verified_count = Column(Integer, nullable=False, default=0, server_default='0')

    # Relationships
    organization = relationship("Organization")
    data_source = relationship("DataSource")
