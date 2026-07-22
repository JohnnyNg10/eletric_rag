FROM python:3.13-slim

# 安装系统依赖（使用 --fix-missing 应对网络不稳定）
RUN apt-get update && apt-get install -y --fix-missing \
    gcc g++ make \
    libgomp1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/* || true

WORKDIR /app

# 复制依赖文件
COPY pyproject.toml uv.lock* ./

# 安装 uv 并安装依赖
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

# 复制应用代码
COPY app/ ./app/

# 复制 AI 模型（embedding + rerank，约 3.3GB）
# 注意：需要先下载模型到 backend/models/ 目录
COPY models/ ./models/

# 创建日志目录
RUN mkdir -p /app/logs

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
