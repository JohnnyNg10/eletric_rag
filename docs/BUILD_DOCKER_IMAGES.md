# Docker 镜像构建完成指南

本文档说明如何构建 Electric RAG 系统的所有 Docker 镜像。

## 📦 镜像列表

| 服务 | 镜像名称 | 大小（估算） | 端口 |
|------|---------|-------------|------|
| MinerU | electric-rag-mineru:latest | ~3GB | 8001 |
| Backend | electric-rag-backend:latest | ~4GB | 8000 |
| Frontend | electric-rag-frontend:latest | ~50MB | 80 |

## 🚀 构建顺序

### 步骤 1: 下载 Backend AI 模型

```bash
cd backend
mkdir -p models && cd models

# 下载所有模型
git clone https://huggingface.co/BAAI/bge-large-zh-v1.5
git clone https://huggingface.co/BAAI/bge-reranker-large
git clone https://huggingface.co/BAAI/bge-reranker-base
git clone https://huggingface.co/naver/efficient-splade-VI-BT-large-query

# 清理 git 历史
find . -name ".git" -type d -exec rm -rf {} + 2>/dev/null || true

cd ../..
```

**国内网络加速**：
```bash
# 使用镜像站
export HF_ENDPOINT=https://hf-mirror.com
git clone https://hf-mirror.com/BAAI/bge-large-zh-v1.5
```

### 步骤 2: 构建 MinerU 镜像

```bash
cd MinerU

# Linux/Mac
./build-docker.sh

# Windows
build-docker.bat

cd ..
```

**预计时间**: 5-10 分钟
**镜像大小**: ~3GB（包含 PDF 解析模型）

### 步骤 3: 构建 Backend 镜像

```bash
cd backend

# Linux/Mac
./build-docker.sh

# Windows
build-docker.bat

cd ..
```

**预计时间**: 10-15 分钟（包含复制 3.3GB 模型）
**镜像大小**: ~4GB

### 步骤 4: 构建 Frontend 镜像

```bash
cd frontend

# Linux/Mac
./build-docker.sh

# Windows
build-docker.bat

cd ..
```

**预计时间**: 3-5 分钟
**镜像大小**: ~50MB

## ✅ 验证构建

查看所有构建的镜像：

```bash
docker images | grep electric-rag
```

应该看到：
```
electric-rag-mineru     latest    ...    ~3GB
electric-rag-backend    latest    ...    ~4GB
electric-rag-frontend   latest    ...    ~50MB
```

## 🧪 测试镜像

### 测试 MinerU

```bash
docker run -d --name mineru-test -p 8001:8001 electric-rag-mineru:latest
sleep 10
curl http://localhost:8001/health
docker stop mineru-test && docker rm mineru-test
```

### 测试 Backend（需要配置环境变量）

```bash
docker run -d --name backend-test \
  -p 8000:8000 \
  -e MYSQL_HOST=host.docker.internal \
  -e REDIS_HOST=host.docker.internal \
  -e QDRANT_HOST=host.docker.internal \
  -e MINERU_API_URL=http://host.docker.internal:8001 \
  -e ARK_API_KEY=your_key \
  -e LLM_MODEL=your_model \
  -e DOUBAO_API_KEY=your_key \
  -e DOUBAO_MODEL=your_model \
  -e SECRET_KEY=test-secret-key-32-chars-long \
  electric-rag-backend:latest

# 等待启动
sleep 30

# 测试健康检查
curl http://localhost:8000/health

# 查看日志
docker logs backend-test

# 停止
docker stop backend-test && docker rm backend-test
```

### 测试 Frontend

```bash
docker run -d --name frontend-test -p 5173:80 electric-rag-frontend:latest
sleep 5
curl http://localhost:5173
docker stop frontend-test && docker rm frontend-test
```

## 📤 导出镜像（用于打包）

```bash
mkdir -p bundle/images

# 导出自定义镜像
docker save electric-rag-mineru:latest -o bundle/images/mineru.tar
docker save electric-rag-backend:latest -o bundle/images/backend.tar
docker save electric-rag-frontend:latest -o bundle/images/frontend.tar

# 拉取并导出基础镜像
docker pull mysql:8.0
docker pull redis:7-alpine
docker pull qdrant/qdrant:v1.7.4
docker pull docker.elastic.co/elasticsearch/elasticsearch:8.11.0
docker pull minio/minio:latest

docker save mysql:8.0 -o bundle/images/mysql.tar
docker save redis:7-alpine -o bundle/images/redis.tar
docker save qdrant/qdrant:v1.7.4 -o bundle/images/qdrant.tar
docker save docker.elastic.co/elasticsearch/elasticsearch:8.11.0 -o bundle/images/elasticsearch.tar
docker save minio/minio:latest -o bundle/images/minio.tar

# 查看导出的镜像
ls -lh bundle/images/
```

## 🐛 故障排查

### 问题 1: 模型下载失败

**症状**: git clone 超时或失败

**解决**:
```bash
# 使用镜像站
export HF_ENDPOINT=https://hf-mirror.com
git clone https://hf-mirror.com/BAAI/bge-large-zh-v1.5

# 或使用代理
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
```

### 问题 2: Docker 构建内存不足

**症状**: 构建过程中 OOM 或卡死

**解决**:
```bash
# 增加 Docker 内存限制（Docker Desktop）
# Settings > Resources > Memory: 8GB+

# 或使用 --memory 限制单个构建
docker build --memory=8g -t electric-rag-backend:latest .
```

### 问题 3: uv.lock 不存在

**症状**: 构建时找不到 uv.lock

**解决**:
```bash
# Backend
cd backend
uv lock
cd ..

# MinerU
cd MinerU
uv lock
cd ..
```

### 问题 4: 镜像体积过大

**优化方法**:
1. 清理不必要的文件（检查 .dockerignore）
2. 使用多阶段构建
3. 压缩模型文件（如果可能）

```bash
# 查看镜像层
docker history electric-rag-backend:latest

# 分析体积
docker system df
```

## 📝 下一步

完成镜像构建后，继续：
1. 创建 `docker-compose.yml`（参考 `docs/DOCKER_ALL_IN_ONE.md`）
2. 创建启动脚本 `start.sh` / `start.bat`
3. 打包所有文件为 `electric-rag-bundle.tar.gz`
4. 测试完整部署流程

## 🔒 安全提示

- 镜像中**不要**包含真实的 API 密钥
- 生产环境使用前修改所有默认密码
- 定期更新基础镜像以修复安全漏洞

## 📚 参考文档

- `docs/DOCKER_ALL_IN_ONE.md` - 完整打包方案
- `MinerU/README.Docker.md` - MinerU 镜像详细说明
- `backend/README.md` - Backend 配置说明
- `frontend/README.md` - Frontend 构建说明
