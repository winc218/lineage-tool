# 后端代码评审报告

> 评审范围：`backend/app` 下 `core/`、`models/`、`api/`、`services/`、`main.py`、`run.py`
> 评审依据：`PRD-批量作业数据血缘关系分析与管理工具.md`（v2.0）、`rules/CLAUDE.md`
> 评审日期：2026-08-08
> 评审人：reviewer

---

## 0. 总体结论

后端整体结构清晰、分层合理（core / models / api / services），核心数据模型与 PRD §5 高度一致，血缘解析（networkx）与 SP 比对（sqllineage）流程与 PRD §10 对齐。但在**安全性、工作空间隔离的完整性、事务一致性、性能**几方面存在阻断级问题，需在上线前修复。

**问题统计**：阻断 6 / 重要 9 / 建议 8

---

## 1. 问题清单

### 1.1 阻断级（必须修复后才能上线）

#### B1. JWT Secret 默认硬编码且未强制校验
- 位置：`app/core/config.py:12`、`app/core/security.py:29`
- 现象：`JWT_SECRET: str = "change-me-in-prod"` 为硬编码默认值，`create_access_token`/`get_current_user` 直接使用而未校验是否仍为默认值。一旦部署忘记设环境变量，所有人都能伪造任意 Token。
- 影响：认证形同虚设，任意用户可冒充任意身份访问任意工作空间。
- 建议：启动时若 `JWT_SECRET` 为默认值或长度 < 32 则抛异常拒绝启动；或从 Docker secrets / 文件读取。

#### B2. 管理员密码明文硬编码
- 位置：`app/core/config.py:18`、`app/core/database.py:48`
- 现象：`ADMIN_PASSWORD: str = "admin123"`，首次启动即用该明文创建管理员。
- 影响：镜像一旦公开，默认管理员口令广为人知，结合 B1 等于直接开门。
- 建议：启动时若未配置 `ADMIN_PASSWORD` 或为弱口令，拒绝初始化并打印警告；强制首次登录改密。

#### B3. 工作空间隔离在部分写操作中失效
- 位置：`app/api/workspaces.py:114-135`（add_member）、`app/api/workspaces.py:138-153`（update_member_role）、`app/api/workspaces.py:156-170`（remove_member）
- 现象：`add_member` / `update_member_role` / `remove_member` 的依赖签名是 `member: WorkspaceMember = Depends(require_owner)`，但 `require_owner` 内部取的是 `member: WorkspaceMember` 形参——FastAPI 不会自动把 `workspace_id` 路径参数注入到 `get_workspace_member` 的 `workspace_id` 形参（`workspace_id` 是普通 `str` 而非 `Path`），导致 `get_workspace_member` 收到的 `workspace_id` 可能为 None 或触发错误，隔离校验链路不完整。对比 `list_members` 使用 `Depends(get_workspace_member)` 同样存在该隐患。
- 影响：若 FastAPI 路径参数与依赖函数形参名匹配规则未被遵守（此处依赖 `workspace_id` 同名自动注入），权限校验可能绕过，非成员可操作他人工作空间。
- 建议：在 `get_workspace_member` 中显式声明 `workspace_id: str = Path(...)`，或改为 `Annotated[str, Path]`，并在所有"成员管理"路由中先经 `get_workspace_member` 再链式 `require_owner`（当前 `require_owner(member)` 依赖注入未串联 `get_workspace_member`，实际 `member` 来源不明）。

#### B4. SP 来源 config 未加密存储
- 位置：`app/models/sp.py:24`、`app/api/sp.py:59`
- 现象：`SpSource.config` 注释为"加密 JSON"，实际 `create_source` 直接 `json.dumps(body.config)` 明文入库，里面含 Git Token / 数据库连接串。
- 影响：数据库泄露即泄露所有 SP 来源凭据，违反 PRD §12 "连接串加密"要求。
- 建议：引入对称加密（Fernet/AES）对 config 字段加解密；密钥从环境变量读取。

#### B5. SP 拉取创建的临时引擎未关闭且连接串来自用户输入
- 位置：`app/api/sp.py:91`
- 现象：`engine = create_engine(config["conn_str"])` 直接用用户提交的连接串创建引擎，无校验；`pull_sp_from_db` 内 `engine.connect()` 后未 dispose，连接泄漏。且 `conn_str` 可指向内网任意地址（SSRF/内网探测风险）。
- 影响：资源泄漏 + 内网探测面。
- 建议：白名单校验数据库主机；用完 `engine.dispose()`；限制连接超时。

#### B6. 大文件上传无大小限制
- 位置：`app/api/import_excel.py:28`、`app/api/import_excel.py:44`、`app/api/import_excel.py:70`
- 现象：`await file.read()` 一次性读全文件到内存，无大小限制。
- 影响：上传超大 Excel 可打爆内存（OOM），且 pandas 解析也会全量加载。
- 建议：限制上传大小（如 50MB）；流式/分块读取；FastAPI 中间件加 `max_request_size`。

