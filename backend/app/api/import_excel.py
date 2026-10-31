"""Excel 导入 API"""
import os
import io
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
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
from openpyxl import Workbook

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


@router.get("/batches/{workspace_id}")
def list_batches(
    workspace_id: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """列出工作空间的所有导入批次"""
    from app.models.job import Job
    from sqlalchemy import func, distinct
    rows = (
        db.query(
            Job.import_batch,
            Job.source_file,
            func.count(Job.id).label("job_count"),
            func.max(Job.updated_at).label("imported_at"),
        )
        .filter(Job.workspace_id == workspace_id, Job.import_batch != "")
        .group_by(Job.import_batch)
        .order_by(func.max(Job.updated_at).desc())
        .all()
    )
    return [
        {
            "batch_no": r.import_batch,
            "source_file": r.source_file,
            "job_count": r.job_count,
            "imported_at": r.imported_at.isoformat() if r.imported_at else None,
        }
        for r in rows
    ]


@router.get("/batches/{workspace_id}/{batch_no}")
def batch_detail(
    workspace_id: str,
    batch_no: str,
    member: WorkspaceMember = Depends(get_workspace_member),
    db: Session = Depends(get_db),
):
    """获取指定批次的作业列表"""
    from app.models.job import Job
    jobs = (
        db.query(Job)
        .filter_by(workspace_id=workspace_id, import_batch=batch_no)
        .order_by(Job.job_name)
        .all()
    )
    return {
        "batch_no": batch_no,
        "job_count": len(jobs),
        "jobs": [
            {
                "id": j.id,
                "job_name": j.job_name,
                "job_type": j.job_type,
                "sp_name": j.sp_name,
                "source_file": j.source_file,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
            for j in jobs
        ],
    }


@router.get("/template")
def download_template():
    """下载 Excel 导入模板"""
    wb = Workbook()
    ws = wb.active
    ws.title = "作业血缘关系"
    # 表头
    headers = ["作业名称", "作业类型", "源表", "目标表", "存过名称", "字段映射", "调度", "描述"]
    ws.append(headers)
    # 示例数据
    examples = [
        ["etl_user_dmt_daily", "ETL", "dbo.t_ods_user", "dbo.t_dmt_user_summary", "etl_user_dmt_daily",
         "[INSERT] dbo.t_ods_user.user_id -> dbo.t_dmt_user_summary.user_id\n[UPDATE] dbo.t_ods_user.name -> dbo.t_dmt_user_summary.name", "daily", "用户汇总ETL作业"],
        ["etl_order_process", "ETL", "dbo.t_ods_order", "dbo.t_dmt_order_daily", "etl_order_process",
         "[INSERT] dbo.t_ods_order.order_id -> dbo.t_dmt_order_daily.order_id\n[INSERT] dbo.t_ods_order.amount -> dbo.t_dmt_order_daily.total_amount", "daily", "订单处理ETL"],
        ["etl_inventory_sync", "PROCEDURE", "dbo.t_dmt_order_daily,dbo.t_ods_product", "dbo.t_dmt_inventory", "sp_inventory_sync",
         "", "hourly", "库存同步存储过程"],
    ]
    for row in examples:
        ws.append(row)
    # 调整列宽
    col_widths = [25, 15, 25, 25, 25, 55, 12, 30]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=lineage_import_template.xlsx"},
    )


@router.get("/fields")
def get_system_fields():
    """返回系统支持的字段列表"""
    return {"fields": SYSTEM_FIELDS, "required": REQUIRED_FIELDS}
