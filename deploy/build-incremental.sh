#!/bin/bash
# ================================================================
# lineage-tool 增量发布包生成脚本
# 生成包含变更文件的增量升级包
# 用法: ./build-incremental.sh [version_tag]
# ================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION="${1:-$(date +%Y%m%d-%H%M%S)}"
BUILD_DIR="${PROJECT_DIR}/build/incremental-${VERSION}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

log "构建增量发布包: incremental-${VERSION}"

# 创建构建目录
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

# 复制 upgrade.sh
cp "${SCRIPT_DIR}/upgrade.sh" "${BUILD_DIR}/"

# 复制后端代码
log "复制后端代码..."
mkdir -p "${BUILD_DIR}/backend/app"
cp -r "${PROJECT_DIR}/backend/app/api" "${BUILD_DIR}/backend/app/"
cp -r "${PROJECT_DIR}/backend/app/core" "${BUILD_DIR}/backend/app/"
cp -r "${PROJECT_DIR}/backend/app/models" "${BUILD_DIR}/backend/app/"
cp -r "${PROJECT_DIR}/backend/app/services" "${BUILD_DIR}/backend/app/"

# 检查 Python 依赖变更
log "检查 Python 依赖..."
if [ -f "${PROJECT_DIR}/backend/requirements.txt" ]; then
  cp "${PROJECT_DIR}/backend/requirements.txt" "${BUILD_DIR}/requirements.txt"
fi

# 构建前端
log "构建前端..."
cd "${PROJECT_DIR}/frontend"
if [ -f "package.json" ]; then
  npm install --silent
  npm run build -- --outDir dist
  cp -r dist "${BUILD_DIR}/frontend-dist"
fi
cd "${PROJECT_DIR}"

# 打包
log "打包增量发布包..."
cd "${PROJECT_DIR}/build"
tar -czf "lineage-tool-incremental-${VERSION}.tar.gz" "incremental-${VERSION}"
rm -rf "incremental-${VERSION}"

log "增量发布包已生成: build/lineage-tool-incremental-${VERSION}.tar.gz"
log "部署方式:"
log "  1. 解压: tar -xzf lineage-tool-incremental-${VERSION}.tar.gz"
log "  2. 进入: cd incremental-${VERSION}"
log "  3. 执行: bash upgrade.sh"
