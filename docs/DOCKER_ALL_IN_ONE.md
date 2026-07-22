# Docker 一体化打包方案（开箱即用）

## 概述

将整个系统（MySQL、Redis、Qdrant、ES、MinIO、Backend、Frontend、MinerU、AI 模型）打包成 **Docker Compose 离线包**，对方只需：

1. 加载镜像
2. 配置 API 密钥
3. 启动容器

**无需源码，开箱即用**。

---

## 架构设计

### 服务拆分

```
Docker Compose 编排
├── mysql:3306          # 数据库
├── redis:6379          # 缓存
├── qdrant:6333         # 向量库
├── elasticsearch:9200  # 全文检索
├── minio:9000          # 对象存储
├── mineru:8001         # MinerU PDF 解析服务（独立）
├── backend:8000        # 主业务 API
├── celery              # 异步任务
└── frontend:5173       # 前端
```

**MinerU 独立服务**:
- 运行在 **8001 端口**
- 基于 MinerU 项目的 `mineru-api` 命令
- Backend 通过 `http://mineru:8001` 调用
- 包含完整 PDF 解析能力（VLM、OCR、Pipeline）

---

## 方案选择

推荐：**Docker Compose 离线包** - 打包所有镜像 + 预置数据 + 配置文件，对方一键启动。

### 最终交付物

```
electric-rag-bundle.tar.gz (7GB)
├── docker-compose.yml
├── .env.template
├── images/                    # 所有 Docker 镜像
│   ├── mysql.tar
│   ├── redis.tar
│   ├── qdrant.tar
│   ├── elasticsearch.tar
│   ├── minio.tar
│   ├── mineru.tar             # MinerU 服务（含模型）
│   ├── backend.tar            # Backend（含 embedding/rerank 模型）
│   └── frontend.tar
├── start.sh                   # Linux/Mac 启动脚本
├── start.bat                  # Windows 启动脚本
└── README.md                  # 使用说明
```

用户操作流程：
```bash
tar xzf electric-rag-bundle.tar.gz
cd electric-rag-bundle
vim .env  # 填写 API 密钥
./start.sh
```

---

## 打包步骤

### 第一部分：准备 MinerU 服务镜像

#### 1. 创建 MinerU Dockerfile

`MinerU/Dockerfile`:

```dockerfile
FROM python:3.13-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc g++ make \
    libgomp1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制 MinerU 项目文件
COPY pyproject.toml uv.lock ./
COPY mineru/ ./mineru/

# 安装 uv 并安装依赖
RUN pip install --no-cache-dir uv && \
    uv sync --frozen

# 下载 MinerU 模型（可选，也可以运行时下载）
# RUN uv run mineru-models-download

# 暴露端口
EXPOSE 8001

# 启动 MinerU API 服务
CMD ["uv", "run", "mineru-api", "--host", "0.0.0.0", "--port", "8001"]
```

#### 2. 创建 Backend Dockerfile（不含 MinerU）

`backend/Dockerfile.allinone`:

```dockerfile
FROM python:3.13-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc g++ make \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件
COPY pyproject.toml uv.lock* ./

# 安装 uv 并安装依赖
RUN pip install --no-cache-dir uv && \
    uv sync --frozen

# 复制应用代码
COPY app/ ./app/

# 复制 AI 模型（embedding + rerank）
COPY models/ ./models/

# 创建日志目录
RUN mkdir -p /app/logs

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 3. 创建 Frontend Dockerfile

`frontend/Dockerfile.allinone`:

```dockerfile
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

`frontend/nginx.conf`:

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### 4. 下载 AI 模型到本地

```bash
# Backend 模型（embedding + rerank）
cd backend
mkdir -p models && cd models

git clone https://huggingface.co/BAAI/bge-large-zh-v1.5
git clone https://huggingface.co/BAAI/bge-reranker-large
git clone https://huggingface.co/BAAI/bge-reranker-base
git clone https://huggingface.co/naver/efficient-splade-VI-BT-large-query

# 清理 git 历史减小体积
find . -name ".git" -type d -exec rm -rf {} + 2>/dev/null || true

cd ../..

# MinerU 模型会在首次运行时自动下载，或预先下载：
# cd MinerU
# uv run mineru-models-download
# cd ..
```

