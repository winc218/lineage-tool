# 批量作业数据血缘关系分析与管理工具 — 产品需求文档（PRD）

> 文档版本：v2.0
> 编写日期：2026-08-08
> 文档目的：指导 AI 开发团队完成"批量作业数据血缘关系分析与管理工具"的设计与实现。
> 适用范围：内网 Docker 化部署，全团队共享，多用户多工作空间隔离。
> 版本变更：v1.0→v2.0 部署改为 Docker；新增用户/工作空间；新增存储过程自动校验补充血缘。

---

## 0. 文档导读

| 章节 | 内容 | 阅读对象 |
|------|------|----------|
| §1 | 背景与目标 | 全员 |
| §2 | 名词术语 | 全员 |
| §3 | 功能范围 | PM / 开发 / 测试 |
| §4 | 交互逻辑与用户流程 | PM / UI / 前端 |
| §5 | 数据模型设计 | 后端 / DBA |
| §6 | 技术栈选型 | 架构 / 全栈 |
| §7 | 数据库适配策略 | 后端 / DBA |
| §8 | 性能与容量要求 | 架构 / 后端 |
| §9 | Docker 化部署与用户/工作空间 | DevOps / 运维 |
| §10 | 存储过程自动血缘校验补充 | 后端 / 架构 |
| §11 | UI / UX 关键要点 | UI / 前端 |
| §12 | 非功能性需求 | 全员 |
| §13 | 里程碑与验收标准 | PM / 测试 |
| §14 | 风险与对策 | 架构 / PM |
| §15 | 现有工具调研与差异分析 | 架构 / PM |
| 附录 A | Excel 模板规范 | 全员 |
| 附录 B | 血缘解析算法 | 后端 |
| 附录 C | 存储过程解析比对算法 | 后端 |
| 附录 D | 交付物清单 | 全员 |

---

## 1. 背景与目标

### 1.1 业务背景

企业内部存在大量批处理作业（ETL / 调度任务 / 存储过程调度），单个作业通常从若干**源表**读取数据，经处理后写入若干**目标表**。随着作业数量增长至上千规模，出现以下痛点：

- 作业之间的数据流向不透明，影响变更影响面评估。
- 出现数据质量问题时，难以快速溯源到上游作业。
- 新人接手困难，缺少可视化的全局依赖视图。
- 现有作业元数据散落在 Excel、文档中，无统一管理。
- 存储过程源码分散在 Git 仓库与数据库中，与 Excel 登记的作业信息可能不一致，缺少自动校验与同步机制。

### 1.2 产品目标

构建一款**批量作业数据血缘关系分析与管理工具**，实现：

1. **导入**：读取 Excel 中的批量作业信息（作业名、源表、目标表、字段映射等）。
2. **解析**：自动分析上千作业之间的数据血缘关系（作业 A 的目标表 = 作业 B 的源表 ⇒ A→B 依赖）。
3. **可视化**：生成交互式关系图，节点为作业，点击节点可查看其源表/目标表详情与字段级映射。
4. **存储过程自动校验补充**：导入 Excel 完成初次分析后，用户可关联存储过程来源（Git 仓库或数据库），程序自动解析存储过程 SQL，与 Excel 血缘进行比对，校验差异、补充遗漏、修订错误。
5. **多用户协作**：Docker 化部署，全团队共享；通过用户管理与工作空间隔离，避免相互影响。
6. **部署**：内网 Docker 一次部署、团队共享，开箱即用。

### 1.3 非目标（本期不做）

- 不做实时作业运行监控（本期只做元数据血缘，不含运行态）。
- 不做作业调度执行（不替代调度系统）。
- 不接入外部元数据管理平台（如 DataHub / Atlas），本期为独立工具。
- 不支持非关系型数据源的血缘（仅 SQL Server / GoldenDB / 内存数据库的表级血缘）。
- 不做存储过程的语法级调试或执行（只解析其 SQL 文本提取血缘）。

### 1.4 成功指标

| 指标 | 目标值 |
|------|--------|
| 单工作空间导入作业数 | ≥ 5000 |
| 全量血缘图渲染时间（2000 节点） | ≤ 5 秒（首屏可交互） |
| 节点点击响应 | ≤ 200ms |
| Excel 血缘解析准确率 | ≥ 99%（对比人工抽样） |
| 存储过程解析比对覆盖率 | ≥ 95%（可匹配到存储过程的作业） |
| 存储过程血缘补充/修订采纳率 | ≥ 80%（用户确认采纳的修订占比） |
| 并发用户数 | ≥ 20 |
| Docker 部署耗时 | ≤ 5 分钟 |

---

## 2. 名词术语

| 术语 | 定义 |
|------|------|
| 批量作业（Job） | 一个独立的数据处理单元，含若干源表与目标表 |
| 源表（Source Table） | 作业读取数据的表 |
| 目标表（Target Table） | 作业写入数据的表 |
| 数据血缘（Lineage） | 数据从源到目标的流转路径 |
| 作业依赖（Job Dependency） | 作业 A 的某目标表是作业 B 的某源表，则 B 依赖 A（A→B） |
| 字段映射（Field Mapping） | 源表字段到目标表字段的对应关系 |
| 影响分析（Impact Analysis） | 给定一个作业/表，分析其下游所有受影响作业 |
| 溯源分析（Root Cause Analysis） | 给定一个作业/表，分析其上游所有来源作业 |
| **工作空间（Workspace）** | 一个隔离的血缘分析空间，含独立的作业集、血缘图、存储过程配置；不同工作空间数据互不可见 |
| **存储过程来源（SP Source）** | 存储过程的存放位置：Git 仓库或数据库连接 |
| **血缘比对（Lineage Reconciliation）** | 将存储过程解析出的血缘与 Excel 导入的血缘进行差异比对，输出校验报告 |
| **血缘修订（Lineage Patch）** | 基于比对结果，对 Excel 血缘进行补充/修订，用户确认后生效 |

---

## 3. 功能范围

### 3.1 功能模块总览

```
┌───────────────────────────────────────────────────────────────┐
│                         工具主界面                             │
├──────────────┬──────────────┬──────────────────────────────────┤
│  数据导入    │  血缘分析    │     可视化与交互                 │
│  (Import)    │  (Analyze)   │     (Visualize)                  │
├──────────────┼──────────────┼──────────────────────────────────┤
│ Excel 读取   │ 作业依赖解析 │ 关系图渲染                      │
│ 列映射配置   │ 字段级血缘   │ 节点点击展开                    │
│ 数据校验     │ 影响分析     │ 搜索/筛选/高亮                  │
│ 增量导入     │ 溯源分析     │ 布局切换                        │
│ 导入预览     │ 环路检测     │ 导出图片/JSON                   │
├──────────────┴──────────────┴──────────────────────────────────┤
│              存储过程血缘校验补充 (Reconcile)                  │
│  关联SP来源(Git/DB) → 拉取SP → SQL解析 → 比对 → 修订建议      │
├───────────────────────────────────────────────────────────────┤
│              作业管理 (Manage)                                  │
│  增删改查 / 版本快照 / 标签分组 / 备注                         │
├───────────────────────────────────────────────────────────────┤
│              用户与工作空间 (Access)                            │
│  用户登录 / 工作空间增删切换 / 成员管理 / 权限控制             │
├───────────────────────────────────────────────────────────────┤
│              系统管理 (System)                                  │
│  数据库切换 / 用户偏好 / 日志 / 关于                           │
└───────────────────────────────────────────────────────────────┘
```

