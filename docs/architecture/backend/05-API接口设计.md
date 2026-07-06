# API接口设计文档

## 一、接口规范

### 1.1 基础信息

| 项目 | 说明 |
|------|------|
| Base URL | `http://localhost:8000` |
| API前缀 | `/api/v1` |
| 数据格式 | JSON |
| 字符编码 | UTF-8 |
| 认证方式 | JWT Bearer Token |

### 1.2 通用响应格式

**成功响应**：
```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

**错误响应**：
```json
{
  "code": 40001,
  "message": "错误描述",
  "trace_id": "uuid-xxxx"
}
```

### 1.3 状态码约定

| HTTP状态码 | 业务code | 说明 |
|-----------|---------|------|
| 200 | 0 | 成功 |
| 400 | 40001 | 请求参数错误 |
| 401 | 40101 | 未认证 |
| 403 | 40301 | 无权限 |
| 404 | 40401 | 资源不存在 |
| 429 | 42901 | 请求频率超限 |
| 500 | 50001 | 服务器内部错误 |
| 503 | 50301 | 服务不可用（下游依赖故障） |

### 1.4 认证方式

除登录、健康检查外，所有接口需在 Header 中携带 Token：

```
Authorization: Bearer <access_token>
```

---

## 二、接口分类总览

| 分类 | 接口数 | 说明 |
|------|-------|------|
| 系统接口 | 2 | 健康检查、根路径 |
| 认证接口 | 4 | 登录、刷新Token、登出、当前用户 |
| 查询接口 | 4 | 查询、提问优化、澄清确认、反馈 |
| 文档管理 | 5 | 上传、列表、详情、删除、重新处理 |
| 术语管理 | 3 | 列表、新增、删除 |
| WebSocket | 1 | 流式查询 |

---

## 三、系统接口

### 3.1 根路径

```
GET /
```

**响应**：
```json
{
  "message": "Electric RAG System API",
  "version": "1.0.0",
  "docs": "/docs"
}
```

### 3.2 健康检查

```
GET /health
```

**响应**：
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0"
}
```

---

## 四、认证接口

### 4.1 用户登录

```
POST /api/v1/auth/login
```

**请求体**：
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**响应**：
```json
{
  "access_token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@electric-rag.com",
    "role": "admin",
    "full_name": "系统管理员"
  }
}
```

> `role` 可选值：`admin`（管理员） / `user`（普通用户） / `readonly`（只读用户）

### 4.2 刷新 Token

```
POST /api/v1/auth/refresh
```

**请求体**：
```json
{
  "refresh_token": "eyJhbGci..."
}
```

**响应**：
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### 4.3 登出

```
POST /api/v1/auth/logout
```

**请求头**：`Authorization: Bearer <token>`

**响应**：
```json
{
  "code": 0,
  "message": "登出成功"
}
```

---

### 4.4 获取当前用户信息

```
GET /api/v1/auth/me
```

**请求头**：`Authorization: Bearer <token>`

**响应**：
```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@electric-rag.com",
  "role": "admin",
  "full_name": "系统管理员",
  "query_count": 0,
  "last_login_at": "2026-07-06T17:00:00"
}
```

---

## 五、查询接口

### 5.1 执行查询（核心接口）

```
POST /api/v1/query
```

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 查询内容（1-500字符） |
| stream | boolean | 否 | 是否流式输出，默认false |
| conversation_id | string | 否 | 会话ID（多轮对话） |
| filters | object | 否 | 手动指定过滤条件 |

```json
{
  "query": "10kV配电室安全距离要求",
  "stream": false,
  "conversation_id": "conv_123",
  "filters": {
    "voltage_level": "10kV",
    "category": "配电"
  }
}
```

**响应**：

| 字段 | 类型 | 说明 |
|------|------|------|
| answer | string | 生成的答案 |
| citations | array | 引用来源列表 |
| lane | string | 路由车道：fast/slow |
| retrieval_time | int | 检索耗时（ms） |
| generation_time | int | 生成耗时（ms） |
| expanded_queries | array | 扩展的查询（HyDE/多Query，便于理解检索过程） |
| query_log_id | int | 查询日志ID（用于反馈） |

