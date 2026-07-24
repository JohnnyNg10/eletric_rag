# 服务器部署指南

本文档介绍如何在支持 Docker + GPU 的服务器上部署 Electric RAG 系统。

---

## 系统要求

### 硬件要求
- **GPU**：至少 16GB 显存（推荐 NVIDIA V100 / A10 / RTX 3090 / 4090）
- **内存**：建议 16GB+
- **磁盘**：至少 50GB 可用空间
  - Docker 镜像：~22GB
  - VLM 模型：~15GB
  - 数据存储：预留 10GB+

### 软件要求
- **操作系统**：Ubuntu 20.04+ / CentOS 7+ / Debian 11+
- **Docker**：20.10+
- **Docker Compose**：v2+
- **NVIDIA Driver**：支持 CUDA 12.1+
- **NVIDIA Container Toolkit**：用于 GPU 支持

---

## 一、环境准备

### 1.1 安装 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 重新登录使权限生效
exit
```

### 1.2 安装 NVIDIA Container Toolkit

```bash
# 添加仓库
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 安装
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 配置 Docker
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 测试 GPU 访问
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### 1.3 验证环境

```bash
# 检查 Docker 版本
docker --version  # 应该 >= 20.10

# 检查 Docker Compose 版本
docker compose version  # 应该 >= v2

# 检查 GPU 是否可访问
nvidia-smi
```

---

## 二、部署步骤

### 2.1 克隆代码

```bash
# SSH 方式（推荐，需配置 SSH Key）
git clone git@github.com:JohnnyNg10/eletric_rag.git

# HTTPS 方式
git clone https://github.com/JohnnyNg10/eletric_rag.git

cd eletric_rag
```

### 2.2 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置文件
vim .env  # 或使用 nano .env
```

**必须填写的配置项**：

```bash
# ==================== LLM API ====================
ARK_API_KEY=your_api_key_here                 # ⚠️ 必填：豆包 API Key
LLM_MODEL=your_model_endpoint_here            # ⚠️ 必填：端点 ID，如 ep-20260717095008-xxxxx

# ==================== VLM API ====================
DOUBAO_API_KEY=your_api_key_here              # ⚠️ 启用扫描版 PDF 需填写（与 ARK_API_KEY 相同）
DOUBAO_MODEL=your_vlm_model_endpoint_here     # ⚠️ VLM 端点 ID，如 ep-20260717161647-xxxxx

# ==================== Security ====================
SECRET_KEY=your_random_32_chars_secret_key    # ⚠️ 必填：运行 openssl rand -hex 32 生成

# ==================== Database ====================
MYSQL_PASSWORD=your_strong_password           # ⚠️ 建议修改默认密码
MINIO_SECRET_KEY=your_strong_minio_password   # ⚠️ 建议修改
```

**可选配置项**（保持默认即可）：

```bash
# GPU 配置（根据你的 GPU 数量调整）
CUDA_VISIBLE_DEVICES=0                        # 使用第 1 块 GPU
RERANKER_USE_GPU=true
RERANKER_BATCH_SIZE=32                        # V100 16GB 可用 32，显存不足改为 16

# 扫描版 PDF 处理（VLM 功能，消耗显存）
ENABLE_SCANNED_PDF=true
ENABLE_IMAGE_SEARCH=true
ENABLE_VLM_DESCRIPTION=true
```

生成安全密钥：
```bash
openssl rand -hex 32
```

### 2.3 启动服务

```bash
# 后台启动所有服务
docker compose up -d

# 查看启动日志
docker compose logs -f
```

**⏳ 首次启动注意事项**：

MinerU 服务首次启动需要下载 VLM 模型（约 15GB），可能需要 **30-60 分钟**。

查看 MinerU 模型下载进度：
```bash
docker logs -f electric-rag-mineru
```

看到以下日志表示模型下载完成：
```
模型下载完成
启动 MinerU API 服务 (port 8001)...
```

### 2.4 验证部署

等待所有服务启动后（约 3-5 分钟，首次启动需等 MinerU 下载完模型）：

```bash
# 查看服务状态
docker compose ps

# 应该看到所有服务都是 Up (healthy)
```

访问以下地址验证：

- **前端界面**：http://你的服务器IP:5173
- **后端 API 文档**：http://你的服务器IP:8000/docs
- **MinerU 健康检查**：http://你的服务器IP:8001/health

---

## 三、常用操作

### 3.1 查看服务状态

```bash
# 查看所有容器状态
docker compose ps