---

### 1.2 重要级（影响功能或稳定性）

#### I1. 关键写操作未使用事务
- 位置：`app/services/import_service.py:96-176`、`app/services/sp_service.py:60-89`、`app/services/sp_service.py:265-323`、`app/services/lineage_service.py:37-54`
- 现象：导入、SP 保存、apply_patch、rebuild_dependencies 中穿插多次 `db.add`/`db.flush`/`db.query.delete`，最后才 `db.commit`；但中间无 try/except 回滚，一旦中途异常，flush 已写入主键但 commit 失败 → 脏数据。
- 建议：用 `with db.begin()` 包裹或显式 `try/except db.rollback()`。

#### I2. `rebuild_dependencies` 删除后未保证重建成功
- 位置：`app/services/lineage_service.py:39`
- 现象：先 `db.query(JobDependency).filter_by(workspace_id=...).delete()` 再重建，若重建中途异常，依赖表被清空且未恢复。
- 影响：血缘图丢失。
- 建议：先构建新边集合，再事务内 delete + insert。

#### I3. N+1 查询泛滥，严重性能隐患
- 位置：
  - `app/api/jobs.py:68-75`（`_tables` 对每条 JobSource/JobTarget 再查 TableMeta）
  - `app/services/lineage_service.py:21-23,27-29`（build_graph 对每个 JobTarget/JobSource 再查 TableMeta）
  - `app/services/lineage_service.py:44`（rebuild_dependencies 对每条边再查 TableMeta）
  - `app/services/sp_service.py:231-238`（run_reconciliation 对每个 JobSource/JobTarget 再查 TableMeta）
- 现象：单次图构建可能产生 (作业数 + 源表数 + 目标表数) 次 TableMeta 查询，PRD §8 要求单空间 5000 作业 / 20000 边，将产生数万次查询。
- 影响：图渲染、影响分析、溯源均超 PRD 性能目标（≤500ms）。
- 建议：批量 `db.query(TableMeta).filter(TableMeta.id.in_(...))` 一次性加载，构造内存索引。

#### I4. `build_graph` 每次调用都重新查询全量
- 位置：`app/services/lineage_service.py:9-34`
- 现象：`graph_data` 内部调 `build_graph`，`detect_cycles` 又调一次 `build_graph`（`graph_data` 末尾 `return {..., "cycles": detect_cycles(...)}`），单次 `/graph` 接口重复构建 2 次图、查询 2 遍全量。
- 建议：`graph_data` 内复用已构建的 `g` 调用 `nx.simple_cycles(g)`。

#### I5. `JobUpdate` 允许任意修改 `sp_name` 等字段但无去重/冲突校验
- 位置：`app/api/jobs.py:113-127`
- 现象：`for k, v in body.model_dump(exclude_unset=True).items(): setattr(job, k, v)` 直接 setattr，未校验字段白名单是否合理；若未来加字段（如 workspace_id）将导致越权改字段。
- 建议：显式列出可更新字段名集合后再 setattr。

#### I6. 删除作业未级联清理 `JobDependency`
- 位置：`app/api/jobs.py:130-146`
- 现象：`delete_job` 删除了 JobSource/JobTarget/FieldMapping/Job，但 `JobDependency` 未删除引用该作业的记录，最后调 `rebuild_dependencies` 是全量重建——虽然最终一致，但中间状态有脏数据；且 rebuild 是全量，5000 作业场景删除一个作业也要重建全图。
- 建议：删除前先删 `JobDependency` 中 upstream/downstream 为该 job 的行；或仅重建受影响子图。

#### I7. `update_member_role` 用 Query 参数传 role 不规范
- 位置：`app/api/workspaces.py:142`
- 现象：`role: str = Query(..., regex="^(EDITOR|VIEWER)$")` 用 Query 传 role，PUT 语义不符；且 pydantic v2 已弃用 `regex`，应为 `pattern`。
- 建议：改为请求体 `{role: str}`；升级 `regex` → `pattern`。

#### I8. `apply_patch` 不校验 `diff_ids` 归属
- 位置：`app/services/sp_service.py:265`
- 现象：`filter_by(id=did, workspace_id=workspace_id)` 已校验空间，但未校验该 diff 是否属于当前 source_id；若同一空间有多个 SP 来源，可跨来源采纳。
- 影响：轻微越权。
- 建议：调用方传入 source_id 一并校验，或在 service 内查 sp_def 归属。

#### I9. `parse_excel`/`validate`/`confirm` 重复解析同一文件
- 位置：`app/api/import_excel.py`
- 现象：validate 和 confirm 都重新 `file.read()` + `parse_excel`，用户需重复上传。
- 影响：大文件场景体验差、重复 IO。
- 建议：parse 阶段返回临时句柄/cache，validate/confirm 复用。

