# AutoDL 容器环境部署指南（无需 Docker）

## ⚠️ 重要提示

AutoDL 的实例**本身就是一个 Docker 容器**，不能在容器内再安装 Docker。你有两个选择：

1. **方案 A（推荐）**：在 AutoDL 容器内**原生部署**（不使用 Docker）
2. **方案 B**：联系 AutoDL 客服，使用宿主机的 Docker 或切换到裸机实例

本文档介绍**方案 A：原生部署**。

---

## 🚀 AutoDL 容器内原生部署

### 优势
- ✅ AutoDL 镜像已预装 CUDA、Python、conda
- ✅ 无需安装 Docker
- ✅ GPU 直接可用
- ✅ 适合 AutoDL 容器环境

### 架构
```
AutoDL 容器（你的实例）
├── MySQL          (apt 安装)
├── Redis          (apt 安装)
├── Qdrant         (二进制安装)
├── Elasticsearch  (apt 安装)
├── MinIO          (二进制安装)
├── Backend        (Python 运行)
├── Celery Worker  (Python 运行)
└── Frontend       (npm 运行)
```

---

## 📋 部署步骤

### 1. 连接到 AutoDL 实例

```bash
ssh -p <端口> root@<IP>
```

### 2. 验证环境

```bash
# 检查 GPU
nvidia-smi

# 检查 Python
python --version  # 应该 >= 3.10

# 检查 conda（AutoDL 通常预装）
conda --version
```

### 3. 更新系统并安装基础依赖

```bash
# 更新包列表
apt-get update

# 安装构建工具
apt-get install -y \
    build-essential \
    git \
    curl \
    wget \
    vim \
    htop \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1
```

### 4. 安装 MySQL

```bash
# 安装 MySQL 8.0
apt-get install -y mysql-server mysql-client libmysqlclient-dev

# 启动 MySQL（使用 service，不是 systemd）
service mysql start

# 设置开机启动
update-rc.d mysql defaults

# 配置 MySQL
mysql -u root <<EOF
CREATE DATABASE electric_rag CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'rag_user'@'localhost' IDENTIFIED BY 'electric_rag_2024';
GRANT ALL PRIVILEGES ON electric_rag.* TO 'rag_user'@'localhost';
FLUSH PRIVILEGES;
EOF

echo "MySQL 配置完成！"
```

### 5. 安装 Redis

```bash
# 安装 Redis
apt-get install -y redis-server

# 启动 Redis
service redis-server start

# 设置开机启动
update-rc.d redis-server defaults

# 验证
redis-cli ping
```

### 6. 安装 Qdrant

```bash
# 下载 Qdrant
mkdir -p /opt/qdrant
cd /opt/qdrant
wget https://github.com/qdrant/qdrant/releases/download/v1.7.4/qdrant-x86_64-unknown-linux-gnu.tar.gz
tar -xzf qdrant-x86_64-unknown-linux-gnu.tar.gz

# 创建数据目录
mkdir -p /data/qdrant

# 后台启动 Qdrant
nohup /opt/qdrant/qdrant --storage-path /data/qdrant > /var/log/qdrant.log 2>&1 &

# 验证（等待 5 秒后）
sleep 5
curl http://localhost:6333/

echo "Qdrant 启动成功！"
```

### 7. 安装 Elasticsearch

```bash
# 导入 GPG Key
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | apt-key add -

# 添加 APT 源
echo "deb https://artifacts.elastic.co/packages/8.x/apt stable main" | \
  tee /etc/apt/sources.list.d/elastic-8.x.list

# 安装
apt-get update
apt-get install -y elasticsearch

# 配置（单节点 + 禁用安全认证）
cat > /etc/elasticsearch/elasticsearch.yml <<EOF
cluster.name: electric-rag
node.name: node-1
path.data: /var/lib/elasticsearch
path.logs: /var/log/elasticsearch
network.host: 0.0.0.0
http.port: 9200
discovery.type: single-node
xpack.security.enabled: false
EOF

# 启动（使用 service）
service elasticsearch start

# 等待启动
echo "等待 Elasticsearch 启动（约 30 秒）..."
sleep 30

# 验证
curl http://localhost:9200/
```

### 8. 安装 MinIO

