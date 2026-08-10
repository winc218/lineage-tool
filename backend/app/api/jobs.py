"""作业管理 API"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, get_workspace_member, require_editor
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.models.job import Job, JobSource, JobTarget, TableMeta, FieldMapping
from app.services.lineage_service import rebuild_dependencies

router = APIRouter()


class JobUpdate(BaseModel):
    job_name: str | None = None
    job_type: str | None = None
    description: str | None = None
    schedule: str | None = None
    sp_name: str | None = None


# 可更新字段白名单
UPDATABLE_FIELDS = {"job_name", "job_type", "description", "schedule", "sp_name"}


@router.get("/list/{workspace_id}")
def list_jobs(
    workspace_id: str,
    keyword: str = Query(""),
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """列出工作空间的作业"""
    q = db.query(Job).filter_by(workspace_id=workspace_id)
    if keyword:
        q = q.filter(Job.job_name.like(f"%{keyword}%"))
    jobs = q.order_by(Job.job_name).all()
    return [
        {
            "id": j.id,
            "job_name": j.job_name,
            "job_type": j.job_type,
            "description": j.description,
            "schedule": j.schedule,
            "sp_name": j.sp_name,
            "import_batch": j.import_batch,
        }
        for j in jobs
    ]


@router.get("/detail/{workspace_id}/{job_id}")
def job_detail(
    workspace_id: str,
    job_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """作业详情：源表、目标表、字段映射、上下游"""
    job = db.query(Job).filter_by(workspace_id=workspace_id, id=job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="作业不存在")

    def _tables(job_id, model):
        rows = db.query(model).filter_by(workspace_id=workspace_id, job_id=job_id).all()
        result = []
        for r in rows:
            t = db.query(TableMeta).filter_by(id=r.table_id).first()
            if t:
                result.append({"table_id": t.id, "table_name": t.table_name, "db_name": t.db_name})
        return result

    source_tables = _tables(job_id, JobSource)
    target_tables = _tables(job_id, JobTarget)

    mappings = db.query(FieldMapping).filter_by(workspace_id=workspace_id, job_id=job_id).all()
    field_mappings = []
    for m in mappings:
        src_t = db.query(TableMeta).filter_by(id=m.source_table_id).first() if m.source_table_id else None
        tgt_t = db.query(TableMeta).filter_by(id=m.target_table_id).first() if m.target_table_id else None
        field_mappings.append({
            "source_field": m.source_field,
            "target_field": m.target_field,
            "operation": m.operation,
            "source": m.source,
            "source_table": src_t.table_name if src_t else "",
            "target_table": tgt_t.table_name if tgt_t else "",
        })

    # 上下游
    from app.services.lineage_service import impact_analysis, root_cause_analysis
    downstream = impact_analysis(db, workspace_id, job_id)
    upstream = root_cause_analysis(db, workspace_id, job_id)

    return {
        "id": job.id,
        "job_name": job.job_name,
        "job_type": job.job_type,
        "description": job.description,
        "schedule": job.schedule,
        "sp_name": job.sp_name,
        "source_tables": source_tables,
        "target_tables": target_tables,
        "field_mappings": field_mappings,
        "upstream": upstream,
        "downstream": downstream,
    }


@router.put("/{workspace_id}/{job_id}")
def update_job(
    workspace_id: str,
    job_id: str,
    body: JobUpdate,
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter_by(workspace_id=workspace_id, id=job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="作业不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        if k in UPDATABLE_FIELDS:
            setattr(job, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/{workspace_id}/{job_id}")
def delete_job(
    workspace_id: str,
    job_id: str,
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter_by(workspace_id=workspace_id, id=job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="作业不存在")
    db.query(JobSource).filter_by(workspace_id=workspace_id, job_id=job_id).delete()
    db.query(JobTarget).filter_by(workspace_id=workspace_id, job_id=job_id).delete()
    db.query(FieldMapping).filter_by(workspace_id=workspace_id, job_id=job_id).delete()
    from app.models.job import JobDependency
    from sqlalchemy import or_
    db.query(JobDependency).filter(
        JobDependency.workspace_id == workspace_id,
        or_(
            JobDependency.upstream_job_id == job_id,
            JobDependency.downstream_job_id == job_id,
        ),
    ).delete()
    db.delete(job)
    db.commit()
    rebuild_dependencies(db, workspace_id)
    return {"ok": True}
