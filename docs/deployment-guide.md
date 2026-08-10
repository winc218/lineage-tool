# 部署运维手册

## 1. 部署架构

```
┌──────────────────────────────────────────────┐
│              Docker 主机 (内网)               │
│  ┌────────────────────────────────────────┐  │
│  │     lineage-tool 容器 (v2.0)           │  │
│  │  ┌──────────┐  ┌───────────────────┐  │  │
│  │  │ Uvicorn  │  │  前端静态资源      │  │  │
│  │  │ :8080    │  │  (Vue3+G6 dist)   │  │  │
│  │  └────┬─────┘  └───────────────────┘  │  │
│  │       │                                │  │
│  │  ┌────▼─────────────────────────────┐ │  │
│  │  │     SQLite / SQL Server / GoldenDB │ │  │
│  │  └──────────────────────────────────┘ │  │
│  └────────────────────────────────────────┘  │
│         │ Volume: /app/data (持久化)         │
└──────────────────────────────────────────────┘
        │ :8080
        ▼
   团队浏览器 http://<内网IP>:8080
```

## 2. 首次部署

### 2.1 前置条件

- Docker 20.10+ 及 Docker Compose v2
- 内网主机，开放 8080 端口

### 2.2 在有网环境构建镜像

```bash
cd TaskManager
docker build -t lineage-tool:v2.0 .
# 导出为 tar 包供内网传输
docker save lineage-tool:v2.0 -o lineage-tool-v2.0.tar
```

### 2.3 内网导入镜像

```bash
docker load -i lineage-tool-v2.0.tar
```

### 2.4 配置并启动

1. 将 `docker-compose.yml` 拷贝到部署目录
2. **修改环境变量**（关键！）：

```yaml
environment:
  - JWT_SECRET=<32位以上随机字符串>        # 必改
  - CONFIG_ENCRYPT_KEY=<Fernet密钥>       # 必改，用于加密SP来源配置
  - ADMIN_PASSWORD=<强密码>               # 必改
```

生成密钥：
```bash
# JWT_SECRET
openssl rand -hex 32

# CONFIG_ENCRYPT_KEY (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

3. 启动：
```bash
docker compose up -d
```

4. 验证：
```bash
curl http://localhost:8080/api/health
# 期望返回: {"status":"ok"}

docker compose ps
# 状态应为 healthy
```

5. 浏览器访问 `http://<服务器IP>:8080`，用 admin 账号登录。

## 3. 升级流程

```bash
# 1. 拉取/导入新镜像
docker load -i lineage-tool-v2.1.tar

# 2. 更新 docker-compose.yml 中的 image tag（如需）
# 3. 滚动重启（数据卷保留）
docker compose up -d

# 4. 验证
curl http://localhost:8080/api/health
```

> 后端启动时自动执行 `Base.metadata.create_all()`，新表自动创建。
> 如有 schema 变更（加列/改类型），需手动执行迁移 SQL。

## 4. 数据备份与恢复

### 4.1 SQLite 模式（默认）

```bash
# 备份
docker run --rm -v lineage-data:/data -v $(pwd):/backup alpine \
    cp /data/lineage.db /backup/lineage-$(date +%Y%m%d).db

# 恢复
docker run --rm -v lineage-data:/data -v $(pwd):/backup alpine \
    cp /backup/lineage-20260808.db /data/lineage.db
docker compose restart
```

### 4.2 SQL Server / GoldenDB 模式

按数据库自身备份方案执行，容器无状态。

## 5. 日志查看

```bash
# 实时日志
docker compose logs -f

# 容器内日志文件（rolling 7 天）
docker exec lineage-tool cat /app/logs/lineage.log

# 最近 100 行
docker compose logs --tail 100
```

## 6. 切换数据库

### 6.1 切换到 SQL Server

1. 确保 SQL Server 2019 可达
2. 修改 `docker-compose.yml`：

```yaml
environment:
  - DB_MODE=sqlserver
  - DB_CONN=mssql+pymssql://user:pass@db-host:1433/lineage
```

3. 重启：`docker compose up -d`

### 6.2 切换到 GoldenDB

```yaml
environment:
  - DB_MODE=goldendb
  - DB_CONN=mysql+pymysql://user:pass@db-host:3306/lineage
```

## 7. 性能调优

| 场景 | 调整 |
|------|------|
| 并发用户 > 20 | 增加 Uvicorn workers（Dockerfile CMD `--workers 8`） |
| 作业数 > 5000 | 切换到 SQL Server/GoldenDB，避免 SQLite 写锁瓶颈 |
| SP 解析大批量 | 已用后台任务，无需额外调优 |
| 图渲染慢 | 前端 G6 已支持分批渲染与聚合视图 |

## 8. 故障排查

| 现象 | 排查 |
|------|------|
| 容器启动失败 | `docker compose logs` 查看错误；检查 JWT_SECRET 是否设置 |
| 401 未授权 | 检查 JWT_SECRET 是否与签发时一致；清除浏览器 localStorage |
| 数据库连接失败 | 检查 DB_CONN 连接串；确认网络可达；pymssql 不需 ODBC |
| SP Git 拉取失败 | 检查 Git 仓库地址与 Token；容器需能访问 Git 服务器 |
| 健康检查不通过 | 等待 start_period（10s）；检查 `curl localhost:8080/api/health` |
| 磁盘空间不足 | 清理旧日志 `/app/logs`；清理 Git 缓存 `/tmp/lineage_git_*` |

## 9. 安全清单

- [ ] JWT_SECRET 已改为随机 32+ 字符
- [ ] CONFIG_ENCRYPT_KEY 已设置（Fernet 密钥）
- [ ] ADMIN_PASSWORD 已改为强密码
- [ ] 8080 端口仅内网可访问（不暴露公网）
- [ ] Docker 容器以非 root 运行（TODO：后续加 USER 指令）
- [ ] 数据卷定期备份
