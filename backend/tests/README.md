# 测试目录说明

## 目录结构

```
tests/
├── conftest.py                          # Pytest 配置（路径、编码、fixtures）
├── fix_imports.py                       # 导入路径修复脚本（仅维护用）
│
├── test_core/                           # 核心层测试
│   ├── preprocessing/                   # 预处理层
│   │   ├── test_preprocessing.py        # 术语标准化 + 笼统度评估
│   │   ├── test_query_optimizer_llm.py  # 提问优化
│   │   ├── test_clarification_flow.py   # 澄清流程
│   │   └── test_integrated_optimize.py  # 集成优化测试
│   │
│   ├── retrieval/                       # 检索层
│   │   ├── test_recall.py               # 三路召回测试
│   │   ├── test_recall_simple.py        # 简化召回测试
│   │   ├── test_rerank_layer.py         # 两阶段重排
│   │   └── test_rerank_realdata.py      # 真实数据重排测试
│   │
│   ├── generation/                      # 生成层
│   │   ├── test_generation_layer.py     # 答案生成
│   │   └── test_llm_client.py           # LLM 客户端
│   │
│   └── embedding/                       # 嵌入层
│       └── test_model_download.py       # 模型下载测试
│
├── test_storage/                        # 存储层测试
│   ├── test_storage.py                  # 通用存储测试
│   ├── test_storage_connections.py      # 连接测试
│   ├── test_vector_store.py             # Qdrant 向量库
│   └── test_object_store.py             # MinIO 对象存储
│
├── test_integration/                    # 集成测试
│   ├── test_e2e_pipeline.py             # 端到端 RAG 管道（5个测试用例）
│   ├── test_document_processor.py       # 文档处理流程
│   └── test_ingestion_pipeline.py       # 文档入库流程
│
├── test_api/                            # API 层测试（待实现）
│   └── __init__.py
│
└── test_services/                       # 服务层测试（待实现）
    └── __init__.py
```

## 运行测试

### 方式 1：直接运行独立脚本（推荐）

这些测试文件都有 `async def main()` 入口，可以直接运行：

```bash
cd backend

# 运行单个测试
uv run tests/test_core/preprocessing/test_preprocessing.py
uv run tests/test_integration/test_e2e_pipeline.py

# 运行某个目录下的所有测试
find tests/test_core/retrieval -name "test_*.py" -exec uv run {} \;
```

### 方式 2：使用 pytest（需要先编写 pytest 兼容测试）

```bash
cd backend

# 运行所有测试
pytest

# 运行特定目录
pytest tests/test_core/preprocessing/

# 运行单个测试文件
pytest tests/test_core/preprocessing/test_preprocessing.py

# 带覆盖率报告
pytest --cov=app --cov-report=html
```

## 配置说明

### conftest.py

统一处理：
- **路径配置**：自动添加 backend 目录到 sys.path
- **UTF-8 编码**：强制 stdout/stderr 使用 UTF-8（避免 Windows GBK 错误）
- **数据库 fixtures**：提供 `db_session` 和 `async_db_session`

测试文件不再需要手动配置这些。

### 导入规则

测试文件中直接导入 app 模块：

```python
from app.core.preprocessing import Preprocessor
from app.services.query_service import QueryService
from app.db.session import SessionLocal
```

无需添加 `sys.path.append()` 或编码设置。

## 测试分类

### 按层次分类

| 目录 | 测试内容 | 依赖外部服务 |
|------|---------|-------------|
| `test_core/` | 核心算法层（预处理/检索/生成/嵌入） | 部分需要（LLM/模型） |
| `test_storage/` | 存储层（数据库/向量库/对象存储） | 是（MySQL/Qdrant/ES/MinIO） |
| `test_integration/` | 端到端集成测试 | 是（全部） |
| `test_api/` | API 接口测试 | 是（FastAPI + 全部存储） |
| `test_services/` | 服务层测试 | 是（QueryService 等） |

### 按执行方式分类

1. **单元测试**：独立模块测试，可 mock 外部依赖
   - 大部分 `test_core/` 下的测试

2. **集成测试**：需要真实外部服务
   - `test_storage/`
   - `test_integration/`
   - 部分 `test_core/retrieval/`（需要 Qdrant/ES）

3. **端到端测试**：完整业务流程验证
   - `test_integration/test_e2e_pipeline.py`（覆盖 7 层架构 + 14 个状态）

## 维护指南

### 添加新测试

1. 根据测试层次选择目录：
   - 核心算法 → `test_core/<layer>/`
   - 存储相关 → `test_storage/`
   - 端到端 → `test_integration/`
   - API → `test_api/`
   - 服务层 → `test_services/`

2. 命名规范：`test_<module_name>.py`

3. 测试函数：
   - 同步测试：`def test_xxx()`
   - 异步测试：`async def test_xxx()`
   - 独立脚本：保留 `async def main()` 入口

### 更新导入路径

如果需要批量修改导入：

```bash
cd backend
uv run tests/fix_imports.py
```

## 已知问题

1. **部分测试需要外部服务**：运行前确保 MySQL/Redis/Qdrant/ES/MinIO 已启动
2. **模型下载**：首次运行需要下载 ~3.3GB 模型（自动完成）
3. **Windows 编码**：已在 conftest.py 中统一处理，无需手动配置

## 相关文档

- 架构设计：`docs/architecture/backend/04-后端架构设计.md`
- RAG 流程：`docs/architecture/backend/08-RAG功能层次与状态机.md`
- 测试验证：`docs/architecture/backend/12-RAG流程集成验证报告.md`
