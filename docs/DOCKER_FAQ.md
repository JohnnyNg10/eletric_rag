# 📌 Docker 部署常见问题解答 (FAQ)

## ❓ 需要手动安装 MySQL、Redis、Qdrant 等服务吗？

### ✅ **不需要！**

本项目使用 **Docker Compose** 进行容器化部署，所有依赖服务都会自动启动，**你不需要在宿主机上安装任何数据库或中间件**。

运行 `docker compose up -d` 后，会自动启动以下 9 个容器：

```
电力知识库 RAG 系统
├── MySQL 8.0          (数据库)
├── Redis 7            (缓存 + 消息队列)  
├── Qdrant             (向量数据库)
├── Elasticsearch 8    (全文检索)
├── MinIO              (对象存储)
├── MinerU             (PDF 解析，GPU 加速)
├── Backend API        (FastAPI，GPU Reranker)
├── Celery Worker      (异步任务，GPU)
└── Frontend           (React 前端)
```

**所有服务都运行在 Docker 容器内，互相隔离，互不干扰。**

---

## 🎯 你只需要准备

### 硬件
- ✅ GPU 服务器 (Tesla V100/T4/A100，16GB+ 显存)
- ✅ 100GB+ 磁盘空间
- ✅ 32GB+ 内存

### 软件 (AutoDL 通常已预装)
- ✅ Ubuntu 20.04/22.04
- ✅ Docker 20.10+
- ✅ Docker Compose 2.0+
- ✅ nvidia-docker (GPU 容器运行时)
- ✅ CUDA 12.1+

---

## 🚀 部署只需 3 步

### 1. 验证 GPU Docker 环境

```bash
# 这是最重要的检查！
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

如果能看到 GPU 信息，说明环境就绪 ✅

### 2. 配置环境变量

```bash
cp .env.autodl .env
vim .env
```

修改 3 个必填项：
- `MYSQL_PASSWORD` - MySQL 密码
- `ARK_API_KEY` - 豆包 API Key
- `SECRET_KEY` - 随机 32 字符密钥

### 3. 一键启动

```bash
docker compose build    # 首次构建镜像 (20 分钟)
docker compose up -d    # 启动所有服务
docker compose logs -f  # 查看启动日志
```

等待 5-10 分钟，所有服务自动启动完成！

---

## 📦 Docker Compose 自动完成的工作

运行 `docker compose up -d` 后，系统会自动：

1. ✅ **拉取官方镜像**: MySQL、Redis、Qdrant、ES、MinIO
2. ✅ **构建自定义镜像**: Backend (GPU)、MinerU (GPU)、Frontend
3. ✅ **创建 Docker 网络**: 所有容器在同一网络内互通
4. ✅ **创建 Docker Volume**: 数据持久化存储
5. ✅ **启动所有容器**: 按依赖顺序启动，等待健康检查
6. ✅ **初始化数据库**: 自动创建表和默认管理员账号
7. ✅ **下载 AI 模型**: BGE Embedding + Reranker (~3.3GB)
8. ✅ **配置 GPU 访问**: 自动检测并使用 GPU

**你无需手动执行任何安装或配置命令！**

---

## 🔍 如何验证部署成功？

### 检查容器状态

```bash
docker compose ps
```

应该看到 9 个容器都是 `Up` 或 `Up (healthy)` 状态。

### 检查服务健康

```bash
# Backend API
curl http://localhost:8000/health

# MinerU
curl http://localhost:8001/health

# MySQL
docker compose exec mysql mysqladmin ping -h localhost -u root -p你的密码

# Redis
docker compose exec redis redis-cli ping

# Qdrant
curl http://localhost:6333/

# Elasticsearch
curl http://localhost:9200/
```

### 检查 GPU 使用

```bash
# 在 Backend 容器内检查 GPU
docker compose exec backend nvidia-smi

# 实时监控 GPU
watch -n 1 nvidia-smi
```

---

## 🛠️ 常见操作

### 查看日志

```bash
docker compose logs -f backend        # 后端日志
docker compose logs -f celery-worker  # 任务日志
docker compose logs -f mysql          # 数据库日志
```

### 重启服务

```bash
docker compose restart backend        # 重启单个服务
docker compose restart                # 重启所有服务
```

### 停止服务

```bash
docker compose down                   # 停止所有容器（数据保留）
docker compose down -v                # 停止并删除所有数据 (危险!)
```

### 更新代码

```bash
git pull origin main
docker compose down
docker compose build
docker compose up -d
```

### 备份数据

```bash
# 备份 MySQL
docker compose exec mysql mysqldump -u root -p你的密码 electric_rag > backup.sql

# 备份向量库
docker compose exec qdrant tar -czf /tmp/qdrant.tar.gz /qdrant/storage
docker cp electric-rag-qdrant:/tmp/qdrant.tar.gz ./qdrant_backup.tar.gz
```

---

## ⚠️ 重要提示

### 关于数据持久化

所有数据存储在 Docker Volume 中，**容器删除后数据不会丢失**：

```bash
# 查看 Volume
docker volume ls | grep electric-rag

# 删除容器但保留数据
docker compose down

# 重新启动，数据依然存在
docker compose up -d
```

**只有执行 `docker compose down -v` 才会删除数据！**

### 关于容器网络

容器之间通过 **服务名** 互相访问，例如：
- Backend 访问 MySQL: `mysql:3306`
- Backend 访问 Redis: `redis:6379`
- Backend 访问 Qdrant: `qdrant:6333`

**宿主机访问容器使用 `localhost` + 端口映射。**

### 关于 GPU 共享

Backend、Celery Worker、MinerU 三个容器**共享同一块 GPU**：

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1           # 共享 1 块 GPU
          capabilities: [gpu]
```

如果显存不足，可以按需停止部分服务：
```bash
docker compose stop mineru  # 临时停用 MinerU 释放显存
```

---

## 🆘 遇到问题？

### 问题 1: 容器无法使用 GPU

**解决方案**: 安装 nvidia-container-toolkit

```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  tee /etc/apt/sources.list.d/nvidia-docker.list
apt-get update && apt-get install -y nvidia-container-toolkit
systemctl restart docker
docker compose restart
```

### 问题 2: 显存溢出 (OOM)

**解决方案**: 降低 batch size 或禁用部分功能

编辑 `.env`:
```bash
RERANKER_BATCH_SIZE=16        # 降低到 16 或 8
ENABLE_SCANNED_PDF=false      # 禁用扫描版 PDF
ENABLE_IMAGE_SEARCH=false     # 禁用图片搜索
```

### 问题 3: 模型下载失败

**解决方案**: 使用 HuggingFace 镜像

```bash
docker compose exec backend bash
export HF_ENDPOINT=https://hf-mirror.com
```

或手动下载模型到 `backend/models/` 目录。

### 问题 4: MySQL 启动失败

**解决方案**: 检查日志并重建

```bash
docker compose logs mysql
docker compose down -v mysql
docker compose up -d mysql
```

---

## 📚 更多文档

- **5 分钟快速开始**: `docs/QUICK_START.md`
- **完整部署指南**: `docs/AUTODL_DEPLOYMENT.md`
- **部署检查清单**: `docs/DEPLOYMENT_CHECKLIST.md`
- **架构设计文档**: `docs/design.md`
- **项目说明**: `CLAUDE.md`

---

## 💡 总结

> **你不需要在服务器上安装 MySQL、Redis、Qdrant、Elasticsearch、MinIO！**
> 
> **你只需要 Docker + Docker Compose + GPU 支持，然后运行 `docker compose up -d`，一切都会自动完成！**

这就是容器化部署的魅力 🎉
