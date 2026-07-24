#!/bin/bash
set -e

echo "=========================================="
echo "  MinerU Docker 镜像构建脚本"
echo "=========================================="

# 检查是否在 MinerU 目录
if [ ! -f "pyproject.toml" ] || [ ! -d "mineru" ]; then
    echo "❌ 错误: 请在 MinerU 项目根目录运行此脚本"
    exit 1
fi

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装"
    exit 1
fi

echo "📋 检查依赖文件..."
if [ ! -f "uv.lock" ]; then
    echo "⚠️  警告: uv.lock 不存在，尝试生成..."
    if command -v uv &> /dev/null; then
        uv lock
    else
        echo "❌ uv 未安装，无法生成 uv.lock"
        exit 1
    fi
fi

echo "✅ 依赖文件检查完成"
echo ""

# 构建镜像
echo "🔨 开始构建 Docker 镜像..."
echo "   镜像名称: electric-rag-mineru:latest"
echo "   Python 版本: 3.13"
echo "   预计时间: 5-10 分钟"
echo ""

docker build -t electric-rag-mineru:latest .

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ 构建成功！"
    echo "=========================================="
    echo ""
    echo "📦 镜像信息:"
    docker images electric-rag-mineru:latest
    echo ""
    echo "🚀 测试运行:"
    echo "   docker run -d --name mineru-test -p 8001:8001 electric-rag-mineru:latest"
    echo "   curl http://localhost:8001/health"
    echo ""
    echo "📝 查看日志:"
    echo "   docker logs -f mineru-test"
    echo ""
    echo "🛑 停止容器:"
    echo "   docker stop mineru-test && docker rm mineru-test"
    echo ""
else
    echo ""
    echo "❌ 构建失败"
    exit 1
fi