```json
{
  "answer": "根据GB 50057-2010第3.2.1条，10kV配电室的安全距离应满足...",
  "citations": [
    {
      "doc_id": 100,
      "title": "GB 50057-2010 建筑物防雷设计规范",
      "standard_no": "GB 50057-2010",
      "clause": "3.2.1",
      "content": "配电室安全距离不应小于...",
      "page": 15
    }
  ],
  "lane": "fast",
  "retrieval_time": 1200,
  "generation_time": 800,
  "expanded_queries": ["10kV配电室安全距离", "10千伏配电室安全间距"],
  "query_log_id": 12345
}
```

**说明**：
- 当 `stream=true` 时，请改用 WebSocket 接口（见第九节）
- 若查询笼统度高，建议先调用「提问优化」接口

---

### 5.2 提问优化

```
POST /api/v1/query/optimize
```

**请求体**：
```json
{
  "query": "接地要求"
}
```

**响应**：

| 字段 | 类型 | 说明 |
|------|------|------|
| strategy | string | 策略：none/suggest/clarify_optional/clarify_required |
| vagueness_score | float | 笼统度评分（0-1） |
| options | array | 澄清/补全选项 |

```json
{
  "strategy": "clarify_optional",
  "vagueness_score": 0.75,
  "options": [
    {
      "id": 1,
      "label": "接地电阻的阻值要求（≤4Ω）",
      "refined_query": "接地电阻要求",
      "standard_preview": "GB 50057",
      "doc_count": 23
    },
    {
      "id": 2,
      "label": "接地装置的材料与施工规范",
      "refined_query": "接地装置施工规范",
      "standard_preview": "DL/T 621",
      "doc_count": 18
    }
  ]
}
```

**策略说明**：

| strategy | vagueness_score | 前端交互 |
|----------|----------------|---------|
| none | 0-0.3 | 直接查询 |
| suggest | 0.3-0.6 | 非阻断补全提示 |
| clarify_optional | 0.6-0.8 | 非阻断澄清卡片 |
| clarify_required | 0.8-1.0 | 阻断式弹窗 |

**澄清流程衔接**：

本接口只负责生成澄清选项，不直接执行查询。前端根据用户选择完成后续流转，无需额外接口：

1. `none` → 直接调用 `POST /api/v1/query`（使用原始 query）
2. `suggest` / `clarify_optional` / `clarify_required` → 展示 `options`
3. 用户选择某个选项 → 前端取该选项的 `refined_query`，调用 `POST /api/v1/query`
4. 用户选择"以上都不是，自行输入" → 前端用用户新输入的文本调用 `POST /api/v1/query`

> 澄清对话的用户选择、自定义输入等数据由后端在查询时记录到 `clarification_logs` 表，用于 Loop Engineering 分析。

---

### 5.3 提交用户反馈

```
POST /api/v1/query/{query_log_id}/feedback
```

**路径参数**：`query_log_id` - 查询日志ID

**请求体**：
```json
{
  "feedback_score": 5,
  "feedback_text": "答案准确，引用清晰"
}
```

**响应**：
```json
{
  "code": 0,
  "message": "反馈已提交"
}
```

---

### 5.4 查询历史

```
GET /api/v1/query/history
```

**查询参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页数量 |
| conversation_id | string | - | 按会话过滤 |

**响应**：
```json
{
  "total": 100,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 12345,
      "query": "10kV配电室安全距离要求",
      "answer": "根据GB 50057...",
      "lane": "fast",
      "recall_success": true,
      "total_time": 2000,
      "feedback_score": 5,
      "created_at": "2026-07-06T17:00:00"
    }
  ]
}
```

---

## 六、文档管理接口

### 6.1 上传文档

```
POST /api/v1/documents/upload
```

**Content-Type**: `multipart/form-data`

**表单字段**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | PDF文件 |
| title | string | 是 | 文档标题 |
| doc_type | string | 是 | standard/textbook/manual/regulation |
| standard_no | string | 否 | 标准号 |
| version | string | 否 | 版本号 |
| category | string | 否 | 专业分类 |
| voltage_level | string | 否 | 电压等级 |

**响应**：
```json
{
  "doc_id": 100,
  "task_id": "celery-task-xxx",
  "process_status": "pending",
  "message": "文档已上传，正在后台处理"
}
```

---

### 6.2 文档列表

```
GET /api/v1/documents
```

**查询参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页数量 |
| doc_type | string | - | 按类型过滤 |
| category | string | - | 按专业分类过滤 |
| voltage_level | string | - | 按电压等级过滤 |
| status | string | - | 按有效性过滤 |
| process_status | string | - | 按处理状态过滤 |
| keyword | string | - | 标题模糊搜索 |

