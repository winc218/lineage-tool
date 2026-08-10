"""血缘分析 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_workspace_member
from app.models.workspace import WorkspaceMember
from app.services.lineage_service import (
    graph_data, detect_cycles, impact_analysis, root_cause_analysis,
)

router = APIRouter()


@router.get("/graph/{workspace_id}")
def get_graph(
    workspace_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """获取完整血缘图数据（nodes/edges/cycles）"""
    return graph_data(db, workspace_id)


@router.get("/cycles/{workspace_id}")
def get_cycles(
    workspace_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """获取环路检测报告"""
    return {"cycles": detect_cycles(db, workspace_id)}


@router.get("/impact/{workspace_id}/{job_id}")
def get_impact(
    workspace_id: str,
    job_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """影响分析：下游作业"""
    return {"downstream": impact_analysis(db, workspace_id, job_id)}


@router.get("/trace/{workspace_id}/{job_id}")
def get_trace(
    workspace_id: str,
    job_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """溯源分析：上游作业"""
    return {"upstream": root_cause_analysis(db, workspace_id, job_id)}
