"""SQLAlchemy 数据库引擎与会话"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import get_db_url

DB_URL = get_db_url()

# SQLite 需要 check_same_thread=False 供 FastAPI 多线程用
engine_kwargs = {}
if DB_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DB_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """建表 + 自动迁移 + 初始化管理员"""
    from app.models import user, workspace, job, sp  # noqa: F401 触发模型注册
    Base.metadata.create_all(bind=engine)
    _auto_migrate()
    _init_admin()


def _auto_migrate():
    """自动检查并修复数据库表结构（仅 SQLite，不删除已有数据）"""
    import sqlite3

    if not DB_URL.startswith("sqlite"):
        return

    db_path = DB_URL.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # 检查并修复 field_mapping 表
        cur.execute("PRAGMA table_info(field_mapping)")
        fm_cols = cur.fetchall()
        if fm_cols:
            col_names = [c[1] for c in fm_cols]
            need_rebuild = False

            # 检查缺失的列
            if "operation" not in col_names or "source" not in col_names:
                need_rebuild = True

            # 检查 transform 列是否有 NOT NULL 约束
            for c in fm_cols:
                if c[1] == "transform" and c[3]:  # notnull == 1
                    need_rebuild = True

            if need_rebuild:
                _rebuild_field_mapping_table(cur, fm_cols)
                conn.commit()

        # 检查并修复 job 表的 NOT NULL 约束
        cur.execute("PRAGMA table_info(job)")
        job_cols = cur.fetchall()
        if job_cols:
            need_rebuild = False
            for c in job_cols:
                if c[1] in ("owner", "tag", "remark") and c[3]:  # notnull == 1
                    need_rebuild = True
            if need_rebuild:
                _rebuild_job_table(cur)
                conn.commit()
    finally:
        conn.close()


def _rebuild_field_mapping_table(cur, old_cols):
    """重建 field_mapping 表（添加缺失列，去掉 NOT NULL 约束）"""
    col_names = [c[1] for c in old_cols]
    cur.execute("ALTER TABLE field_mapping RENAME TO field_mapping_old")
    cur.execute("""
        CREATE TABLE field_mapping (
            id VARCHAR(64) PRIMARY KEY,
            workspace_id VARCHAR(64),
            job_id VARCHAR(64),
            source_table_id VARCHAR(64),
            target_table_id VARCHAR(64),
            source_field VARCHAR(200) DEFAULT '',
            target_field VARCHAR(200) DEFAULT '',
            transform VARCHAR(1000) DEFAULT '',
            operation VARCHAR(50) DEFAULT '',
            source VARCHAR(20) DEFAULT 'excel',
            created_at DATETIME
        )
    """)
    # 构建迁移 SQL
    select_cols = [
        "id", "workspace_id", "job_id", "source_table_id", "target_table_id",
        "source_field", "target_field",
        "COALESCE(transform, '')" if "transform" in col_names else "''",
        "COALESCE(operation, '')" if "operation" in col_names else "''",
        "COALESCE(source, 'excel')" if "source" in col_names else "'excel'",
        "created_at",
    ]
    cur.execute(f"""
        INSERT INTO field_mapping ({', '.join(['id','workspace_id','job_id','source_table_id','target_table_id','source_field','target_field','transform','operation','source','created_at'])})
        SELECT {', '.join(select_cols)}
        FROM field_mapping_old
    """)
    cur.execute("DROP TABLE field_mapping_old")


def _rebuild_job_table(cur):
    """重建 job 表（去掉 owner/tag/remark 的 NOT NULL 约束）"""
    cur.execute("ALTER TABLE job RENAME TO job_old")
    cur.execute("""
        CREATE TABLE job (
            id VARCHAR(64) PRIMARY KEY,
            workspace_id VARCHAR(64),
            job_name VARCHAR(200),
            job_type VARCHAR(50) DEFAULT 'ETL',
            description VARCHAR(1000) DEFAULT '',
            schedule VARCHAR(50) DEFAULT '',
            owner VARCHAR(100) DEFAULT '',
            tag VARCHAR(200) DEFAULT '',
            remark VARCHAR(1000) DEFAULT '',
            sp_name VARCHAR(200) DEFAULT '',
            source_file VARCHAR(500) DEFAULT '',
            import_batch VARCHAR(64) DEFAULT '',
            created_at DATETIME,
            updated_at DATETIME
        )
    """)
    cur.execute("""
        INSERT INTO job (id, workspace_id, job_name, job_type, description, schedule,
                         owner, tag, remark, sp_name, source_file, import_batch, created_at, updated_at)
        SELECT id, workspace_id, job_name, COALESCE(job_type, 'ETL'), COALESCE(description, ''), COALESCE(schedule, ''),
               COALESCE(owner, ''), COALESCE(tag, ''), COALESCE(remark, ''), COALESCE(sp_name, ''), COALESCE(source_file, ''),
               COALESCE(import_batch, ''), created_at, COALESCE(updated_at, created_at)
        FROM job_old
    """)
    cur.execute("DROP TABLE job_old")


def _init_admin():
    """首次启动创建管理员账号"""
    from app.models.user import User
    from app.core.config import settings
    import bcrypt

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username=settings.ADMIN_USERNAME).first()
        if admin:
            return
        pw_hash = bcrypt.hashpw(settings.ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
        admin = User(
            username=settings.ADMIN_USERNAME,
            password_hash=pw_hash,
            display_name="Administrator",
            role="GLOBAL_ADMIN",
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()
