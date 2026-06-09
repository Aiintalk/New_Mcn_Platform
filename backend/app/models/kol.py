from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class Kol(Base):
    __tablename__ = "kols"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    account_name = Column(String(128), nullable=True)    # 抖音昵称（来自 TikHub）
    category = Column(String(64), nullable=True)
    platform = Column(String(32), nullable=True, default="douyin")
    douyin_id = Column(String(128), nullable=True)       # 抖音号（短ID）
    sec_uid = Column(String(128), nullable=True)         # TikHub 长标识
    avatar_url = Column(Text, nullable=True)
    signature = Column(Text, nullable=True)          # 抖音个人简介
    follower_count = Column(BigInteger, nullable=True)
    video_count = Column(Integer, nullable=True)
    owner = Column(String(128), nullable=True)          # 负责人姓名（自由文本）
    persona = Column(Text, nullable=True)
    content_plan = Column(Text, nullable=True)
    style_notes = Column(Text, nullable=True)
    tikhub_raw = Column(JSONB, nullable=True)
    owner_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    status = Column(String(32), nullable=False, default="active")
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(TIMESTAMP(timezone=True), nullable=True)