### 3.2 功能清单（F-XXX）

| 编号 | 功能 | 优先级 | 描述 |
|------|------|--------|------|
| F-01 | Excel 导入 | P0 | 支持 .xlsx/.xls，交互式选择列映射 |
| F-02 | 列映射配置 | P0 | 可视化下拉指定列含义，可保存模板 |
| F-03 | 导入预览 | P0 | 表格预览前 N 行，标红异常行 |
| F-04 | 数据校验 | P0 | 必填项、表名格式、字段映射完整性校验 |
| F-05 | 增量导入 | P1 | 多次导入合并，按作业名 upsert |
| F-06 | 作业依赖解析 | P0 | 自动计算作业间依赖关系 |
| F-07 | 字段级血缘 | P1 | 含字段映射时生成字段级血缘 |
| F-08 | 影响分析 | P0 | 高亮下游所有作业 |
| F-09 | 溯源分析 | P0 | 高亮上游所有作业 |
| F-10 | 环路检测 | P0 | 检测依赖环，告警标红 |
| F-11 | 关系图渲染 | P0 | 交互式有向图，节点=作业 |
| F-12 | 节点点击展开 | P0 | 侧栏显示源表/目标表/字段映射 |
| F-13 | 搜索/筛选 | P0 | 按作业名/表名搜索，按标签筛选 |
| F-14 | 布局切换 | P1 | 力导向 / 分层 / 环形 |
| F-15 | 导出 | P1 | PNG/SVG/JSON/Excel |
| F-16 | 作业增删改查 | P1 | 手工维护作业元数据 |
| F-17 | 版本快照 | P2 | 保存血缘快照，版本对比 |
| F-18 | 标签分组 | P2 | 标签筛选/着色 |
| F-19 | 数据库切换 | P0 | 运行时切换 SQL Server / GoldenDB / 内存 |
| F-20 | 用户偏好 | P2 | 记住布局、主题、模板 |
| **F-21** | **用户注册登录** | **P0** | 账号密码登录，会话管理 |
| **F-22** | **工作空间管理** | **P0** | 创建/切换/删除工作空间，数据隔离 |
| **F-23** | **成员管理** | **P0** | 工作空间内成员邀请、角色（Owner/Editor/Viewer） |
| **F-24** | **关联存储过程来源** | **P0** | 配置 Git 仓库或数据库连接作为 SP 来源 |
| **F-25** | **拉取存储过程** | **P0** | 从 Git 拉取 .sql 文件 / 从 DB 查询 SP 定义 |
| **F-26** | **SP 自动匹配作业** | **P0** | 按作业名↔SP名 匹配，支持手动绑定 |
| **F-27** | **SP SQL 解析血缘** | **P0** | 用 sqllineage 解析 SP 内 SQL，提取表/列血缘 |
| **F-28** | **血缘比对** | **P0** | SP 血缘 vs Excel 血缘，输出差异报告 |
| **F-29** | **血缘修订建议** | **P0** | 差异项生成补充/修订建议，用户确认采纳 |
| **F-30** | **SP 来源刷新** | **P1** | 重新拉取最新 SP，增量比对 |

### 3.3 用户故事（核心场景）

**US-01：分析师首次导入**
> 作为数据架构师，我希望在工作空间中导入一份含 1500 个作业的 Excel，工具自动解析出血缘图，让我一眼看出关键枢纽。

**US-02：变更影响评估**
> 作为 ETL 开发者，我希望选中某个作业后，工具高亮其所有下游作业，评估修改影响范围。

**US-03：问题溯源**
> 作为数据运维人员，当某张目标表数据异常时，我希望输入表名，工具沿上游标出所有来源作业。

**US-04：节点详情查看**
> 作为新人，我希望点击图中任意作业节点，立即看到它的源表、目标表及字段映射。

**US-05：存储过程自动校验补充**（新增）
> 作为数据架构师，我导入 Excel 完成初版血缘后，希望关联存储过程所在的 Git 仓库，工具自动拉取 SP、解析 SQL、与我登记的血缘比对，告诉我哪些作业的源表/目标表登记有误或遗漏，并支持一键采纳修订。

**US-06：多用户协作隔离**（新增）
> 作为团队负责人，我希望通过 Docker 部署一个全团队共享的实例，不同小组在不同工作空间中分析各自的作业血缘，互不干扰；成员只能访问被授权的工作空间。

**US-07：工作空间切换**
> 作为跨项目分析师，我希望在同一登录会话中切换多个工作空间，快速对比不同业务域的血缘。

---

## 4. 交互逻辑与用户流程

### 4.1 主流程

```
启动应用 → 登录
   │
   ▼
[工作空间选择] ── 我拥有的 / 被邀请的 / 新建
   │
   ▼
[首页 / 仪表盘] ── 该工作空间的作业总数、表总数、依赖数、SP覆盖率、最近导入
   │
   ├──► [导入向导]
   │        1. 选择 Excel 文件
   │        2. 选择 Sheet
   │        3. 配置列映射
   │        4. 预览数据（前 100 行，标红异常）
   │        5. 校验报告
   │        6. 确认导入 → 写入当前工作空间
   │        7. 触发血缘解析 → 进入关系图
   │
   ├──► [血缘关系图]
   │        - 全局视图（默认）
   │        - 搜索/筛选/布局切换
   │        - 节点交互：单击选中、双击展开详情、右键菜单
   │        - 节点角标：已用 SP 校验✓ / 有差异⚠ / 未关联 SP○
   │
   ├──► [存储过程校验补充]（新增，详见 §10）
   │        1. 关联 SP 来源（Git 仓库 / 数据库连接）
   │        2. 拉取存储过程
   │        3. 自动匹配作业（SP名↔作业名）
   │        4. 解析 SP SQL 提取血缘
   │        5. 与 Excel 血缘比对 → 差异报告
   │        6. 逐条/批量采纳修订 → 更新血缘图
   │
   ├──► [作业管理]
   │
   ├──► [影响分析 / 溯源分析]
   │
   ├──► [工作空间管理]
   │        - 成员管理（邀请、角色）
   │        - 工作空间设置
   │
   └──► [系统设置]
            - 数据库切换、偏好、日志
```

### 4.2 关键交互细节

#### 4.2.1 Excel 列映射交互（F-02）

- 选择文件与 Sheet 后，读取表头，以**左右两列对照**展示：
  - 左列：Excel 实际列名（只读）
  - 右列：下拉框，选项为系统字段（作业名、源表名、目标表名、源字段、目标字段、作业描述、作业类型、调度频率、负责人、备注、**存储过程名**）
- 必填字段（作业名、源表、目标表）未映射时禁用下一步。
- 支持"保存为模板"。

#### 4.2.2 关系图节点交互（F-11/F-12）

- **节点视觉**：圆形，颜色按作业类型区分，大小按"出度+入度"缩放。
- **SP 校验角标**（新增）：
  - ✓ 绿色：已用 SP 校验且一致
  - ⚠ 橙色：SP 解析结果与 Excel 登记存在差异
  - ○ 灰色：未关联 SP