**响应**：
```json
{
  "total": 60,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 100,
      "title": "GB 50057-2010 建筑物防雷设计规范",
      "doc_type": "standard",
      "standard_no": "GB 50057-2010",
      "category": "配电",
      "voltage_level": "10kV",
      "status": "valid",
      "process_status": "completed",
      "chunk_count": 156,
      "created_at": "2026-07-06T10:00:00"
    }
  ]
}
```

---

### 6.3 文档详情

```
GET /api/v1/documents/{doc_id}
```

**响应**：
```json
{
  "id": 100,
  "title": "GB 50057-2010 建筑物防雷设计规范",
  "doc_type": "standard",
  "standard_no": "GB 50057-2010",
  "version": "2010",
  "publish_org": "住房和城乡建设部",
  "publish_date": "2010-11-03",
  "implement_date": "2011-10-01",
  "status": "valid",
  "category": "配电",
  "voltage_level": "10kV",
  "abstract": "本规范适用于...",
  "file_size": 2048576,
  "page_count": 89,
  "chunk_count": 156,
  "view_count": 320,
  "created_at": "2026-07-06T10:00:00"
}
```

---

### 6.4 删除文档

```
DELETE /api/v1/documents/{doc_id}
```

**权限**：需要 admin 角色

**响应**：
```json
{
  "code": 0,
  "message": "文档已删除",
  "deleted_chunks": 156
}
```

**说明**：删除文档会级联删除关联的 chunks、向量、全文索引。

---

### 6.5 重新处理文档

```
POST /api/v1/documents/{doc_id}/reprocess
```

**权限**：需要 admin 角色

**响应**：
```json
{
  "doc_id": 100,
  "task_id": "celery-task-yyy",
  "process_status": "processing",
  "message": "文档重新处理中"
}
```

---

### 6.6 查询处理任务状态

```
GET /api/v1/documents/tasks/{task_id}
```

**响应**：
```json
{
  "task_id": "celery-task-xxx",
  "status": "PROCESSING",
  "progress": 60,
  "message": "正在向量化...",
  "error": null
}
```

**响应字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | string | Celery 任务ID |
| status | string | Celery 任务状态（见下） |
| progress | int | 进度百分比（0-100） |
| message | string | 当前步骤描述 |
| error | string/null | 失败时的错误信息 |

**status 状态值**：`PENDING` / `PROCESSING` / `SUCCESS` / `FAILURE`

> **注意**：此处 `status` 是 **Celery 异步任务状态**（大写），与 `documents.process_status` 字段（`pending/processing/completed/failed`，小写）是两个不同概念：
> - Celery 任务状态：描述后台任务本身的执行情况
> - 文档处理状态：持久化在 documents 表中，描述文档的处理结果
>
> 任务完成后（SUCCESS），可通过「文档详情」接口查看 `process_status=completed`。

---

## 七、术语管理接口

### 7.1 术语列表

```
GET /api/v1/terms
```

**查询参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| page | int | 页码 |
| page_size | int | 每页数量 |
| category | string | 按分类过滤 |
| source | string | 按来源过滤（manual/auto/loop_engineering） |
| keyword | string | 术语关键词搜索 |

**响应**：
```json
{
  "total": 5000,
  "items": [
    {
      "id": 1,
      "standard_term": "电压互感器",
      "aliases": ["PT", "电压互感器"],
      "category": "设备",
      "source": "manual",
      "frequency": 156
    }
  ]
}
```

---

### 7.2 新增术语

```
POST /api/v1/terms
```

**权限**：需要 admin 角色

**请求体**：
```json
{
  "standard_term": "避雷器",
  "aliases": ["MOA", "氧化锌避雷器", "避雷器"],
  "category": "设备",
  "definition": "用于保护电气设备免受雷电过电压..."
}
```

**响应**：
```json
{
  "id": 5001,
  "message": "术语已添加"
}
```

---

### 7.3 删除术语

```
DELETE /api/v1/terms/{term_id}
```

**权限**：需要 admin 角色

**响应**：
```json
{
  "code": 0,
  "message": "术语已删除"
}
```

---

## 八、Pydantic 数据模型

### 8.1 请求模型

```python
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    stream: bool = False
    conversation_id: Optional[str] = None
    filters: Optional[dict] = None

class OptimizeRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)

class FeedbackRequest(BaseModel):
    feedback_score: int = Field(..., ge=1, le=5)
    feedback_text: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class TermCreateRequest(BaseModel):
    standard_term: str
    aliases: List[str]
    category: Optional[str] = None
    definition: Optional[str] = None

class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)
```