---

### 1.3 建议级（提升质量）

#### S1. 重复的 `_uuid`/`_now` 工具函数
- 位置：`app/models/user.py:9-14`、`app/models/workspace.py:9-14`、`app/models/job.py:9-14`、`app/models/sp.py:9-14`
- 现象：4 个模型文件各自定义相同的 `_uuid` 和 `_now`。
- 建议：抽到 `app/models/base.py` 或 `app/core/types.py` 复用。

#### S2. 缺少响应 schema 统一
- 位置：所有 api 文件
- 现象：部分接口返回 `dict`（如 `{"ok": True}`、`{"pulled": n}`），部分用 `response_model`（如 `WorkspaceOut`），风格不统一。
- 建议：统一用 Pydantic response model；`schemas/` 目录目前为空，正好用来集中定义。

#### S3. `import_rows` 内字段映射处理过于简化且低效
- 位置：`app/services/import_service.py:150-170`
- 现象：每个字段都重新 `_split_tables` + `get_or_create_table`，循环内重复查询；字段映射"按逗号位置对应"是简化假设，PRD 附录 A 允许字段映射单独 Sheet，当前实现无法支持。
- 建议：提取一次 source/target 表后复用；字段映射支持多源多目标需设计更结构化输入。

#### S4. `pull_sp_from_git` 临时目录未清理
- 位置：`app/services/sp_service.py:17-36`、`app/api/sp.py:80`
- 现象：`tempfile.mkdtemp` 创建后从不清理，多次拉取磁盘膨胀。
- 建议：用 `tempfile.TemporaryDirectory` 上下文或 finally 清理。

#### S5. `pull_sp_from_git` 增量逻辑不完整
- 位置：`app/services/sp_service.py:20-22`
- 现象：`if os.path.exists(local_path)` 直接 pull，但 local_path 是 `tempfile.mkdtemp` 每次新建 → 永远走 clone 分支，增量拉取失效。
- 建议：固定工作空间级缓存目录，或显式持久化 clone 路径。

#### S6. `match_sp_to_jobs` 模糊匹配遍历全量作业
- 位置：`app/services/sp_service.py:123-128`
- 现象：每个 SP 对所有作业做 SequenceMatcher，O(SP数 × 作业数)，2000×2000=400 万次。
- 建议：先按前缀/分词粗筛，或建倒排索引。

#### S7. CORS 全开
- 位置：`app/main.py:21-27`
- 现象：`allow_origins=["*"]` + `allow_credentials=True`，浏览器会拒绝；且生产不应全开。
- 建议：开发环境单独配置，生产读环境变量。

#### S8. 缺少日志
- 位置：全局
- 现象：无 `logging` 配置，PRD §12 要求"容器内文件日志 + stdout，rolling 7 天"。
- 建议：引入 `logging.config`，按 PRD 配置 rolling handler。

---

## 2. 好的实践（值得沉淀到开发规范）

1. **分层清晰**：`core`(基础设施) / `models`(数据) / `api`(路由) / `services`(业务) 四层，路由薄、服务厚，职责单一，符合"关注点分离"。
2. **权限分层依赖**：`get_current_user` → `get_workspace_member` → `require_editor`/`require_owner` 形成可组合的依赖链，写操作统一走 `require_editor`，危险操作走 `require_owner`，思路正确（修复 B3 后即可作为范例）。
3. **所有业务表带 `workspace_id` + 索引**：`models/` 下每张业务表都有 `workspace_id` 并建索引与唯一约束，工作空间隔离的数据层基础到位，符合 PRD §5.3 关键约束。
4. **派生表预计算**：`JobDependency` 作为派生表缓存，避免实时计算图，符合 PRD §8.3 "job_dependency 预计算缓存"思路。
5. **`_split_tables` 去重保序**：`import_service.py:181` 实现去重同时保持顺序，细节到位。
6. **upsert 语义**：`import_rows` 按 `(workspace_id, job_name)` upsert，符合 PRD F-05 增量导入"按作业名 upsert"。
7. **SP 解析失败不阻断**：`parse_sp_sql` 单条失败仅标记，不抛异常中断批次，符合 PRD §4.3 "SP SQL 解析失败 → 不阻断其他 SP"。
8. **lifespan 初始化**：`main.py` 用 `@asynccontextmanager lifespan` 而非已弃用的 `@on_event`，做法现代。
9. **唯一约束护航数据完整性**：`UNIQUE(workspace_id, table_name)`、`UNIQUE(workspace_id, job_name)`、`UNIQUE(workspace_id, upstream_job_id, downstream_job_id, via_table_id)` 等约束到位。

---

