"""作业管理 API"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user, get_workspace_member, require_editor
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.job import Job, JobSource, JobTarget, TableMeta, FieldMapping, JobDependency
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
    """列出工作空间的作业（含统计列）"""
    q = db.query(Job).filter_by(workspace_id=workspace_id)
    if keyword:
        q = q.filter(Job.job_name.like(f"%{keyword}%"))
    jobs = q.order_by(Job.job_name).all()

    # 批量统计
    job_ids = [j.id for j in jobs]
    if job_ids:
        src_counts = dict(
            db.query(JobSource.job_id, func.count(JobSource.id))
            .filter(JobSource.job_id.in_(job_ids), JobSource.workspace_id == workspace_id)
            .group_by(JobSource.job_id)
            .all()
        )
        tgt_counts = dict(
            db.query(JobTarget.job_id, func.count(JobTarget.id))
            .filter(JobTarget.job_id.in_(job_ids), JobTarget.workspace_id == workspace_id)
            .group_by(JobTarget.job_id)
            .all()
        )
        fm_counts = dict(
            db.query(FieldMapping.job_id, func.count(FieldMapping.id))
            .filter(FieldMapping.job_id.in_(job_ids), FieldMapping.workspace_id == workspace_id)
            .group_by(FieldMapping.job_id)
            .all()
        )
        up_counts = dict(
            db.query(JobDependency.downstream_job_id, func.count(JobDependency.id))
            .filter(JobDependency.downstream_job_id.in_(job_ids), JobDependency.workspace_id == workspace_id)
            .group_by(JobDependency.downstream_job_id)
            .all()
        )
        down_counts = dict(
            db.query(JobDependency.upstream_job_id, func.count(JobDependency.id))
            .filter(JobDependency.upstream_job_id.in_(job_ids), JobDependency.workspace_id == workspace_id)
            .group_by(JobDependency.upstream_job_id)
            .all()
        )
    else:
        src_counts = tgt_counts = fm_counts = up_counts = down_counts = {}

    return [
        {
            "id": j.id,
            "job_name": j.job_name,
            "job_type": j.job_type,
            "description": j.description,
            "schedule": j.schedule,
            "sp_name": j.sp_name,
            "import_batch": j.import_batch,
            "source_count": src_counts.get(j.id, 0),
            "target_count": tgt_counts.get(j.id, 0),
            "field_mapping_count": fm_counts.get(j.id, 0),
            "upstream_count": up_counts.get(j.id, 0),
            "downstream_count": down_counts.get(j.id, 0),
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
        "import_batch": job.import_batch,
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


@router.post("/batch-delete/{workspace_id}")
def batch_delete_jobs(
    workspace_id: str,
    job_ids: list[str] = Body(...),
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """批量删除作业"""
    from sqlalchemy import or_
    for job_id in job_ids:
        db.query(JobSource).filter_by(workspace_id=workspace_id, job_id=job_id).delete()
        db.query(JobTarget).filter_by(workspace_id=workspace_id, job_id=job_id).delete()
        db.query(FieldMapping).filter_by(workspace_id=workspace_id, job_id=job_id).delete()
        db.query(JobDependency).filter(
            JobDependency.workspace_id == workspace_id,
            or_(
                JobDependency.upstream_job_id == job_id,
                JobDependency.downstream_job_id == job_id,
            ),
        ).delete()
    db.query(Job).filter(Job.id.in_(job_ids), Job.workspace_id == workspace_id).delete(synchronize_session=False)
    db.commit()
    rebuild_dependencies(db, workspace_id)
    return {"ok": True, "deleted": len(job_ids)}


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


@router.get("/export/{workspace_id}")
def export_jobs(
    workspace_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """导出工作空间所有作业为 Excel"""
    import io
    from fastapi.responses import StreamingResponse
    from openpyxl import Workbook

    jobs = db.query(Job).filter_by(workspace_id=workspace_id).order_by(Job.job_name).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "作业血缘关系"
    headers = ["作业名称", "作业类型", "源表", "目标表", "存过名称", "字段映射", "调度", "描述"]
    ws.append(headers)

    for job in jobs:
        sources = db.query(JobSource).filter_by(workspace_id=workspace_id, job_id=job.id).all()
        targets = db.query(JobTarget).filter_by(workspace_id=workspace_id, job_id=job.id).all()
        mappings = db.query(FieldMapping).filter_by(workspace_id=workspace_id, job_id=job.id).all()

        src_names = []
        tgt_names = []
        for s in sources:
            t = db.query(TableMeta).filter_by(id=s.table_id).first()
            if t:
                src_names.append(t.table_name)
        for t in targets:
            tbl = db.query(TableMeta).filter_by(id=t.table_id).first()
            if tbl:
                tgt_names.append(tbl.table_name)

        fm_lines = []
        for m in mappings:
            src_t = db.query(TableMeta).filter_by(id=m.source_table_id).first() if m.source_table_id else None
            tgt_t = db.query(TableMeta).filter_by(id=m.target_table_id).first() if m.target_table_id else None
            src_part = f"{src_t.table_name}.{m.source_field}" if src_t and m.source_field else m.source_field
            tgt_part = f"{tgt_t.table_name}.{m.target_field}" if tgt_t and m.target_field else m.target_field
            prefix = f"[{m.operation}] " if m.operation else ""
            fm_lines.append(f"{prefix}{src_part} -> {tgt_part}")

        ws.append([
            job.job_name,
            job.job_type,
            ", ".join(src_names),
            ", ".join(tgt_names),
            job.sp_name,
            "\n".join(fm_lines),
            job.schedule,
            job.description,
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    ws_name = db.query(Workspace).filter_by(id=workspace_id).first()
    filename = f"lineage_export_{ws_name.name if ws_name else workspace_id}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
