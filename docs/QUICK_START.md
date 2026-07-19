# 🚀 AutoDL 快速部署指南（5 分钟版）

**适合有 Docker 经验的用户快速上手**

## ❓ 常见问题

### Q1: 需要手动安装 MySQL/Redis/Qdrant 吗？

**❌ 不需要！Docker Compose 会自动为你启动所有服务！**

### Q2: AutoDL 上有 Docker 吗？

**❌ 没有！AutoDL 默认不带 Docker，需要先安装（5 分钟）**

详见：**[在 AutoDL 上安装 Docker](AUTODL_DOCKER_INSTALL.md)** ⬅️ **AutoDL 用户必读**

本项目使用 Docker Compose 一键部署以下 9 个服务：

| 服务 | 说明 | 自动启动 |
|------|------|---------|
| MySQL 8.0 | 数据库 | ✅ |
| Redis 7 | 缓存 + 消息队列 | ✅ |
| Qdrant | 向量数据库 | ✅ |
| Elasticsearch 8 | 全文检索 | ✅ |
| MinIO | 对象存储 | ✅ |
| MinerU | PDF 解析 (GPU) | ✅ |
| Backend | FastAPI 后端 (GPU) | ✅ |
| Celery Worker | 异步任务 (GPU) | ✅ |
| Frontend | React 前端 | ✅ |

你只需要：
1. 有一台带 GPU 的 Linux 服务器
2. 已安装 Docker + Docker Compose + nvidia-docker
3. 运行 `docker compose up -d`

就这么简单！

---

## 🎯 快速部署流程

### 1. 连接 AutoDL 服务器

```bash
ssh -p <端口> root@<IP>
```

### 2. 安装 Docker（AutoDL 必需，仅首次）

```bash
# 一键安装 Docker
curl -fsSL https://get.docker.com | sh
systemctl start docker

# 安装 Docker Compose
curl -SL https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-linux-x86_64 \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# 安装 nvidia-docker (GPU 支持)
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  tee /etc/apt/sources.list.d/nvidia-docker.list
apt-get update && apt-get install -y nvidia-container-toolkit
systemctl restart docker
```

详细安装说明：**[AUTODL_DOCKER_INSTALL.md](AUTODL_DOCKER_INSTALL.md)**

### 3. 验证环境

```bash
# 检查 GPU
nvidia-smi

# 检查 Docker GPU 支持 (最重要!)
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

如果上面的命令成功显示 GPU 信息，说明环境就绪！✅

### 3. 克隆项目

```bash
cd /root
git clone <your-repo-url> electric-rag
cd electric-rag
```

### 4. 配置环境变量

```bash
cp .env.autodl .env
vim .env
```

**必须修改的配置**:
```bash
# MySQL 密码
MYSQL_PASSWORD=your_strong_password_2024

# 豆包 API Key (必填!)
ARK_API_KEY=your_doubao_api_key_here

# 安全密钥
SECRET_KEY=your_random_32_chars_secret_key
```

### 5. 一键启动

```bash
# 构建镜像 (首次约 20 分钟)
docker compose build

# 启动所有服务
docker compose up -d

# 查看日志
docker compose logs -f
```

### 6. 验证部署

```bash
# 等待 2-3 分钟后检查
docker compose ps

# 应该看到 9 个容器都是 "Up" 或 "Up (healthy)"
```

### 7. 访问服务

配置 AutoDL 端口映射后访问：
- Frontend: `https://<实例ID>-3000.sh.autodl.com`
- Backend API: `https://<实例ID>-8000.sh.autodl.com/docs`

默认账号: `admin` / `admin123`

---

## 🐛 常见问题速查

### Q1: 容器无法使用 GPU？

```bash
# 安装 nvidia-container-toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  tee /etc/apt/sources.list.d/nvidia-docker.list
apt-get update && apt-get install -y nvidia-container-toolkit
systemctl restart docker
docker compose restart
```

### Q2: 显存不足 (OOM)？

编辑 `.env`:
```bash
RERANKER_BATCH_SIZE=16  # 从 32 降到 16
ENABLE_SCANNED_PDF=false  # 禁用扫描版 PDF
```

### Q3: 模型下载失败？

```bash
# 在容器内设置 HuggingFace 镜像
docker compose exec backend bash
export HF_ENDPOINT=https://hf-mirror.com
```

### Q4: MySQL 连接失败？

```bash
# 等待 MySQL 启动完成 (约 30s)
docker compose logs mysql
docker compose exec mysql mysqladmin ping -h localhost -u root -p你的密码
```

### Q5: 如何停止/重启服务？

```bash
docker compose down        # 停止所有服务
docker compose up -d       # 重新启动
docker compose restart backend  # 重启单个服务
```

---

## 📚 详细文档

- **完整部署指南**: `docs/AUTODL_DEPLOYMENT.md` (包含详细说明和故障排查)
- **部署检查清单**: `docs/DEPLOYMENT_CHECKLIST.md` (70+ 检查项)
- **架构设计**: `docs/design.md`

---

## 💡 关键提示

1. **无需手动安装任何数据库或服务** - Docker Compose 全部自动完成
2. **首次启动会自动下载 ~3.3GB AI 模型** - 需要耐心等待 5-10 分钟
3. **GPU 必须能被 Docker 访问** - 验证 `docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi`
4. **数据是持久化的** - 存储在 Docker Volume，重启不会丢失
5. **所有服务都在容器内互联** - 无需配置外部网络连接

---

**部署成功后，系统会自动**:
- ✅ 创建 MySQL 数据库和表
- ✅ 创建默认管理员账号 (admin/admin123)
- ✅ 下载 BGE Embedding 模型
- ✅ 下载 Reranker 模型
- ✅ 初始化向量库和搜索引擎
- ✅ 启动 GPU 加速推理

祝部署顺利！ 🎉
