FROM python:3.13-slim

# 安装系统依赖（使用 --fix-missing 应对网络不稳定）
RUN apt-get update && apt-get install -y --fix-missing \
    gcc g++ make \
    libgomp1 \
    libglib2.0-0 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* || true

WORKDIR /app

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY mineru/ ./mineru/

# 安装 uv 并安装依赖（使用 pipeline 后端，包含 OCR 和模型）
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

# 创建模型和输出目录
RUN mkdir -p /app/models /app/output

# 暴露端口
EXPOSE 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# 启动 MinerU API 服务
CMD ["uv", "run", "mineru-api", "--host", "0.0.0.0", "--port", "8001"]
