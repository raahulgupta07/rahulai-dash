from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index

from app.models.base import BaseSchema


class FolderSyncState(BaseSchema):
    """One row per (org, local file path) tracked by the desktop Folder Sync agent
    (HYBRID_FOLDER_SYNC, default OFF).

    The local agent watches a folder and POSTs changed files to /api/sync/file with
    an API key. This table is the server-side delta ledger: it remembers the last
    synced sha256 per path so byte-identical re-pushes are no-ops, and it remembers
    which DataSource / Studio a path maps to so an edited file replaces the same
    data agent instead of spawning a duplicate.

    No file bytes live here — only the path, hash and the ids it resolved to.
    """

    __tablename__ = "folder_sync_states"
    __table_args__ = (
        # A path is unique per org — that's the upsert key.
        Index("ix_folder_sync_org_path", "organization_id", "source_path", unique=True),
        Index("ix_folder_sync_org_machine", "organization_id", "machine_label"),
    )

    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    machine_label = Column(String(255), nullable=True)   # "Rahul — MacBook Pro"
    source_path = Column(String(1024), nullable=False)    # local absolute path (the key)
    file_name = Column(String(512), nullable=True)

    file_hash = Column(String(64), nullable=True)         # sha256 of last synced bytes
    file_id = Column(String(36), nullable=True)           # last File row created
    data_source_id = Column(String(36), nullable=True)    # the data agent this path feeds
    studio_id = Column(String(36), nullable=True)         # optional target Studio binding

    status = Column(String(20), nullable=False, default="new")  # new|updated|skipped|error
    error = Column(Text, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
