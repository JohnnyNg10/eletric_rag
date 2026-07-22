#!/bin/bash
set -e

echo "=========================================="
echo "  Frontend Docker 镜像构建脚本"
echo "=========================================="

# 检查是否在 frontend 目录
if [ ! -f "package.json" ] || [ ! -d "src" ]; then
    echo "❌ 错误: 请在 frontend 目录运行此脚本"
    exit 1
fi

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装"
    exit 1
fi

echo "📋 检查依赖文件..."
if [ ! -f "package-lock.json" ]; then
    echo "⚠️  警告: package-lock.json 不存在"
    if command -v npm &> /dev/null; then
        echo "   尝试生成 package-lock.json..."
        npm install
    else
        echo "❌ npm 未安装"
        exit 1
    fi
fi

echo "✅ 依赖文件检查完成"
echo ""

# 检查 nginx.conf
if [ ! -f "nginx.conf" ]; then
    echo "❌ 错误: nginx.conf 不存在"
    echo "   请确保 nginx.conf 在当前目录"
    exit 1
fi

echo "✅ Nginx 配置文件存在"
echo ""

# 构建镜像
echo "🔨 开始构建 Docker 镜像..."
echo "   镜像名称: electric-rag-frontend:latest"
echo "   Node 版本: 18"
echo "   预计时间: 3-5 分钟"
echo ""

docker build -t electric-rag-frontend:latest .

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ 构建成功！"
    echo "=========================================="
    echo ""
    echo "📦 镜像信息:"
    docker images electric-rag-frontend:latest
    echo ""
    echo "🚀 测试运行:"
    echo "   docker run -d --name frontend-test -p 5173:80 electric-rag-frontend:latest"
    echo "   访问: http://localhost:5173"
    echo ""
    echo "📝 查看日志:"
    echo "   docker logs -f frontend-test"
    echo ""
    echo "🛑 停止容器:"
    echo "   docker stop frontend-test && docker rm frontend-test"
    echo ""
else
    echo ""
    echo "❌ 构建失败"
    exit 1
fi