# 查看特定服务日志
docker compose logs -f backend      # 后端日志
docker compose logs -f celery       # 异步任务日志
docker compose logs -f mineru       # MinerU 日志
docker compose logs -f frontend     # 前端日志
```

### 3.2 重启服务

```bash
# 重启所有服务
docker compose restart

# 重启单个服务
docker compose restart backend
docker compose restart mineru
```

### 3.3 停止服务

```bash
# 停止所有服务（保留数据）
docker compose down

# 停止并删除所有数据（⚠️ 危险操作）
docker compose down -v
```

### 3.4 更新代码

```bash
# 拉取最新代码
git pull origin master

# 重新构建并启动（如果 Dockerfile 有更新）
docker compose up -d --build

# 如果只是代码更新，重启即可
docker compose restart backend celery
```

### 3.5 查看资源占用

```bash
# GPU 使用情况
nvidia-smi

# 容器资源占用
docker stats

# 磁盘占用
docker system df
```

---

## 四、故障排查

### 4.1 MinerU 一直显示 unhealthy

**原因**：首次启动正在下载 VLM 模型（15GB）

**解决**：
```bash
# 查看下载进度
docker logs -f electric-rag-mineru

# 如果看到 "模型下载完成"，等待几分钟即可恢复健康
```

### 4.2 GPU 不可用

**检查**：
```bash
# 1. 检查 nvidia-smi 是否正常
nvidia-smi

# 2. 检查 Docker 是否能访问 GPU
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# 3. 检查容器内 GPU
docker exec -it electric-rag-mineru nvidia-smi
```

**解决**：如果 Docker 无法访问 GPU，重新安装 NVIDIA Container Toolkit（见 1.2 节）

### 4.3 端口被占用

**检查端口占用**：
```bash
netstat -tunlp | grep -E "8000|5173|8001|3306|6379|6333|9200|9000"
```

**解决**：修改 `docker-compose.yml` 中的端口映射：
```yaml
services:
  backend:
    ports:
      - "8080:8000"  # 改为 8080 端口
```

### 4.4 内存不足

**症状**：Elasticsearch 启动失败或 OOM

**解决**：调整 Elasticsearch 内存限制
```bash
# 编辑 docker-compose.yml
vim docker-compose.yml

# 修改 ES 配置
elasticsearch:
  environment:
    - "ES_JAVA_OPTS=-Xms256m -Xmx256m"  # 从 512m 降低到 256m
```

### 4.5 API 调用失败

**检查**：
```bash
# 1. 确认 .env 中 API Key 是否正确
cat .env | grep API_KEY

# 2. 测试 API 连接
curl -X POST "https://ark.cn-beijing.volces.com/api/v3/chat/completions" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "YOUR_MODEL", "messages": [{"role": "user", "content": "test"}]}'
```

### 4.6 模型下载速度慢

**使用 ModelScope 镜像**（国内服务器）：

```bash
# 进入 MinerU 容器
docker exec -it electric-rag-mineru bash

# 设置环境变量使用 ModelScope
export HF_ENDPOINT=https://hf-mirror.com

# 或者直接使用 ModelScope SDK
# （MinerU 已内置 modelscope 支持）
```

---

## 五、性能优化

### 5.1 调整并发数

根据服务器配置调整并发：

```yaml
# docker-compose.yml
backend:
  command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

celery:
  command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
```

### 5.2 限制容器资源

```yaml
backend:
  deploy:
    resources:
      limits:
        cpus: '4'
        memory: 8G
```

### 5.3 使用 Redis 持久化

```yaml
redis:
  command: redis-server --appendonly yes --save 60 1
```

---

## 六、数据备份

### 6.1 备份数据卷

```bash
# 创建备份目录
mkdir -p ~/backups/electric-rag

# 备份 MySQL
docker run --rm \
  -v electric-rag_mysql_data:/data \
  -v ~/backups/electric-rag:/backup \
  alpine tar czf /backup/mysql_backup_$(date +%Y%m%d).tar.gz -C /data .

# 备份 Qdrant
docker run --rm \
  -v electric-rag_qdrant_data:/data \
  -v ~/backups/electric-rag:/backup \
  alpine tar czf /backup/qdrant_backup_$(date +%Y%m%d).tar.gz -C /data .

# 备份 MinIO
docker run --rm \
  -v electric-rag_minio_data:/data \
  -v ~/backups/electric-rag:/backup \
  alpine tar czf /backup/minio_backup_$(date +%Y%m%d).tar.gz -C /data .