- **悬停**：tooltip（作业名、源表数、目标表数、上下游数、SP 校验状态）。
- **单击**：选中节点，高亮直接上下游。
- **双击**：右侧抽屉展示：
  - 作业基本信息
  - 源表列表（表名 + 字段）
  - 目标表列表（表名 + 字段）
  - 字段映射表
  - 上下游作业列表（可点击跳转）
  - **SP 校验信息**（新增）：关联的 SP 名、来源、解析出的源表/目标表、差异项
- **右键菜单**：影响分析、溯源分析、编辑、删除、复制作业名、设为起点、**重新校验此作业**。

#### 4.2.3 影响分析 / 溯源分析（F-08/F-09）

- 输入作业名或表名，BFS 遍历上下游，高亮路径，非相关灰化。
- 右侧列表按层级展示，可点击跳转。

#### 4.2.4 环路检测（F-10）

- 解析阶段执行有向图环检测（Tarjan / DFS 三色标记）。
- 发现环：全局告警条 + 红色边 + 定位按钮。

#### 4.2.5 工作空间切换交互（新增，F-22）

- 顶部导航栏左侧显示当前工作空间名 + 切换下拉。
- 切换时整页刷新数据，所有查询带 `workspace_id`。
- 无权限工作空间不在列表中显示。

#### 4.2.6 存储过程校验补充交互（新增，详见 §10）

- 独立菜单"SP 校验"，分三步向导：
  1. **关联来源**：填写 Git 仓库地址 + 分支 + token，或数据库连接信息。
  2. **匹配作业**：自动按 SP名↔作业名 匹配，展示匹配表（已匹配/未匹配/疑似匹配）。
  3. **比对采纳**：展示差异报告，逐条勾选采纳或全部采纳。

### 4.3 异常流程

| 场景 | 处理 |
|------|------|
| Excel 格式错误 | 提示具体错误，不进入下一步 |
| 必填列未映射 | 禁用下一步，红色提示 |
| 作业名重复 | 默认 upsert，提示"将更新 N 个已存在作业" |
| 解析出环 | 不阻断，告警提示 |
| 数据库连接失败 | 降级为内存模式，提示"数据不持久化" |
| 图节点过多（>5000） | 提示启用聚合视图 |
| **未登录访问** | 跳转登录页 |
| **无权限工作空间** | 403 提示，不显示该空间 |
| **Git 拉取失败** | 提示网络/token/分支错误，支持重试 |
| **SP SQL 解析失败** | 标记该 SP 为"解析失败"，不阻断其他 SP；记录到日志 |
| **SP 无法匹配作业** | 列入"未匹配"区，支持手动绑定 |

---

## 5. 数据模型设计

### 5.1 实体关系总览

```
┌────────────┐  ┌──────────────┐  ┌──────────────┐
│  User      │  │  Workspace   │  │ Workspace    │
│  用户      │──│  Member      │──│  工作空间    │
└────────────┘  └──────────────┘  └──────┬───────┘
                                         │ 1
                                         │ n
┌──────────┐    ┌──────────────┐    ┌──────────────┐
│   Job    │----│  JobSource   │----│   Table      │
│  作业    │ 1  │  作业源表    │ N  │   表(WS隔离) │
└──────────┘ m  └──────────────┘ 1  └──────────────┘
     │ 1                                 │ 1
     │ m                                 │ m
┌──────────────┐                  ┌──────────────────┐
│  JobTarget   │------------------│  FieldMapping    │
└──────────────┘                  └──────────────────┘
     │
     │ 派生
     ▼
┌──────────────────┐
│  JobDependency   │
└──────────────────┘

┌──────────────────┐    ┌──────────────────────┐
│  SpSource        │    │  SpParseResult       │
│  SP来源(Git/DB)  │───│  SP解析结果(血缘)    │
└──────────────────┘    └──────────────────────┘
         │                        │
         └──────────┬─────────────┘
                    ▼
         ┌────────────────────┐
         │  LineageDiff       │
         │  血缘差异(比对结果)│
         └────────────────────┘
```

> **关键约束**：所有业务表（job、table_meta、job_source、job_target、field_mapping、job_dependency、sp_source、sp_parse_result、lineage_diff）均含 `workspace_id` 字段，实现工作空间数据隔离。

### 5.2 表结构（逻辑模型）

> 主键使用 `VARCHAR(64)` UUID。所有业务表含 `workspace_id`、`created_at`、`updated_at`。

#### 5.2.1 user（用户表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | |
| username | VARCHAR(100) UNIQUE | 登录名 |
| password_hash | VARCHAR(200) | bcrypt 哈希 |
| display_name | VARCHAR(100) | 显示名 |
| email | VARCHAR(200) | |
| role | VARCHAR(20) | GLOBAL_ADMIN / USER |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### 5.2.2 workspace（工作空间）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | |
| name | VARCHAR(200) | 工作空间名 |
| description | VARCHAR(1000) | |
| owner_id | VARCHAR(64) FK→user | 创建者 |
| db_mode | VARCHAR(20) | memory / sqlserver / goldendb |
| db_conn | VARCHAR(1000) | 加密连接串（若非 memory） |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### 5.2.3 workspace_member（工作空间成员）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | |
| workspace_id | VARCHAR(64) FK | |
| user_id | VARCHAR(64) FK→user | |
| role | VARCHAR(20) | OWNER / EDITOR / VIEWER |
| created_at | TIMESTAMP | |

唯一约束：`UNIQUE(workspace_id, user_id)`

#### 5.2.4 job（作业表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | |
| workspace_id | VARCHAR(64) FK | **工作空间隔离** |
| job_name | VARCHAR(200) | 作业名 |
| job_type | VARCHAR(50) | ETL / PROCEDURE / SCRIPT / OTHER |
| description | VARCHAR(1000) | |
| schedule | VARCHAR(50) | |
| owner | VARCHAR(100) | |
| tag | VARCHAR(200) | |
| remark | VARCHAR(1000) | |
| sp_name | VARCHAR(200) | 关联的存储过程名（可空） |
| source_file | VARCHAR(500) | |
| import_batch | VARCHAR(64) | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

唯一索引：`UNIQUE(workspace_id, job_name)`

#### 5.2.5 table_meta（表元数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | |
| workspace_id | VARCHAR(64) FK | |
| table_name | VARCHAR(200) | 含 schema |
| db_name | VARCHAR(100) | |
| remark | VARCHAR(500) | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

唯一索引：`UNIQUE(workspace_id, table_name)`

#### 5.2.6 job_source / job_target / field_mapping / job_dependency

结构与 v1.0 相同，均新增 `workspace_id` 字段并纳入索引。

`job_dependency` 示例：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | |
| workspace_id | VARCHAR(64) FK | |
| upstream_job_id | VARCHAR(64) FK→job | |
| downstream_job_id | VARCHAR(64) FK→job | |
| via_table_id | VARCHAR(64) FK→table_meta | |
| via_table_name | VARCHAR(200) | |
| source | VARCHAR(20) | **excel / sp**（血缘来源标记） |
| created_at | TIMESTAMP | |

唯一约束：`UNIQUE(workspace_id, upstream_job_id, downstream_job_id, via_table_id)`

