# 后端开发规范

> 基于 PRD v2.0 代码评审沉淀，指导后续开发。
> 与 `rules/CLAUDE.md` 配合使用，本文件聚焦项目特定约束。

## R1. 安全启动校验

应用启动时必须校验关键密钥/口令非默认值且达强度要求，否则拒绝启动。

- `JWT_SECRET` 禁止使用默认值 `"change-me-in-prod"`，长度 ≥ 32。
- `ADMIN_PASSWORD` 必须由环境变量提供，首次登录强制改密（TODO）。
- 敏感配置（JWT Secret、管理员口令、数据库连接串、SP 来源 config）一律从环境变量/secret 文件读取，禁止硬编码入库。
- SP 来源 config 字段必须经 `app/core/crypto.py` 加密后入库，读取时解密。

## R2. 工作空间隔离强制清单

- 所有业务表查询/写入必须带 `workspace_id` 过滤，包括 delete/update 语句。
- 依赖注入链：`get_current_user` → `get_workspace_member` → `require_editor/owner`，禁止跨级直连。
- `require_editor` / `require_owner` 必须声明 `member: WorkspaceMember = Depends(get_workspace_member)`，形成链式依赖。
- 新增业务表必须包含 `workspace_id` 字段并建索引。

## R3. 事务边界

涉及多表写入的服务方法必须用 `with db.begin()` 或 `try/commit/except rollback` 包裹。

```python
# 正确
try:
    db.query(Model).filter_by(...).delete()
    for item in new_items:
        db.add(item)
    db.commit()
except Exception:
    db.rollback()
    raise
```

- 禁止"分散 flush + 末尾 commit"模式。
- 先构建内存集合再事务内 delete+insert，禁止"先 delete 再逐步重建"的非原子操作。

## R4. 批量查询禁 N+1

任何在循环内对同一表的单行查询都视为缺陷。

```python
# 错误
for js in job_sources:
    t = db.query(TableMeta).filter_by(id=js.table_id).first()  # N+1

# 正确
table_ids = {js.table_id for js in job_sources}
table_map = {t.id: t for t in db.query(TableMeta).filter(TableMeta.id.in_(table_ids)).all()}
for js in job_sources:
    t = table_map.get(js.table_id)
```

- 图算法类服务在单次请求内复用已构建的图对象，禁止重复 `build_graph`（参考 `graph_data` 复用 `g` 调用 `_cycles_from_graph`）。

## R5. 上传与外部输入约束

- 文件上传设最大体积（`_read_limited` 工具函数，默认 50MB）。
- 用户提供的数据库连接串必须设连接超时（`connect_args={"connect_timeout": 10}`）。
- 外部引擎用完必须 `engine.dispose()`。
- 临时目录用固定缓存路径（`tempfile.gettempdir() + 工作空间/来源ID`）实现增量，禁止每次 `mkdtemp`。

## R6. 响应格式

- 所有 API 返回尽量走 Pydantic `response_model`。
- `schemas/` 目录集中管理输入/输出 schema，与 `models/` 解耦。
- 简单操作返回 `{"ok": True}` 可接受，但复杂响应必须有 schema。

## R7. 日志可观测

- 启动即配置 `logging`（stdout + rolling 文件 7 天，见 `logging_config.py`）。
- 关键操作（导入、SP 拉取、采纳修订、登录失败）打 INFO 级日志。
- 异常打 ERROR + 堆栈。

## R8. 字段更新白名单

`setattr(obj, k, v)` 模式必须先过滤字段名白名单。

```python
UPDATABLE_FIELDS = {"job_name", "job_type", "description", ...}
for k, v in body.model_dump(exclude_unset=True).items():
    if k in UPDATABLE_FIELDS:
        setattr(obj, k, v)
```

禁止直接吃 `model_dump()` 全量字段，防止越权改 `workspace_id` 等。

## R9. 模型工具函数复用

`_uuid` / `_now` 等工具函数禁止在每个模型文件重复定义，抽到公共位置复用（TODO: 后续迁移到 `base.py`）。

## R10. 依赖管理

- `requirements.txt` 锁定主版本号（`==X.*`）。
- 新增依赖必须在此文件登记，禁止直接 `pip install` 后不记录。
- `cryptography` 用于 SP config 加密；`sqllineage` 用于 SP SQL 解析；`gitpython` 用于 Git 拉取。

## R11. 测试要求

- 核心算法（血缘解析、SP 比对）单元测试覆盖率 ≥ 80%。
- 测试用独立 SQLite（`test_data/`），不污染开发库。
- 每个 P0 功能至少一个端到端测试（参考 `test_core.py`）。
- 测试必须可在无网络环境下运行（不依赖外部 Git/DB）。

## R12. 文件组织

```
backend/app/
├── api/           # 路由层，薄，只做参数校验和调用 service
├── core/          # 基础设施：config, database, security, crypto, logging
├── models/        # SQLAlchemy 模型，每张表一个文件
├── schemas/       # Pydantic 输入输出 schema（TODO 填充）
├── services/      # 业务逻辑层，厚，所有复杂逻辑在此
└── tests/         # 测试
```

- 路由层不写业务逻辑，只调用 service。
- service 层不直接返回 HTTP 响应，只返回数据或抛异常。
