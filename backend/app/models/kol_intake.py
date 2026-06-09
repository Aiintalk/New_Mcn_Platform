from sqlalchemy import (
    TIMESTAMP, BigInteger, Boolean, Column, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class KolIntakeQuestion(Base):
    """问卷题目配置（AI 对话引导提纲）"""
    __tablename__ = "kol_intake_questions"

    id            = Column(Integer,     primary_key=True, autoincrement=True)
    order_num     = Column(Integer,     nullable=False, default=0)
    category      = Column(String(50),  nullable=False, default="")
    question_text = Column(Text,        nullable=False)
    question_type = Column(String(20),  nullable=False, default="text")
    max_items     = Column(Integer,     nullable=True)
    is_required   = Column(Boolean,     nullable=False, default=True)
    is_active     = Column(Boolean,     nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class KolIntakeConfig(Base):
    """AI 配置（conversation_bridge / report_generation）"""
    __tablename__ = "kol_intake_configs"

    id            = Column(Integer,      primary_key=True, autoincrement=True)
    config_key    = Column(String(50),   nullable=False, unique=True)
    ai_model_id   = Column(Integer,      ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    system_prompt = Column(Text,         nullable=True)
    is_active     = Column(Boolean,      nullable=False, default=True)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class KolIntakeLink(Base):
    """一次性分享链接"""
    __tablename__ = "kol_intake_links"

    id           = Column(Integer,     primary_key=True, autoincrement=True)
    token        = Column(String(64),  nullable=False, unique=True)
    operator_id  = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kol_name     = Column(String(200), nullable=True)
    expires_at   = Column(TIMESTAMP(timezone=True), nullable=False)
    used_at      = Column(TIMESTAMP(timezone=True), nullable=True)
    submitted_at = Column(TIMESTAMP(timezone=True), nullable=True)
    is_active    = Column(Boolean,     nullable=False, default=True)
    created_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class KolIntakeOperatorSession(Base):
    """运营直发对话会话（不走分享链接）"""
    __tablename__ = "kol_intake_operator_sessions"

    id                  = Column(Integer,     primary_key=True, autoincrement=True)
    operator_id         = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kol_name            = Column(String(200), nullable=True)
    messages            = Column(JSONB,       nullable=False, default=list)
    ai_report           = Column(Text,        nullable=True)
    ai_report_raw       = Column(JSONB,       nullable=True)
    report_status       = Column(String(20),  nullable=False, default="pending")
    report_generated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    docx_path           = Column(String(500), nullable=True)
    pdf_path            = Column(String(500), nullable=True)
    created_at          = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at          = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class KolIntakeSubmission(Base):
    """对话记录与报告"""
    __tablename__ = "kol_intake_submissions"

    id                     = Column(Integer,     primary_key=True, autoincrement=True)
    link_id                = Column(Integer,     ForeignKey("kol_intake_links.id", ondelete="CASCADE"), nullable=False, unique=True)
    messages               = Column(JSONB,       nullable=False, default=list)
    ai_report              = Column(Text,        nullable=True)
    ai_report_raw          = Column(JSONB,       nullable=True)
    report_status          = Column(String(20),  nullable=False, default="pending")
    report_generated_at    = Column(TIMESTAMP(timezone=True), nullable=True)
    docx_path              = Column(String(500), nullable=True)
    pdf_path               = Column(String(500), nullable=True)
    kol_downloaded_at      = Column(TIMESTAMP(timezone=True), nullable=True)
    operator_downloaded_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at             = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at             = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