```bash
# 下载 MinIO
wget https://dl.min.io/server/minio/release/linux-amd64/minio -O /usr/local/bin/minio
chmod +x /usr/local/bin/minio

# 创建数据目录
mkdir -p /data/minio

# 后台启动 MinIO
nohup /usr/local/bin/minio server /data/minio \
  --console-address ":9001" \
  --address ":9000" > /var/log/minio.log 2>&1 &

# 等待启动
sleep 3

# 验证
curl http://localhost:9000/minio/health/live

echo "MinIO 启动成功！默认账号: minioadmin / minioadmin"
```

### 9. 克隆项目代码

```bash
# 进入工作目录（AutoDL 建议使用 /root/autodl-tmp，数据盘更大）
cd /root/autodl-tmp

# 克隆项目
git clone <your-repo-url> electric-rag
cd electric-rag
```

### 10. 配置 Python 环境

```bash
cd /root/autodl-tmp/electric-rag/backend

# 方法 1: 使用 conda（AutoDL 推荐）
conda create -n electric-rag python=3.13 -y
conda activate electric-rag

# 方法 2: 使用 venv（如果没有 conda）
python3 -m venv .venv
source .venv/bin/activate

# 安装 uv（现代包管理器，更快）
pip install uv

# 使用 uv 安装依赖
uv sync

# 或使用传统 pip（如果 uv 有问题）
# uv export --no-hashes > requirements.txt
# pip install -r requirements.txt
```

### 11. 配置环境变量

```bash
cd /root/autodl-tmp/electric-rag/backend
cp .env.example .env
vim .env
```

**关键配置** (`.env`):

```bash
# Database
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=rag_user
MYSQL_PASSWORD=electric_rag_2024
MYSQL_DB=electric_rag

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Elasticsearch
ES_HOSTS=http://localhost:9200
ELASTICSEARCH_HOST=localhost
ELASTICSEARCH_PORT=9200

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false

# LLM API（必填！）
ARK_API_KEY=your_doubao_api_key_here
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_MODEL=doubao-pro-32k

# GPU 配置
CUDA_VISIBLE_DEVICES=0
RERANKER_USE_GPU=true
RERANKER_BATCH_SIZE=32
OCR_USE_GPU=true

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# 模型自动下载
AUTO_DOWNLOAD_MODELS=true

# Security
SECRET_KEY=your_random_32_chars_secret_key_change_this
```

### 12. 安装 MinerU（可选）

```bash
# 激活环境
conda activate electric-rag  # 或 source .venv/bin/activate

# 安装 MinerU
pip install "magic-pdf[full]==0.7.0b1" --extra-index-url https://wheels.myhloli.com
```

### 13. 使用 screen 后台运行服务

AutoDL 容器内没有 systemd，使用 `screen` 管理后台进程。

```bash
# 安装 screen
apt-get install -y screen

# 创建 screen 会话并启动 Backend
screen -S backend
conda activate electric-rag
cd /root/autodl-tmp/electric-rag/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 按 Ctrl+A 然后按 D 退出 screen（保持后台运行）

# 创建 screen 会话并启动 Celery Worker
screen -S celery
conda activate electric-rag
cd /root/autodl-tmp/electric-rag/backend
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2

# 按 Ctrl+A 然后按 D 退出 screen
```

### 14. 启动 Frontend（可选）

```bash
# 安装 Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y nodejs

# 安装依赖
cd /root/autodl-tmp/electric-rag/frontend
npm install

# 后台运行（使用 screen）
screen -S frontend
npm run dev

# 按 Ctrl+A 然后按 D 退出 screen
```

### 15. 验证部署

```bash
# 检查所有服务
service mysql status
service redis-server status
ps aux | grep qdrant
ps aux | grep elasticsearch
ps aux | grep minio

# 检查 screen 会话
screen -ls

# 测试 API
curl http://localhost:8000/health

# 测试 GPU 使用
nvidia-smi

# 查看 Backend 日志
screen -r backend  # 查看后退出: Ctrl+A D
```

### 16. 配置 AutoDL 端口映射

在 AutoDL 控制台添加：

| 端口 | 服务 |
|------|------|
| 8000 | Backend API |
| 3000 | Frontend |

---

## 🔧 常用命令

### 管理 screen 会话

```bash
# 查看所有 screen 会话
screen -ls

# 重新进入某个会话
screen -r backend
screen -r celery
screen -r frontend

# 退出会话（保持后台运行）
Ctrl+A, 然后按 D

# 杀死某个会话
screen -S backend -X quit
```

### 重启服务

