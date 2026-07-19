# 电力知识库 RAG 系统

工业级电力专业知识库 RAG 系统，回答来自中国国家标准（GB/DL/NB）和电力教材的专业问题，严格引用溯源（零臆测、可溯源、可校验）。

## 🚀 快速部署

### ⚠️ AutoDL 用户特别说明

**AutoDL 的实例本身就是一个 Docker 容器**（hostname 类似 `autodl-container-xxx`），不能在容器内再安装 Docker。

你有两个选择：

| 方案 | 说明 | 部署时间 | 推荐度 |
|------|------|---------|--------|
| **方案 A：原生部署** | 在 AutoDL 容器内直接部署 | 1-2 小时（首次） | ⭐⭐⭐⭐ |
| 方案 B：裸机实例 | 租用裸机实例使用 Docker | 20 分钟 | ⭐⭐⭐⭐⭐（需额外费用） |

**推荐使用方案 A**，详见：**[AutoDL 容器环境部署指南](docs/AUTODL_CONTAINER_DEPLOYMENT.md)**

---

### 方案 A：AutoDL 容器内原生部署

适合 AutoDL 标准实例（容器环境）：

```bash
# 1. 安装所有依赖服务（MySQL、Redis、Qdrant、ES、MinIO）
# 详细步骤见 docs/AUTODL_CONTAINER_DEPLOYMENT.md

# 2. 克隆项目
cd /root/autodl-tmp
git clone <your-repo-url> electric-rag && cd electric-rag

# 3. 配置环境
conda create -n electric-rag python=3.13 -y
conda activate electric-rag
cd backend && pip install uv && uv sync
cp .env.example .env && vim .env

# 4. 使用 screen 后台运行
screen -dmS backend bash -c "conda activate electric-rag && uvicorn app.main:app --host 0.0.0.0 --port 8000"
screen -dmS celery bash -c "conda activate electric-rag && celery -A app.tasks.celery_app worker --loglevel=info"
```

---

### 方案 B：Docker 部署（裸机或其他服务器）

适合有 Docker 环境的服务器：

### ❓ 需要手动安装 MySQL/Redis/Qdrant 吗？

**❌ 不需要！Docker Compose 会自动启动所有服务！**

本项目使用容器化部署，一条命令启动 9 个服务：

```bash
docker compose up -d
```

自动启动：MySQL、Redis、Qdrant、Elasticsearch、MinIO、MinerU (GPU)、Backend (GPU)、Celery Worker (GPU)、Frontend

### ⚠️ AutoDL 用户注意

AutoDL 默认**没有安装 Docker**，需要先安装（只需 5 分钟）：

```bash
# 一键安装 Docker + nvidia-docker
curl -fsSL https://get.docker.com | sh
apt-get install -y nvidia-container-toolkit
systemctl restart docker

# 验证 GPU Docker
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

详见：**[在 AutoDL 上安装 Docker](docs/AUTODL_DOCKER_INSTALL.md)**

### 📖 部署文档

| 文档 | 说明 | 适用场景 |
|------|------|---------|
| **[⚡ AutoDL 容器环境部署](docs/AUTODL_CONTAINER_DEPLOYMENT.md)** | **AutoDL 标准实例原生部署** | **AutoDL 用户必读** ⭐⭐⭐⭐⭐ |
| **[🔧 在裸机上安装 Docker](docs/AUTODL_DOCKER_INSTALL.md)** | 裸机实例 Docker 安装 | AutoDL 裸机用户 |
| **[🚀 5分钟快速开始](docs/QUICK_START.md)** | Docker 快速部署 | 已有 Docker 环境 |
| **[📘 完整部署指南](docs/AUTODL_DEPLOYMENT.md)** | Docker 详细步骤 | Docker 首次部署 |
| **[❓ Docker 部署 FAQ](docs/DOCKER_FAQ.md)** | Docker 常见问题 | 故障排查 |
| **[✅ 部署检查清单](docs/DEPLOYMENT_CHECKLIST.md)** | 70+ 检查项 | 生产部署验收 |

### ⚡ 完整部署步骤（AutoDL）

```bash
# 0. 安装 Docker (AutoDL 必需，仅首次)
curl -fsSL https://get.docker.com | sh
apt-get install -y nvidia-container-toolkit
systemctl restart docker

# 1. 克隆项目
git clone <your-repo-url> && cd electric-rag

# 2. 配置环境变量（修改 MySQL 密码、API Key）
cp .env.autodl .env && vim .env

# 3. 构建镜像
docker compose build

# 4. 启动服务
docker compose up -d

# 5. 查看日志
docker compose logs -f
```

等待 5-10 分钟，访问 `http://localhost:3000` 开始使用！

### 🎯 前置要求

