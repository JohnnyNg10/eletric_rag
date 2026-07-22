#!/bin/bash
set -e

echo "=========================================="
echo "  Backend Docker 镜像构建脚本"
echo "=========================================="

# 检查是否在 backend 目录
if [ ! -f "pyproject.toml" ] || [ ! -d "app" ]; then
    echo "❌ 错误: 请在 backend 目录运行此脚本"
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

# 检查模型目录
echo "📦 检查 AI 模型..."
if [ ! -d "models" ]; then
    echo "❌ 错误: models/ 目录不存在"
    echo "   请先下载模型："
    echo "   mkdir -p models && cd models"
    echo "   git clone https://huggingface.co/BAAI/bge-large-zh-v1.5"
    echo "   git clone https://huggingface.co/BAAI/bge-reranker-large"
    echo "   git clone https://huggingface.co/BAAI/bge-reranker-base"
    echo "   git clone https://huggingface.co/naver/efficient-splade-VI-BT-large-query"
    exit 1
fi

# 检查模型是否完整
REQUIRED_MODELS=("bge-large-zh-v1.5" "bge-reranker-large" "bge-reranker-base" "efficient-splade-VI-BT-large-query")
MISSING_MODELS=()

for model in "${REQUIRED_MODELS[@]}"; do
    if [ ! -d "models/$model" ]; then
        MISSING_MODELS+=("$model")
    fi
done

if [ ${#MISSING_MODELS[@]} -ne 0 ]; then
    echo "⚠️  警告: 以下模型缺失:"
    for model in "${MISSING_MODELS[@]}"; do
        echo "   - $model"
    done
    echo ""
    read -p "是否继续构建？(y/n): " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ 所有模型文件完整"
fi

echo ""

# 构建镜像
echo "🔨 开始构建 Docker 镜像..."
echo "   镜像名称: electric-rag-backend:latest"
echo "   Python 版本: 3.13"
echo "   预计时间: 10-15 分钟（包含 ~3.3GB 模型）"
echo ""

docker build -t electric-rag-backend:latest .

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ 构建成功！"
    echo "=========================================="
    echo ""
    echo "📦 镜像信息:"
    docker images electric-rag-backend:latest
    echo ""
    echo "🚀 测试运行（需要配置环境变量）:"
    echo "   docker run -d --name backend-test \\"
    echo "     -p 8000:8000 \\"
    echo "     -e MYSQL_HOST=host.docker.internal \\"
    echo "     -e REDIS_HOST=host.docker.internal \\"
    echo "     -e ARK_API_KEY=your_key \\"
    echo "     electric-rag-backend:latest"
    echo ""
    echo "📝 查看日志:"
    echo "   docker logs -f backend-test"
    echo ""
    echo "🛑 停止容器:"
    echo "   docker stop backend-test && docker rm backend-test"
    echo ""
else
    echo ""
    echo "❌ 构建失败"
    exit 1
fi