#### 5.2.7 sp_source（存储过程来源，新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | |
| workspace_id | VARCHAR(64) FK | |
| name | VARCHAR(200) | 来源名称（如"生产Git仓库"） |
| type | VARCHAR(20) | git / database |
| config | TEXT | 加密的配置 JSON（Git: url/branch/token/path；DB: 连接串） |
| last_sync_at | TIMESTAMP | 最近拉取时间 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

#### 5.2.8 sp_definition（存储过程定义，新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | |
| workspace_id | VARCHAR(64) FK | |
| sp_source_id | VARCHAR(64) FK→sp_source | |
| sp_name | VARCHAR(200) | 存储过程名 |
| sp_text | TEXT | SP 完整 SQL 文本 |
| file_path | VARCHAR(500) | Git 中的路径（git 类型） |
| matched_job_id | VARCHAR(64) FK→job | 匹配的作业（可空，手动绑定） |
| match_status | VARCHAR(20) | auto_matched / manual / unmatched |
| parse_status | VARCHAR(20) | pending / success / failed |
| parse_error | TEXT | 解析错误信息 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

唯一约束：`UNIQUE(workspace_id, sp_source_id, sp_name)`

#### 5.2.9 sp_parse_result（SP 解析血缘结果，新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | |
| workspace_id | VARCHAR(64) FK | |
| sp_def_id | VARCHAR(64) FK→sp_definition | |
| source_tables | TEXT | JSON 数组：解析出的源表名 |
| target_tables | TEXT | JSON 数组：解析出的目标表名 |
| column_lineage | TEXT | JSON：列级血缘 |
| parsed_at | TIMESTAMP | |

#### 5.2.10 lineage_diff（血缘差异，新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | |
| workspace_id | VARCHAR(64) FK | |
| job_id | VARCHAR(64) FK→job | |
| sp_def_id | VARCHAR(64) FK→sp_definition | |
| diff_type | VARCHAR(20) | source_missing / target_missing / source_extra / target_extra / mismatch |
| excel_value | VARCHAR(500) | Excel 登记的值 |
| sp_value | VARCHAR(500) | SP 解析的值 |
| status | VARCHAR(20) | pending / accepted / rejected |
| action | VARCHAR(20) | add / remove / update |
| created_at | TIMESTAMP | |
| resolved_at | TIMESTAMP | |

### 5.3 血缘解析逻辑（详见附录 B）

Excel 作业级依赖：遍历作业目标表与源表，匹配建立 `producer→consumer` 边。

---

## 6. 技术栈选型

### 6.1 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                   Docker 容器 (Web应用)                  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │            前端 (Vue 3 + TS + Vite)              │  │
│  │   UI: Element Plus    图: AntV G6 5.x           │  │
│  │   状态: Pinia        路由: Vue Router            │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │ HTTP                          │
│  ┌───────────────────────┴───────────────────────────┐  │
│  │            后端 (Python 3.11 + FastAPI)          │  │
│  │   Excel: openpyxl/pandas   图: networkx         │  │
│  │   ORM: SQLAlchemy 2.x     认证: JWT              │  │
│  │   SP解析: sqllineage      Git: GitPython         │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │                               │
│  ┌───────────────────────┴───────────────────────────┐  │
│  │          数据库适配层 (SQLAlchemy Dialect)       │  │
│  │  ┌─────────┬──────────┬──────────────────────┐   │  │
│  │  │ SQLite  │SQLServer │ GoldenDB  (pymysql)  │   │  │
│  │  │(容器内置)│(pymssql) │                      │   │  │
│  │  └─────────┴──────────┴──────────────────────┘   │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
        │ docker run -p 8080:80
        ▼
   团队浏览器访问 http://内网IP:8080
```

### 6.2 技术选型理由

| 层 | 技术 | 版本 | 选型理由 |
|----|------|------|----------|
| 前端框架 | Vue 3 | 3.4+ | 生态成熟 |
| 语言 | TypeScript | 5.x | 类型安全 |
| 构建 | Vite | 5.x | 快速构建 |
| UI 组件 | Element Plus | 2.x | 企业级组件 |
| 图可视化 | AntV G6 | 5.x | 万级节点关系图 |
| 状态 | Pinia | 2.x | Vue 3 官方推荐 |
| 路由 | Vue Router | 4.x | SPA 路由 |
| 后端框架 | FastAPI | 0.110+ | 异步高性能 |
| Excel | openpyxl + pandas | latest | xlsx 解析 |
| 图算法 | networkx | 3.x | 有向图、环检测、BFS |
| ORM | SQLAlchemy | 2.x | 多数据库适配 |
| 认证 | python-jose (JWT) | latest | 无状态认证，适合多用户 |
| 密码 | bcrypt | latest | 安全哈希 |
| **SP 解析** | **sqllineage** | **1.5+** | **开源 SQL 血缘解析，支持表/列级，多方言** |
| **Git** | **GitPython** | **3.x** | **Python 操作 Git 仓库，拉取 SP 文件** |
| Web 服务器 | Uvicorn / Nginx | latest | 生产级 ASGI |
| 容器 | Docker | latest | 一次构建随处部署 |

### 6.3 为什么选 sqllineage？

经调研（详见 §15），sqllineage 是最契合本场景的开源工具：
- 纯 Python，可直接作为依赖内嵌。
- 支持表级与列级血缘提取。
- 支持多种 SQL 方言（含 SQL Server / MySQL 方言，GoldenDB 兼容 MySQL）。
- 可解析 `INSERT INTO ... SELECT`、`CREATE TABLE AS`、存储过程体内的多条 SQL。
- 提供 Python API，便于集成到比对流程。

本工具**不直接使用 sqllineage 的 Web UI**，而是调用其解析 API，将结果纳入自己的工作空间与比对流程。

---

## 7. 数据库适配策略

### 7.1 支持的数据库

| 数据库 | 角色 | 驱动 | 说明 |
|--------|------|------|------|
| **SQLite** | 默认 | Python 内置 `sqlite3` | 容器内置，零配置，数据存容器卷或挂载卷 |
| **SQL Server 2019** | 可选 | `pymssql`（纯 Python） | 企业级持久化；使用 pymssql 避免 ODBC 依赖 |
| **GoldenDB** | 可选 | `pymysql` | 兼容 MySQL 协议 |

### 7.2 适配层设计

与 v1.0 一致，采用 **Repository + SQLAlchemy Dialect** 双层适配。

### 7.3 数据库切换

- **系统级**：Docker 启动时通过环境变量 `DB_MODE` 指定（默认 sqlite）。
- **工作空间级**：每个工作空间可选自己的数据库模式（memory/sqlserver/goldendb），便于不同团队用不同库。
- 切换时自动建表、可选数据迁移。

### 7.4 GoldenDB 适配要点

- 复用 MySQL Dialect，连接串 `mysql+pymysql://...`。
- 针对分布式限制（复杂 JOIN 下推、FOR UPDATE）降级处理。

---

## 8. 性能与容量要求

### 8.1 容量目标

| 指标 | 目标 |
|------|------|
| 单工作空间作业数 | ≥ 5000 |
| 单工作空间表数 | ≥ 2000 |
| 作业依赖边数 | ≥ 20000 |
| 字段映射数 | ≥ 50000 |
| 全平台工作空间数 | ≥ 50 |
| 并发用户数 | ≥ 20 |
| Excel 单文件行数 | ≥ 5000 |
| SP 解析单批次 | ≥ 2000 个 SP |

### 8.2 性能指标

