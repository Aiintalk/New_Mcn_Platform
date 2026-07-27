"""
app/evaluation/models/version.py

eval_versions — 工具版本快照（不可编辑，只能创建/复制/软删）。

config_payload 固化被测工具完整配置（prompt 模板、model_id、参数、维度权重、评委模型），
保证历史 run 可复现。source_kol_id 用于「关联维护」：记录 config_payload 来源红人便于追溯。
"""
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.core.database import Base


class EvalVersion(Base):
    """版本快照：自包含配置，不引用外部表（除 created_by/source_kol_id 可选关联）。"""

    __tablename__ = "eval_versions"

    id                 = Column(BigInteger, primary_key=True, autoincrement=True)
    tool_code          = Column(String(64), nullable=False)
    name               = Column(String(128), nullable=False)
    description        = Column(Text, nullable=True)
    config_payload     = Column(JSONB, nullable=False)
    parent_version_id  = Column(
        BigInteger,
        ForeignKey("eval_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_kol_id      = Column(
        BigInteger,
        ForeignKey("kols.id", ondelete="SET NULL"),
        nullable=True,
    )
    auto_run_on_create = Column(Boolean, nullable=False, default=False)
    auto_run_tags      = Column(ARRAY(Text), nullable=False, default=list)
    is_active          = Column(Boolean, nullable=False, default=True)
    created_by         = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at         = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at         = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    deleted_at         = Column(TIMESTAMP(timezone=True), nullable=True)
