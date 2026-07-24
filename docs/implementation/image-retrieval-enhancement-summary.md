# 图片检索增强功能实现总结

**实施日期**: 2026-07-22  
**设计文档**: `docs/architecture/modules/29-图片检索增强设计.md`  
**实现优先级**: 阶段一（核心功能）

---

## 实现概览

根据设计文档第 8 节优先级规划，本次实现完成了**阶段一：核心联动（快速收益）**的所有功能：

1. ✅ 图文语义关联计算（入库时）
2. ✅ 图片伴随召回（检索时）
3. ✅ 图片链接注入（生成前）
4. ✅ 重排提权（rerank 时）

---

## 代码变更清单

### 1. Schema 扩展 (`app/schemas/retrieval.py`)

**新增字段**：
```python
class ChunkResult(BaseModel):
    content_type: str = "text"           # 内容类型：text / table / image_description
    related_chunk_ids: List[int] = []    # 关联的图片块 ID 列表
```

**用途**：
- `content_type`: 区分文本、表格、图片描述，用于重排提权
- `related_chunk_ids`: 存储文本块关联的图片块 ID，用于伴随召回

---

### 2. 图文关联计算 (`app/core/document_processor/chunker.py`)

**函数**：`compute_image_text_associations()`

**策略**：
- **物理邻近**：文本块与前后 1 页内的图片自动关联
- **语义相似**：计算文本向量与图片描述向量的余弦相似度，≥ 0.75 则关联

**集成点**：
- 在 `app/core/ingestion_pipeline.py` 的入库流程中调用
- 位于向量生成后、数据库写入前（line 483）

**示例输出**：
```python
{
    text_chunk_id_1: [img_chunk_id_101, img_chunk_id_102],
    text_chunk_id_2: [img_chunk_id_103]
}
```

---

### 3. 图片伴随召回与链接注入 (`app/core/retrieval/image_link_injector.py`)

**新增模块**，提供两个核心函数：

#### 3.1 `pull_along_images(chunks, db)`
**职责**：伴随召回关联图片

**逻辑**：
1. 提取文本块的 `related_chunk_ids`
2. 从数据库批量查询关联图片块
3. 将图片块追加到召回结果中
4. 图片块初始 score 设为关联文本块的最高分 × 0.9

**示例**：
```
输入: [文本块 A (score=0.85, related=[101, 102])]
输出: [文本块 A, 图片块 101 (score=0.765), 图片块 102 (score=0.765)]
```

#### 3.2 `inject_image_links(chunks, db)`
**职责**：为文本块注入图片引用

**逻辑**：
1. 提取文本块的 `related_chunk_ids`
2. 从数据库批量查询图片块的元数据（minio_key, page_number）
3. 在文本块内容末尾注入 Markdown 图片链接

**示例**：
```
原始文本: "配电网电压等级包括 10kV、35kV 等。"

注入后:
"配电网电压等级包括 10kV、35kV 等。

[关联配图]
- 图1-1 (p.5): ![配电网结构示意图](/api/v1/images/doc123/chunk101)"
```

---

### 4. 快车道集成 (`app/core/retrieval/fast_lane.py`)

**集成位置**：
- **步骤 2.6**：在去重后、重排前调用图片功能
- **两个位置**：
  1. 首次召回后（line 177）
  2. 二次检索后（line 248）

**代码**：
```python
# 步骤2.6: 图片伴随召回 + 图片链接注入
from app.core.retrieval.image_link_injector import pull_along_images, inject_image_links
deduped_chunks = await pull_along_images(deduped_chunks, self.db)
deduped_chunks = await inject_image_links(deduped_chunks, self.db)
```

**执行顺序**：
```
召回 (50) → 去重 (40) → 图片伴随 (45) → 图片注入 (45) → 重排 (20) → 充分性判断
```

---

### 5. 重排提权 (`app/core/retrieval/rerank.py`)

**新增方法**：`_apply_type_boost(chunk, score)`

**提权系数**：
```python
TYPE_BOOST = {
    "text": 1.0,               # 纯文本：无提权
    "table": 1.05,             # 表格：5% 提权
    "image_description": 1.08, # 图片：8% 提权
}
```

**原理**：
- 工程标准中图表信息密度高，适当提权防止纯文本偏置导致图片沉底
- 提权在 `_chunk_to_rerank_result()` 中自动应用

**示例**：
```
原始分数 0.80 → 文本块保持 0.80，图片块提升至 0.864
```

---

### 6. 召回层扩展 (`app/core/retrieval/recall.py`)

**变更**：`StructuredRecall._to_chunk_result()`