| 操作 | 目标耗时 |
|------|----------|
| Excel 导入（2000 行） | ≤ 3 秒 |
| Excel 导入（5000 行） | ≤ 8 秒 |
| 血缘解析（2000 作业） | ≤ 1 秒 |
| 全图渲染首屏（2000 节点） | ≤ 5 秒 |
| 节点点击响应 | ≤ 200ms |
| 影响分析（BFS） | ≤ 500ms |
| 搜索 | ≤ 300ms |
| 环路检测（5000 节点） | ≤ 1 秒 |
| **SP 拉取（Git，500 文件）** | ≤ 30 秒 |
| **SP SQL 解析（500 个 SP）** | ≤ 60 秒 |
| **血缘比对（2000 作业）** | ≤ 5 秒 |

### 8.3 性能保障策略

- 图渲染：分批渲染 + 聚合视图 + Web Worker 布局。
- 查询：`job_dependency` 预计算缓存；影响分析走内存图 BFS。
- 导入：pandas 批量读取 + executemany 批量插入。
- **SP 解析**：sqllineage 解析为 CPU 密集型，使用后台任务队列（Celery / FastAPI BackgroundTasks），异步执行，前端轮询进度。
- **多用户**：Uvicorn 多 worker；SQLite 在高并发写时切换到 SQL Server/GoldenDB。

---

## 9. Docker 化部署与用户/工作空间

### 9.1 Docker 镜像设计

#### Dockerfile 要点

```dockerfile
FROM python:3.11-slim

# 系统依赖（Git 用于拉取 SP）
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 前端静态资源（构建阶段产物）
COPY app/static /app/static

# 后端代码
COPY app /app/app
COPY run.py /app/run.py

WORKDIR /app
EXPOSE 8080

# Uvicorn 启动
CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]
```

#### requirements.txt 关键依赖

```
fastapi==0.110.*
uvicorn[standard]==0.27.*
sqlalchemy==2.0.*
pymssql==2.3.*
pymysql==1.1.*
openpyxl==3.1.*
pandas==2.2.*
networkx==3.2.*
sqllineage==1.5.*
gitpython==3.1.*
python-jose[cryptography]==3.3.*
bcrypt==4.1.*
python-multipart==0.0.*
```

### 9.2 docker-compose 部署

```yaml
version: "3.8"
services:
  lineage-tool:
    image: lineage-tool:v2.0
    container_name: lineage-tool
    ports:
      - "8080:8080"
    volumes:
      - lineage-data:/app/data          # SQLite 数据持久化
      - lineage-logs:/app/logs
      - lineage-config:/app/config
    environment:
      - DB_MODE=sqlite                   # 默认 sqlite，可改 sqlserver/goldendb
      - JWT_SECRET=change-me-in-prod
      - ADMIN_USERNAME=admin
      - ADMIN_PASSWORD=change-me
    restart: unless-stopped

volumes:
  lineage-data:
  lineage-logs:
  lineage-config:
```

### 9.3 部署流程

```
1. 将镜像 tar 包导入内网 Docker 主机：
   docker load -i lineage-tool-v2.0.tar
2. 编写 docker-compose.yml（或使用附带的模板）
3. docker compose up -d
4. 浏览器访问 http://<服务器IP>:8080
5. 首次访问用环境变量配置的 admin 账号登录
6. 创建工作空间 → 邀请成员 → 导入 Excel → 开始分析
```

### 9.4 用户与工作空间机制

#### 9.4.1 用户体系

- **全局账号**：用户在系统级注册/登录，账号跨工作空间。
- **角色**：
  - `GLOBAL_ADMIN`：系统管理员，管理所有用户和工作空间。
  - `USER`：普通用户，只能访问被授权的工作空间。
- **认证**：JWT Token，登录后下发，前端存 localStorage，请求头携带。

#### 9.4.2 工作空间体系

- **工作空间（Workspace）**：血缘分析的隔离单元。
  - 每个工作空间有独立的作业集、表、血缘图、SP 来源配置。
  - 工作空间之间数据完全隔离（所有查询带 `workspace_id`）。
- **成员角色**（工作空间内）：
  - `OWNER`：空间创建者，可增删成员、删除空间、一切操作。
  - `EDITOR`：可导入、编辑、触发 SP 校验。
  - `VIEWER`：只读浏览血缘图与详情。
- **切换**：顶部下拉切换当前工作空间，切换后整页数据刷新。

#### 9.4.3 隔离实现

- **数据层**：每张业务表含 `workspace_id`，ORM 查询自动注入过滤。
- **API 层**：所有 API 需携带 `workspace_id`（从当前会话上下文取），后端校验当前用户是否为该空间成员。
- **SP 来源**：`sp_source` 也按工作空间隔离，不同空间可配不同的 Git 仓库或数据库连接。

### 9.5 数据持久化与备份

- SQLite 模式：数据文件挂载到 `lineage-data` 卷，备份即拷贝卷。
- SQL Server / GoldenDB 模式：数据存外部库，容器无状态。
- 配置（用户、工作空间元数据）始终存 SQLite（系统库），即使业务数据走外部库。

### 9.6 升级方案

```
docker compose pull   # 拉取新镜像
docker compose up -d  # 滚动重启，卷数据保留
# 后端启动时自动执行数据库迁移（Alembic）
```

---

## 10. 存储过程自动血缘校验补充（核心新增模块）

### 10.1 模块目标

在用户通过 Excel 导入完成初版血缘图后，支持关联存储过程来源（Git 仓库或数据库），程序自动：

1. 拉取存储过程定义（SP 文本）。
2. 将 SP 与已导入的作业匹配（SP 名 ↔ 作业名）。
3. 用 sqllineage 解析 SP 内的 SQL，提取表级与列级血缘。
4. 将 SP 解析血缘与 Excel 登记血缘比对，输出差异报告。
5. 用户确认后，采纳修订（补充遗漏表、删除多余表、更新字段映射），更新血缘图。

### 10.2 整体流程

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 1.关联SP来源 │───►│ 2.拉取SP    │───►│ 3.匹配作业  │
│ Git / DB    │    │ sp_definition│    │ auto/manual │
└─────────────┘    └─────────────┘    └──────┬──────┘
                                             │
                                             ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 6.采纳修订   │◄───│ 5.血缘比对  │◄───│ 4.SQL解析   │
