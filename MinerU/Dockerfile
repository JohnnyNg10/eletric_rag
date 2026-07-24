FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# 安装 Python 3.13 和系统依赖
RUN apt-get update && apt-get install -y --fix-missing \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --fix-missing \
    python3.13 \
    python3.13-venv \
    python3.13-dev \
    python3-pip \
    gcc g++ make \
    libgomp1 \
    libglib2.0-0 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/* || true

# 设置 Python 3.13 为默认
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.13 1

WORKDIR /app

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY mineru/ ./mineru/

# 安装 uv 并安装 VLM 依赖（包含 torch, transformers, accelerate）
RUN python3 -m pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev --extra vlm --extra pipeline

# 创建模型和输出目录
RUN mkdir -p /app/models /app/output /root/.cache/huggingface /root/.cache/modelscope

# 设置模型缓存目录环境变量
ENV HF_HOME=/root/.cache/huggingface
ENV MODELSCOPE_CACHE=/root/.cache/modelscope

# 暴露端口
EXPOSE 8001

# 健康检查（首次启动需要下载模型，可能需要 30-60 分钟）
HEALTHCHECK --interval=60s --timeout=30s --start-period=3600s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# 启动脚本：先下载模型（如果不存在），再启动 API
COPY docker/start-vlm.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
