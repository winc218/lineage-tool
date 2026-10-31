#!/bin/bash
# ================================================================
# lineage-tool 增量升级脚本
# 用于在已部署的环境中应用增量更新
# 用法: ./upgrade.sh [--full] [--dry-run]
#   --full     : 完整升级（重新部署全部文件）
#   --dry-run  : 仅检查变更，不实际执行
# ================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="${APP_DIR:-/app}"
BACKUP_DIR="${APP_DIR}/backups/$(date +%Y%m%d_%H%M%S)"
DRY_RUN=false
FULL_UPGRADE=false

for arg in "$@"; do
  case $arg in
    --full) FULL_UPGRADE=true ;;
    --dry-run) DRY_RUN=true ;;
  esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }
dry() { if [ "$DRY_RUN" = true ]; then log "[DRY-RUN] $1"; else eval "$1"; fi; }

log "========================================="
log "lineage-tool 增量升级开始"
log "========================================="

# 1. 备份当前版本
log "步骤 1/6: 备份当前版本..."
dry "mkdir -p ${BACKUP_DIR}"
if [ -d "${APP_DIR}/backend" ]; then
  dry "cp -r ${APP_DIR}/backend ${BACKUP_DIR}/backend"
fi
if [ -d "${APP_DIR}/frontend/dist" ]; then
  dry "cp -r ${APP_DIR}/frontend/dist ${BACKUP_DIR}/frontend-dist"
fi

# 2. 检查 Python 依赖变更
log "步骤 2/6: 检查 Python 依赖变更..."
if [ -f "${SCRIPT_DIR}/requirements.diff" ]; then
  log "  检测到新增依赖，正在安装..."
  dry "pip install --no-cache-dir -r ${SCRIPT_DIR}/requirements.diff"
fi
if [ "$FULL_UPGRADE" = true ] && [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
  log "  完整模式：重新安装全部依赖..."
  dry "pip install --no-cache-dir -r ${SCRIPT_DIR}/requirements.txt"
fi

# 3. 更新后端代码
log "步骤 3/6: 更新后端代码..."
if [ -d "${SCRIPT_DIR}/backend" ]; then
  dry "cp -r ${SCRIPT_DIR}/backend/app ${APP_DIR}/backend/"
fi

# 4. 更新前端静态资源
log "步骤 4/6: 更新前端静态资源..."
if [ -d "${SCRIPT_DIR}/frontend-dist" ]; then
  dry "rm -rf ${APP_DIR}/frontend/dist/*"
  dry "cp -r ${SCRIPT_DIR}/frontend-dist/* ${APP_DIR}/frontend/dist/"
  # 更新到 backend 的 static 目录
  if [ -d "${APP_DIR}/backend/app/static" ]; then
    dry "rm -rf ${APP_DIR}/backend/app/static/*"
    dry "cp -r ${SCRIPT_DIR}/frontend-dist/* ${APP_DIR}/backend/app/static/"
  fi
fi

# 5. 数据库迁移
log "步骤 5/6: 执行数据库迁移..."
if [ -f "${SCRIPT_DIR}/migrate.py" ]; then
  dry "python ${SCRIPT_DIR}/migrate.py"
fi

# 6. 重启服务
log "步骤 6/6: 重启服务..."
if command -v supervisorctl &> /dev/null; then
  dry "supervisorctl restart lineage-tool"
elif [ -f "${APP_DIR}/run.py" ]; then
  # 尝试使用 docker-compose 重启
  if command -v docker-compose &> /dev/null; then
    dry "docker-compose restart lineage-tool"
  else
    log "  请手动重启服务: cd ${APP_DIR} && uvicorn run:app --host 0.0.0.0 --port 8080 --workers 4"
  fi
fi

log "========================================="
log "升级完成！备份位于: ${BACKUP_DIR}"
log "========================================="

# 清理超过 5 个的旧备份
BACKUP_COUNT=$(ls -d ${APP_DIR}/backups/20* 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 5 ]; then
  log "清理旧备份..."
  ls -dt ${APP_DIR}/backups/20* | tail -n +6 | xargs rm -rf
fi