```

### 6.2 恢复数据

```bash
# 恢复 MySQL
docker run --rm \
  -v electric-rag_mysql_data:/data \
  -v ~/backups/electric-rag:/backup \
  alpine sh -c "cd /data && tar xzf /backup/mysql_backup_20260724.tar.gz"
```

---

## 七、安全建议

**生产环境部署必须**：

1. **修改默认密码**：
   ```bash
   MYSQL_PASSWORD=your_strong_password
   MINIO_SECRET_KEY=your_strong_secret
   ```

2. **使用强随机密钥**：
   ```bash
   SECRET_KEY=$(openssl rand -hex 32)
   ```

3. **启用防火墙**：
   ```bash
   # 只开放必要端口
   sudo ufw allow 22/tcp    # SSH
   sudo ufw allow 5173/tcp  # Frontend
   sudo ufw allow 8000/tcp  # Backend API
   sudo ufw enable
   ```

4. **使用反向代理 + HTTPS**：
   - 推荐使用 Nginx + Let's Encrypt 配置 SSL
   - 不直接暴露 Docker 容器端口

5. **定期更新**：
   ```bash
   git pull origin master
   docker compose up -d --build
   ```

6. **定期备份数据卷**（见第六节）

---

## 八、卸载

```bash
# 停止并删除所有容器
docker compose down

# 删除数据卷（⚠️ 会删除所有数据）
docker volume rm electric-rag_mysql_data \
  electric-rag_redis_data \
  electric-rag_qdrant_data \
  electric-rag_es_data \
  electric-rag_minio_data \
  electric-rag_mineru_cache

# 删除镜像
docker rmi electric-rag-backend:latest \
  electric-rag-frontend:latest \
  electric-rag-mineru:latest

# 删除代码
cd .. && rm -rf eletric_rag
```

---

## 九、推荐服务器配置

### 开发测试环境
- **GPU**：RTX 3060 (12GB) / T4 (16GB)
- **内存**：16GB
- **磁盘**：100GB SSD
- **成本**：约 $0.1-0.3/小时（Vast.ai）

### 生产环境
- **GPU**：V100 (16GB) / A10 (24GB) / RTX 3090 (24GB)
- **内存**：32GB+
- **磁盘**：200GB+ SSD
- **成本**：约 $1-3/小时（阿里云/腾讯云按量付费）

---

## 十、技术支持

- **文档**：https://github.com/JohnnyNg10/eletric_rag
- **Issues**：https://github.com/JohnnyNg10/eletric_rag/issues

---

## 附录：快速启动脚本

创建 `deploy.sh`：

```bash
#!/bin/bash
set -e

echo "=========================================="
echo "  Electric RAG 服务器部署"
echo "=========================================="

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装"
    echo "运行: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

# 检查 GPU
if ! nvidia-smi &> /dev/null; then
    echo "⚠️  警告：未检测到 NVIDIA GPU，MinerU 将无法使用 VLM 模式"
fi

# 检查配置文件
if [ ! -f .env ]; then
    echo "📝 创建配置文件..."
    cp .env.example .env
    echo ""
    echo "⚠️  请编辑 .env 文件，填写必填项："
    echo "   - ARK_API_KEY"
    echo "   - LLM_MODEL"
    echo "   - DOUBAO_API_KEY"
    echo "   - DOUBAO_MODEL"
    echo "   - SECRET_KEY (运行: openssl rand -hex 32)"
    echo ""
    read -p "配置完成后按 Enter 继续..." -r
fi

# 启动服务
echo "🚀 启动所有服务..."
docker compose up -d

echo ""
echo "=========================================="
echo "✅ 部署完成！"
echo "=========================================="
echo ""
echo "📌 访问地址:"
echo "   前端:      http://$(hostname -I | awk '{print $1}'):5173"
echo "   后端 API:  http://$(hostname -I | awk '{print $1}'):8000"
echo "   API 文档:  http://$(hostname -I | awk '{print $1}'):8000/docs"
echo ""
echo "⏳ 首次启动提示:"
echo "   MinerU 正在下载 VLM 模型（约 15GB），需要 30-60 分钟"
echo "   查看进度: docker logs -f electric-rag-mineru"
echo ""
echo "📊 查看状态: docker compose ps"
echo "📝 查看日志: docker compose logs -f"
echo "🛑 停止服务: docker compose down"
```

```bash
chmod +x deploy.sh
./deploy.sh
```
