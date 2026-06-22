from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, Integer, String, Text, func

from app.core.database import Base


class OssCallLog(Base):
    __tablename__ = "oss_call_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    credential_id = Column(BigInteger, ForeignKey("service_credentials.id", ondelete="SET NULL"))
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    operation = Column(String(16), nullable=False)  # upload / download / delete
    status = Column(String(32), nullable=False)     # success / fail
    latency_ms = Column(Integer)
    oss_key = Column(Text)
    error_message = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
