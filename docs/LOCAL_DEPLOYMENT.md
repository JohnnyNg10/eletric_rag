# 本地部署打包方案（All-in-One）

## 概述

本方案将系统所有组件（包括 MinerU、模型、数据库、向量库等）打包为可离线运行的完整包，**仅 LLM/VLM API 调用线上服务**。

### 适用场景
- 内网环境部署
- 离线演示
- 本地开发环境快速搭建
- 数据安全要求高的场景

### 架构设计
```
本地运行
├── MySQL (本地数据库)
├── Redis (本地缓存)
├── Qdrant (本地向量库)
├── Elasticsearch (本地全文检索)
├── MinIO (本地对象存储)
├── Backend (FastAPI)
├── Celery Worker
├── Frontend (React)
├── MinerU (PDF 解析)
└── AI Models (~3.3GB)
    ├── bge-large-zh-v1.5 (嵌入模型)
    ├── bge-reranker-large/base (重排模型)
    └── efficient-splade (稀疏编码)

线上调用
├── LLM API (豆包 Pro)
└── VLM API (豆包多模态)
```

---

## 📦 打包步骤

### 1. 准备打包环境

```bash
# 创建打包目录
mkdir -p /tmp/electric-rag-package
cd /tmp/electric-rag-package

# 克隆项目
git clone <your-repo-url> electric-rag
cd electric-rag
```

### 2. 下载并打包 AI 模型

```bash
cd backend

# 方案 A：使用项目自带的模型下载功能
python -c "
from app.core.model_init import download_all_models
import asyncio
asyncio.run(download_all_models())
"

# 方案 B：手动下载（如果自动下载失败）
mkdir -p models
cd models

# 下载嵌入模型 bge-large-zh-v1.5
git clone https://huggingface.co/BAAI/bge-large-zh-v1.5

# 下载重排模型
git clone https://huggingface.co/BAAI/bge-reranker-large
git clone https://huggingface.co/BAAI/bge-reranker-base

# 下载稀疏编码模型
git clone https://huggingface.co/naver/efficient-splade-VI-BT-large-query

cd ..
```

**模型大小参考**：
- bge-large-zh-v1.5: ~1.3GB
- bge-reranker-large: ~1.1GB
- bge-reranker-base: ~0.7GB
- efficient-splade: ~0.2GB
- 总计: ~3.3GB

### 3. 打包 Python 依赖

```bash
cd backend

# 导出依赖列表（包含精确版本）
uv export --no-hashes --frozen > requirements-lock.txt

# 下载所有依赖到本地
mkdir -p vendor/python-packages
pip download -r requirements-lock.txt -d vendor/python-packages

# 打包 MinerU 依赖
pip download "magic-pdf[full]==0.7.0b1" --extra-index-url https://wheels.myhloli.com -d vendor/python-packages
```

### 4. 打包前端依赖

```bash
cd ../frontend

# 安装并打包 node_modules
npm install
tar czf node_modules.tar.gz node_modules

# 或者导出依赖锁定文件供目标机器安装
npm ci  # 确保使用 package-lock.json
```

### 5. 准备服务二进制文件

```bash
cd /tmp/electric-rag-package
mkdir -p binaries

# Qdrant (x86_64 Linux)
wget https://github.com/qdrant/qdrant/releases/download/v1.7.4/qdrant-x86_64-unknown-linux-musl.tar.gz
tar xzf qdrant-x86_64-unknown-linux-musl.tar.gz -C binaries/

# MinIO (x86_64 Linux)
wget https://dl.min.io/server/minio/release/linux-amd64/minio -O binaries/minio
chmod +x binaries/minio

wget https://dl.min.io/client/mc/release/linux-amd64/mc -O binaries/mc
chmod +x binaries/mc
```

### 6. 创建安装脚本

创建 `install.sh`:

