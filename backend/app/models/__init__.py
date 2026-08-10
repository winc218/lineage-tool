"""模型包 - 导入触发注册"""
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.job import (
    TableMeta, Job, JobSource, JobTarget, FieldMapping, JobDependency,
)
from app.models.sp import SpSource, SpDefinition, SpParseResult, LineageDiff

__all__ = [
    "User", "Workspace", "WorkspaceMember",
    "TableMeta", "Job", "JobSource", "JobTarget", "FieldMapping", "JobDependency",
    "SpSource", "SpDefinition", "SpParseResult", "LineageDiff",
]
