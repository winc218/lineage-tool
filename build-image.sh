#!/bin/bash
# 离线镜像构建与导出脚本
# 在有网环境执行，产出 lineage-tool-v2.0.tar 供内网 docker load

set -e

IMAGE_NAME="lineage-tool"
IMAGE_TAG="v2.0"
TAR_FILE="${IMAGE_NAME}-${IMAGE_TAG}.tar"

echo "===== 1. 构建镜像 ====="
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

echo "===== 2. 导出 tar 包 ====="
docker save ${IMAGE_NAME}:${IMAGE_TAG} -o ${TAR_FILE}

echo "===== 3. 验证 ====="
docker images | grep ${IMAGE_NAME}
ls -lh ${TAR_FILE}

echo "===== 完成 ====="
echo "内网部署命令:"
echo "  docker load -i ${TAR_FILE}"
echo "  docker compose up -d"