### 第二部分：构建并导出 Docker 镜像

#### 5. 构建 MinerU 镜像

```bash
cd MinerU
docker build -t electric-rag-mineru:latest .
cd ..
```

#### 6. 构建 Backend 镜像

```bash
cd backend
docker build -f Dockerfile.allinone -t electric-rag-backend:latest .
cd ..
```

#### 7. 构建 Frontend 镜像

```bash
cd frontend
docker build -f Dockerfile.allinone -t electric-rag-frontend:latest .
cd ..
```

#### 8. 拉取基础服务镜像

```bash
docker pull mysql:8.0
docker pull redis:7-alpine
docker pull qdrant/qdrant:v1.7.4
docker pull docker.elastic.co/elasticsearch/elasticsearch:8.11.0
docker pull minio/minio:latest
```

#### 9. 导出所有镜像

```bash
mkdir -p bundle/images

# 导出所有镜像为 tar 文件
docker save electric-rag-mineru:latest -o bundle/images/mineru.tar
docker save electric-rag-backend:latest -o bundle/images/backend.tar
docker save electric-rag-frontend:latest -o bundle/images/frontend.tar
docker save mysql:8.0 -o bundle/images/mysql.tar
docker save redis:7-alpine -o bundle/images/redis.tar
docker save qdrant/qdrant:v1.7.4 -o bundle/images/qdrant.tar
docker save docker.elastic.co/elasticsearch/elasticsearch:8.11.0 -o bundle/images/elasticsearch.tar
docker save minio/minio:latest -o bundle/images/minio.tar

echo "✅ 镜像导出完成"
ls -lh bundle/images/
```

### 第三部分：创建配置和启动脚本

#### 9. 创建 docker-compose.yml

将这个文件保存为 `bundle/docker-compose.yml`（内容见下方完整配置）。

#### 10. 创建环境变量模板

`bundle/.env.template`:

```bash
# ==================== 必填项 ====================
# LLM API（豆包 Pro）
ARK_API_KEY=your_api_key_here
LLM_MODEL=your_model_endpoint_here

# VLM API（豆包多模态）
DOUBAO_API_KEY=your_api_key_here
DOUBAO_MODEL=your_vlm_endpoint_here

# 安全密钥（运行: openssl rand -hex 32）
SECRET_KEY=your_random_32_chars_secret_key_here
# ================================================

# ==================== 可选配置 ====================
# 数据库
MYSQL_ROOT_PASSWORD=root
MYSQL_DB=electric_rag
MYSQL_USER=rag_user
MYSQL_PASSWORD=electric_rag_2024

# MinIO
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# LLM Base URL
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
# ===================================================
```

#### 11. 创建启动脚本（Linux/Mac）

`bundle/start.sh`:

```bash
#!/bin/bash
set -e

echo "=========================================="
echo "  Electric RAG 一键启动"
echo "=========================================="

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装"
    echo "   安装: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

# 检查 Docker Compose
if ! docker compose version &> /dev/null 2>&1; then
    echo "❌ Docker Compose 未安装或版本过旧"
    echo "   需要 Docker Compose v2+"
    exit 1
fi

# 检查配置文件
if [ ! -f .env ]; then
    echo "📝 首次运行，创建配置文件..."
    cp .env.template .env
    echo ""
    echo "⚠️  请编辑 .env 文件，填写以下必填项："
    echo "   - ARK_API_KEY"
    echo "   - LLM_MODEL"
    echo "   - DOUBAO_API_KEY"
    echo "   - DOUBAO_MODEL"
    echo "   - SECRET_KEY"
    echo ""
    echo "配置文件位置: $(pwd)/.env"
    echo ""
    read -p "配置完成后按 Enter 继续..." -r
fi

# 加载镜像
if [ -d "images" ]; then
    echo "📦 加载 Docker 镜像（首次运行需要几分钟）..."
    for img in images/*.tar; do
        if [ -f "$img" ]; then
            echo "  → $(basename $img)"
            docker load -i "$img" -q
        fi
    done
    echo "✅ 镜像加载完成"
    echo ""
fi

# 启动服务
echo "🚀 启动所有服务..."
docker compose up -d

# 等待服务就绪
echo "⏳ 等待服务启动（约 30 秒）..."
sleep 30

# 显示状态
echo ""
echo "=========================================="
echo "✅ 启动完成！"
echo "=========================================="
echo ""
echo "📌 访问地址:"
echo "   前端:      http://localhost:5173"
echo "   后端 API:  http://localhost:8000"
echo "   API 文档:  http://localhost:8000/docs"
echo ""
echo "📊 查看服务状态:"
echo "   docker compose ps"
echo ""
echo "📝 查看日志:"
echo "   docker compose logs -f backend"
echo "   docker compose logs -f celery"
echo ""
echo "🛑 停止服务:"
echo "   ./stop.sh"
echo ""
```

