"""
app/models/subtitle.py

字幕提取（subtitle-extractor）ORM 模型 — Sprint 19 迁移自旧架构 subtitle-extractor-web：
  - SubtitleJob:     批量字幕任务（含 job_code 服务端 ID + access_code 用户查询码）
  - SubtitleItem:    批量任务条目（一行一条视频）
  - SubtitleConfig:  管理端配置（思维导图 Prompt + AI 模型）

公共服务走 adapter：tikhub / oss / asr / yunwu（不在本表存配置）。
"""
from sqlalchemy import BigInteger, Column, String, Text, Boolean, Integer, ForeignKey, TIMESTAMP, func

from app.core.database import Base


class SubtitleJob(Base):
    """字幕任务（单条 + 批量统一）

    kind='single' 单条 extract（Sprint 21 起异步化）
    kind='batch'  批量任务（Sprint 19 起的原生批量）
    deleted_at IS NULL 表示未删除（前端用户主动删除走软删除）
    """
    __tablename__ = "subtitle_jobs"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    job_code    = Column(String(32), nullable=False, unique=True)
    kind        = Column(String(16), nullable=False, default="batch")  # single / batch
    status      = Column(String(16), nullable=False, default="processing")  # processing/completed/failed
    phase       = Column(String(64), nullable=False, default="")
    total       = Column(Integer, nullable=False, default=0)
    success     = Column(Integer, nullable=False, default=0)
    failed      = Column(Integer, nullable=False, default=0)
    created_by  = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at  = Column(TIMESTAMP(timezone=True), nullable=True)  # 软删除时间戳


class SubtitleItem(Base):
    """任务条目（每个视频一行）

    批量任务：每条 share_text 一行
    单条任务：total=1，只有 1 行
    meta_json：单条任务完成后存视频元信息（play_url/cover_url/nickname 等），
              批量任务为 NULL
    """
    __tablename__ = "subtitle_items"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    job_id       = Column(BigInteger, ForeignKey("subtitle_jobs.id", ondelete="CASCADE"), nullable=False)
    row_number   = Column(Integer, nullable=False)
    original_url = Column(Text, nullable=False, default="")
    title        = Column(Text, nullable=False, default="")
    transcript   = Column(Text, nullable=False, default="")
    status       = Column(String(16), nullable=False, default="pending")  # pending/processing/success/failed
    error        = Column(Text, nullable=False, default="")
    meta_json    = Column(Text, nullable=True)  # 单条任务的视频元信息 JSON
    created_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class SubtitleConfig(Base):
    """字幕库管理端配置（思维导图 Prompt + AI 模型，参照 material_library_configs）"""
    __tablename__ = "subtitle_configs"

    id                = Column(BigInteger, primary_key=True, autoincrement=True)
    config_key        = Column(String(64), nullable=False, unique=True)
    mindmap_prompt    = Column(Text, nullable=True)
    mindmap_model_id  = Column(BigInteger, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    is_active         = Column(Boolean, nullable=False, default=True)
    created_at        = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at        = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
