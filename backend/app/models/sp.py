"""存储过程来源、定义、解析结果、血缘差异模型"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SpSource(Base):
    __tablename__ = "sp_source"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))  # git / database
    config: Mapped[str] = mapped_column(Text, default="")  # 加密 JSON
    last_sync_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class SpDefinition(Base):
    __tablename__ = "sp_definition"
    __table_args__ = (
        UniqueConstraint("workspace_id", "sp_source_id", "sp_name", name="uq_ws_spdef"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    sp_source_id: Mapped[str] = mapped_column(String(64), ForeignKey("sp_source.id"), index=True)
    sp_name: Mapped[str] = mapped_column(String(200), index=True)
    sp_text: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(String(500), default="")
    matched_job_id: Mapped[str] = mapped_column(String(64), ForeignKey("job.id"), nullable=True)
    match_status: Mapped[str] = mapped_column(String(20), default="unmatched")
    parse_status: Mapped[str] = mapped_column(String(20), default="pending")
    parse_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class SpParseResult(Base):
    __tablename__ = "sp_parse_result"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    sp_def_id: Mapped[str] = mapped_column(String(64), ForeignKey("sp_definition.id"), index=True)
    source_tables: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组
    target_tables: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组
    column_lineage: Mapped[str] = mapped_column(Text, default="[]")  # JSON
    parsed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class LineageDiff(Base):
    __tablename__ = "lineage_diff"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("job.id"), index=True)
    sp_def_id: Mapped[str] = mapped_column(String(64), ForeignKey("sp_definition.id"), index=True)
    diff_type: Mapped[str] = mapped_column(String(20))  # source_missing/source_extra/target_missing/target_extra/mismatch
    excel_value: Mapped[str] = mapped_column(String(500), default="")
    sp_value: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/accepted/rejected
    action: Mapped[str] = mapped_column(String(20), default="add")  # add/remove/update
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