#### 12. 创建停止脚本

`bundle/stop.sh`:

```bash
#!/bin/bash

echo "🛑 停止所有服务..."
docker compose down

echo "✅ 已停止"
echo ""
echo "💡 提示:"
echo "   - 数据已保留在 Docker volumes"
echo "   - 下次启动: ./start.sh"
echo "   - 完全清理（删除数据）: docker compose down -v"
```

#### 13. 创建 Windows 启动脚本

`bundle/start.bat`:

```batch
@echo off
chcp 65001 >nul
echo ==========================================
echo   Electric RAG 一键启动
echo ==========================================
echo.

where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ Docker 未安装
    echo    请安装 Docker Desktop for Windows
    pause
    exit /b 1
)

if not exist .env (
    echo 📝 首次运行，创建配置文件...
    copy .env.template .env
    echo.
    echo ⚠️  请编辑 .env 文件，填写 API 密钥
    notepad .env
    pause
)

if exist images (
    echo 📦 加载 Docker 镜像...
    for %%f in (images\*.tar) do (
        echo   → %%~nxf
        docker load -i "%%f" -q
    )
    echo ✅ 镜像加载完成
    echo.
)

echo 🚀 启动所有服务...
docker compose up -d

echo.
echo ==========================================
echo ✅ 启动完成！
echo ==========================================
echo.
echo 📌 访问地址:
echo    前端:      http://localhost:5173
echo    后端 API:  http://localhost:8000
echo    API 文档:  http://localhost:8000/docs
echo.
pause
```

`bundle/stop.bat`:

```batch
@echo off
echo 🛑 停止所有服务...
docker compose down
echo ✅ 已停止
pause
```

chmod +x bundle/start.sh bundle/stop.sh

#### 14. 创建完整的 docker-compose.yml

