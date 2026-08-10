"""JWT 认证与工作空间上下文"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
import bcrypt

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, pw_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), pw_hash.encode())


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise cred_exc
    except JWTError:
        raise cred_exc
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise cred_exc
    return user


def get_workspace_member(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceMember:
    """校验用户是否为某工作空间成员，返回成员记录"""
    member = (
        db.query(WorkspaceMember)
        .filter_by(workspace_id=workspace_id, user_id=user.id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="无权访问该工作空间")
    return member


def require_editor(member: WorkspaceMember = Depends(get_workspace_member)) -> WorkspaceMember:
    """要求至少 EDITOR 权限"""
    if member.role not in ("OWNER", "EDITOR"):
        raise HTTPException(status_code=403, detail="需要编辑权限")
    return member


def require_owner(member: WorkspaceMember = Depends(get_workspace_member)) -> WorkspaceMember:
    """要求 OWNER 权限"""
    if member.role != "OWNER":
        raise HTTPException(status_code=403, detail="需要所有者权限")
    return member


def require_global_admin(user: User = Depends(get_current_user)) -> User:
    """要求全局管理员权限 (GLOBAL_ADMIN)"""
    if user.role != "GLOBAL_ADMIN":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
