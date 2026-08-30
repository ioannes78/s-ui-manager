from sqlalchemy import (
    String, Integer, BigInteger, Float, Boolean, DateTime, Text,
    ForeignKey, UniqueConstraint,
)
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
    group_name: Mapped[str] = mapped_column(String(100), default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str] = mapped_column(Text, default="")
    sui_version: Mapped[str] = mapped_column(String(50), default="")
    last_latency_ms: Mapped[int|None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    last_ok_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CentralUser(Base):
    __tablename__ = "central_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), default="")
    credential_enc: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    total_gb: Mapped[float] = mapped_column(Float, default=0)
    used_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    expire_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    limit_ip: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserNodeBinding(Base):
    __tablename__ = "user_node_bindings"
    __table_args__ = (UniqueConstraint("user_id", "node_id", name="uq_user_node_binding"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("central_users.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    sync_status: Mapped[str] = mapped_column(String(30), default="pending")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_synced_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)


class TaskJob(Base):
    __tablename__ = "task_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    actor: Mapped[str] = mapped_column(String(100), default="admin")
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)


class TaskTarget(Base):
    __tablename__ = "task_targets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("task_jobs.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int|None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    target_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    detail: Mapped[str] = mapped_column(Text, default="")


class ConfigSnapshot(Base):
    __tablename__ = "config_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(200), default="manual")
    payload: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int|None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(30), default="warning")
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    message: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(100), default="admin")
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