│ update 图   │    │ lineage_diff│    │ sqllineage  │
└─────────────┘    └─────────────┘    └─────────────┘
```

### 10.3 各步骤详述

#### 10.3.1 关联 SP 来源（F-24）

支持两种来源类型：

**A. Git 仓库**
- 配置项：仓库 URL、分支、访问 Token、SP 文件目录（如 `/stored_procedures/`）。
- 拉取方式：使用 GitPython 克隆/拉取指定分支，遍历目录下 `.sql` 文件。
- 文件名约定：`<sp_name>.sql`（如 `etl_user_dmt_daily.sql`），便于与作业名匹配。

**B. 数据库连接**
- 配置项：数据库类型（SQL Server / GoldenDB）、连接串、Schema。
- 拉取方式：
  - SQL Server：查询 `sys.sql_modules` + `sys.objects` 获取 SP 定义文本。
  - GoldenDB：查询 `information_schema.routines` 获取 SP 定义。
- 拉取后存入 `sp_definition.sp_text`。

配置信息加密存储于 `sp_source.config`。

#### 10.3.2 拉取存储过程（F-25）

- 后台任务执行，前端显示进度。
- 每个	SP 存为一条 `sp_definition` 记录。
- 增量拉取：记录 `last_sync_at`，Git 用 `git pull` + diff，DB 用修改时间过滤。
- 拉取后 `parse_status = pending`。

#### 10.3.3 SP 自动匹配作业（F-26）

匹配规则（按优先级）：

1. **作业的 `sp_name` 字段已填** → 直接匹配。
2. **SP 文件名/SP 名 == 作业名** → 自动匹配。
3. **模糊匹配**：SP 名去掉前缀/后缀（如 `sp_`、`proc_`）后与作业名相似度 > 0.8 → 标记"疑似匹配"。
4. **未匹配** → 列入"未匹配"区，用户可手动绑定。

匹配结果表：

| SP 名 | 作业名 | 匹配方式 | 操作 |
|--------|--------|----------|------|
| etl_user_dmt_daily | etl_user_dmt_daily | 自动 | ✓ |
| sp_order_calc | order_calculate | 疑似(0.85) | 确认/取消 |
| proc_inventory_sync | （无） | 未匹配 | 手动绑定 |

#### 10.3.4 SP SQL 解析（F-27）

- 使用 `sqllineage` 解析 `sp_definition.sp_text`。
- 存储过程通常含多条 SQL（INSERT INTO ... SELECT、UPDATE、MERGE 等），逐条解析后合并。
- 提取：
  - `source_tables`：SP 中所有被读取的表（FROM/JOIN）。
  - `target_tables`：SP 中所有被写入的表（INSERT INTO/UPDATE/DELETE/MERGE）。
  - `column_lineage`：列级血缘（源字段→目标字段）。
- 解析结果存入 `sp_parse_result`。
- 解析失败的 SP：`parse_status = failed`，记录错误，不阻断其他 SP。

```python
from sqllineage.runner import LineageRunner

def parse_sp(sp_text, dialect="mysql"):
    """
    解析存储过程文本，返回源表/目标表/列血缘
    dialect: mysql / tsql / ansi（GoldenDB用mysql，SQL Server用tsql）
    """
    r = LineageRunner(sp_text, dialect=dialect)
    return {
        "source_tables": [t.raw for t in r.source_tables()],
        "target_tables": [t.raw for t in r.target_tables()],
        "column_lineage": r.get_column_lineage()
    }
