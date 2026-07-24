# 图片召回功能修复进度

**日期**: 2026-07-23  
**状态**: 代码已修复，等待重新入库测试

---

## 已完成的修复

### 1. 图片提取逻辑 ✅
**文件**: `app/core/document_processor/parser.py`

**问题**: MinerU 返回的图片路径指向服务端，无法直接访问

**解决方案**: 
- 新增 `_extract_images_from_markdown()` 方法
- 从 Markdown 中提取图片引用
- 在 `D:\dl\MinerU\output` 递归搜索图片文件
- 优先级：Markdown 提取 > content_list 提取

**验证**: ✅ 文档 84 成功索引 5 张图片

---

### 2. 召回层字段传递 ✅
**文件**: `app/core/retrieval/recall.py`

**问题**: VectorRecall 和 KeywordRecall 没有传递 `content_type` 和 `related_chunk_ids`

**修复**:
```python
# VectorRecall (line 87-108)
chunk_result = ChunkResult(
    ...
    content_type=payload.get('content_type', 'text'),
    related_chunk_ids=payload.get('related_chunk_ids', [])
)

# KeywordRecall (line 278-293)
chunk_result = ChunkResult(
    ...
    content_type=source.get('content_type', 'text'),
    related_chunk_ids=source.get('related_chunk_ids', [])
)
```

---

### 3. 向量库索引字段 ✅
**文件**: `app/core/ingestion_pipeline.py`

**问题**: Qdrant 和 Elasticsearch 中缺少 `related_chunk_ids` 字段

**修复**:
```python
# Qdrant payload (line 605-616)
"payload": {
    ...
    "related_chunk_ids": chunk.related_chunk_ids or [],
}

# Elasticsearch (line 619-630)
{
    ...
    "related_chunk_ids": chunk.related_chunk_ids or [],
}
```

---

### 4. Session Rollback ✅
**文件**: `app/core/ingestion_pipeline.py`

**问题**: Chunk 插入失败时 session 状态错误，导致后续操作失败

**修复**: 在异常处理中添加 `db.rollback()`

---

## 当前状态

### ✅ 已验证
1. MinerU 服务运行正常（8001 端口）
2. 图片成功提取并上传到 MinIO
3. VLM 描述成功生成（通过 API）
4. 图片元数据写入 MySQL（Images 表 + Chunks 表）

### ⏳ 待验证（需要重新入库）
1. 向量库（Qdrant）包含 `related_chunk_ids` 字段
2. 搜索引擎（Elasticsearch）包含 `related_chunk_ids` 字段
3. 召回层正确识别 `content_type='image_description'`
4. 图片伴随召回功能正常工作

---

## 测试计划

### 步骤 1: 重新入库文档
- [x] 删除文档 84
- [⏳] 通过 Celery 重新入库 GB 5226.6-2014.pdf
- [ ] 验证入库结果：`chunk_count=128`, `image_count=5`

### 步骤 2: 验证向量库数据
```python
# 检查 Qdrant payload 是否包含新字段
from app.core.storage.vector_store import qdrant_client
results = qdrant_client.scroll(
    collection_name="documents",
    scroll_filter={"must": [{"key": "doc_id", "match": {"value": 新文档ID}}]},
    limit=1
)
# 应包含: content_type, related_chunk_ids
```

### 步骤 3: 测试召回
```bash
cd backend
uv run python test_image_recall.py
```

**预期结果**:
- 问题："电气控制系统的框图结构是什么样的？"
- 召回：至少 1 个 `content_type='image_description'` 的块
- 或：至少 1 个 `related_chunk_ids` 非空的文本块

### 步骤 4: 端到端测试
通过前端界面提问，验证：
1. 图片块被召回并展示
2. 图片链接可点击查看
3. 生成的答案引用了图片内容

---

## 当前阻塞

⏳ **等待重新入库完成**
- Celery 任务 ID: `5a5a9ea5-8bef-4591-858a-c2bbb5134417`
- 预计时间: 3-4 分钟
- 监控脚本正在后台运行

---

## 相关文档

- 图片检索增强设计: `docs/architecture/modules/29-图片检索增强设计.md`
- 图片入库修复: `docs/implementation/image-ingestion-fix.md`
- 实现总结: `docs/implementation/image-retrieval-enhancement-summary.md`

---

## 备注

- MinerU 输出目录: `D:\dl\MinerU\output`
- MinerU 服务: `http://127.0.0.1:8001`
- VLM API: 通过 settings.VLM_API_URL
- 图片存储: MinIO bucket `electric-rag-images`
