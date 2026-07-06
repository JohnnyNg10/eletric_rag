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

### 3. 初始化数据库

```bash
alembic upgrade head
```

### 4. 启动服务

开发模式：
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

生产模式：
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5. 启动 Celery Worker

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
- [业务流程图](../docs/architecture/flows/16-业务流程图.md)

## License

Private