```

#### 10.3.5 血缘比对（F-28）

对每个已匹配且解析成功的作业，比对 Excel 血缘与 SP 血缘：

| 比对项 | Excel 血缘 | SP 血缘 | 差异类型 |
|--------|-----------|---------|----------|
| 源表 | {A, B} | {A, B, C} | source_missing（Excel 漏登 C） |
| 源表 | {A, B, D} | {A, B} | source_extra（Excel 多登 D） |
| 目标表 | {X} | {X, Y} | target_missing（Excel 漏登 Y） |
| 目标表 | {X, Z} | {X} | target_extra（Excel 多登 Z） |
| 字段映射 | user_id→user_id | user_id→uid | mismatch（字段名不一致） |

差异存入 `lineage_diff`，`status = pending`。

#### 10.3.6 修订建议与采纳（F-29）

差异报告界面：

```
作业: etl_user_dmt_daily  (SP: etl_user_dmt_daily.sql)
┌──────────────────────────────────────────────────────────────┐
│ 类型         │ Excel 登记    │ SP 解析       │ 建议   │ 操作  │
├──────────────────────────────────────────────────────────────┤
│ 源表遗漏     │ —             │ dbo.t_ods_log │ 补充   │ ☑采纳 │
│ 源表多余     │ dbo.t_ods_tmp │ —             │ 删除   │ ☑采纳 │
│ 目标表遗漏   │ —             │ dbo.t_dmt_idx │ 补充   │ ☑采纳 │
│ 字段不一致   │ user_id→uid   │ user_id→user_id│ 更新  │ ☐采纳 │
└──────────────────────────────────────────────────────────────┘
[全选] [批量采纳选中] [全部采纳] [导出报告]
```

- 用户勾选后点"采纳"，后端执行：
  - `source_missing` → 向 `job_source` 插入遗漏表。
  - `source_extra` → 从 `job_source` 删除多余表。
  - `target_missing/target_extra` → 同理操作 `job_target`。
  - `mismatch` → 更新 `field_mapping`。
  - 同步更新 `job_dependency`（重新解析受影响作业的依赖边）。
  - `lineage_diff.status = accepted`。
- 拒绝的差异：`status = rejected`，不再提示。
- 采纳后血缘图实时刷新，节点角标变为 ✓。

### 10.4 SP 校验状态总览

仪表盘新增"SP 校验概览"卡片：

| 指标 | 值 |
|------|----|
| 已关联 SP 的作业 | 1200 / 1500 |
| 解析成功 | 1180 |
| 解析失败 | 20 |
| 存在差异 | 156 |
| 已采纳修订 | 132 |
| 待处理差异 | 24 |

### 10.5 增量刷新（F-30）

- SP 来源变更后，用户可点击"重新拉取并比对"。
- 系统执行增量：只解析有变更的 SP（Git diff 或 DB 修改时间）。
- 对已采纳的差异，若 SP 再次变更产生新差异，重新标记为 pending。

---

## 11. UI / UX 关键要点

### 11.1 整体风格

- 企业级、专业。主色深蓝 #1A5FAB。
- 顶部导航：Logo + 工作空间切换 + 菜单 + 用户头像。
- 左侧次级导航 + 主内容区。

### 11.2 信息架构

```
┌────────────────────────────────────────────────────────────┐
│ 顶部栏: Logo | [工作空间切换▼] | 血缘 | SP校验 | 管理 | 👤 │
├────────┬───────────────────────────────────────────────────┤
│ 左侧栏 │              主内容区                             │
│ - 搜索 │   (关系图 / SP校验向导 / 列表 / 表单)            │
│ - 筛选 │                                                   │
│ - 图例 │                                                   │
│ - SP状态│                                                  │
└────────┴───────────────────────────────────────────────────┘
```

### 11.3 关系图 UX 要点

1. 首屏即价值：立即展示全局图。
2. 渐进披露：节点默认只显示作业名。
3. 焦点+上下文：选中时相关高亮、无关淡化。
4. **SP 校验角标**：节点右上角 ✓/⚠/○ 标识校验状态。
5. 边用贝塞尔曲线，标签防重叠。
6. 图例常驻左下角；节点 > 500 时显示小地图。
7. 加载态：骨架屏 + 进度条。

### 11.4 SP 校验向导 UX（新增）

1. 三步向导：关联来源 → 匹配作业 → 比对采纳，顶部进度条。
2. 关联来源页：表单填写 Git/DB 配置，"测试连接"按钮即时验证。
3. 匹配页：左右对照表，疑似匹配高亮，支持一键确认全部疑似。
4. 比对页：差异报告表格，支持筛选（按差异类型/作业名），批量勾选采纳。
5. 采纳后 Toast 提示"已采纳 N 项修订，血缘图已更新"。

### 11.5 工作空间 UX（新增）

- 顶部工作空间下拉：显示空间名 + 角色，点击切换。
- 工作空间管理页：成员列表、邀请按钮、角色下拉。
- 创建工作空间：弹窗输入名称、描述、数据库模式。

### 11.6 反馈规范

| 场景 | 反馈 |
|------|------|
| 导入成功 | 绿色 Toast + 跳转关系图 |
| SP 解析进度 | 进度条 + 百分比 + 当前 SP 名 |
| 差异采纳成功 | Toast + 图刷新 |
| 危险操作 | 二次确认 |
| 环路告警 | 红色告警条 |
| 无权限 | 403 页面 + 返回按钮 |

---

## 12. 非功能性需求

| 类别 | 要求 |
|------|------|
| 可用性 | Docker 容器化，团队共享访问 |
| 可靠性 | 异常崩溃不丢数据（事务）；容器自动重启 |
| 性能 | 见 §8 |
| 安全性 | 内网部署；JWT 认证；连接串加密；工作空间隔离；无外部网络请求 |
| 多用户 | ≥ 20 并发；Uvicorn 多 worker |
| 可维护性 | 前后端分离；核心算法单测覆盖率 ≥ 80% |
| 可移植性 | Docker 镜像，任意支持 Docker 的内网主机 |
| 国际化 | 本期中文，文案集中管理 |
| 日志 | 容器内文件日志 + stdout，rolling 7 天 |
| 备份 | SQLite 卷可备份；外部库自行备份 |

---

## 13. 里程碑与验收标准

### 13.1 里程碑

| 里程碑 | 内容 | 周期 |
|--------|------|------|
| M1 | 架构搭建 + 用户/工作空间 + Excel 导入 + SQLite | 2 周 |
| M2 | 血缘解析 + 关系图渲染 + 节点交互（含 SP 角标） | 2 周 |
| M3 | 影响分析 + 溯源 + 环路检测 + 作业管理 | 1 周 |
| M4 | **SP 来源关联 + 拉取 + 匹配** | 1 周 |
| M5 | **SP SQL 解析 + 血缘比对 + 修订采纳** | 2 周 |
| M6 | SQL Server / GoldenDB 适配 + 数据库切换 | 1 周 |
| M7 | **Docker 化打包 + 部署验证 + 多用户并发测试** | 1 周 |
| M8 | 测试 + 文档 + 交付 | 1 周 |

### 13.2 验收标准

| 编号 | 验收项 | 标准 |
|------|--------|------|
| A-01 | Excel 导入 | 5000 行 ≤ 8 秒，校验报告准确 |
| A-02 | 列映射 | 交互式指定列含义，模板可复用 |
| A-03 | 血缘图 | 2000 节点首屏 ≤ 5 秒，点击 ≤ 200ms |
| A-04 | 节点详情 | 双击展示源表/目标表/字段映射/上下游/SP校验 |
| A-05 | 影响分析 | 高亮全部下游，准确率 100% |
| A-06 | 溯源分析 | 高亮全部上游，准确率 100% |
| A-07 | 环路检测 | 检出所有环路并标红 |
| A-08 | 数据库切换 | 三模式可切换，数据一致 |
| **A-09** | **Docker 部署** | **docker compose up 后 5 分钟内可访问** |
| **A-10** | **用户/工作空间** | **多用户登录、工作空间隔离、权限控制正确** |
| **A-11** | **SP 关联拉取** | **Git/DB 两种来源均可拉取 SP，500 文件 ≤ 30 秒** |
| **A-12** | **SP 解析比对** | **500 SP 解析 ≤ 60 秒，差异报告准确率 ≥ 95%** |
| **A-13** | **SP 修订采纳** | **采纳后血缘图正确更新，角标状态正确** |
| A-14 | 并发 | 20 用户并发操作响应正常 |

---

## 14. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|------|------|------|------|
| G6 万级节点性能下降 | 中 | 高 | 分批渲染 + 聚合视图 + Web Worker |
| sqllineage 解析复杂 SP 失败 | 中 | 中 | 失败标记不阻断；支持手动指定 SP 血缘 |
| Git 仓库在内网不可达 | 中 | 中 | 支持数据库直连方式拉取 SP 作为备选 |
| SP 名与作业名差异大导致匹配率低 | 中 | 中 | 模糊匹配 + 手动绑定；积累匹配词典 |
| SQLite 高并发写性能瓶颈 | 中 | 中 | 建议多用户场景切换 SQL Server/GoldenDB |
| GoldenDB 兼容性差异 | 中 | 中 | 复用 MySQL Dialect 降级处理 |
| Docker 环境内网无外网 | 低 | 低 | 离线导出镜像 tar 包，内网 docker load |
| 存储过程含动态 SQL 难解析 | 高 | 中 | 标记为"动态SQL，需人工确认"；不做强行解析 |

---

## 15. 现有工具调研与差异分析

### 15.1 调研结果

经互联网检索，现有血缘分析相关工具如下：

| 工具 | 类型 | 能力 | 是否适用本场景 | 原因 |
|------|------|------|----------------|------|
| **sqllineage** | 开源(Python) | 解析单条/多条 SQL，提取表级与列级血缘，支持多方言 | **部分适用，作为 SP 解析引擎集成** | 缺少批量作业管理、Excel 导入、可视化关系图、工作空间；本工具调用其解析能力 |
| **OpenLineage** | 开源标准 | 数据血缘追踪的标准与采集框架，面向作业运行态 | 不适用 | 面向运行时事件采集，非元数据分析；需调度系统接入 |
| **Apache Atlas** | 开源 | 元数据治理平台，含血缘 | 不适用 | 重量级，需 Hadoop 生态；部署复杂；非专项工具 |
| **DataHub** | 开源 | LinkedIn 元数据平台，含血缘 | 不适用 | 重量级，面向全企业元数据；部署复杂 |
| **data-lineage-parent** | 开源(Java) | 基于 Druid SqlParser 解析 SQL 血缘，Neo4j 存储 | 不适用 | Java 技术栈，需 Neo4j；与本期 Python 栈不符 |
| **DataLineageResearch** | 开源 | 报表 SQL 列级血缘解析 | 不适用 | 面向报表场景，功能有限 |
| **普元/商用血缘工具** | 商用 | 表元数据同步、血缘展示 | 不适用 | 商业付费、重型平台 |

### 15.2 差异分析（本工具的独有价值）

现有工具普遍存在以下缺口，本工具正是填补这些缺口：

| 能力 | sqllineage | OpenLineage | Atlas/DataHub | **本工具** |
|------|-----------|-------------|---------------|-----------|
| Excel 批量作业导入 | ✗ | ✗ | ✗ | **✓** |
| 交互式列映射 | ✗ | ✗ | ✗ | **✓** |
| 上千作业可视化关系图 | ✗ | ✗ | 部分（重型） | **✓（G6 轻量）** |
| 节点点击展开详情 | ✗ | ✗ | 部分 | **✓** |
| 影响分析/溯源 | ✗ | 部分 | 部分 | **✓** |
| 存储过程自动比对修订 | ✗ | ✗ | ✗ | **✓（核心创新）** |
| 多用户工作空间隔离 | ✗ | ✗ | ✓（重型） | **✓（轻量）** |
| 内网 Docker 一键部署 | ✓（库） | ✗ | ✗（复杂） | **✓** |
| 支持 SQL Server/GoldenDB | 部分 | ✗ | 部分 | **✓** |

**结论**：本工具不重复造 SQL 解析轮子（复用 sqllineage），而是在其之上构建"批量作业管理 + Excel 导入 + 可视化 + SP 自动比对修订 + 多用户协作"的产品层，这是市场空缺。

---

## 附录 A：Excel 模板规范

### A.1 推荐列

| 列名 | 必填 | 示例 |
|------|------|------|
| 作业名称 | 是 | `etl_user_dmt_daily` |
| 作业类型 | 否 | ETL / PROCEDURE / SCRIPT |
| 源表 | 是 | `dbo.t_ods_user,dbo.t_ods_order`（逗号分隔） |
| 目标表 | 是 | `dbo.t_dmt_user_summary` |
| 源字段 | 否 | `user_id,order_id` |
| 目标字段 | 否 | `user_id,order_id` |
| **存储过程名** | 否 | `etl_user_dmt_daily`（用于 SP 匹配） |
| 调度频率 | 否 | daily |
| 负责人 | 否 | 张三 |
| 描述 | 否 | |

### A.2 多源多目标

- 单元格内逗号分隔多个表。
- 字段映射可单独 Sheet。

---

## 附录 B：血缘解析算法

### B.1 作业级依赖（Excel）

```python
import networkx as nx

