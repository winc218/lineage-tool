"""Excel 导入服务 — 单行作业格式 + 字段映射 DSL"""
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.models.job import Job, JobSource, JobTarget, TableMeta, FieldMapping


# ===== 系统字段定义 =====
# 必填字段：作业名、作业类型、源表、目标表、存过名称
REQUIRED_FIELDS = ["job_name", "job_type", "source_tables", "target_tables", "sp_name"]

# 可选字段
OPTIONAL_FIELDS = ["field_mappings", "schedule", "description"]

# 全部系统字段
SYSTEM_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

# 中英文列名 → 系统字段名 的自动匹配映射
COLUMN_ALIASES: dict[str, str] = {
    # 必填
    "作业名": "job_name", "作业名称": "job_name", "job_name": "job_name", "job": "job_name",
    "作业类型": "job_type", "类型": "job_type", "job_type": "job_type",
    "源表": "source_tables", "源表名": "source_tables", "source_tables": "source_tables", "source_table": "source_tables",
    "目标表": "target_tables", "目标表名": "target_tables", "target_tables": "target_tables", "target_table": "target_tables",
    "存过名称": "sp_name", "存储过程": "sp_name", "存储过程名称": "sp_name", "sp_name": "sp_name", "sp": "sp_name",
    # 可选
    "字段映射": "field_mappings", "字段血缘": "field_mappings", "field_mappings": "field_mappings",
    "调度": "schedule", "调度频率": "schedule", "schedule": "schedule",
    "描述": "description", "说明": "description", "description": "description",
}


def parse_excel(file_bytes: bytes, sheet_name: Optional[str] = None) -> dict:
    """解析 Excel，返回 {sheets: [], headers: [], rows: [], count}"""
    df_dict = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, dtype=str, engine="openpyxl")
    sheets = list(df_dict.keys())
    if sheet_name and sheet_name in df_dict:
        df = df_dict[sheet_name]
    else:
        df = df_dict[sheets[0]]
    df = df.fillna("")
    headers = df.columns.tolist()
    rows = df.to_dict(orient="records")
    return {"sheets": sheets, "headers": headers, "rows": rows, "count": len(rows)}


def auto_match_mapping(headers: list[str]) -> dict[str, str]:
    """自动匹配 Excel 列名到系统字段，返回 {excel_col: system_field}"""
    mapping: dict[str, str] = {}
    used_fields: set[str] = set()
    for h in headers:
        key = h.strip()
        # 精确匹配
        if key in COLUMN_ALIASES:
            field = COLUMN_ALIASES[key]
            if field not in used_fields:
                mapping[h] = field
                used_fields.add(field)
                continue
        # 模糊匹配（包含关键词）
        for alias, field in COLUMN_ALIASES.items():
            if field in used_fields:
                continue
            if alias in key or key in alias:
                mapping[h] = field
                used_fields.add(field)
                break
    return mapping


def validate_mapping(mapping: dict[str, str]) -> list[str]:
    """校验列映射，返回错误列表"""
    errors = []
    mapped_targets = set(mapping.values())
    for req in REQUIRED_FIELDS:
        if req not in mapped_targets:
            errors.append(f"必填字段未映射: {req}")
    return errors


def validate_rows(rows: list[dict], mapping: dict[str, str]) -> dict:
    """按映射转换并校验行，返回 {valid_rows, errors}"""
    valid_rows = []
    errors = []
    for i, row in enumerate(rows, start=2):  # Excel 行号从 2 开始
        record = {}
        for excel_col, sys_field in mapping.items():
            if excel_col in row:
                record[sys_field] = str(row[excel_col]).strip()
        # 校验必填
        row_errors = []
        for req in REQUIRED_FIELDS:
            if not record.get(req):
                row_errors.append(f"行{i}: 必填字段 {req} 为空")
        if row_errors:
            errors.extend(row_errors)
            continue
        valid_rows.append(record)
    return {"valid_rows": valid_rows, "errors": errors}


def import_rows(
    db: Session, workspace_id: str, rows: list[dict], source_file: str = ""
) -> dict:
    """将校验后的行写入数据库，返回统计"""
    batch_no = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc)
    table_cache: dict[str, TableMeta] = {}

    try:
        job_count = _do_import_rows(db, workspace_id, rows, source_file, batch_no, now, table_cache)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # 导入后重建依赖
    from app.services.lineage_service import rebuild_dependencies
    rebuild_dependencies(db, workspace_id)

    return {"batch_no": batch_no, "job_count": job_count}