| 要求 | 说明 | AutoDL 状态 |
|------|------|------------|
| GPU | Tesla V100/T4/A100, 16GB+ 显存 | ✅ 已有 |
| CUDA 12.1+ | GPU 驱动 | ✅ 已有 |
| Docker 20.10+ | 容器引擎 | ❌ **需要安装** |
| Docker Compose 2.0+ | 编排工具 | ❌ **需要安装** |
| nvidia-docker | GPU 容器运行时 | ❌ **需要安装** |

**AutoDL 用户必须先安装 Docker**，详见 [安装指南](docs/AUTODL_DOCKER_INSTALL.md)

**验证环境**:
```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

如果能看到 GPU 信息，说明环境就绪 ✅

---

## 📁 项目结构

```
electric-rag/
├── backend/              # FastAPI 后端 (Python 3.13)
│   ├── app/
│   │   ├── api/         # API 路由
│   │   ├── core/        # RAG 核心逻辑
│   │   ├── db/          # 数据库模型
│   │   ├── storage/     # 存储层封装
│   │   └── tasks/       # Celery 异步任务
│   └── pyproject.toml   # uv 依赖管理
├── frontend/            # React 前端
├── docker/              # Dockerfile 文件
│   ├── Dockerfile.backend    # Backend GPU 镜像
│   ├── Dockerfile.mineru     # MinerU GPU 镜像
│   └── mineru_api.py         # MinerU API 服务
├── docs/                # 文档
│   ├── QUICK_START.md        # 快速开始
│   ├── AUTODL_DEPLOYMENT.md  # 完整部署指南
│   ├── DOCKER_FAQ.md         # Docker FAQ
│   ├── design.md             # 系统设计
│   └── architecture/         # 架构文档
├── docker-compose.yml   # Docker Compose 配置
├── .env.autodl          # AutoDL 环境变量模板
└── CLAUDE.md            # 项目说明（给 Claude Code 使用）
```

---

## 🏗️ 系统架构

### RAG 查询流程

```
用户查询
    ↓
预处理 (术语归一化 + 模糊度评估)
    ↓
路由决策 (快车道 / 慢车道)
    ↓
快车道: 查询改写 → 三路召回 (Dense + Sparse + BM25) → 两阶段重排 (GPU) → 充分性检查
慢车道: 工具调用循环 (最多 3 步多跳推理)
    ↓
生成 (LLM 回答 + 引用 + 事实校验)
    ↓
返回结果
```

### 技术栈

**后端**:
- FastAPI (API 框架)
- SQLAlchemy (ORM)
- Celery (异步任务)
- uv (依赖管理)

**AI 模型**:
- Embedding: `bge-large-zh-v1.5` (Dense) + `efficient-splade` (Sparse)
- Reranker: `bge-reranker-large` (GPU 加速)
- LLM: 豆包 Pro / 通义千问

**存储**:
- MySQL 8.0 (元数据)
- Redis 7 (缓存 + 消息队列)
- Qdrant (向量数据库，混合检索)
- Elasticsearch 8 (BM25 全文检索)
- MinIO (PDF 对象存储)

**前端**:
- React 18
- TypeScript
- Vite

---

## 🔧 开发

### 本地开发（非 Docker）

**后端**:
```bash
cd backend
uv sync                          # 安装依赖
cp .env.example .env             # 配置环境变量
uvicorn app.main:app --reload    # 启动开发服务器
```

**前端**:
```bash
cd frontend
npm install
npm run dev
```

**Celery Worker**:
```bash
cd backend
celery -A app.tasks.celery_app worker --loglevel=info
```

### 代码风格

```bash
cd backend
black app/                       # 格式化
mypy app/                        # 类型检查
pytest                           # 运行测试
```

---

## 📊 性能指标

**硬件**: Tesla V100 16GB

- **Embedding**: ~200 docs/s
- **Reranker** (GPU): ~100 pairs/s (batch_size=32)
- **查询延迟**: 2-5s (检索 + 重排 + 生成)
- **显存占用**: 8-12GB

---

## 🔐 默认账号

- **用户名**: `admin`
- **密码**: `admin123`

⚠️ **生产环境请立即修改默认密码！**

---

## 📝 提交规范

遵循 Conventional Commits:

```
feat: 新功能
fix: Bug 修复
docs: 文档更新
refactor: 代码重构
chore: 构建/工具链更新
```

**Commit 消息使用英文，代码注释使用中文。**

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📄 许可证

MIT License

---

## 🆘 获取帮助

- **部署问题**: 查看 `docs/DOCKER_FAQ.md`
- **架构问题**: 查看 `docs/design.md` 和 `docs/architecture/`
- **API 文档**: 启动服务后访问 `http://localhost:8000/docs`

---

**部署愉快！🎉**