def build_lineage(jobs, job_sources, job_targets):
    g = nx.DiGraph()
    for j in jobs:
        g.add_node(j.id)

    table_to_producers = {}
    for job_id, targets in job_targets.items():
        for t in targets:
            table_to_producers.setdefault(t, []).append(job_id)

    for job_id, sources in job_sources.items():
        for t in sources:
            for producer in table_to_producers.get(t, []):
                if producer != job_id:
                    g.add_edge(producer, job_id, via_table=t)
    return g
```

### B.2 环路检测 / 影响分析 / 溯源

```python
cycles = list(nx.simple_cycles(g))
downstream = nx.descendants(g, source_job_id)
upstream = nx.ancestors(g, source_job_id)
```

---

## 附录 C：存储过程解析比对算法

### C.1 SP 拉取（Git）

```python
import git, os, glob

def pull_sp_from_git(repo_url, branch, token, sp_dir, local_path):
    """克隆/拉取 Git 仓库，返回 SP 文件列表"""
    if os.path.exists(local_path):
        repo = git.Repo(local_path)
        repo.remotes.origin.pull()
    else:
        repo_url_auth = repo_url.replace("https://", f"https://{token}@")
        repo = git.Repo.clone_from(repo_url_auth, local_path, branch=branch)
    
    sp_files = glob.glob(os.path.join(local_path, sp_dir, "*.sql"))
    result = []
    for f in sp_files:
        sp_name = os.path.splitext(os.path.basename(f))[0]
        with open(f, encoding="utf-8") as fh:
            sp_text = fh.read()
        result.append({"sp_name": sp_name, "sp_text": sp_text, "file_path": f})
    return result
```

### C.2 SP 拉取（数据库）

```python
def pull_sp_from_db(engine, schema="dbo"):
    """从数据库查询存储过程定义"""
    if engine.dialect.name == "mssql":
        sql = f"""
            SELECT o.name AS sp_name, m.definition AS sp_text
            FROM sys.sql_modules m
            JOIN sys.objects o ON m.object_id = o.object_id
            WHERE o.type = 'P' AND SCHEMA_NAME(o.schema_id) = '{schema}'
        """
    else:  # goldendb/mysql
        sql = f"""
            SELECT routine_name AS sp_name, routine_definition AS sp_text
            FROM information_schema.routines
            WHERE routine_type = 'PROCEDURE' AND routine_schema = '{schema}'
        """
    with engine.connect() as conn:
        return conn.execute(sql).fetchall()
```

### C.3 SP 匹配作业

```python
from difflib import SequenceMatcher

def match_sp_to_job(sp_name, jobs, threshold=0.8):
    """SP 名匹配作业名"""
    # 1. 精确匹配
    for j in jobs:
        if j.sp_name == sp_name or j.job_name == sp_name:
            return (j, "auto_matched")
    # 2. 去前缀模糊匹配
    cleaned = sp_name.lower()
    for prefix in ("sp_", "proc_", "p_"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    for j in jobs:
        ratio = SequenceMatcher(None, cleaned, j.job_name.lower()).ratio()
        if ratio >= threshold:
            return (j, "fuzzy_matched")
    return (None, "unmatched")
```

### C.4 SP SQL 解析

```python
from sqllineage.runner import LineageRunner

def parse_sp(sp_text, dialect="mysql"):
    """解析 SP 文本，返回表级与列级血缘"""
    try:
        r = LineageRunner(sp_text, dialect=dialect)
        return {
            "source_tables": sorted({t.raw for t in r.source_tables()}),
            "target_tables": sorted({t.raw for t in r.target_tables()}),
            "column_lineage": r.get_column_lineage(),
            "status": "success"
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}
```

### C.5 血缘比对

```python
def reconcile_lineage(excel_sources, excel_targets, sp_sources, sp_targets):
    """
    比对 Excel 血缘与 SP 解析血缘，返回差异列表
    """
    diffs = []
    es, et = set(excel_sources), set(excel_targets)
    ss, st = set(sp_sources), set(sp_targets)

    for t in ss - es:
        diffs.append({"diff_type": "source_missing", "excel_value": None, "sp_value": t, "action": "add"})
    for t in es - ss:
        diffs.append({"diff_type": "source_extra", "excel_value": t, "sp_value": None, "action": "remove"})
    for t in st - et:
        diffs.append({"diff_type": "target_missing", "excel_value": None, "sp_value": t, "action": "add"})
    for t in et - st:
        diffs.append({"diff_type": "target_extra", "excel_value": t, "sp_value": None, "action": "remove"})
    return diffs
```

### C.6 采纳修订

```python
def apply_patch(workspace_id, job_id, diffs, session):
    """根据差异列表更新血缘"""
    for d in diffs:
        if d["status"] != "accepted":
            continue
        if d["diff_type"] in ("source_missing", "source_extra"):
            table = d["sp_value"] or d["excel_value"]
            if d["action"] == "add":
                add_job_source(workspace_id, job_id, table, source="sp", session)
            else:
                remove_job_source(workspace_id, job_id, table, session)
        elif d["diff_type"] in ("target_missing", "target_extra"):
            table = d["sp_value"] or d["excel_value"]
            if d["action"] == "add":
                add_job_target(workspace_id, job_id, table, source="sp", session)
            else:
                remove_job_target(workspace_id, job_id, table, session)
    # 重新解析受影响的依赖
    rebuild_dependencies(workspace_id, job_id, session)
```

---

## 附录 D：交付物清单

| 编号 | 交付物 | 格式 |
|------|--------|------|
| D-01 | Docker 镜像 | tar（docker load 导入） |
| D-02 | docker-compose.yml | yml |
| D-03 | 源代码仓库 | Git |
| D-04 | 用户手册 | PDF |
| D-05 | 部署运维手册 | PDF |
| D-06 | Excel 模板 | xlsx |
| D-07 | 数据库建表脚本 | sql（三种数据库） |
| D-08 | 单元测试报告 | html |
| D-09 | 性能测试报告 | pdf |
| D-10 | SP 校验功能说明 | pdf |

---

**—— 文档结束 ——**
