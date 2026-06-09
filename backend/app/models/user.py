from sqlalchemy import TIMESTAMP, BigInteger, Column, Index, Integer, String, Text, func

from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False)
    real_name = Column(String(64), nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(32), nullable=False, default="operator")
    status = Column(String(32), nullable=False, default="enabled")
    password_changed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    token_version = Column(Integer, nullable=False, default=0)
    last_login_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_active_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)