`bundle/docker-compose.yml`:

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    container_name: electric-rag-mysql
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-root}
      MYSQL_DATABASE: ${MYSQL_DB:-electric_rag}
      MYSQL_USER: ${MYSQL_USER:-rag_user}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-electric_rag_2024}
    volumes:
      - mysql_data:/var/lib/mysql
    networks:
      - electric-rag-net
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: electric-rag-redis
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    networks:
      - electric-rag-net
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:v1.7.4
    container_name: electric-rag-qdrant
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - electric-rag-net
    restart: unless-stopped

  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    container_name: electric-rag-es
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    volumes:
      - es_data:/usr/share/elasticsearch/data
    networks:
      - electric-rag-net
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    container_name: electric-rag-minio
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY:-minioadmin}
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data
    networks:
      - electric-rag-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  mineru:
    image: electric-rag-mineru:latest
    container_name: electric-rag-mineru
    ports:
      - "8001:8001"
    networks:
      - electric-rag-net
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

  backend:
    image: electric-rag-backend:latest
    container_name: electric-rag-backend
    environment:
      APP_NAME: Electric RAG System
      DEBUG: "False"
      ENV: production
      API_V1_PREFIX: /api/v1
      
      # Database
      MYSQL_HOST: mysql
      MYSQL_PORT: 3306
      MYSQL_USER: ${MYSQL_USER:-rag_user}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-electric_rag_2024}
      MYSQL_DB: ${MYSQL_DB:-electric_rag}
      
      # Redis
      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_DB: 0
      
      # Qdrant
      QDRANT_HOST: qdrant
      QDRANT_PORT: 6333
      QDRANT_COLLECTION: documents
      
      # Elasticsearch
      ES_HOSTS: http://elasticsearch:9200
      ES_INDEX: documents
      
      # MinIO
      MINIO_ENDPOINT: minio:9000
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY:-minioadmin}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY:-minioadmin}
      MINIO_BUCKET: electric-rag
      
      # MinerU Service
      MINERU_API_URL: http://mineru:8001
      
      # LLM API
      ARK_API_KEY: ${ARK_API_KEY}
      LLM_BASE_URL: ${LLM_BASE_URL:-https://ark.cn-beijing.volces.com/api/v3}
      LLM_MODEL: ${LLM_MODEL}
      
      # VLM API
      VLM_PROVIDER: doubao
      DOUBAO_API_KEY: ${DOUBAO_API_KEY}
      DOUBAO_API_ENDPOINT: https://ark.cn-beijing.volces.com/api/v3/chat/completions
      DOUBAO_MODEL: ${DOUBAO_MODEL}
      
      # Celery
      CELERY_BROKER_URL: redis://redis:6379/1
      CELERY_RESULT_BACKEND: redis://redis:6379/2
      
      # Model Config
      MODELS_DIR: /app/models
      AUTO_DOWNLOAD_MODELS: "False"
      MAX_RECALL_COUNT: 20
      TOP_K_RESULTS: 5
      CACHE_TTL: 3600
      
      # PDF Processing (delegated to MinerU)
      ENABLE_SCANNED_PDF: "true"
      ENABLE_IMAGE_SEARCH: "true"
      ENABLE_VLM_DESCRIPTION: "true"
      
      # OCR (MinerU handles this)
      OCR_USE_GPU: "False"
      OCR_CONFIDENCE_THRESHOLD: 0.85
      
      # Security
      SECRET_KEY: ${SECRET_KEY}
      ALGORITHM: HS256
      ACCESS_TOKEN_EXPIRE_MINUTES: 30
    ports:
      - "8000:8000"
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_started
      qdrant:
        condition: service_started
      minio:
        condition: service_healthy
      mineru:
        condition: service_started
    networks:
      - electric-rag-net
    restart: unless-stopped

  celery:
    image: electric-rag-backend:latest
    container_name: electric-rag-celery
    command: uv run celery -A app.tasks.celery_app worker --loglevel=info
    environment:
      MYSQL_HOST: mysql
      MYSQL_USER: ${MYSQL_USER:-rag_user}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-electric_rag_2024}
      MYSQL_DB: ${MYSQL_DB:-electric_rag}
      REDIS_HOST: redis
      QDRANT_HOST: qdrant
      ES_HOSTS: http://elasticsearch:9200
      MINIO_ENDPOINT: minio:9000
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY:-minioadmin}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY:-minioadmin}
      CELERY_BROKER_URL: redis://redis:6379/1
      CELERY_RESULT_BACKEND: redis://redis:6379/2
      MODELS_DIR: /app/models
      AUTO_DOWNLOAD_MODELS: "False"
      MINERU_API_URL: http://mineru:8001
      ARK_API_KEY: ${ARK_API_KEY}
      LLM_BASE_URL: ${LLM_BASE_URL}
      LLM_MODEL: ${LLM_MODEL}
      DOUBAO_API_KEY: ${DOUBAO_API_KEY}
      DOUBAO_MODEL: ${DOUBAO_MODEL}
    depends_on:
      - backend
    networks:
      - electric-rag-net
    restart: unless-stopped

  frontend:
    image: electric-rag-frontend:latest
    container_name: electric-rag-frontend
    ports:
      - "5173:80"
    depends_on:
      - backend
    networks:
      - electric-rag-net
    restart: unless-stopped

volumes:
  mysql_data:
  redis_data:
  qdrant_data:
  es_data:
  minio_data:

networks:
  electric-rag-net:
    driver: bridge
