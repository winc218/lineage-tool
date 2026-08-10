"""用户管理 API（仅管理员）"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, require_global_admin, get_current_user
from app.models.user import User

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str = ""
    email: str = ""
    role: str = "USER"  # USER / GLOBAL_ADMIN

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if len(v) < 2:
            raise ValueError("用户名长度不能少于2位")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("密码长度不能少于6位")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("USER", "GLOBAL_ADMIN"):
            raise ValueError("角色必须是 USER 或 GLOBAL_ADMIN")
        return v


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: str | None = None


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    email: str
    role: str
    created_at: str

    model_config = {"from_attributes": True}


class ResetPasswordRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("密码长度不能少于6位")
        return v


@router.get("", response_model=list[UserOut])
def list_users(
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """列出所有用户（仅管理员）"""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        UserOut(
            id=u.id, username=u.username, display_name=u.display_name,
            email=u.email, role=u.role, created_at=u.created_at.isoformat() if u.created_at else "",
        )
        for u in users
    ]


@router.post("", response_model=UserOut)
def create_user(
    body: UserCreate,
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """创建用户（仅管理员）"""
    exist = db.query(User).filter_by(username=body.username).first()
    if exist:
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        email=body.email,
        role=body.role,
    )
    db.add(user)
    db.commit()
    return UserOut(
        id=user.id, username=user.username, display_name=user.display_name,
        email=user.email, role=user.role,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdate,
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """修改用户信息（仅管理员）"""
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.email is not None:
        user.email = body.email
    if body.role is not None:
        if body.role not in ("USER", "GLOBAL_ADMIN"):
            raise HTTPException(status_code=400, detail="角色必须是 USER 或 GLOBAL_ADMIN")
        # 防止把自己降级导致没有管理员
        if user.id == admin.id and body.role != "GLOBAL_ADMIN":
            raise HTTPException(status_code=400, detail="不能取消自己的管理员权限")
        user.role = body.role
    db.commit()
    return UserOut(
        id=user.id, username=user.username, display_name=user.display_name,
        email=user.email, role=user.role,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.put("/{user_id}/reset-password")
def reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """管理员重置用户密码（仅管理员）"""
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True, "message": "密码重置成功"}


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """删除用户（仅管理员），不能删除自己"""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(user)
    db.commit()
    return {"ok": True, "message": "用户已删除"}
