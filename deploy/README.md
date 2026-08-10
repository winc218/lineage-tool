# 部署指南

> 离线一体化包，**无需联网，无需安装任何第三方依赖或运行时环境**，拷贝即用。
>
> 支持 Windows 和 Linux 双平台。

---

## 快速开始（2 步）

### 1. 拷贝离线包

将整个 `lineage-tool-offline/` 目录拷贝到目标机器的任意位置。

### 2. 运行

**Windows：**
```
双击 start.bat          # 前台运行（关闭窗口即停止）
双击 start-background.bat  # 后台静默运行
双击 stop.bat           # 停止服务
```

**Linux（空白虚机，无 Python）：**
```bash
bash setup.sh           # 首次运行一次，自动部署 Python 和依赖
bash start.sh           # 前台运行（Ctrl+C 停止）
bash start-daemon.sh    # 后台运行
bash stop.sh            # 停止服务
```

**Linux（已有 Python 3.11+）：**
```bash
# 安装依赖
python3 -m venv venv
source venv/bin/activate
pip install --no-index --find-links packages/ -r requirements.txt
# 启动
bash start.sh
```

### 3. 访问

浏览器打开 `http://机器IP:8080`，默认账号 `admin` / `admin123`

---

## 离线包目录结构

```
lineage-tool-offline/
├── app/                       应用代码
│   ├── api/                   API 路由
│   ├── core/                  核心模块（认证、配置、数据库）
│   ├── models/                数据模型
│   ├── services/              业务逻辑
│   └── static/                前端预构建产物
├── packages/                  Python 离线 wheel 包（Linux 安装用）
├── runtime/
│   ├── windows-python/        Windows 嵌入式 Python 3.11 + pip 依赖
│   ├── linux-python.tar.gz    Linux 便携 Python（setup.sh 自动解压）
│   └── git/                   Windows MinGit（可选）
├── data/                      SQLite 数据库文件
├── logs/                      日志
├── .env                       配置文件
├── setup.sh                   Linux 安装脚本（仅首次）
├── start.sh / start.bat       启动脚本
├── start-daemon.sh            Linux 后台启动
├── stop.sh / stop.bat         停止脚本
└── requirements.txt           依赖清单
```

---

## 配置说明

编辑 `.env` 文件：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `DB_MODE` | 数据库模式 | `sqlite` |
| `JWT_SECRET` | JWT 签名密钥（生产务必修改） | `lineage-offline-secret-change-me` |
| `ADMIN_USERNAME` | 管理员用户名 | `admin` |
| `ADMIN_PASSWORD` | 管理员初始密码 | `admin123` |
| `DATA_DIR` | 数据目录 | `./data` |
| `LOG_DIR` | 日志目录 | `./logs` |

---

## 数据备份

SQLite 模式下，定期备份 `data/lineage.db` 文件即可。

## 更新应用

1. 停止服务
2. 用新版本的 `app/` 和 `app/static/` 目录替换旧目录
3. 如果 `requirements.txt` 有变更，重新运行 `setup.sh`（仅 `packages/` 中的包）
4. 重新启动

---

## 权限模型

| 角色 | 工作空间 | 用户管理 | 修改密码 |
|------|---------|---------|---------|
| 管理员 (GLOBAL_ADMIN) | 增删改查 + 成员管理 | 增删改查 + 重置密码 | 可 |
| 普通用户 (USER) | 只读（仅可见被分配的） | 无 | 可 |