```

#### 15. 创建 README 使用说明

`bundle/README.md`:

```markdown
# Electric RAG 一体化部署包

## 📦 包含内容

✅ **完整打包，开箱即用**
- MySQL 8.0 数据库
- Redis 缓存
- Qdrant 向量数据库
- Elasticsearch 全文检索
- MinIO 对象存储
- Backend API（FastAPI + AI 模型 + MinerU）
- Frontend（React）
- Celery 异步任务队列

✅ **AI 模型已内置**（3.3GB）
- bge-large-zh-v1.5（中文嵌入）
- bge-reranker-large/base（重排）
- efficient-splade（稀疏编码）

✅ **仅需配置 API 密钥**
- LLM API（豆包 Pro）
- VLM API（豆包多模态）

---

## 🚀 快速开始

### 系统要求

- **Docker**: 20.10+ 或 Docker Desktop
- **Docker Compose**: v2+
- **磁盘空间**: 至少 10GB
- **内存**: 建议 8GB+（最低 4GB）
- **CPU**: 建议 4 核+

### 安装 Docker

**Windows/Mac**: 下载安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)

**Linux**:
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

### 使用步骤

#### 1. 解压部署包

```bash
# Linux/Mac
tar xzf electric-rag-bundle.tar.gz
cd electric-rag-bundle

# Windows
# 使用 7-Zip 或 WinRAR 解压
```

#### 2. 配置 API 密钥

编辑 `.env.template`，填写以下必填项并另存为 `.env`:

```bash
ARK_API_KEY=your_actual_api_key_here
LLM_MODEL=ep-20260717095008-vr5r8
DOUBAO_API_KEY=your_actual_api_key_here
DOUBAO_MODEL=ep-20260717161647-s9plq
SECRET_KEY=$(openssl rand -hex 32)  # 或任意 32 字符随机字符串
```

#### 3. 启动服务

**Linux/Mac**:
```bash
./start.sh
```

**Windows**:
```
双击 start.bat
```

首次启动会加载 Docker 镜像（约 5GB），需要 3-5 分钟。

#### 4. 访问系统

启动完成后访问:
- **前端**: http://localhost:5173
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

---

## 🛠️ 常用操作

### 查看服务状态

```bash
docker compose ps
```

### 查看日志

```bash
# 实时查看所有日志
docker compose logs -f

# 查看特定服务
docker compose logs -f backend
docker compose logs -f celery
```

### 重启服务

```bash
# 重启所有服务
docker compose restart

# 重启单个服务
docker compose restart backend
```

### 停止服务

**Linux/Mac**:
```bash
./stop.sh
```

**Windows**:
```
双击 stop.bat
```

或手动:
```bash
docker compose down
```

### 完全清理（删除所有数据）

```bash
docker compose down -v
```

⚠️ **警告**: 这会删除所有数据库数据、上传的文件、向量索引等。

---

## 🔧 高级配置

### 修改端口

编辑 `docker-compose.yml`，修改 `ports` 部分:

```yaml
services:
  backend:
    ports:
      - "8080:8000"  # 将后端改为 8080 端口
  frontend:
    ports:
      - "3000:80"    # 将前端改为 3000 端口
```

### 启用 GPU 加速

如果宿主机有 NVIDIA GPU:

1. 安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

2. 修改 `.env`:
   ```bash
   OCR_USE_GPU=True
   ```

3. 在 `docker-compose.yml` 的 `backend` 和 `celery` 服务添加:
   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: 1
             capabilities: [gpu]
   ```

4. 重启服务

### 数据持久化

所有数据存储在 Docker volumes 中，即使重启也会保留:

```bash
# 查看数据卷
docker volume ls | grep electric-rag

# 备份数据卷
docker run --rm -v electric-rag_mysql_data:/data -v $(pwd)/backup:/backup alpine tar czf /backup/mysql_backup.tar.gz -C /data .
```

---

## 🐛 故障排查

### 问题：服务启动失败

**解决**:
```bash
# 查看详细日志
docker compose logs

