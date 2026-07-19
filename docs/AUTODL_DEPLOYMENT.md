# AutoDL GPU 服务器部署指南

本文档详细说明如何在 AutoDL 服务器上部署电力知识库 RAG 系统，包括 GPU 加速的 Reranker 和 MinerU 集成。

## ⚡ 核心优势

**一键部署，无需手动安装任何依赖！**

- ✅ **无需手动安装 MySQL、Redis、Qdrant、Elasticsearch、MinIO** - 全部通过 Docker Compose 自动部署
- ✅ **无需配置 Python 环境** - 所有依赖都在容器中
- ✅ **无需手动下载模型** - 首次启动自动下载 BGE/Reranker 模型
- ✅ **GPU 开箱即用** - 自动检测并使用 GPU 加速 Reranker 和 MinerU
- ✅ **数据持久化** - 所有数据存储在 Docker Volume，重启不丢失

## 📋 前置条件

### 硬件要求
- **GPU**: Tesla V100/T4/A100 等，至少 16GB 显存
- **内存**: 建议 32GB+
- **磁盘**: 至少 100GB (存储模型、数据、Docker 镜像)

### 软件要求（AutoDL 通常已预装）
- **操作系统**: Ubuntu 20.04/22.04
- **CUDA**: 12.1+ (AutoDL 镜像通常已预装)
- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **nvidia-docker**: GPU 容器运行时

> **重要提示**: AutoDL 的官方镜像通常已经预装了 Docker、CUDA 和 nvidia-docker，你只需要验证即可，无需手动安装 MySQL、Redis 等服务！

---

## 🚀 部署步骤

### 1. 租用 AutoDL 实例

