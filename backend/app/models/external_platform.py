from sqlalchemy import Column, String, ForeignKey, Boolean, JSON, Text
from sqlalchemy.orm import relationship
from app.models.base import BaseSchema
from cryptography.fernet import Fernet
from app.settings.config import settings
import json

class ExternalPlatform(BaseSchema):
    __tablename__ = "external_platforms"
    
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    platform_type = Column(String, nullable=False)  # 'slack', 'teams', 'email', 'telegram'
    platform_config = Column(JSON, nullable=False)  # Platform-specific configuration
    credentials = Column(Text, nullable=True)  # Encrypted sensitive credentials
    is_active = Column(Boolean, default=True, nullable=False)
    # HYBRID_AGENT_CHANNELS (mig agentchan1): when set, this channel belongs to a
    # single Studio (agent) instead of the whole org. NULL = org-wide (upstream).
    studio_id = Column(String(36), ForeignKey("studios.id"), nullable=True, index=True)
    # 'members' (verified org members only) | 'anyone' (open). Default 'members'.
    audience = Column(String(20), nullable=False, server_default="members", default="members")

    # Relationships
    reports = relationship("Report", back_populates="external_platform")
    organization = relationship("Organization", back_populates="external_platforms")
    external_user_mappings = relationship("ExternalUserMapping", back_populates="external_platform")
    studio = relationship("Studio")
    
    def encrypt_credentials(self, credentials: dict):
        """Encrypt sensitive credentials before storing"""
        fernet = Fernet(settings.dash_config.encryption_key)
        self.credentials = fernet.encrypt(json.dumps(credentials).encode()).decode()
    
    def decrypt_credentials(self) -> dict:
        """Decrypt stored credentials"""
        if not self.credentials:
            return {}
        fernet = Fernet(settings.dash_config.encryption_key)
        return json.loads(fernet.decrypt(self.credentials.encode()).decode())
    
    def __repr__(self):
        return f"<ExternalPlatform {self.platform_type}:{self.id} - {self.organization.name}>"