```bash
# 重启 MySQL
service mysql restart

# 重启 Redis
service redis-server restart

# 重启 Elasticsearch
service elasticsearch restart

# 重启 Backend（进入 screen）
screen -r backend
# Ctrl+C 停止，然后重新运行 uvicorn
```

### 查看日志

```bash
# Backend 日志（进入 screen 查看）
screen -r backend

# MySQL 日志
tail -f /var/log/mysql/error.log

# Elasticsearch 日志
tail -f /var/log/elasticsearch/electric-rag.log

# Qdrant 日志
tail -f /var/log/qdrant.log

# MinIO 日志
tail -f /var/log/minio.log
```

### 停止所有服务

```bash
# 停止 screen 会话
screen -S backend -X quit
screen -S celery -X quit
screen -S frontend -X quit

# 停止数据库服务
service mysql stop
service redis-server stop
service elasticsearch stop

# 停止 Qdrant 和 MinIO
pkill qdrant
pkill minio
```

---

## 🚀 一键启动脚本

创建启动脚本方便后续使用：

```bash
cat > /root/start-electric-rag.sh <<'EOF'
#!/bin/bash
set -e

echo "===== 启动基础服务 ====="
service mysql start
service redis-server start
service elasticsearch start

echo "===== 启动 Qdrant ====="
nohup /opt/qdrant/qdrant --storage-path /data/qdrant > /var/log/qdrant.log 2>&1 &

echo "===== 启动 MinIO ====="
nohup /usr/local/bin/minio server /data/minio \
  --console-address ":9001" \
  --address ":9000" > /var/log/minio.log 2>&1 &

echo "等待服务启动..."
sleep 5

echo "===== 启动 Backend (screen) ====="
screen -dmS backend bash -c "conda activate electric-rag && cd /root/autodl-tmp/electric-rag/backend && uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo "===== 启动 Celery Worker (screen) ====="
screen -dmS celery bash -c "conda activate electric-rag && cd /root/autodl-tmp/electric-rag/backend && celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2"

echo "===== 所有服务已启动 ====="
screen -ls
echo ""
echo "访问 Backend API: http://localhost:8000/docs"
echo "查看 Backend 日志: screen -r backend"
echo "查看 Celery 日志: screen -r celery"
EOF

chmod +x /root/start-electric-rag.sh
```

使用方法：

```bash
# 启动所有服务
/root/start-electric-rag.sh

# 查看运行状态
screen -ls
curl http://localhost:8000/health
```

---

## 📊 性能对比

| 部署方式 | 启动时间 | GPU 性能 | 维护难度 | AutoDL 兼容性 |
|---------|---------|---------|---------|--------------|
| AutoDL 原生部署 | 1-2 小时首次 | 100% | 中 | ✅ 完美支持 |
| Docker（理论） | 20 分钟 | 100% | 低 | ❌ 不支持 |

---

## 🐛 常见问题

### 1. MySQL 启动失败

```bash
service mysql status
tail -f /var/log/mysql/error.log

# 重置 MySQL
service mysql stop
rm -rf /var/lib/mysql/*
mysqld --initialize
service mysql start
```

### 2. Elasticsearch 内存不足

```bash
# 编辑 JVM 配置
vim /etc/elasticsearch/jvm.options

# 修改堆内存（根据实例内存调整）
-Xms2g
-Xmx2g

service elasticsearch restart
```

### 3. GPU 显存溢出

编辑 `.env`:
```bash
RERANKER_BATCH_SIZE=16  # 降低到 16 或 8
ENABLE_SCANNED_PDF=false
```

### 4. screen 会话丢失

AutoDL 实例重启后 screen 会话会丢失，使用启动脚本重新启动。

### 5. conda 环境问题

```bash
# 重新创建环境
conda remove -n electric-rag --all -y
conda create -n electric-rag python=3.13 -y
conda activate electric-rag
cd /root/autodl-tmp/electric-rag/backend
pip install uv && uv sync
```

---

## 🎉 总结

虽然 AutoDL 容器内不能使用 Docker，但原生部署同样可以实现完整功能：

- ✅ 所有 9 个服务都能正常运行
- ✅ GPU 直接可用，性能无损失
- ✅ 使用 screen 管理后台进程
- ✅ 一键启动脚本简化运维

**首次部署约需 1-2 小时，后续使用启动脚本只需 1 分钟！**

---

**部署完成！🚀**
