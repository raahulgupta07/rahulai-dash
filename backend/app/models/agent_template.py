from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Index

from app.models.base import BaseSchema


class AgentTemplate(BaseSchema):
    """A shareable, versioned Agent Template (HYBRID_AGENT_TEMPLATES, default OFF).

    Captures the *data-agnostic* know-how of a smart Studio — instructions/rules,
    metric definitions (formula + grain), example *patterns*, skill refs and
    persona/voice/summary — so another user can BIND it to their own columns and
    spin up their own agent. Data, credentials, rows/values, org id, members and
    literal table/column names NEVER live here.

    The portable artifact is ``body_md`` (markdown + frontmatter). ``manifest`` is
    the parsed JSON mirror of the frontmatter for fast querying (name, version,
    author, domain, requires_columns, uses_skills, example_questions).

    The binding contract lives in ``manifest['requires_columns']`` — a list of
    ``{role, as}`` (e.g. ``{role:'TEMPORAL', as:'order_date'}``). On import the
    binder maps each role to the consumer's real column and rewrites the
    ``{placeholder}`` tokens in the body.

    Versioning: published versions are IMMUTABLE. A new version of the same logical
    template = a new row sharing ``slug`` with a bumped ``version`` (semver).

    Scope: ``org`` (visible to the owning organization) or ``global`` (cross-org
    gallery). For global rows ``organization_id`` may be NULL.
    """

    __tablename__ = "agent_templates"

    name = Column(String, nullable=False, index=True)
    slug = Column(String(160), nullable=False, index=True)        # stable logical id across versions
    version = Column(String(20), nullable=False, default="1.0.0")  # semver

    description = Column(Text, nullable=True)
    domain_tags = Column(JSON, nullable=True, default=list)        # ['retail','sales']

    scope = Column(String(20), nullable=False, default="org")      # 'org'|'global'
    status = Column(String(20), nullable=False, default="draft")   # 'draft'|'published'

    body_md = Column(Text, nullable=False)                         # the portable artifact (md+frontmatter)
    manifest = Column(JSON, nullable=True, default=dict)           # parsed frontmatter (requires_columns, uses_skills, ...)

    author_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    source_studio_id = Column(String(36), ForeignKey("studios.id"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_agent_template_scope_status", "scope", "status"),
        Index("ix_agent_template_slug_version", "slug", "version"),
        Index("ix_agent_template_org", "organization_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<AgentTemplate(id={self.id}, slug={self.slug}, v={self.version}, scope={self.scope}, status={self.status})>"
