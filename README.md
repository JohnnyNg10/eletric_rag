# 电力知识库 RAG 系统

工业级电力专业知识库 RAG 系统，回答来自中国国家标准（GB/DL/NB）和电力教材的专业问题，严格引用溯源（零臆测、可溯源、可校验）。

---

## 快速部署

### 系统要求

| 要求 | 说明 |
|------|------|
| GPU | NVIDIA 16GB+ 显存（推荐 V100 / A10 / RTX 3090） |
| CUDA | 12.1+ |
| Docker | 20.10+ |
| Docker Compose | v2+ |
| NVIDIA Container Toolkit | 用于 GPU 支持 |
| 磁盘 | 50GB+ |

### 一键部署

```bash
# 1. 克隆项目
git clone https://github.com/JohnnyNg10/eletric_rag.git
cd eletric_rag

# 2. 配置环境变量
cp .env.example .env
vim .env  # 填写 API Key、密码等必填项

# 3. 启动所有服务
docker compose up -d

# 4. 查看状态
docker compose ps
```

自动启动 9 个服务：MySQL、Redis、Qdrant、Elasticsearch、MinIO、MinerU (GPU)、Backend (GPU)、Celery Worker、Frontend

> **首次启动注意**：MinerU 会自动下载 VLM 模型（约 15GB），需要 30-60 分钟。
> 查看进度：`docker logs -f electric-rag-mineru`

### 必填配置项

编辑 `.env` 文件，以下项必须填写：

```bash
ARK_API_KEY=your_doubao_api_key        # 豆包 API Key
LLM_MODEL=your_llm_model_endpoint      # LLM 模型端点
DOUBAO_API_KEY=your_doubao_api_key     # VLM API Key
DOUBAO_MODEL=your_vlm_model_endpoint   # VLM 模型端点
SECRET_KEY=                            # 运行 openssl rand -hex 32 生成
MYSQL_PASSWORD=your_strong_password    # 数据库密码
```

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端界面 | http://服务器IP:5173 |
| 后端 API | http://服务器IP:8000 |
| API 文档 | http://服务器IP:8000/docs |

### 默认账号

- **用户名**：`admin`
- **密码**：`admin123`

⚠️ 生产环境请立即修改默认密码！

---

## 部署文档

| 文档 | 说明 |
|------|------|
| [服务器部署指南](docs/SERVER_DEPLOYMENT.md) | 完整部署步骤、故障排查、安全建议 |
| [Docker 一体化打包](docs/DOCKER_ALL_IN_ONE.md) | 离线打包交付方案 |

---

## 项目结构

```
eletric_rag/
├── backend/              # FastAPI 后端 (Python 3.13)
│   ├── app/
│   │   ├── api/          # API 路由
│   │   ├── core/         # RAG 核心逻辑（召回、重排、生成）
│   │   ├── db/           # 数据库模型
│   │   ├── storage/      # 存储层封装
│   │   └── tasks/        # Celery 异步任务
│   └── pyproject.toml    # uv 依赖管理
├── frontend/             # React 前端
├── MinerU/               # MinerU PDF 解析服务
├── docker/               # Dockerfile 文件
├── docs/                 # 文档
├── docker-compose.yml    # Docker Compose 配置
└── .env.example          # 环境变量模板
```

---

## 系统架构

### RAG 查询流程

```
用户查询
    ↓
预处理（术语归一化 + 模糊度评估）
    ↓
路由决策（快车道 / 慢车道）
    ↓
快车道：查询改写 → 三路召回（Dense + Sparse + BM25）→ 两阶段重排（GPU）→ 充分性检查
慢车道：工具调用循环（最多 3 步多跳推理）
    ↓
生成（LLM 回答 + 引用 + 事实校验）
    ↓
返回结果
```

### 技术栈

**后端**：FastAPI、SQLAlchemy、Celery、uv

**AI 模型**：
- Embedding：`bge-large-zh-v1.5`（Dense）+ `efficient-splade`（Sparse）
- Reranker：`bge-reranker-large`（GPU 加速）
- LLM：豆包 Pro / 通义千问
- PDF 解析：MinerU VLM 模式（本地 GPU 推理）

**存储**：MySQL 8.0、Redis 7、Qdrant、Elasticsearch 8、MinIO

**前端**：React 18、TypeScript、Vite

---

## 本地开发

**后端**：
```bash
cd backend
uv sync
cp .env.example .env
uvicorn app.main:app --reload
```

**前端**：
```bash
cd frontend
npm install
npm run dev
```

**Celery Worker**：
```bash
cd backend
celery -A app.tasks.celery_app worker --loglevel=info
```

**代码检查**：
```bash
cd backend
black app/      # 格式化
mypy app/       # 类型检查
```

---

## 提交规范

遵循 Conventional Commits，消息使用英文，代码注释使用中文：

```
feat: 新功能
fix: Bug 修复
docs: 文档更新
refactor: 代码重构
chore: 构建/工具链更新
```

---

## 获取帮助

- **部署问题**：查看 [服务器部署指南](docs/SERVER_DEPLOYMENT.md)
- **架构问题**：查看 `docs/design.md` 和 `docs/architecture/`
- **API 文档**：启动服务后访问 `http://localhost:8000/docs`
- **Issues**：https://github.com/JohnnyNg10/eletric_rag/issues