**新增字段**：
```python
return ChunkResult(
    # ... 原有字段 ...
    related_chunk_ids=chunk.related_chunk_ids or [],
    content_type=chunk.content_type or "text"
)
```

**用途**：确保结构化召回的块也携带图文关联信息

---

## 测试验证

**测试文件**: `backend/test_image_retrieval_enhancement.py`

**测试覆盖**：
1. ✅ ChunkResult 扩展字段正确性
2. ✅ 图文关联计算（物理邻近 + 语义相似）
3. ✅ 图片注入接口可用性
4. ✅ 类型提权准确性（1.0x / 1.05x / 1.08x）

**运行结果**：
```bash
$ cd backend && uv run python test_image_retrieval_enhancement.py
============================================================
图片检索增强功能测试
============================================================

=== 测试 1: ChunkResult 扩展字段 ===
✓ ChunkResult 扩展字段测试通过
✓ 图片块类型测试通过

=== 测试 2: 图文关联计算 ===
关联结果: {1: [101, 102], 2: [101, 102]}
✓ 图文关联计算测试通过

=== 测试 3: 图片注入接口 ===
✓ pull_along_images 接口存在
✓ inject_image_links 接口存在

=== 测试 4: 类型提权 ===
✓ 文本块提权: 0.80 -> 0.8000 (1.0x)
✓ 表格块提权: 0.80 -> 0.8400 (1.05x)
✓ 图片块提权: 0.80 -> 0.8640 (1.08x)

============================================================
✓ 所有测试通过
============================================================
```

---

## 数据流示意

### 入库阶段（Ingestion）
```
PDF → 切块 → 向量化 → 计算图文关联 → 写入 DB (related_chunk_ids)
                 ↓
         文本块: [101, 102]
         图片块: []
```

### 检索阶段（Retrieval）
```
查询 → 召回(40块) → 去重(35块)
                      ↓
                  图片伴随(+5图片块) = 40块
                      ↓
                  图片链接注入(文本块添加引用)
                      ↓
                  重排(类型提权: 图片×1.08)
                      ↓
                  Top5 → 生成层(可见图片链接)
```

---

## 配置参数

**可调参数**（位于各模块）：

| 参数 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `threshold` | `compute_image_text_associations` | 0.75 | 语义相似度阈值 |
| `INITIAL_SCORE_RATIO` | `image_link_injector.py` | 0.9 | 伴随图片初始分数比例 |
| `TYPE_BOOST["image_description"]` | `rerank.py` | 1.08 | 图片提权系数 |
| `TYPE_BOOST["table"]` | `rerank.py` | 1.05 | 表格提权系数 |

---

## 性能影响

### 时间开销（估算）
- **入库阶段**：+50ms（图文关联计算，矩阵乘法）
- **检索阶段**：+20ms（DB 查询图片块，批量操作）
- **重排阶段**：<1ms（简单浮点乘法）

### 召回数量变化
- 原始召回：40 块
- 伴随召回后：40-50 块（取决于关联密度）
- 重排后：仍返回 Top5/Top20（数量不变，但质量提升）

---

## 已知限制

1. **向量召回暂未直接支持**：
   - 图片块目前依赖伴随召回，不会直接出现在向量召回的 Top50 中
   - 设计文档阶段二会实现 VLM 向量化，届时图片可直接参与向量检索

2. **MinIO 链接生成**：
   - 当前生成的是 `/api/v1/images/{doc_id}/{chunk_id}` 格式
   - 需要后端实现对应的图片代理接口（预留 API 路由）

3. **图文关联持久化**：
   - `related_chunk_ids` 存储在 MySQL（JSON 字段）
   - 向量库（Qdrant）的 payload 需同步更新（TODO）

---

## 后续优化方向（阶段二、三）

### 阶段二：多模态向量化（设计文档 8.2）
- [ ] 引入 VLM（CLIP/Qwen-VL）对图片生成向量
- [ ] 图片向量直接参与向量召回
- [ ] 支持"纯图像查询"（用户上传图片提问）

### 阶段三：高级优化（设计文档 8.3）
- [ ] 图片缓存预热（常见配图预加载到 CDN）
- [ ] 动态提权（根据查询类型调整系数）
- [ ] A/B 测试框架（评估图片检索效果）

---

## 参考文档

- **设计文档**: `docs/architecture/modules/29-图片检索增强设计.md`
- **架构总览**: `docs/design.md` § 3.3 召回层
- **数据库模型**: `backend/app/db/models.py` (Chunk 表)
- **测试文件**: `backend/test_image_retrieval_enhancement.py`

---

## 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-07-22 | v1.0 | 实现阶段一功能：关联计算、伴随召回、链接注入、重排提权 |

---

**实施者**: Claude Code  
**复审**: 待用户验收
