from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, Integer, String, Text, func

from app.core.database import Base


class TikHubCallLog(Base):
    __tablename__ = "tikhub_call_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    credential_id = Column(BigInteger, ForeignKey("tikhub_credentials.id", ondelete="SET NULL"))
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    platform = Column(String(64), nullable=False)
    endpoint = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    latency_ms = Column(Integer)
    error_message = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
