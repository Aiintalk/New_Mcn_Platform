from sqlalchemy import Column, Integer, String, Text, Boolean, Date, TIMESTAMP, func
from app.core.database import Base


class QianchuanCollectionPersona(Base):
    """千川爆文合集 — 达人分组表"""
    __tablename__ = "qianchuan_collection_personas"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), nullable=False, unique=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class QianchuanCollectionScript(Base):
    """千川爆文合集 — 脚本表"""
    __tablename__ = "qianchuan_collection_scripts"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    pool           = Column(String(20), nullable=False, default="global")
    persona_name   = Column(String(100), nullable=True)
    title          = Column(String(200), nullable=False)
    content        = Column(Text, nullable=False)
    likes          = Column(Integer, nullable=True)
    source         = Column(String(100), nullable=True)
    source_account = Column(String(100), nullable=True)
    script_date    = Column(Date, nullable=True)
    is_deleted     = Column(Boolean, nullable=False, default=False)
    created_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