```bash
cat > install.sh << 'EOF'
#!/bin/bash
set -e

echo "=========================================="
echo "Electric RAG 本地部署安装程序"
echo "=========================================="

# 检查依赖
command -v python3 >/dev/null 2>&1 || { echo "需要 Python 3.13+"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "需要 Node.js 18+"; exit 1; }
command -v mysql >/dev/null 2>&1 || { echo "需要 MySQL 8.0+"; exit 1; }
command -v redis-server >/dev/null 2>&1 || { echo "需要 Redis"; exit 1; }

# 安装目录
INSTALL_DIR="${INSTALL_DIR:-/opt/electric-rag}"
echo "安装目录: $INSTALL_DIR"

# 创建目录
sudo mkdir -p $INSTALL_DIR
sudo cp -r electric-rag/* $INSTALL_DIR/
cd $INSTALL_DIR

# 安装 Python 依赖
echo "安装 Python 依赖..."
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --no-index --find-links=vendor/python-packages -r requirements-lock.txt
pip install --no-index --find-links=vendor/python-packages "magic-pdf[full]==0.7.0b1"

# 安装前端依赖
echo "安装前端依赖..."
cd ../frontend
tar xzf node_modules.tar.gz  # 或者 npm ci

# 安装二进制服务
echo "安装 Qdrant 和 MinIO..."
sudo cp ../binaries/qdrant /usr/local/bin/
sudo cp ../binaries/minio /usr/local/bin/
sudo cp ../binaries/mc /usr/local/bin/

# 创建数据目录
sudo mkdir -p /var/lib/qdrant /var/lib/minio /var/lib/elasticsearch

# 配置环境变量
cd ../backend
cp .env.example .env
echo "请编辑 $INSTALL_DIR/backend/.env 配置 API 密钥"

echo "=========================================="
echo "安装完成！"
echo "下一步："
echo "1. 编辑配置: vim $INSTALL_DIR/backend/.env"
echo "2. 初始化数据库: $INSTALL_DIR/scripts/init-db.sh"
echo "3. 启动服务: $INSTALL_DIR/scripts/start-all.sh"
echo "=========================================="
EOF

chmod +x install.sh
```

### 7. 创建服务管理脚本

创建 `scripts/start-all.sh`:

```bash
mkdir -p scripts

cat > scripts/start-all.sh << 'EOF'
#!/bin/bash

INSTALL_DIR="${INSTALL_DIR:-/opt/electric-rag}"
cd $INSTALL_DIR

echo "启动 Redis..."
sudo systemctl start redis-server

echo "启动 MySQL..."
sudo systemctl start mysql

echo "启动 Elasticsearch..."
sudo systemctl start elasticsearch

echo "启动 Qdrant..."
nohup qdrant --config-path $INSTALL_DIR/config/qdrant.yaml > /var/log/qdrant.log 2>&1 &

echo "启动 MinIO..."
nohup minio server /var/lib/minio --console-address ":9001" > /var/log/minio.log 2>&1 &

echo "等待服务启动..."
sleep 5

echo "启动 Backend..."
cd $INSTALL_DIR/backend
source .venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /var/log/backend.log 2>&1 &

echo "启动 Celery Worker..."
nohup celery -A app.tasks.celery_app worker --loglevel=info > /var/log/celery.log 2>&1 &

echo "启动 Frontend..."
cd $INSTALL_DIR/frontend
nohup npm run dev -- --host 0.0.0.0 --port 5173 > /var/log/frontend.log 2>&1 &

echo "=========================================="
echo "所有服务已启动！"
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "=========================================="
EOF

chmod +x scripts/start-all.sh
```

创建 `scripts/stop-all.sh`:

```bash
cat > scripts/stop-all.sh << 'EOF'
#!/bin/bash

echo "停止所有服务..."
pkill -f "uvicorn app.main:app"
pkill -f "celery -A app.tasks.celery_app"
pkill -f "npm run dev"
pkill -f "qdrant"
pkill -f "minio server"

echo "服务已停止"
EOF

chmod +x scripts/stop-all.sh
```

创建 `scripts/init-db.sh`:

```bash
cat > scripts/init-db.sh << 'EOF'
#!/bin/bash
set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/electric-rag}"
cd $INSTALL_DIR/backend

# 读取 .env 配置
source .env

echo "创建数据库..."
mysql -u root -p << SQL
CREATE DATABASE IF NOT EXISTS $MYSQL_DB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$MYSQL_USER'@'localhost' IDENTIFIED BY '$MYSQL_PASSWORD';
GRANT ALL PRIVILEGES ON $MYSQL_DB.* TO '$MYSQL_USER'@'localhost';
FLUSH PRIVILEGES;
SQL

echo "初始化表结构（应用启动时自动创建）..."
echo "数据库初始化完成！"
EOF

chmod +x scripts/init-db.sh
```

