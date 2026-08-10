"""工作空间与成员模型"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspace"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000), default="")
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("user.id"))
    db_mode: Mapped[str] = mapped_column(String(20), default="memory")  # memory/sqlserver/goldendb
    db_conn: Mapped[str] = mapped_column(String(1000), default="")  # 加密连接串
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class WorkspaceMember(Base):
    __tablename__ = "workspace_member"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_ws_user"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("user.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="VIEWER")  # OWNER/EDITOR/VIEWER
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
