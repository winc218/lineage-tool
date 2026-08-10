"""FastAPI 应用入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.core.database import init_db
from app.core.logging_config import setup_logging
from app.api import auth, workspaces, jobs, lineage, sp, import_excel, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    yield


app = FastAPI(title="批量作业数据血缘关系分析与管理工具", version="2.0", lifespan=lifespan)

# CORS（开发期；生产由 Nginx 同源代理，应通过环境变量收紧）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(workspaces.router, prefix="/api/workspaces", tags=["工作空间"])
app.include_router(import_excel.router, prefix="/api/import", tags=["导入"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["作业管理"])
app.include_router(lineage.router, prefix="/api/lineage", tags=["血缘分析"])
app.include_router(sp.router, prefix="/api/sp", tags=["存储过程校验"])
app.include_router(users.router, prefix="/api/users", tags=["用户管理"])

# 健康检查（必须在静态资源 mount 之前注册，否则被 StaticFiles 拦截）
@app.get("/api/health")
def health():
    return {"status": "ok"}

# 前端静态资源（生产环境，必须放在所有 API 路由之后）
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
