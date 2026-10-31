"""数据库管理 API（仅 GLOBAL_ADMIN 可访问）"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

from app.core.database import get_db, engine
from app.core.security import require_global_admin
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)

# 允许查询的表白名单
ALLOWED_TABLES = {
    "user", "workspace", "workspace_member",
    "job", "job_source", "job_target", "field_mapping", "job_dependency",
    "table_meta", "sp_source", "sp_definition", "sp_parse_result", "lineage_diff",
}


@router.get("/tables")
def list_tables(
    admin: User = Depends(require_global_admin),
):
    """列出所有业务表"""
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()
    return [t for t in all_tables if t in ALLOWED_TABLES]


@router.get("/tables/{table_name}")
def get_table_data(
    table_name: str,
    limit: int = 500,
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """获取指定表的数据"""
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=403, detail="不允许访问该表")
    try:
        rows = db.execute(text(f"SELECT * FROM {table_name} LIMIT :limit"), {"limit": limit}).fetchall()
        columns = list(rows[0]._mapping.keys()) if rows else []
        data = [dict(r._mapping) for r in rows]
        return {"columns": columns, "rows": data}
    except Exception as e:
        logger.error(f"Failed to query table {table_name}: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


class SqlQuery(BaseModel):
    sql: str


@router.post("/query")
def execute_query(
    body: SqlQuery,
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    """执行只读 SQL 查询（仅 SELECT）"""
    sql = body.sql.strip()
    # 安全检查：只允许 SELECT 语句
    sql_upper = sql.upper()
    if not sql_upper.startswith("SELECT"):
        raise HTTPException(status_code=400, detail="仅支持 SELECT 查询")
    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE"]
    for kw in forbidden:
        if kw in sql_upper:
            raise HTTPException(status_code=400, detail=f"不允许的 SQL 关键字: {kw}")
    try:
        rows = db.execute(text(sql)).fetchall()
        columns = list(rows[0]._mapping.keys()) if rows else []
        data = [dict(r._mapping) for r in rows]
        return {"columns": columns, "rows": data}
    except Exception as e:
        logger.error(f"SQL execution failed: {sql[:200]} - {e}")
        raise HTTPException(status_code=500, detail=f"SQL 执行失败: {e}")