def _do_import_rows(
    db: Session, workspace_id: str, rows: list[dict],
    source_file: str, batch_no: str, now, table_cache: dict,
) -> int:
    """实际写入逻辑 — 每行一个作业"""
    job_count = 0

    def get_or_create_table(name: str) -> TableMeta:
        name = name.strip()
        if name in table_cache:
            return table_cache[name]
        t = db.query(TableMeta).filter_by(workspace_id=workspace_id, table_name=name).first()
        if not t:
            t = TableMeta(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                table_name=name,
            )
            db.add(t)
            db.flush()
            table_cache[name] = t
        return t

    for rec in rows:
        job_name = rec["job_name"]

        # upsert job
        job = db.query(Job).filter_by(workspace_id=workspace_id, job_name=job_name).first()
        if job:
            job.job_type = rec.get("job_type", job.job_type) or job.job_type
            job.description = rec.get("description", job.description)
            job.schedule = rec.get("schedule", job.schedule)
            job.sp_name = rec.get("sp_name", job.sp_name)
            job.source_file = source_file
            job.import_batch = batch_no
            job.updated_at = now
            db.query(JobSource).filter_by(workspace_id=workspace_id, job_id=job.id).delete()
            db.query(JobTarget).filter_by(workspace_id=workspace_id, job_id=job.id).delete()
            db.query(FieldMapping).filter_by(workspace_id=workspace_id, job_id=job.id, source="excel").delete()
        else:
            job = Job(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                job_name=job_name,
                job_type=rec.get("job_type", "ETL"),
                description=rec.get("description", ""),
                schedule=rec.get("schedule", ""),
                sp_name=rec.get("sp_name", ""),
                source_file=source_file,
                import_batch=batch_no,
            )
            db.add(job)
            db.flush()
        job_count += 1

        # 解析源表和目标表（支持换行、逗号、分号分隔）
        src_tables = _split_multi(rec.get("source_tables", ""))
        tgt_tables = _split_multi(rec.get("target_tables", ""))

        # 写入源表关系
        for tname in src_tables:
            t = get_or_create_table(tname)
            db.add(JobSource(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                job_id=job.id,
                table_id=t.id,
            ))
        # 写入目标表关系
        for tname in tgt_tables:
            t = get_or_create_table(tname)
            db.add(JobTarget(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                job_id=job.id,
                table_id=t.id,
            ))

        # 解析字段映射 DSL
        fm_text = rec.get("field_mappings", "")
        if fm_text:
            mappings = parse_field_mappings(fm_text, src_tables, tgt_tables)
            for m in mappings:
                src_t = get_or_create_table(m["source_table"]) if m["source_table"] else None
                tgt_t = get_or_create_table(m["target_table"]) if m["target_table"] else None
                db.add(FieldMapping(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    job_id=job.id,
                    source_table_id=src_t.id if src_t else None,
                    target_table_id=tgt_t.id if tgt_t else None,
                    source_field=m["source_field"],
                    target_field=m["target_field"],
                    operation=m["operation"],
                    source="excel",
                ))

    return job_count


# ===== 字段映射 DSL 解析器 =====
# 格式：源表名.字段名->目标表名.字段名
# 多组映射之间用换行、逗号、分号分隔
# 操作类型用 [INSERT]/[UPDATE]/[MERGE] 前缀标注，可选

# 匹配单条映射规则的正则
# 示例: dbo.t1.col1 -> dbo.t2.col2
#       t1.col1 -> t2.col2
#       col1 -> col2  (无表名，使用默认)
#       [INSERT] t1.col1 -> t2.col2
_MAPPING_PATTERN = re.compile(
    r'(?:\[([A-Z_]+)\]\s*)?'           # 可选的操作类型 [INSERT]
    r'([^,;\n\->]+?)'                   # 源（表.字段 或 字段）
    r'\s*->\s*'                         # 箭头分隔
    r'([^,;\n\->]+?)'                   # 目标（表.字段 或 字段）
    r'(?:\s*[;,\n]|\s*$)',             # 分隔符或行尾
    re.MULTILINE
)


def parse_field_mappings(text: str, src_tables: list[str], tgt_tables: list[str]) -> list[dict]:
    """
    解析字段映射 DSL 文本，返回映射列表。

    格式：源表名.字段名->目标表名.字段名
    多条映射用换行、逗号、分号分隔。
    可用 [INSERT]/[UPDATE]/[MERGE] 前缀标注操作类型。

    如果字段映射为空或不符合格式，返回空列表（只保留表级血缘）。
    """
    if not text or not text.strip():
        return []

    results: list[dict] = []
    default_src = src_tables[0] if src_tables else ""
    default_tgt = tgt_tables[0] if tgt_tables else ""

    for match in _MAPPING_PATTERN.finditer(text):
        operation = (match.group(1) or "").strip()
        source_part = match.group(2).strip()
        target_part = match.group(3).strip()

        if not source_part and not target_part:
            continue

        # 解析 "表名.字段名" 格式
        src_table, src_field = _parse_table_field(source_part)
        tgt_table, tgt_field = _parse_table_field(target_part)

        # 如果没有表名，使用默认表
        if not src_table and src_field:
            src_table = default_src
        if not tgt_table and tgt_field:
            tgt_table = default_tgt

        # 如果源和目标都解析不出来，跳过
        if not src_field and not tgt_field:
            continue

        results.append({
            "source_table": src_table,
            "source_field": src_field,
            "target_table": tgt_table,
            "target_field": tgt_field,
            "operation": operation,
        })

    return results


def _parse_table_field(s: str) -> tuple[str, str]:
    """
    解析 "表名.字段名" 格式，返回 (table_name, field_name)。
    支持多段 schema.table.field 格式。
    如果没有点号，返回 ("", s)。
    """
    s = s.strip()
    if not s:
        return "", ""
    if "." in s:
        parts = s.rsplit(".", 1)
        return parts[0].strip(), parts[1].strip()
    return "", s


def _split_multi(s: str) -> list[str]:
    """分割多值单元格：支持换行、逗号、分号分隔，去空去重保序"""
    if not s:
        return []
    # 先按换行分割，再按逗号分号分割
    parts = re.split(r'[\n,;]+', s)
    seen = set()
    result = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            result.append(p)
    return result
