"""存储过程校验 API"""
import os
import tempfile
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_workspace_member, require_editor
from app.core.crypto import encrypt, decrypt
from app.models.workspace import WorkspaceMember
from app.models.sp import SpSource, SpDefinition, SpParseResult, LineageDiff
from app.services.sp_service import (
    save_sp_definitions, match_sp_to_jobs, parse_all_sp,
    run_reconciliation, apply_patch, supplement_field_lineage,
)

router = APIRouter()


class SpSourceCreate(BaseModel):
    name: str
    type: str  # git / database
    config: dict  # git: {url, branch, token, sp_dir}; database: {conn_str, schema, dialect}


@router.get("/sources/{workspace_id}")
def list_sources(
    workspace_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    rows = db.query(SpSource).filter_by(workspace_id=workspace_id).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "type": s.type,
            "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
        }
        for s in rows
    ]


@router.post("/sources/{workspace_id}")
def create_source(
    workspace_id: str,
    body: SpSourceCreate,
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    import uuid
    src = SpSource(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=body.name,
        type=body.type,
        config=encrypt(json.dumps(body.config, ensure_ascii=False)),
    )
    db.add(src)
    db.commit()
    return {"id": src.id}


@router.post("/sources/{workspace_id}/{source_id}/pull")
def pull_sp(
    workspace_id: str,
    source_id: str,
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """拉取存储过程"""
    from app.services.sp_service import pull_sp_from_git, pull_sp_from_db
    src = db.query(SpSource).filter_by(id=source_id, workspace_id=workspace_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="SP 来源不存在")
    config = json.loads(decrypt(src.config))
    if src.type == "git":
        # 固定缓存目录实现增量拉取
        local_path = os.path.join(tempfile.gettempdir(), f"lineage_git_{workspace_id}_{source_id}")
        try:
            sp_list = pull_sp_from_git(
                config["url"], config.get("branch", "main"),
                config.get("token", ""), config.get("sp_dir", "/"),
                local_path,
                protocol=config.get("git_protocol", "https"),
                username=config.get("username", ""),
                ssh_key=config.get("ssh_key", ""),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Git 拉取失败: {e}")
    else:
        engine = None
        try:
            engine = create_engine(config["conn_str"], connect_args={"connect_timeout": 10})
            sp_list = pull_sp_from_db(engine, config.get("schema", "dbo"))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"数据库拉取失败: {e}")
        finally:
            if engine:
                engine.dispose()
    save_sp_definitions(db, workspace_id, source_id, sp_list)
    return {"pulled": len(sp_list)}


@router.post("/sources/{workspace_id}/{source_id}/match")
def match_sp(
    workspace_id: str,
    source_id: str,
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    return match_sp_to_jobs(db, workspace_id, source_id)


@router.post("/sources/{workspace_id}/{source_id}/parse")
def parse_sp(
    workspace_id: str,
    source_id: str,
    dialect: str = Query("mysql"),
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    return parse_all_sp(db, workspace_id, source_id, dialect=dialect)


@router.post("/sources/{workspace_id}/{source_id}/reconcile")
def reconcile(
    workspace_id: str,
    source_id: str,
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    return run_reconciliation(db, workspace_id, source_id)


@router.post("/sources/{workspace_id}/{source_id}/supplement")
def supplement(
    workspace_id: str,
    source_id: str,
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """从 SP 解析结果自动补充字段级血缘"""
    return supplement_field_lineage(db, workspace_id, source_id)


@router.get("/diffs/{workspace_id}")
def list_diffs(
    workspace_id: str,
    status: str = Query("pending"),
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    rows = db.query(LineageDiff).filter_by(workspace_id=workspace_id, status=status).all()
    return [
        {
            "id": d.id,
            "job_id": d.job_id,
            "sp_def_id": d.sp_def_id,
            "diff_type": d.diff_type,
            "excel_value": d.excel_value,
            "sp_value": d.sp_value,
            "status": d.status,
            "action": d.action,
        }
        for d in rows
    ]


class PatchRequest(BaseModel):
    diff_ids: list[str]


@router.post("/diffs/{workspace_id}/apply")
def apply_diffs(
    workspace_id: str,
    body: PatchRequest,
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    return apply_patch(db, workspace_id, body.diff_ids)


@router.get("/overview/{workspace_id}")
def sp_overview(
    workspace_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """SP 校验概览"""
    from app.models.job import Job
    total_jobs = db.query(Job).filter_by(workspace_id=workspace_id).count()
    sp_defs = db.query(SpDefinition).filter_by(workspace_id=workspace_id).all()
    matched = sum(1 for s in sp_defs if s.match_status in ("auto_matched", "fuzzy_matched", "manual"))
    parse_success = sum(1 for s in sp_defs if s.parse_status == "success")
    parse_failed = sum(1 for s in sp_defs if s.parse_status == "failed")
    diffs_pending = db.query(LineageDiff).filter_by(workspace_id=workspace_id, status="pending").count()
    diffs_accepted = db.query(LineageDiff).filter_by(workspace_id=workspace_id, status="accepted").count()
    return {
        "total_jobs": total_jobs,
        "sp_matched": matched,
        "parse_success": parse_success,
        "parse_failed": parse_failed,
        "diffs_pending": diffs_pending,
        "diffs_accepted": diffs_accepted,
    }