# 检查端口占用
# Linux/Mac
netstat -tunlp | grep -E "8000|5173|3306|6379|6333|9200|9000"

# Windows
netstat -ano | findstr "8000 5173 3306 6379"
```

### 问题：API 调用失败

**检查**:
1. 确认 `.env` 中 API 密钥配置正确
2. 测试 API 连接:
   ```bash
   curl -X POST "https://ark.cn-beijing.volces.com/api/v3/chat/completions" \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model": "YOUR_MODEL", "messages": [{"role": "user", "content": "test"}]}'
   ```

### 问题：内存不足

**解决**: 调整 Elasticsearch 内存限制，编辑 `docker-compose.yml`:

```yaml
elasticsearch:
  environment:
    - "ES_JAVA_OPTS=-Xms256m -Xmx256m"  # 从 512m 降低到 256m
```

### 问题：模型加载失败

模型已打包在 `backend` 镜像中，如果加载失败:

```bash
# 进入容器检查
docker exec -it electric-rag-backend bash
ls -lh /app/models/
```

---

## 📊 性能优化建议

### 生产环境配置

1. **调整并发数**: 编辑 `docker-compose.yml`
   ```yaml
   backend:
     command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

2. **增加 Celery worker 数量**:
   ```yaml
   celery:
     command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
   ```

3. **限制容器资源**:
   ```yaml
   backend:
     deploy:
       resources:
         limits:
           cpus: '4'
           memory: 8G
   ```

---

## 📝 文件结构

```
electric-rag-bundle/
├── docker-compose.yml          # 服务编排配置
├── .env.template               # 配置模板
├── start.sh / start.bat        # 启动脚本
├── stop.sh / stop.bat          # 停止脚本
├── README.md                   # 本文档
└── images/                     # Docker 镜像（5GB+）
    ├── backend.tar             # 后端（含模型、MinerU）
    ├── frontend.tar            # 前端
    ├── mysql.tar               # MySQL
    ├── redis.tar               # Redis
    ├── qdrant.tar              # Qdrant
    ├── elasticsearch.tar       # Elasticsearch
    └── minio.tar               # MinIO
```

---

## 🔐 安全建议

**生产环境部署前务必**:

1. 修改默认密码:
   ```bash
   MYSQL_PASSWORD=your_strong_password
   MINIO_SECRET_KEY=your_strong_secret
   ```

2. 使用强随机密钥:
   ```bash
   SECRET_KEY=$(openssl rand -hex 32)
   ```

3. 启用 HTTPS（建议使用 Nginx 反向代理）

4. 定期备份数据卷

---

## 📞 技术支持

- **文档**: 查看 `docs/` 目录
- **Issues**: 项目仓库 Issues
- **更新**: 下载新版本部署包，保留旧的 `.env` 配置

---

## 📄 许可证

[根据项目实际情况填写]
```

### 第四部分：最终打包

#### 16. 打包所有文件

```bash
cd bundle
chmod +x start.sh stop.sh

# 创建最终压缩包
tar czf ../electric-rag-bundle.tar.gz \
  docker-compose.yml \
  .env.template \
  start.sh \
  stop.sh \
  start.bat \
  stop.bat \
  README.md \
  images/

cd ..
echo "✅ 打包完成: electric-rag-bundle.tar.gz"
ls -lh electric-rag-bundle.tar.gz
```

**预计打包大小**:
- MinerU 镜像（含 PDF 解析模型）: ~3GB
- Backend 镜像（含 embedding/rerank 模型）: ~4GB
- Frontend 镜像: ~50MB
- MySQL 镜像: ~500MB
- Redis 镜像: ~30MB
- Qdrant 镜像: ~150MB
- Elasticsearch 镜像: ~600MB
- MinIO 镜像: ~200MB
- **总计**: ~8.5GB

---

## 📋 完整打包脚本

创建一键打包脚本 `build-bundle.sh`:

```bash
#!/bin/bash
set -e

echo "=========================================="
echo "  Electric RAG Docker 一体化打包"
echo "=========================================="

