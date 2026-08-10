# 批量作业数据血缘关系分析与管理工具

基于 PRD v2.0 实现的 Docker 化部署工具。

## 快速启动

### 开发模式（本地）

后端：
```bash
cd backend
pip install -r requirements.txt
python run.py  # http://localhost:8080
```

前端：
```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
```

### Docker 部署

```bash
docker compose up -d --build
# 访问 http://localhost:8080
# 默认账号 admin / admin123
```

## 技术栈

- 后端：Python 3.11 + FastAPI + SQLAlchemy + networkx + sqllineage + GitPython
- 前端：Vue 3 + TypeScript + Vite + Element Plus + AntV G6
- 数据库：SQLite（默认）/ SQL Server（pymssql）/ GoldenDB（pymysql）
- 部署：Docker

## 目录结构

```
TaskManager/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI 路由
│   │   ├── core/         # 配置、数据库、安全
│   │   ├── models/       # SQLAlchemy 模型
│   │   ├── services/     # 业务逻辑
│   │   ├── tests/        # 测试
│   │   └── main.py
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── api/          # axios 封装
│   │   ├── components/   # 组件
│   │   ├── views/        # 页面
│   │   ├── stores/       # Pinia
│   │   ├── router/
│   │   └── main.ts
│   └── package.json
├── docs/
├── Dockerfile
├── docker-compose.yml
└── PRD-批量作业数据血缘关系分析与管理工具.md
```
