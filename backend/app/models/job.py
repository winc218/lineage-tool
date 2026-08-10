"""作业、表、源/目标关系、字段映射、依赖关系模型"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TableMeta(Base):
    __tablename__ = "table_meta"
    __table_args__ = (UniqueConstraint("workspace_id", "table_name", name="uq_ws_table"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    table_name: Mapped[str] = mapped_column(String(200), index=True)
    db_name: Mapped[str] = mapped_column(String(100), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (UniqueConstraint("workspace_id", "job_name", name="uq_ws_job"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    job_name: Mapped[str] = mapped_column(String(200), index=True)
    job_type: Mapped[str] = mapped_column(String(50), default="ETL")
    description: Mapped[str] = mapped_column(String(1000), default="")
    schedule: Mapped[str] = mapped_column(String(50), default="")
    sp_name: Mapped[str] = mapped_column(String(200), default="")
    source_file: Mapped[str] = mapped_column(String(500), default="")
    import_batch: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class JobSource(Base):
    """作业-源表关系"""
    __tablename__ = "job_source"
    __table_args__ = (UniqueConstraint("workspace_id", "job_id", "table_id", name="uq_ws_src"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("job.id"), index=True)
    table_id: Mapped[str] = mapped_column(String(64), ForeignKey("table_meta.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class JobTarget(Base):
    """作业-目标表关系"""
    __tablename__ = "job_target"
    __table_args__ = (UniqueConstraint("workspace_id", "job_id", "table_id", name="uq_ws_tgt"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("job.id"), index=True)
    table_id: Mapped[str] = mapped_column(String(64), ForeignKey("table_meta.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class FieldMapping(Base):
    """字段映射（支持多源字段→目标字段，按操作类型分组）"""
    __tablename__ = "field_mapping"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("job.id"), index=True)
    source_table_id: Mapped[str] = mapped_column(String(64), ForeignKey("table_meta.id"), index=True)
    target_table_id: Mapped[str] = mapped_column(String(64), ForeignKey("table_meta.id"), index=True)
    source_field: Mapped[str] = mapped_column(String(200), default="")
    target_field: Mapped[str] = mapped_column(String(200), default="")
    # 操作类型：INSERT / UPDATE / MERGE / 其他（表示该映射属于哪种操作的写入）
    operation: Mapped[str] = mapped_column(String(50), default="")
    # 来源：excel / sp（标记该映射是从 Excel 导入还是 SP 解析补充的）
    source: Mapped[str] = mapped_column(String(20), default="excel")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class JobDependency(Base):
    """作业依赖（血缘核心，派生表）"""
    __tablename__ = "job_dependency"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "upstream_job_id", "downstream_job_id", "via_table_id",
            name="uq_ws_dep",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey("workspace.id"), index=True)
    upstream_job_id: Mapped[str] = mapped_column(String(64), ForeignKey("job.id"), index=True)
    downstream_job_id: Mapped[str] = mapped_column(String(64), ForeignKey("job.id"), index=True)
    via_table_id: Mapped[str] = mapped_column(String(64), ForeignKey("table_meta.id"), index=True)
    via_table_name: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(20), default="excel")  # excel / sp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