# 1. 下载 Backend 模型
echo "📥 步骤 1/8: 下载 Backend AI 模型..."
cd backend
if [ ! -d "models/bge-large-zh-v1.5" ]; then
    mkdir -p models && cd models
    git clone https://huggingface.co/BAAI/bge-large-zh-v1.5
    git clone https://huggingface.co/BAAI/bge-reranker-large
    git clone https://huggingface.co/BAAI/bge-reranker-base
    git clone https://huggingface.co/naver/efficient-splade-VI-BT-large-query
    find . -name ".git" -type d -exec rm -rf {} + 2>/dev/null || true
    cd ..
else
    echo "   ✓ Backend 模型已存在"
fi
cd ..

# 2. 构建 MinerU 镜像
echo "🔨 步骤 2/8: 构建 MinerU 镜像..."
cd MinerU
docker build -t electric-rag-mineru:latest .
cd ..

# 3. 构建 Backend 镜像
echo "🔨 步骤 3/8: 构建 Backend 镜像..."
cd backend
docker build -f Dockerfile.allinone -t electric-rag-backend:latest .
cd ..

# 4. 构建 Frontend 镜像
echo "🔨 步骤 4/8: 构建 Frontend 镜像..."
cd frontend
docker build -f Dockerfile.allinone -t electric-rag-frontend:latest .
cd ..

# 5. 拉取基础镜像
echo "📥 步骤 5/8: 拉取基础服务镜像..."
docker pull mysql:8.0
docker pull redis:7-alpine
docker pull qdrant/qdrant:v1.7.4
docker pull docker.elastic.co/elasticsearch/elasticsearch:8.11.0
docker pull minio/minio:latest

# 6. 导出镜像
echo "💾 步骤 6/8: 导出所有镜像..."
mkdir -p bundle/images
docker save electric-rag-mineru:latest -o bundle/images/mineru.tar
docker save electric-rag-backend:latest -o bundle/images/backend.tar
docker save electric-rag-frontend:latest -o bundle/images/frontend.tar
docker save mysql:8.0 -o bundle/images/mysql.tar
docker save redis:7-alpine -o bundle/images/redis.tar
docker save qdrant/qdrant:v1.7.4 -o bundle/images/qdrant.tar
docker save docker.elastic.co/elasticsearch/elasticsearch:8.11.0 -o bundle/images/elasticsearch.tar
docker save minio/minio:latest -o bundle/images/minio.tar

# 7. 打包所有文件
echo "📋 步骤 7/8: 打包所有文件..."
cd bundle
chmod +x start.sh stop.sh 2>/dev/null || true

tar czf ../electric-rag-bundle.tar.gz \
  docker-compose.yml \
  .env.template \
  start.sh \
  stop.sh \
  start.bat \
  stop.bat \
  README.md \
  images/

cd ..

# 8. 清理
echo "🧹 步骤 8/8: 清理临时文件..."
# 可选：删除导出的镜像 tar 文件以节省空间
# rm -rf bundle/images/

echo ""
echo "=========================================="
echo "✅ 打包完成！"
echo "=========================================="
echo ""
echo "📦 输出文件: electric-rag-bundle.tar.gz"
ls -lh electric-rag-bundle.tar.gz
echo ""
echo "📤 交付给用户:"
echo "   1. 发送 electric-rag-bundle.tar.gz"
echo "   2. 用户解压后运行 start.sh 或 start.bat"
echo "   3. 用户配置 .env 中的 API 密钥"
echo ""
echo "🔧 服务架构:"
echo "   - MinerU:    8001 (PDF 解析服务)"
echo "   - Backend:   8000 (主业务 API)"
echo "   - Frontend:  5173 (前端界面)"
echo ""
```

chmod +x build-bundle.sh

---

## 🎯 使用流程总结

### 打包方（你）

```bash
# 1. 确保项目结构正确
# - backend/ 包含主业务代码
# - MinerU/ 包含 MinerU 项目
# - frontend/ 包含前端代码

# 2. 创建所有配置文件（Dockerfile、docker-compose.yml、脚本等）

# 3. 运行打包脚本
./build-bundle.sh

