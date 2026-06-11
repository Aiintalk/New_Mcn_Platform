from sqlalchemy import TIMESTAMP, BigInteger, Column, Integer, String, Text, func

from app.core.database import Base


class TikHubCredential(Base):
    __tablename__ = "tikhub_credentials"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    provider = Column(String(64), nullable=False, default="tikhub")
    label = Column(String(128))
    api_key = Column(Text, nullable=False)
    base_url = Column(String(512), nullable=False, default="https://api.tikhub.io")
    status = Column(String(32), nullable=False, default="active")
    active_requests = Column(Integer, nullable=False, default=0)
    max_concurrent = Column(Integer, nullable=False, default=5)
    max_users = Column(Integer, nullable=False, default=10)
    last_tested_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_latency_ms = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
