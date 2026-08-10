"""认证 API"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_password, hash_password, create_access_token, get_current_user
from app.models.user import User

router = APIRouter()


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 6:
            raise ValueError("新密码长度不能少于6位")
        if len(v) > 64:
            raise ValueError("新密码长度不能超过64位")
        return v


@router.put("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """用户修改自己的密码"""
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")
    if body.old_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True, "message": "密码修改成功"}


def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "email": u.email,
        "role": u.role,
    }
