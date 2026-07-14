# 跨标准引用检索增强

## 问题描述

在检索储能系统相关标准时，用户查询 GB/T 43526-2023，系统返回的文本包含：

> "需符合 GB/T 14549《电能质量 公用电网谐波》的要求"

但系统**没有自动检索** GB/T 14549 的实际内容（如谐波限值表），导致用户无法获得完整答案。

## 根本原因

1. **充分性判断**识别出缺口："缺少 GB/T 14549 的具体限值"
2. **gap-filling 机制**只是简单拼接 gap 文本重试，无法针对性检索被引用标准
3. **缺少跨标准引用解析**：没有从 gaps 或 chunks 中提取被引用标准号

## 解决方案

### 1. 引用提取器（`reference_extractor.py`）

新增 `ReferenceExtractor` 组件，从两个来源提取被引用标准号：

- **gaps**：充分性判断识别的信息缺口（如 "缺少 GB/T 14549 的具体限值"）
- **chunks**：已召回的文档块（如 "应符合 GB/T 14549"）

**提取逻辑：**
- 标准号匹配：支持 `GB/T`、`GB`、`DL/T`、`NB/T` 等，带年份或不带年份
- 引用指示词检测：只从包含 "应符合"、"需满足"、"参见"、"依据" 等指示词的文本中提取

### 2. 增强 Fast Lane 二次检索（`fast_lane.py:167-193`）

当充分性判断失败时：

```python
# 步骤1: 提取被引用标准号
referenced_standards_from_gaps = self.reference_extractor.extract_from_gaps(gaps)
referenced_standards_from_chunks = self.reference_extractor.extract_from_chunks(chunks)

# 步骤2: 改写查询（包含被引用标准号）
retry_query = self._refine_query_for_gaps(query, gaps, referenced_standards)

# 步骤3: 补充召回
retry_chunks = await self._multi_path_recall([retry_query], filters)

# 步骤4: 针对被引用标准进行精确召回
if referenced_standards:
    ref_chunks = await self._recall_referenced_standards(referenced_standards)
    retry_chunks.extend(ref_chunks)

# 步骤5: 合并去重并重新精排
```

### 3. 精确召回被引用标准（`fast_lane.py:_recall_referenced_standards`）

使用 `StructuredRecall` 按标准号精确匹配：

```python
for standard_no in standard_nos:
    filters = {"standard_no": normalized_std}
    chunks = await structured_recall.search("", filters, top_k=10)
```

## 效果

**原始行为：**
1. 用户查询："储能系统谐波要求"
2. 召回 GB/T 43526-2023 的内容："需符合 GB/T 14549"
3. **缺少** GB/T 14549 的谐波限值表

**增强后：**
1. 用户查询："储能系统谐波要求"
2. 召回 GB/T 43526-2023 的内容："需符合 GB/T 14549"
3. 充分性判断识别 gap："缺少 GB/T 14549 的具体限值"
4. **自动检索** GB/T 14549，获取谐波限值表
5. 合并返回完整答案

## 测试

运行测试验证提取功能：

```bash
uv run python test_reference_extraction.py
```

测试覆盖：
- 从 gaps 提取标准号（带/不带年份）
- 从 chunks 提取标准号（需包含引用指示词）
- 引用指示词检测（正例/负例）

## 文件清单

- `app/core/retrieval/reference_extractor.py` - 引用提取器（新增）
- `app/core/retrieval/fast_lane.py` - 增强二次检索逻辑（修改）
- `test_reference_extraction.py` - 单元测试（新增）

## 未来优化

1. **跨标准引用索引**：在文档导入时预先解析引用关系，构建图谱
2. **多跳引用**：A 引用 B，B 引用 C（当前只支持一跳）
3. **引用类型分类**：强制性引用 vs 参考性引用，决定是否自动获取
