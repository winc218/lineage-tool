"""工作空间 API"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, get_workspace_member, require_owner, require_editor, require_global_admin
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

router = APIRouter()


class WorkspaceCreate(BaseModel):
    name: str
    description: str = ""


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class WorkspaceOut(BaseModel):
    id: str
    name: str
    description: str
    db_mode: str
    role: str
    owner_name: str

    model_config = {"from_attributes": True}


class MemberAdd(BaseModel):
    user_id: str
    role: str = "VIEWER"  # EDITOR / VIEWER


class MemberOut(BaseModel):
    id: str
    user_id: str
    username: str
    display_name: str
    role: str


@router.get("", response_model=list[WorkspaceOut])
def list_my_workspaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """列出当前用户可访问的工作空间（普通用户只能看到自己是成员的工作空间）"""
    if user.role == "GLOBAL_ADMIN":
        # 管理员可以看到所有工作空间
        rows = (
            db.query(Workspace, User.display_name)
            .join(User, User.id == Workspace.owner_id)
            .all()
        )
        # 管理员视角返回角色为 OWNER
        return [
            WorkspaceOut(
                id=ws.id, name=ws.name, description=ws.description,
                db_mode=ws.db_mode, role="OWNER", owner_name=owner_name,
            )
            for ws, owner_name in rows
        ]
    rows = (
        db.query(Workspace, WorkspaceMember.role, User.display_name)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .join(User, User.id == Workspace.owner_id)
        .filter(WorkspaceMember.user_id == user.id)
        .all()
    )
    return [
        WorkspaceOut(
            id=ws.id, name=ws.name, description=ws.description,
            db_mode=ws.db_mode, role=role, owner_name=owner_name,
        )
        for ws, role, owner_name in rows
    ]


@router.get("/admin-overview")
def admin_overview(
    user: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """Admin全局概览：每个工作空间的作业数和统计"""
    from app.models.job import Job
    from sqlalchemy import func
    all_ws = db.query(Workspace).all()
    result = []
    for ws in all_ws:
        job_count = db.query(func.count(Job.id)).filter(Job.workspace_id == ws.id).scalar() or 0
        owner = db.query(User).filter(User.id == ws.owner_id).first()
        result.append({
            "workspace_id": ws.id,
            "workspace_name": ws.name,
            "description": ws.description,
            "owner_name": owner.display_name if owner else "",
            "db_mode": ws.db_mode,
            "job_count": job_count,
            "created_at": ws.created_at.isoformat() if ws.created_at else None,
        })
    return result


@router.post("", response_model=WorkspaceOut)
def create_workspace(
    body: WorkspaceCreate,
    user: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """创建工作空间（仅管理员可操作）"""
    ws = Workspace(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        owner_id=user.id,
        db_mode="sqlite",
    )
    db.add(ws)
    # 创建者自动成为 OWNER 成员
    db.add(WorkspaceMember(
        id=str(uuid.uuid4()),
        workspace_id=ws.id,
        user_id=user.id,
        role="OWNER",
    ))
    db.commit()
    return WorkspaceOut(
        id=ws.id, name=ws.name, description=ws.description,
        db_mode=ws.db_mode, role="OWNER", owner_name=user.display_name,
    )


@router.put("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: str,
    body: WorkspaceUpdate,
    user: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """修改工作空间信息（仅管理员可操作）"""
    ws = db.query(Workspace).filter_by(id=workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="工作空间不存在")
    if body.name is not None:
        ws.name = body.name
    if body.description is not None:
        ws.description = body.description
    db.commit()
    # 获取当前用户的成员角色
    member = db.query(WorkspaceMember).filter_by(workspace_id=workspace_id, user_id=user.id).first()
    owner = db.query(User).filter_by(id=ws.owner_id).first()
    return WorkspaceOut(
        id=ws.id, name=ws.name, description=ws.description,
        db_mode=ws.db_mode, role=member.role if member else "OWNER",
        owner_name=owner.display_name if owner else "",
    )


@router.delete("/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    user: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """删除工作空间（仅管理员可操作）"""
    ws = db.query(Workspace).filter_by(id=workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="工作空间不存在")
    # 先删除成员关系
    db.query(WorkspaceMember).filter_by(workspace_id=workspace_id).delete()
    db.delete(ws)
    db.commit()
    return {"ok": True, "message": "工作空间已删除"}


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
def list_members(
    workspace_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    )
    return [
        MemberOut(
            id=m.id, user_id=m.user_id, username=u.username,
            display_name=u.display_name, role=m.role,
        )
        for m, u in rows
    ]


@router.post("/{workspace_id}/members")
def add_member(
    workspace_id: str,
    body: MemberAdd,
    member: WorkspaceMember = Depends(require_owner),
    db: Session = Depends(get_db),
):
    exist = (
        db.query(WorkspaceMember)
        .filter_by(workspace_id=workspace_id, user_id=body.user_id)
        .first()
    )
    if exist:
        raise HTTPException(status_code=400, detail="该用户已是成员")
    db.add(WorkspaceMember(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        user_id=body.user_id,
        role=body.role,
    ))
    db.commit()
    return {"ok": True}


@router.put("/{workspace_id}/members/{member_id}")
def update_member_role(
    workspace_id: str,
    member_id: str,
    role: str = Query(..., pattern="^(EDITOR|VIEWER)$"),
    member: WorkspaceMember = Depends(require_owner),
    db: Session = Depends(get_db),
):
    target = db.query(WorkspaceMember).filter_by(id=member_id, workspace_id=workspace_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="成员不存在")
    if target.role == "OWNER":
        raise HTTPException(status_code=400, detail="不能修改所有者角色")
    target.role = role
    db.commit()
    return {"ok": True}


@router.delete("/{workspace_id}/members/{member_id}")
def remove_member(
    workspace_id: str,
    member_id: str,
    member: WorkspaceMember = Depends(require_owner),
    db: Session = Depends(get_db),
):
    target = db.query(WorkspaceMember).filter_by(id=member_id, workspace_id=workspace_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="成员不存在")
    if target.role == "OWNER":
        raise HTTPException(status_code=400, detail="不能移除所有者")
    db.delete(target)
    db.commit()
    return {"ok": True}
