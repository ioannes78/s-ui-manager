from sqlalchemy import String, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base

class Node(Base):
    __tablename__ = "nodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    region: Mapped[str] = mapped_column(String(100), default="")
    base_url: Mapped[str] = mapped_column(String(500))
    api_token_enc: Mapped[str] = mapped_column(Text)
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_ok_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(100), default="admin")
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
