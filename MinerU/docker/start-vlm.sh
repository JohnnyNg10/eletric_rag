#!/bin/bash
set -e

echo "=========================================="
echo "  MinerU VLM 服务启动"
echo "=========================================="

# 检查模型是否已下载
MODEL_FLAG="/root/.cache/mineru_models_downloaded"

if [ ! -f "$MODEL_FLAG" ]; then
    echo "首次启动，开始下载 VLM 模型（约 15GB，可能需要 30-60 分钟）..."
    uv run mineru-models-download
    touch "$MODEL_FLAG"
    echo "模型下载完成"
else
    echo "模型已存在，跳过下载"
fi

echo "启动 MinerU API 服务 (port 8001)..."
exec uv run mineru-api --host 0.0.0.0 --port 8001