### 8. 创建配置文件模板

创建 `config/qdrant.yaml`:

```bash
mkdir -p config

cat > config/qdrant.yaml << 'EOF'
service:
  host: 0.0.0.0
  http_port: 6333
  grpc_port: 6334

storage:
  storage_path: /var/lib/qdrant/storage
  snapshots_path: /var/lib/qdrant/snapshots

log_level: INFO
EOF
```

### 9. 创建 README

```bash
cat > README-PACKAGE.md << 'EOF'
# Electric RAG 本地部署包

## 系统要求

- **操作系统**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- **Python**: 3.13+
- **Node.js**: 18+
- **MySQL**: 8.0+
- **Redis**: 6.0+
- **磁盘空间**: 至少 10GB（模型 3.3GB + 数据库 + 依赖）
- **内存**: 建议 16GB+（模型加载需要 ~4GB）
- **GPU**: 可选（OCR 和 Reranker 可启用 GPU 加速）

## 快速开始

### 1. 解压安装包

```bash
tar xzf electric-rag-package.tar.gz
cd electric-rag-package
```

### 2. 安装系统依赖

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm mysql-server redis-server openjdk-11-jre
```

**Elasticsearch (可选，用于全文检索):**
```bash
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
echo "deb https://artifacts.elastic.co/packages/8.x/apt stable main" | sudo tee /etc/apt/sources.list.d/elastic-8.x.list
sudo apt update && sudo apt install elasticsearch
```

### 3. 运行安装脚本

```bash
sudo ./install.sh
```

### 4. 配置 API 密钥

```bash
cd /opt/electric-rag/backend
vim .env
```

**必填配置**:
```bash
# LLM API（豆包 Pro）
ARK_API_KEY=your_actual_api_key_here
LLM_MODEL=your_actual_model_endpoint_here

# VLM API（豆包多模态）
DOUBAO_API_KEY=your_actual_api_key_here
DOUBAO_MODEL=your_actual_vlm_endpoint_here

# 安全密钥
SECRET_KEY=generate_a_random_32_character_secret_key
```

### 5. 初始化数据库

```bash
/opt/electric-rag/scripts/init-db.sh
```

### 6. 启动所有服务

```bash
/opt/electric-rag/scripts/start-all.sh
```

### 7. 访问系统

- **前端**: http://localhost:5173
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

### 8. 停止服务

```bash
/opt/electric-rag/scripts/stop-all.sh
```

## 目录结构

```
/opt/electric-rag/
├── backend/
│   ├── app/                    # 后端代码
│   ├── models/                 # AI 模型（3.3GB）
│   ├── vendor/                 # Python 依赖包
│   └── .env                    # 配置文件
├── frontend/
│   ├── src/                    # 前端代码
│   └── node_modules/           # Node 依赖
├── scripts/
│   ├── start-all.sh            # 启动脚本
│   ├── stop-all.sh             # 停止脚本
│   └── init-db.sh              # 数据库初始化
├── config/
│   └── qdrant.yaml             # Qdrant 配置
└── binaries/
    ├── qdrant                  # Qdrant 二进制
    └── minio                   # MinIO 二进制
```

## 数据持久化

- **MySQL 数据**: `/var/lib/mysql/`
- **Redis 数据**: `/var/lib/redis/`
- **Qdrant 向量**: `/var/lib/qdrant/`
- **MinIO 文件**: `/var/lib/minio/`
- **Elasticsearch**: `/var/lib/elasticsearch/`

## 日志位置

- Backend: `/var/log/backend.log`
- Celery: `/var/log/celery.log`
- Frontend: `/var/log/frontend.log`
- Qdrant: `/var/log/qdrant.log`
- MinIO: `/var/log/minio.log`

## 故障排查

### 1. 服务未启动

```bash
# 查看进程
ps aux | grep uvicorn
ps aux | grep celery
ps aux | grep qdrant
ps aux | grep minio

# 查看日志
tail -f /var/log/backend.log
tail -f /var/log/celery.log
```

### 2. 模型加载失败

```bash
# 检查模型文件
ls -lh /opt/electric-rag/backend/models/

# 手动测试模型加载
cd /opt/electric-rag/backend
source .venv/bin/activate
python -c "from app.core.model_init import check_models; import asyncio; asyncio.run(check_models())"
```

