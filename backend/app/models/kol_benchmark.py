from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.sql import func

from app.core.database import Base


class KolBenchmark(Base):
    __tablename__ = "kol_benchmarks"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    kol_id       = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False)
    account_name = Column(String(200), nullable=False)
    account_type = Column(String(20), nullable=False)   # 'content' | 'livestream'
    description  = Column(Text, nullable=True)
    sort_order   = Column(Integer, nullable=False, default=0)
    created_by   = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