### 8.2 响应模型

```python
class Citation(BaseModel):
    doc_id: int
    title: str
    standard_no: Optional[str] = None
    clause: Optional[str] = None
    content: str
    page: Optional[int] = None

class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
    lane: Literal["fast", "slow"]
    retrieval_time: int
    generation_time: int
    expanded_queries: List[str] = []
    query_log_id: int

class ClarifyOption(BaseModel):
    id: int
    label: str
    refined_query: str
    standard_preview: Optional[str] = None
    doc_count: Optional[int] = None

class OptimizeResponse(BaseModel):
    strategy: Literal["none", "suggest", "clarify_optional", "clarify_required"]
    vagueness_score: float
    options: List[ClarifyOption] = []

class DocumentResponse(BaseModel):
    id: int
    title: str
    doc_type: Literal["standard", "textbook", "manual", "regulation"]
    standard_no: Optional[str] = None
    version: Optional[str] = None
    publish_org: Optional[str] = None
    publish_date: Optional[date] = None
    implement_date: Optional[date] = None
    category: Optional[str] = None
    voltage_level: Optional[str] = None
    abstract: Optional[str] = None
    status: Literal["valid", "expired", "draft"]
    process_status: Literal["pending", "processing", "completed", "failed"]
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    chunk_count: int
    view_count: int = 0
    created_at: datetime

class TaskStatusResponse(BaseModel):
    task_id: str
    status: Literal["PENDING", "PROCESSING", "SUCCESS", "FAILURE"]
    progress: int
    message: str
    error: Optional[str] = None

class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[dict]

class UserInfo(BaseModel):
    id: int
    username: str
    email: str
    role: Literal["admin", "user", "readonly"]
    full_name: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo

class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
```

---

## 九、WebSocket 接口（流式查询）

### 9.1 连接

```
WS /ws/query?token=<access_token>
```

### 9.2 客户端发送

```json
{
  "type": "query",
  "data": {
    "query": "10kV配电室安全距离要求",
    "conversation_id": "conv_123"
  }
}
```

### 9.3 服务端推送

**答案片段（多次推送）**：
```json
{
  "type": "chunk",
  "data": {"content": "根据GB 50057-2010"}
}
```

**引用来源**：
```json
{
  "type": "citation",
  "data": {
    "doc_id": 100,
    "title": "GB 50057-2010 建筑物防雷设计规范",
    "standard_no": "GB 50057-2010",
    "clause": "3.2.1"
  }
}
```

> 流式推送的 citation 仅含引用标识字段（doc_id/title/standard_no/clause），省略 `content`/`page` 以减少传输量；如需完整引用内容，前端可凭 doc_id 调用「文档详情」接口获取。

**慢车道推理过程（可选）**：
```json
{
  "type": "reasoning",
  "data": {"step": 1, "content": "检索到GB 50057条款X"}
}
```

**生成完成**：
```json
{
  "type": "done",
  "data": {
    "query_log_id": 12345,
    "total_time": 2500
  }
}
```

**错误**：
```json
{
  "type": "error",
  "data": {"message": "生成失败", "code": 50001}
}
```

---

## 十、限流规则

| 接口 | 限流策略 |
|------|---------|
| /api/v1/query | 每用户 60次/分钟 |
| /api/v1/query/optimize | 每用户 120次/分钟 |
| /api/v1/documents/upload | 每用户 10次/分钟 |
| 慢车道查询 | 全局 QPS=10 |

超限返回 `429` + `Retry-After` 头。

---

## 十一、错误码对照表

| code | 说明 | HTTP |
|------|------|------|
| 0 | 成功 | 200 |
| 40001 | 请求参数错误 | 400 |
| 40002 | 查询内容为空 | 400 |
| 40003 | 查询超长（>500字符） | 400 |
| 40101 | 未认证/Token无效 | 401 |
| 40102 | Token已过期 | 401 |
| 40301 | 无权限（需admin） | 403 |
| 40401 | 文档不存在 | 404 |
| 42901 | 请求频率超限 | 429 |
| 50001 | 服务器内部错误 | 500 |
| 50002 | LLM调用失败 | 500 |
| 50301 | 检索服务不可用 | 503 |

---

**相关文档**：
- [04-后端架构设计.md](./04-后端架构设计.md)
- [06-数据模型设计.md](./06-数据模型设计.md)
- [16-业务流程图.md](../flows/16-业务流程图.md)
