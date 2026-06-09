from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, String, Text, func


from app.core.database import Base


class File(Base):
    __tablename__ = "files"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(64), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    oss_key = Column(Text, nullable=False)
    content_type = Column(String(128), nullable=True)
    output_id = Column(BigInteger, ForeignKey("outputs.id"), nullable=True)
    task_id = Column(BigInteger, ForeignKey("task_jobs.id"), nullable=True)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)
