#!/bin/bash

echo "=========================================="
echo "  Docker 镜像构建验证"
echo "=========================================="
echo ""

# 检查所有镜像
echo "📦 检查已构建的镜像:"
echo ""

IMAGES=(
    "electric-rag-mineru:latest"
    "electric-rag-backend:latest"
    "electric-rag-frontend:latest"
)

ALL_BUILT=true

for image in "${IMAGES[@]}"; do
    if docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^${image}$"; then
        SIZE=$(docker images --format "{{.Size}}" "${image}")
        CREATED=$(docker images --format "{{.CreatedAt}}" "${image}" | cut -d' ' -f1-2)
        echo "✅ ${image}"
        echo "   Size: ${SIZE}"
        echo "   Created: ${CREATED}"
        echo ""
    else
        echo "❌ ${image} - 未找到"
        echo ""
        ALL_BUILT=false
    fi
done

if [ "$ALL_BUILT" = true ]; then
    echo "=========================================="
    echo "✅ 所有镜像构建成功！"
    echo "=========================================="
    echo ""
    echo "📊 总镜像大小:"
    docker images | grep electric-rag | awk '{sum+=$NF} END {print sum " (单位可能混合)"}'
    echo ""
    echo "🚀 下一步:"
    echo "   1. 拉取基础服务镜像（MySQL, Redis, etc.）"
    echo "   2. 导出所有镜像到 bundle/images/"
    echo "   3. 创建 docker-compose.yml 和启动脚本"
    echo "   4. 打包成 electric-rag-bundle.tar.gz"
    echo ""
else
    echo "=========================================="
    echo "⚠️  部分镜像构建失败"
    echo "=========================================="
    echo ""
    echo "请检查构建日志并重新构建失败的镜像"
    exit 1
fi
