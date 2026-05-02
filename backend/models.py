from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from database import Base
import uuid

def gen_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id           = Column(String(36), primary_key=True, default=gen_uuid)
    username     = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100))
    role         = Column(String(20), default="viewer")
    created_at   = Column(DateTime, server_default=func.now())

class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"
    id                = Column(String(36), primary_key=True, default=gen_uuid)
    user_id           = Column(String(36), ForeignKey("users.id"), nullable=False)
    credential_id     = Column(Text, unique=True, nullable=False)
    public_key        = Column(Text, nullable=False)
    sign_count        = Column(String(20), default="0")
    created_at        = Column(DateTime, server_default=func.now())

class Session(Base):
    __tablename__ = "sessions"
    id         = Column(String(36), primary_key=True, default=gen_uuid)
    user_id    = Column(String(36), ForeignKey("users.id"), nullable=False)
    token      = Column(Text, nullable=False)
    revoked    = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())