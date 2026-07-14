# 扫描件PDF处理功能使用指南

## 功能概述

纯VLM（视觉语言模型）方案处理扫描件PDF：
- ✅ 无需OCR，直接用VLM识别整页内容
- ✅ 保持原文结构（章节、条款编号、表格、图注）
- ✅ 每页作为一个可检索单元
- ✅ 统一文本检索，无需区分图片/文字

## 架构设计

```
扫描件PDF → 转图片 → VLM识别整页 → 保存为Image+Chunk → 向量化 → 统一检索
```

### 关键设计

1. **整页识别**：每页PDF转为图片，VLM识别全部内容（文字+表格+图注）
2. **内容保留**：VLM提示词要求保留章节结构、条款编号、表格格式
3. **统一检索**：VLM识别的文本存为 `Chunk(content_type='image_description')`，参与正常文本检索
4. **图文关联**：检索到Chunk时，自动展示关联的页面图片

## 环境配置

### 1. 安装依赖

```bash
cd backend
pip install PyMuPDF httpx  # PDF转图片 + HTTP客户端
```

### 2. 配置 .env

```bash
# 启用扫描件处理
ENABLE_SCANNED_PDF=true
ENABLE_VLM_DESCRIPTION=true

# VLM API配置（选择豆包或通义千问）
VLM_PROVIDER=doubao  # doubao / qwen

# 豆包API
DOUBAO_API_KEY=your_doubao_api_key
DOUBAO_API_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3/chat/completions
DOUBAO_MODEL=doubao-vision-pro

# 或者通义千问API
QWEN_API_KEY=your_qwen_api_key
QWEN_MODEL=qwen-vl-plus
```

### 3. 启动Celery Worker

扫描件处理是异步任务，需要启动Celery：

```bash
cd backend
celery -A app.tasks.celery_app worker --loglevel=info
```

## 使用方法

### 方式1：脚本导入

```bash
# 导入单个目录的PDF
python import_scanned_pdfs.py --dir "实际数据/DL" --doc-type standard

# 首次运行需要初始化数据库
python import_scanned_pdfs.py --dir "实际数据/DL" --init-db
```

### 方式2：API调用

```python
from app.tasks.scan_processor_tasks import process_scanned_pdf_task

# 提交异步任务
task = process_scanned_pdf_task.delay(pdf_path="/path/to/scan.pdf", doc_id=123)

# 查询任务状态
result = task.get(timeout=600)  # 10分钟超时
print(result)
# {'status': 'success', 'pages_processed': 156, 'image_count': 156, ...}
```

## 处理流程

1. **PDF转图片**：PyMuPDF 300 DPI渲染
2. **VLM识别**：并行处理每页，提示词要求保留结构
3. **保存记录**：
   - `images` 表：每页作为一张图片
   - `chunks` 表：VLM识别的全文作为可检索内容（`content_type='image_description'`）
4. **生成Markdown**：合并所有页面为结构化文档
5. **向量化**：Chunk向量化并存入Qdrant+ES

## 检索示例

扫描件内容与普通文本统一检索：

```python
# 用户查询："水坝廊道结构"
# 系统自动检索所有Chunk（包括扫描件的VLM识别内容）

results = await unified_search(query="水坝廊道结构", top_k=10)

for chunk in results:
    if chunk.content_type == 'image_description':
        # 这是扫描件页面
        print(f"来源：扫描件 {chunk.document.title} 第{chunk.page_start}页")
        print(f"内容：{chunk.content[:100]}...")
        
        # 自动展示页面图片
        image = db.query(Image).filter(Image.chunk_id == chunk.id).first()
        print(f"图片：{image.minio_path}")
```

## VLM提示词

当前使用的提示词（可在 `processor.py` 中修改）：

```
请识别这一页的全部内容，并按原文结构输出。

要求：
1. 保留章节标题、条款编号（如 3.2.1）
2. 保留表格结构（用Markdown格式）
3. 标注图片位置（如 [图5-2: 水坝剖面图]）
4. 保持原文排版顺序（双栏时从左到右）

输出格式：纯文本，保持原文层级结构。

这是第{page_num}页。
```

## 性能估算

- **处理速度**：~3-5秒/页（VLM API调用）
- **成本**：~0.01元/页（豆包多模态）
- **示例**：
  - 20个DL标准，平均30页/个 = 600页
  - 总时间：600页 × 4秒 = 40分钟
  - 总成本：600页 × 0.01元 = 6元

## 故障排查

### 1. VLM API调用失败

检查日志：`backend/logs/app.log`

常见问题：
- API Key未配置或错误
- 网络问题（需要外网访问）
- 配额不足

### 2. Celery任务卡住

```bash
# 查看任务队列
celery -A app.tasks.celery_app inspect active

# 清空队列
celery -A app.tasks.celery_app purge
```

### 3. 图片上传MinIO失败

检查 MinIO 配置：
```bash
# .env
MINIO_HOST=localhost
MINIO_PORT=9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

## 数据库表结构

### images 表

| 字段 | 说明 |
|------|------|
| id | 图片ID |
| document_id | 所属文档 |
| chunk_id | 关联的Chunk ID（VLM识别内容） |
| page_number | 页码 |
| minio_path | MinIO路径 |
| vlm_description | VLM描述（摘要） |
| vlm_model | 使用的模型 |

### chunks 表扩展

| 字段 | 说明 |
|------|------|
| content_type | `text` / `image_description` / `table_summary` |
| related_resource_id | 关联的图片/表格ID |
| related_resource_type | `image` / `table` |

## 与现有系统并行

- ✅ 默认关闭：`ENABLE_SCANNED_PDF=false`
- ✅ 独立存储：扫描件使用独立的MinIO路径
- ✅ 统一检索：扫描件Chunk与普通文本Chunk统一检索
- ✅ 无侵入：不影响现有文本RAG流程

## 后续优化

1. **批量处理**：支持多个PDF并发处理
2. **断点续传**：处理失败后从失败页重试
3. **质量检测**：VLM识别质量评分，低分页面人工复核
4. **结构解析**：后处理提取章节条款结构
5. **增量更新**：检测PDF变更，只处理修改的页面

## 参考文档

- 设计文档：`docs/architecture/modules/14.1-扫描件PDF存储方案.md`
- 数据模型：`docs/architecture/backend/06-数据模型设计.md`
- VLM客户端：`app/core/vlm/vlm_client.py`
- 处理器：`app/core/scan_processor/processor.py`