# 4. 得到 electric-rag-bundle.tar.gz（约 8.5GB）
# 5. 发送给用户
```

### 使用方（对方）

```bash
# 1. 解压
tar xzf electric-rag-bundle.tar.gz
cd electric-rag-bundle

# 2. 配置 API 密钥
cp .env.template .env
vim .env  # 填写必填项

# 3. 启动（会自动加载镜像）
./start.sh  # Linux/Mac
# 或双击 start.bat（Windows）

# 4. 访问系统
# 前端: http://localhost:5173
# Backend API: http://localhost:8000
# MinerU API: http://localhost:8001

# 5. 测试 MinerU（可选）
curl http://localhost:8001/health
```

---

## ✅ 优势总结

1. ✅ **无需源码** - 所有代码编译在镜像内
2. ✅ **开箱即用** - 解压、配置、启动三步完成
3. ✅ **服务拆分** - MinerU 独立服务，便于扩展和维护
4. ✅ **完全离线** - 除 LLM/VLM API 外全部本地运行
5. ✅ **跨平台** - Windows/Mac/Linux 都支持
6. ✅ **模型内置** - 所有 AI 模型打包在镜像中
7. ✅ **数据持久化** - 使用 Docker volumes 保存数据
8. ✅ **一键启停** - 简单脚本控制
9. ✅ **使用 uv** - 统一依赖管理工具

---

## 📌 关键架构说明

### MinerU 服务独立部署

**为什么独立？**
- MinerU 是重型 PDF 解析服务，资源消耗大
- 独立部署便于横向扩展（多实例负载均衡）
- Backend 轻量化，专注业务逻辑
- 便于后续替换或升级 MinerU

**Backend 如何调用 MinerU？**

在 Backend 代码中通过 HTTP 调用：

```python
# backend/app/services/pdf_parser.py
import httpx

MINERU_API_URL = os.getenv("MINERU_API_URL", "http://mineru:8001")

async def parse_pdf(file_path: str) -> dict:
    """调用 MinerU 解析 PDF"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        with open(file_path, "rb") as f:
            response = await client.post(
                f"{MINERU_API_URL}/file_parse",
                files={"files": f},
                data={
                    "backend": "pipeline",
                    "return_md": "true",
                    "return_content_list": "true",
                },
            )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"MinerU 解析失败: {response.text}")
```

**MinerU API 接口**:
- `GET /health` - 健康检查
- `POST /file_parse` - 同步解析（推荐）
- `POST /tasks` - 异步解析
- `GET /tasks/{task_id}` - 查询任务状态
- `GET /tasks/{task_id}/result` - 获取结果

参考 `MinerU/test_local_api.py` 的完整示例。

---

## 📝 注意事项

### 1. 镜像体积控制

- MinerU 镜像: ~3GB（包含 VLM/OCR 模型）
- Backend 镜像: ~4GB（包含 embedding/rerank 模型）
- 总计约 8.5GB

### 2. 网络要求

**本地运行**:
- MySQL、Redis、Qdrant、ES、MinIO
- Backend、Frontend、MinerU、Celery

**需要外网**:
- LLM API（豆包 Pro）
- VLM API（豆包多模态）

### 3. 依赖管理

项目统一使用 **uv** 作为包管理器：
- Backend: `uv sync --frozen`
- MinerU: `uv sync --frozen`
- 确保 `pyproject.toml` 和 `uv.lock` 存在

### 4. 安全建议

生产环境必须修改：
- `SECRET_KEY` - 强随机字符串
- `MYSQL_PASSWORD` - 数据库密码
- `MINIO_SECRET_KEY` - MinIO 凭证

### 5. 更新策略

- 重新打包新版本镜像
- 用户下载新包，保留旧的 `.env` 配置
- 停止旧版本: `docker compose down`
- 启动新版本: `./start.sh`
- 数据卷会自动保留

---

## 🚀 进阶：单镜像方案（不推荐）

如果一定要单个镜像包含所有服务（类似虚拟机），可以使用 **supervisord** 在一个容器内运行多个服务，但这违反 Docker 最佳实践，不推荐。

推荐使用上述 **Docker Compose 多镜像方案**，既符合最佳实践，又易于维护。

