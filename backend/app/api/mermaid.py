"""Mermaid 流程图 API"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.security import get_workspace_member, require_editor
from app.models.workspace import WorkspaceMember
from app.models.mermaid import MermaidDiagram

router = APIRouter()
logger = logging.getLogger(__name__)


class MermaidSave(BaseModel):
    job_id: str
    mermaid_text: str


@router.get("/diagrams/{workspace_id}")
def list_diagrams(
    workspace_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """列出工作空间的所有 Mermaid 流程图"""
    from app.models.job import Job
    diagrams = db.query(MermaidDiagram).filter_by(workspace_id=workspace_id).order_by(MermaidDiagram.updated_at.desc()).all()
    result = []
    for d in diagrams:
        job = db.query(Job).filter_by(id=d.job_id).first()
        result.append({
            "id": d.id,
            "job_id": d.job_id,
            "job_name": job.job_name if job else "",
            "mermaid_text": d.mermaid_text,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        })
    return result


@router.get("/diagrams/{workspace_id}/{job_id}")
def get_diagram(
    workspace_id: str,
    job_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """获取指定作业的 Mermaid 流程图"""
    d = db.query(MermaidDiagram).filter_by(workspace_id=workspace_id, job_id=job_id).first()
    if not d:
        return {"mermaid_text": ""}
    return {"id": d.id, "job_id": d.job_id, "mermaid_text": d.mermaid_text}


@router.post("/diagrams/{workspace_id}")
def save_diagram(
    workspace_id: str,
    body: MermaidSave,
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """保存或更新 Mermaid 流程图"""
    d = db.query(MermaidDiagram).filter_by(workspace_id=workspace_id, job_id=body.job_id).first()
    now = datetime.now(timezone.utc)
    if d:
        d.mermaid_text = body.mermaid_text
        d.updated_at = now
    else:
        d = MermaidDiagram(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            job_id=body.job_id,
            mermaid_text=body.mermaid_text,
        )
        db.add(d)
    db.commit()
    return {"ok": True}


@router.delete("/diagrams/{workspace_id}/{job_id}")
def delete_diagram(
    workspace_id: str,
    job_id: str,
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """删除 Mermaid 流程图"""
    d = db.query(MermaidDiagram).filter_by(workspace_id=workspace_id, job_id=job_id).first()
    if d:
        db.delete(d)
        db.commit()
    return {"ok": True}
