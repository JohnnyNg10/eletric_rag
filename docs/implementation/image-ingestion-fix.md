# 图片入库问题修复

**日期**: 2026-07-22  
**问题**: MinerU 解析后图片未被索引（0 images indexed）

---

## 问题分析

### 根本原因
MinerU API 返回的 `content_list` 中包含图片引用（`img_path: "images/xxx.jpg"`），但这些路径指向的是 **MinerU 服务端的输出目录**，后端代码无法直接访问。

### 现象
1. Markdown 文件中有图片引用：`![](images/e9c5752034733b41f26df35d0f1e66fdc7e53c718e53c67b651fa6e7861c4be8.jpg)`
2. 图片实际存储在：`D:\dl\MinerU\output\{task_id}\{pdf_name}\auto\images\*.jpg`
3. 原代码在 `pdf_path.parent` 附近搜索图片，找不到文件
4. 结果：`_extract_images_from_content_list()` 返回空列表

---

## 解决方案

### 1. 新增 `_extract_images_from_markdown()` 方法

**位置**: `app/core/document_processor/parser.py`

**功能**:
- 从 Markdown 文本中提取图片引用（正则匹配 `!\[.*?\]\((.*?)\)`）
- 在 MinerU output 目录中**递归搜索**图片文件（使用 `rglob()`）
- 读取图片字节并返回标准格式

**搜索策略**:
```python
# 优先级1: MinerU output (递归搜索)
mineru_output = Path("D:/dl/MinerU/output")
for img_file in mineru_output.rglob(img_filename):
    if img_file.is_file():
        found_path = img_file
        break

# 优先级2: 其他常规目录
search_dirs = [
    pdf_path.parent / "images",
    pdf_path.parent / "output" / "images",
    Path("debug_markdown") / "images",
    ...
]
```

### 2. 修改调用逻辑

**位置**: `app/core/document_processor/parser.py:300`

```python
# 从 Markdown 文件中提取图片引用（优先）
images = self._extract_images_from_markdown(md_content, pdf_path)

# 如果提取失败，尝试从 content_list 提取（兼容旧版）
if not images:
    images = self._extract_images_from_content_list(content_list, pdf_path)
```

### 3. 修复 Session Rollback 问题

**位置**: `app/core/ingestion_pipeline.py:518, 536`

在 chunk 插入失败时添加 `db.rollback()`，避免后续操作因 session 状态错误而失败：

```python
except Exception as e:
    logger.error(f"Failed to index parent chunk: {e}")
    db.rollback()  # 新增
```

---

## 代码变更

### 变更文件
1. `app/core/document_processor/parser.py`
   - 新增 `_extract_images_from_markdown()` 方法（~80行）
   - 修改 `_parse_text_pdf_with_mineru()` 调用逻辑

2. `app/core/ingestion_pipeline.py`
   - 添加 chunk 插入异常处理中的 `db.rollback()`

### 测试验证
```bash
# 删除测试文档
uv run python -c "
from app.db.session import get_db
from app.db.models import Document, Chunk
from sqlalchemy import delete
db = next(get_db())
db.execute(delete(Chunk).where(Chunk.document_id == 82))
db.execute(delete(Document).where(Document.id == 82))
db.commit()
"

# 重新入库（通过前端或 Celery）
# 预期结果: images_count > 0
```

---

## 依赖条件

1. **MinerU 服务运行在 8001 端口**
2. **MinerU 输出目录**: `D:\dl\MinerU\output`
3. **目录结构**: `{output}/{task_id}/{pdf_name}/auto/images/*.jpg`

如果 MinerU 服务未启动或输出目录配置不同，需要：
- 启动 MinerU 服务：按照 `MinerU/docs/deployment-and-api.md`
- 或修改代码中的 `mineru_output` 路径

---

## 后续优化

1. **从配置读取 MinerU 输出目录**（避免硬编码）
   ```python
   from app.config import settings
   mineru_output = Path(settings.MINERU_OUTPUT_DIR)
   ```

2. **图片缓存**（避免每次都递归搜索）
   - 使用 LRU cache 缓存 `filename -> full_path` 映射

3. **并行图片读取**（加速入库）
   - 使用 `asyncio.gather()` 并行读取多张图片

4. **VLM 描述生成**
   - 当前 `ENABLE_VLM_DESCRIPTION=true` 时会调用 VLM API
   - 确认 VLM 服务可用性（`settings.py` 配置）

---

## 相关文档

- MinerU 部署文档: `MinerU/docs/deployment-and-api.md`
- 图片检索增强设计: `docs/architecture/modules/29-图片检索增强设计.md`
- 实现总结: `docs/implementation/image-retrieval-enhancement-summary.md`
