"""Excel 导入 API"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

from app.core.database import get_db
from app.core.security import get_current_user, get_workspace_member, require_editor
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.services.import_service import (
    parse_excel, validate_mapping, validate_rows, import_rows,
    SYSTEM_FIELDS, REQUIRED_FIELDS, auto_match_mapping,
)

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB


async def _read_limited(file: UploadFile) -> bytes:
    """读取上传文件，限制最大体积"""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"文件超过 {MAX_UPLOAD_BYTES // 1024 // 1024}MB 限制")
    return content


@router.post("/parse")
async def parse_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """上传 Excel，返回 sheet 列表、表头和自动匹配的映射"""
    content = await _read_limited(file)
    try:
        result = parse_excel(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel 解析失败: {e}")
    # 自动匹配列名
    auto_mapping = auto_match_mapping(result["headers"])
    result["auto_mapping"] = auto_mapping
    return result


@router.post("/validate")
async def validate_import(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    sheet_name: str = Form(None),
    user: User = Depends(get_current_user),
):
    """校验导入数据，返回预览与错误"""
    content = await _read_limited(file)
    mapping_dict = json.loads(mapping)
    errors = validate_mapping(mapping_dict)
    if errors:
        return {"valid": False, "errors": errors, "preview": []}
    parsed = parse_excel(content, sheet_name=sheet_name)
    result = validate_rows(parsed["rows"], mapping_dict)
    return {
        "valid": len(result["errors"]) == 0,
        "errors": result["errors"],
        "preview": result["valid_rows"][:100],
        "total_valid": len(result["valid_rows"]),
        "total_invalid": len(result["errors"]),
    }


@router.post("/confirm/{workspace_id}")
async def confirm_import(
    workspace_id: str,
    file: UploadFile = File(...),
    mapping: str = Form(...),
    sheet_name: str = Form(None),
    member: WorkspaceMember = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """确认导入到指定工作空间"""
    content = await _read_limited(file)
    mapping_dict = json.loads(mapping)
    parsed = parse_excel(content, sheet_name=sheet_name)
    result = validate_rows(parsed["rows"], mapping_dict)
    if not result["valid_rows"]:
        raise HTTPException(status_code=400, detail="无有效数据可导入")
    stats = import_rows(db, workspace_id, result["valid_rows"], source_file=file.filename)
    return stats


@router.get("/fields")
def get_system_fields():
    """返回系统支持的字段列表"""
    return {"fields": SYSTEM_FIELDS, "required": REQUIRED_FIELDS}
