# Electric RAG Backend

工业级电力专业知识库RAG系统 - 后端服务

## 技术栈

- **框架**: FastAPI
- **数据库**: MySQL 8.0, Redis 7.x
- **向量库**: Qdrant
- **全文检索**: Elasticsearch 8.x
- **对象存储**: MinIO
- **任务队列**: Celery
- **AI模型**: bge-large-zh-v1.5, bge-reranker-large

## 快速开始

### 1. 安装依赖

使用 uv（推荐）：
```bash
uv sync
```

或使用 pip：
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入实际配置
```

### 3. 下载AI模型（首次运行）

系统启动时会自动检查并下载所需的AI模型（约3.3GB）。

**国内网络环境需要设置代理**：
```bash
# Windows
set HTTP_PROXY=http://127.0.0.1:7897
set HTTPS_PROXY=http://127.0.0.1:7897

# Linux/Mac
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897
```

**测试模型下载**（可选）：
```bash
python test_model_download.py
```

详细说明参考：[模型自动下载指南](../docs/architecture/backend/07-模型自动下载指南.md)

### 4. 初始化数据库

```bash
alembic upgrade head
```

### 5. 启动服务

**激活虚拟环境**：
```bash
# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

**开发模式**：
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**生产模式**：
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 6. 启动 Celery Worker

**确保虚拟环境已激活**，然后：
```bash
celery -A app.tasks.celery_app worker --loglevel=info
```

## 项目结构

```
backend/
├── app/
│   ├── api/              # API路由层
│   ├── core/             # 核心业务逻辑
│   ├── db/               # 数据库层
│   ├── storage/          # 存储访问层
│   ├── schemas/          # Pydantic模型
│   ├── services/         # 业务服务层
│   ├── utils/            # 工具模块
│   └── tasks/            # Celery任务
├── tests/                # 测试
└── alembic/              # 数据库迁移
```

## API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 开发规范

### 代码格式化

```bash
black app/
```

### 类型检查

```bash
mypy app/
```

### 运行测试

```bash
pytest
```

### 测试覆盖率

```bash
pytest --cov=app --cov-report=html
```

## 架构文档

详细架构设计请参考：
- [系统总体架构](../docs/architecture/01-系统总体架构.md)
- [后端架构设计](../docs/architecture/backend/04-后端架构设计.md)
- [模型自动下载指南](../docs/architecture/backend/07-模型自动下载指南.md)
- [业务流程图](../docs/architecture/flows/17-业务流程图.md)
- [模型使用总结](../docs/architecture/modules/22-模型使用总结.md)

## 实施日志

- [数据库自动建表完成报告](../docs/logs/02-数据库自动建表完成报告.md)
- [数据库初始化详细日志](../docs/logs/03-数据库初始化详细日志.md)

## License

Private