1. 访问 [AutoDL](https://www.autodl.com/)
2. 选择实例配置:
   - **GPU**: Tesla V100 16GB 或更高
   - **镜像**: `PyTorch 2.0.0` 或 `Ubuntu 22.04 + CUDA 12.1`
   - **数据盘**: 建议 100GB+
3. 开机并记录:
   - SSH 连接信息 (IP、端口、密码)
   - 实例 ID

### 2. 连接到服务器

```bash
# 使用 AutoDL 提供的 SSH 命令连接
ssh -p <端口> root@<IP地址>

# 或使用 AutoDL 的一键连接功能
```

### 3. 验证 GPU 和 NVIDIA Docker

```bash
# 检查 GPU 是否可用
nvidia-smi

# 验证 CUDA 版本
nvcc --version

# 检查 Docker
docker --version
docker compose version

# 验证 nvidia-docker (关键!)
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

**如果 `nvidia-smi` 在容器内成功运行，说明 GPU 容器运行时已就绪。**

### 4. 安装必要工具 (如未安装)

```bash
# 更新系统
apt-get update && apt-get upgrade -y

# 安装基础工具
apt-get install -y git curl wget vim htop

# 如果需要安装 Docker Compose v2
curl -SL https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-linux-x86_64 \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

### 5. 克隆项目代码

```bash
# 进入工作目录
cd /root

# 克隆仓库 (替换为你的仓库地址)
git clone <your-repo-url> electric-rag
cd electric-rag

# 或者如果已有代码，使用 rsync/scp 上传
# rsync -avz -e "ssh -p <端口>" ./electric-rag root@<IP>:/root/
```

### 6. 配置环境变量

```bash
cd /root/electric-rag

# 创建 .env 文件
cp backend/.env.example .env

# 编辑配置 (重要!)
vim .env
```

**关键配置项 (`.env`)**:

```bash
# MySQL 密码 (修改为强密码)
MYSQL_PASSWORD=your_strong_password_here

# Redis (默认无密码即可)
REDIS_PASSWORD=

# MinIO 密钥 (建议修改)
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin_secure_2024

# LLM API 配置 (豆包/通义千问)
ARK_API_KEY=your_doubao_api_key
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_MODEL=doubao-pro-32k

# VLM API (如果启用扫描版 PDF)
DOUBAO_API_KEY=your_doubao_api_key
DOUBAO_MODEL=your_vlm_model

# GPU 配置
CUDA_VISIBLE_DEVICES=0
RERANKER_USE_GPU=true
RERANKER_BATCH_SIZE=32
OCR_USE_GPU=true

# 模型自动下载
AUTO_DOWNLOAD_MODELS=true
```

**保存并退出 (`:wq`)**

### 7. 检查 Docker Compose 配置

```bash
# 验证配置是否正确
docker compose config

# 检查 GPU 配置是否生效
docker compose config | grep -A 5 "deploy:"
```

你应该看到类似输出:
```yaml
deploy:
  resources:
    reservations:
      devices:
      - capabilities:
        - gpu
        count: "1"
        driver: nvidia
```

### 8. 构建镜像

```bash
# 构建所有镜像 (首次约需 20-30 分钟)
docker compose build

# 如果网络不佳，可以分步构建
docker compose build mineru
docker compose build backend
docker compose build frontend
```

**构建过程中会自动完成**:
- ✅ 下载 CUDA 基础镜像 (~5GB)
- ✅ 安装 Python 3.13 和所有依赖
- ✅ 安装 MinerU PDF 解析库
- ✅ 配置 GPU 运行时环境
- ✅ **MySQL、Redis、Qdrant、ES、MinIO 使用官方镜像，无需手动构建**

**如果遇到网络超时，可以配置 Docker 镜像加速**:

```bash
# 配置 Docker 镜像加速 (可选)
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
EOF
systemctl restart docker
```

### 9. 启动服务

```bash
# 启动所有服务 (后台运行)
docker compose up -d

# 查看启动日志
docker compose logs -f

# 或者分别查看各服务日志
docker compose logs -f backend
docker compose logs -f mineru
docker compose logs -f celery-worker
```

**Docker Compose 会自动启动以下服务**:

| 服务 | 容器名 | 说明 | 启动时间 |
|------|--------|------|---------|
| MySQL 8.0 | electric-rag-mysql | 关系数据库，存储文档元数据 | ~30s |
| Redis 7 | electric-rag-redis | 缓存 + Celery 消息队列 | ~10s |
| Qdrant | electric-rag-qdrant | 向量数据库，存储 embeddings | ~20s |
| Elasticsearch 8 | electric-rag-elasticsearch | 全文检索引擎 (BM25) | ~40s |
| MinIO | electric-rag-minio | 对象存储，存储 PDF 文件 | ~20s |
| MinerU | electric-rag-mineru | PDF 解析服务 (GPU 加速) | ~60s |
| Backend | electric-rag-backend | FastAPI 后端 (GPU Reranker) | ~60s |
| Celery Worker | electric-rag-celery | 异步任务处理 (共享 GPU) | ~30s |
| Frontend | electric-rag-frontend | React 前端界面 | ~20s |

**启动顺序** (Docker Compose 自动管理):
1. 基础设施: MySQL, Redis, Qdrant, ES, MinIO (约 30-40s)
2. 等待健康检查通过
3. MinerU 服务 (约 60s，首次启动会下载模型)
4. Backend API (约 60s，会自动下载 BGE/Reranker 模型 ~3.3GB)
5. Celery Worker (依赖 Backend)
6. Frontend (依赖 Backend)

**首次启动预计总时间: 5-10 分钟** (后续启动 < 2 分钟)

> **重要**: 所有服务都运行在 Docker 容器中，互相隔离，无需手动安装和配置！

### 10. 验证部署

```bash
# 检查所有容器状态
docker compose ps

# 应该看到所有服务 STATUS 为 "Up" 或 "Up (healthy)"
```

**健康检查** (验证所有容器服务是否正常):

```bash
# 1. 检查 MySQL (Docker 容器内的 MySQL)
docker compose exec mysql mysqladmin ping -h localhost -u root -p<你的密码>

# 2. 检查 Redis (Docker 容器内的 Redis)
docker compose exec redis redis-cli ping

# 3. 检查 Qdrant (Docker 容器内的 Qdrant)
curl http://localhost:6333/

# 4. 检查 Elasticsearch (Docker 容器内的 ES)
curl http://localhost:9200/_cluster/health

# 5. 检查 MinIO (Docker 容器内的 MinIO)
curl http://localhost:9000/minio/health/live

# 6. 检查 MinerU API (GPU 容器)
curl http://localhost:8001/health

# 7. 检查 Backend API (GPU 容器)
curl http://localhost:8000/health

# 8. 检查 Frontend (前端容器)
curl http://localhost:3000
```

> **提示**: 所有这些服务都运行在 Docker 容器内，你无需在宿主机上安装 MySQL、Redis 等软件！

### 11. 验证 GPU 使用

```bash
# 在 backend 容器内验证 GPU
docker compose exec backend nvidia-smi

# 在 mineru 容器内验证 GPU
docker compose exec mineru nvidia-smi

# 在 celery-worker 容器内验证 GPU
docker compose exec celery-worker nvidia-smi

# 实时监控 GPU 使用率
watch -n 1 nvidia-smi
```

**预期结果**: 应该看到容器进程在 GPU 进程列表中。

### 12. 配置 AutoDL 端口映射

AutoDL 需要手动配置端口映射以从外网访问:

1. 登录 AutoDL 控制台
2. 进入你的实例页面
3. 点击 "自定义服务" 或 "端口映射"
4. 添加以下映射:

| 容器端口 | 映射名称 | 说明 |
|---------|---------|------|
| 8000 | backend-api | 后端 API |
| 3000 | frontend | 前端界面 |
| 8001 | mineru-api | MinerU 服务 |
| 6333 | qdrant | Qdrant 向量库 |
| 9000 | minio | MinIO 对象存储 |
| 9001 | minio-console | MinIO 控制台 |

保存后，AutoDL 会提供外网访问地址，例如:
- Frontend: `https://<实例ID>-3000.sh.autodl.com`
- Backend API: `https://<实例ID>-8000.sh.autodl.com`

### 13. 测试 API 接口

```bash
# 测试登录 (获取 token)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'

# 保存返回的 token
TOKEN="<返回的 access_token>"

# 测试查询接口
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "什么是电力系统稳定性？",
    "top_k": 5
  }'
```

---

## 📊 性能优化

### GPU 显存优化

如果遇到显存不足 (16GB Tesla):

**方法 1: 调整 Reranker batch size**

编辑 `.env`:
```bash
RERANKER_BATCH_SIZE=16  # 从 32 降低到 16
```

**方法 2: 使用 base 版本 reranker**

编辑 `backend/.env`:
```bash
RERANKER_MODEL_LARGE=BAAI/bge-reranker-base  # 替代 large 版本
```

**方法 3: 分时复用 GPU**

修改 `docker-compose.yml`，让 MinerU 和 Backend 使用不同的 GPU 时间片:

```yaml
# 方案: MinerU 不常用，可以按需启动
docker compose stop mineru  # 停用 MinerU 释放显存
docker compose start mineru  # 需要时再启动
```

### 模型预热

```bash
# 首次查询会加载模型到显存，较慢
# 可以运行预热脚本加速后续请求

docker compose exec backend python -c "
from app.core.model_init import check_and_download_models
check_and_download_models()
print('Models loaded successfully!')
"
```

---

## 🔧 常见问题

### 1. 容器无法使用 GPU

**症状**: `RuntimeError: CUDA not available`

**解决**:
```bash
# 检查 nvidia-container-runtime
dpkg -l | grep nvidia-container

# 如果未安装
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  tee /etc/apt/sources.list.d/nvidia-docker.list
apt-get update && apt-get install -y nvidia-container-toolkit
systemctl restart docker

# 重新启动容器
docker compose down
docker compose up -d
```

### 2. 模型下载失败

**症状**: HuggingFace 连接超时

**解决方案 1: 使用国内镜像**

```bash
# 在容器内设置环境变量
docker compose exec backend bash
export HF_ENDPOINT=https://hf-mirror.com
```

**解决方案 2: 手动下载模型**

```bash
# 在宿主机下载
cd backend/models
git lfs install

# 下载 embedding 模型
git clone https://huggingface.co/BAAI/bge-large-zh-v1.5

# 下载 reranker 模型
git clone https://huggingface.co/BAAI/bge-reranker-large

# 重启服务
cd /root/electric-rag
docker compose restart backend
```

### 3. MySQL 连接失败

**症状**: `Can't connect to MySQL server`

**解决**:
```bash
# 检查 MySQL 容器
docker compose logs mysql

# 等待 MySQL 完全启动 (约 30s)
docker compose exec mysql mysqladmin ping -h localhost -u root -p<密码>

# 如果持续失败，重建 MySQL
docker compose down -v mysql
docker compose up -d mysql
```

### 4. Celery Worker 无任务执行

**症状**: 文档上传后无处理结果

**排查**:
```bash
# 查看 Celery 日志
docker compose logs -f celery-worker

# 检查 Redis 连接
docker compose exec celery-worker python -c "
from app.tasks.celery_app import celery_app
print(celery_app.control.inspect().active())
"

# 手动触发任务测试
docker compose exec backend python -c "
from app.tasks.document_tasks import process_document_task
result = process_document_task.delay(1)
print(result.get())
"
```

### 5. 显存溢出 (OOM)

**症状**: `CUDA out of memory`

**解决**:
```bash
# 方案 1: 降低 batch size
# 编辑 .env
RERANKER_BATCH_SIZE=8

# 方案 2: 使用 smaller models
# 编辑 backend/.env
RERANKER_MODEL_LARGE=BAAI/bge-reranker-base

# 方案 3: 禁用部分 GPU 功能
ENABLE_SCANNED_PDF=false
ENABLE_IMAGE_SEARCH=false

# 重启服务
docker compose restart backend celery-worker
```

---

## 🛠️ 维护操作

### 查看日志

```bash
# 实时日志
docker compose logs -f

# 特定服务日志
docker compose logs -f backend
docker compose logs -f celery-worker

# 保存日志到文件
docker compose logs > deployment.log
```

### 重启服务

```bash
# 重启所有服务
docker compose restart

# 重启特定服务
docker compose restart backend
docker compose restart celery-worker

# 重启并重建
docker compose up -d --force-recreate backend
```

### 更新代码

```bash
cd /root/electric-rag

# 拉取最新代码
git pull origin main

# 重建并重启
docker compose down
docker compose build
docker compose up -d
```

### 备份数据

```bash
# 备份 MySQL
docker compose exec mysql mysqldump -u root -p<密码> electric_rag > backup_$(date +%F).sql

# 备份向量库 (Qdrant)
docker compose exec qdrant tar -czf /tmp/qdrant_backup.tar.gz /qdrant/storage
docker cp electric-rag-qdrant:/tmp/qdrant_backup.tar.gz ./qdrant_backup_$(date +%F).tar.gz

# 备份对象存储 (MinIO)
docker compose exec minio mc mirror /data /tmp/minio_backup
docker cp electric-rag-minio:/tmp/minio_backup ./minio_backup_$(date +%F)
```

### 清理空间

```bash
# 清理未使用的 Docker 资源
docker system prune -a

# 清理特定服务的 volume
docker compose down
docker volume rm electric-rag_backend_logs
docker volume rm electric-rag_backend_tmp

# 重新启动
docker compose up -d
```

---

## 📈 监控

### GPU 使用监控

```bash
# 实时监控
watch -n 1 nvidia-smi

# 或使用 gpustat (更友好)
pip install gpustat
watch -n 1 gpustat -cpu
```

### 容器资源监控

```bash
# 查看容器资源使用
docker stats

# 或使用 ctop (更友好)
docker run --rm -ti \
  --name=ctop \
  --volume /var/run/docker.sock:/var/run/docker.sock:ro \
  quay.io/vektorlab/ctop:latest
```

### 应用性能监控

```bash
# Backend API 响应时间
curl -w "@-" -o /dev/null -s http://localhost:8000/health <<'EOF'
time_namelookup:  %{time_namelookup}\n
time_connect:  %{time_connect}\n
time_starttransfer:  %{time_starttransfer}\n
time_total:  %{time_total}\n
EOF

# 查看 Celery 任务队列长度
docker compose exec redis redis-cli llen celery
```

---

## 🔒 安全建议

1. **修改默认密码**: MySQL、MinIO、Admin 账号
2. **使用环境变量**: 不要在代码中硬编码密钥
3. **配置防火墙**: 仅开放必要端口
4. **启用 HTTPS**: 生产环境使用 Nginx + SSL
5. **定期备份**: 数据库、向量库、对象存储
6. **监控日志**: 检查异常访问和错误

---

## 📞 技术支持

- **项目文档**: `docs/design.md`, `docs/architecture/`
- **API 文档**: `http://localhost:8000/docs`
- **问题反馈**: 项目 Issue 页面

---

## 附录: 快速命令参考

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f backend

# 进入容器
docker compose exec backend bash

# 重启服务
docker compose restart backend

# 重建镜像
docker compose build backend

# 清理所有数据 (危险!)
docker compose down -v

# GPU 监控
nvidia-smi
watch -n 1 nvidia-smi

# 测试 API
curl http://localhost:8000/health
curl http://localhost:8001/health
```

---

**部署完成! 🎉**

访问 `https://<实例ID>-3000.sh.autodl.com` 开始使用系统。