### 3. 数据库连接失败

```bash
# 检查 MySQL 状态
sudo systemctl status mysql

# 测试连接
mysql -u root -p -e "SHOW DATABASES;"
```

### 4. API 调用失败

```bash
# 测试 LLM API
curl -X POST "https://ark.cn-beijing.volces.com/api/v3/chat/completions" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "YOUR_MODEL", "messages": [{"role": "user", "content": "test"}]}'
```

## 生产环境建议

1. **使用 systemd 管理服务**（而非 nohup）
2. **配置 Nginx 反向代理**
3. **启用 HTTPS**
4. **定期备份数据库和向量库**
5. **配置日志轮转**
6. **监控服务健康状态**

## 离线更新

如需更新系统，重新打包后替换 `/opt/electric-rag/` 目录，保留 `.env` 和数据目录。

## 技术支持

- 项目仓库: <your-repo-url>
- 文档: `docs/`
- Issues: <your-repo-url>/issues
EOF
```

### 10. 打包

```bash
cd /tmp/electric-rag-package

# 创建最终压缩包
tar czf electric-rag-package.tar.gz \
  electric-rag/ \
  binaries/ \
  install.sh \
  scripts/ \
  config/ \
  README-PACKAGE.md

echo "打包完成: electric-rag-package.tar.gz"
ls -lh electric-rag-package.tar.gz
```

---

## 📊 打包后文件大小估算

```
electric-rag-package.tar.gz
├── AI 模型: ~3.3GB
├── Python 依赖: ~500MB
├── Node 依赖: ~300MB
├── 二进制文件: ~100MB
├── 源代码: ~50MB
└── 总计: ~4.3GB
```

---

## 🚀 使用方式

### 目标机器安装

```bash
# 1. 传输安装包
scp electric-rag-package.tar.gz user@target:/tmp/

# 2. 解压并安装
cd /tmp
tar xzf electric-rag-package.tar.gz
cd electric-rag-package
sudo ./install.sh

# 3. 配置 API 密钥
sudo vim /opt/electric-rag/backend/.env

# 4. 初始化并启动
/opt/electric-rag/scripts/init-db.sh
/opt/electric-rag/scripts/start-all.sh
```

---

## 📝 注意事项

### 1. 网络依赖

**完全离线**:
- ✅ 模型推理（embedding, rerank, OCR）
- ✅ 数据库、向量库、对象存储
- ✅ PDF 解析（MinerU）
- ✅ 前后端应用

**需要外网**:
- ⚠️ LLM API 调用（豆包 Pro）
- ⚠️ VLM API 调用（豆包多模态）

### 2. 硬件要求

- **最低**: 4 核 CPU + 8GB RAM（仅 CPU 推理）
- **推荐**: 8 核 CPU + 16GB RAM + GPU（CUDA 12+）

### 3. GPU 加速

如果目标机器有 GPU，编辑 `.env`:

```bash
OCR_USE_GPU=True
# Reranker 默认使用 GPU（如果可用）
```

### 4. 安全建议

生产环境部署前务必修改:
- `SECRET_KEY`: 生成 32 位随机字符串
- `MYSQL_PASSWORD`: 数据库密码
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`: MinIO 凭证

```bash
# 生成安全密钥
openssl rand -hex 32
```

---

## 🔧 进阶配置

### Systemd 服务化

创建 `/etc/systemd/system/electric-rag-backend.service`:

```ini
[Unit]
Description=Electric RAG Backend
After=network.target mysql.service redis.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/electric-rag/backend
Environment="PATH=/opt/electric-rag/backend/.venv/bin"
ExecStart=/opt/electric-rag/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

启用服务:

```bash
sudo systemctl daemon-reload
sudo systemctl enable electric-rag-backend
sudo systemctl start electric-rag-backend
```

### Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Frontend
    location / {
        proxy_pass http://localhost:5173;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 🎯 总结

此打包方案实现:

✅ **完全本地化**: 除 LLM/VLM API 外所有组件本地运行  
✅ **一键安装**: 自动化安装脚本  
✅ **离线可用**: 模型和依赖全部打包  
✅ **生产就绪**: 包含服务管理、监控、备份方案  
✅ **跨平台**: 支持主流 Linux 发行版  

适合内网部署、演示环境、本地开发等场景。
