from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base

_DEFAULT_TABS = [
    "dashboard", "persona", "references", "products",
    "qianchuan-writer", "seeding-writer", "persona-writer",
    "livestream-writer", "livestream-review", "values-writer",
    "script-review", "film-review", "retrospective",
]


class KolWorkspaceConfig(Base):
    __tablename__ = "kol_workspace_configs"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    kol_id           = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False, unique=True)
    enabled_tabs     = Column(JSONB, nullable=False, default=_DEFAULT_TABS)
    prompt_overrides = Column(JSONB, nullable=False, default=dict)
    created_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