## 3. 建议沉淀的开发规范条目

> 建议将以下条目加入 `rules/CLAUDE.md` 或新建 `rules/backend-conventions.md`。

### R1. 安全启动校验
应用启动时必须校验关键密钥/口令非默认值且达强度要求，否则拒绝启动。敏感配置（JWT Secret、管理员口令、数据库连接串、SP 来源 config）一律从环境变量/secret 文件读取，禁止硬编码默认值入库。

### R2. 工作空间隔离强制清单
- 所有业务表查询/写入必须带 `workspace_id` 过滤，包括 delete/update 语句。
- 依赖注入链：`get_current_user` → `get_workspace_member`（显式 `Path` 参数） → `require_editor/owner`，禁止跨级直连。
- 路径参数 `workspace_id` 必须在依赖函数签名中显式声明为 `Path`，禁止依赖 FastAPI 隐式同名注入。

### R3. 事务边界
涉及多表写入的服务方法必须用 `with db.begin()` 或 `try/commit/except rollback` 包裹，禁止"分散 flush + 末尾 commit"模式。先构建内存集合再事务内 delete+insert，禁止"先 delete 再逐步重建"的非原子操作。

### R4. 批量查询禁 N+1
任何在循环内对同一表的单行查询都视为缺陷；改为一次性 `in_()` 批量加载 + 内存索引。图算法类服务在单次请求内复用已构建的图对象，禁止重复 `build_graph`。

### R5. 上传与外部输入约束
- 文件上传设最大体积（中间件 + 路由双重限制）。
- 用户提供的数据库连接串必须白名单校验主机，并设连接超时；外部引擎用完 `dispose()`。
- 临时目录用 `TemporaryDirectory` 上下文，禁止 mkdtemp 后不清理。

### R6. 响应格式统一
所有 API 返回走 Pydantic `response_model`，禁止裸 `dict` 返回；`schemas/` 目录集中管理输入/输出 schema，与 `models/` 解耦。

### R7. 日志可观测
启动即配置 `logging`（stdout + rolling 文件 7 天），关键操作（导入、SP 拉取、采纳修订、登录失败）打 INFO 级日志，异常打 ERROR + 堆栈。

### R8. 字段更新白名单
`setattr(obj, k, v)` 模式必须先过滤字段名白名单，禁止直接吃 `model_dump()` 全量字段，防止越权改字段（如 `workspace_id`）。

---

## 4. PRD 合规对照

| PRD 条目 | 实现情况 | 备注 |
|---------|---------|------|
| F-01 Excel 导入 | ✓ | `import_excel.py` 支持解析 |
| F-02 列映射配置 | 部分 | 未实现"保存为模板"（PRD F-02 要求） |
| F-03 导入预览 | ✓ | validate 接口返回 preview[:100] |
| F-04 数据校验 | ✓ | 必填校验到位 |
| F-05 增量导入 | ✓ | upsert by job_name |
| F-06 作业依赖解析 | ✓ | networkx 构图 |
| F-07 字段级血缘 | 部分 | 字段映射按逗号位置对应，过于简化 |
| F-08 影响分析 | ✓ | `nx.descendants` |
| F-09 溯源分析 | ✓ | `nx.ancestors` |
| F-10 环路检测 | ✓ | `nx.simple_cycles` |
| F-11 关系图渲染 | ✓ | graph_data 返回 nodes/edges |
| F-16 作业增删改查 | ✓ | jobs.py CRUD 完整 |
| F-19 数据库切换 | ✓ | config.DB_MODE 三模式 |
| F-21 用户登录 | ✓ | JWT + bcrypt |
| F-22 工作空间管理 | ✓ | workspaces.py |
| F-23 成员管理 | 部分 | 角色 PUT 用 Query 参数不规范（I7） |
| F-24 关联 SP 来源 | ✓ | sp.py create_source |
| F-25 拉取存储过程 | 部分 | Git/DB 两种，但 Git 增量失效（S5） |
| F-26 SP 自动匹配 | ✓ | 精确 + 模糊 |
| F-27 SP SQL 解析 | ✓ | sqllineage |
| F-28 血缘比对 | ✓ | reconcile_lineage |
| F-29 修订建议 | 部分 | apply_patch 不处理 `mismatch` 字段差异（PRD §10.3.5 列了 mismatch 类型，代码未实现） |
| F-30 SP 来源刷新 | 部分 | 增量比对未实现（PRD F-30 要求按 diff 增量） |
| §5 数据模型 | ✓ | 表结构与 PRD §5.2 一一对应 |
| §12 连接串加密 | ✗ | B4 未加密 |
| §12 日志 rolling 7 天 | ✗ | S8 无日志 |
| §8 性能 | 风险 | I3/I4 N+1 与重复构建 |

---

**—— 评审结束 ——**
