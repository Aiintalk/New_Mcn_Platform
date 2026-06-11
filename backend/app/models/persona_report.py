"""
app/models/persona_report.py

人格定位报告 ORM 模型。
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Integer,
    String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class PersonaReport(Base):
    __tablename__ = "persona_reports"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    operator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Step 1 输入
    douyin_id = Column(String(200))
    douyin_nickname = Column(String(200))
    top10_text = Column(Text)
    recent30_text = Column(Text)
    questionnaire_files = Column(JSONB, default=list)
    supplement_text = Column(Text)
    supplement_files = Column(JSONB, default=list)

    # Step 2 输入（对标资料）
    benchmark_profile_files = Column(JSONB, default=list)
    benchmark_plan_files = Column(JSONB, default=list)

    # Step 3 生成结果
    profile_result = Column(Text)
    plan_result = Column(Text)
    raw_output = Column(Text)
    influencer_name = Column(String(200))

    # 文件路径
    profile_docx_path = Column(String(500))
    plan_docx_path = Column(String(500))

    # 状态
    status = Column(String(20), nullable=False, default="pending")
    generated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(DateTime(timezone=True))
