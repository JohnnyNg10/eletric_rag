# 禁用预处理阶段标准号推荐功能

## 修改说明

### 问题
预处理阶段返回的标准号推荐存在以下问题：
1. LLM 推荐的标准可能与查询不相关
2. 混淆了"澄清维度"和"推荐标准"两个不同的功能
3. 未经知识库验证的标准号会误导用户

### 解决方案
**预处理阶段只专注于澄清问题和解决维度缺失**，不返回标准号推荐。

---

## 修改内容

### 文件：`backend/app/core/preprocessing/query_optimizer.py`

#### 修改 1：禁用 KB 标准聚合填充

```python
# 注释掉标准系列填充逻辑
# if "standard_series" in result.missing_dimension_keys and result.options:
#     result = await self._fill_standard_series_options(query, result)
```

**效果**：即使 LLM 识别出 `missing_dimension_keys` 包含 `"standard_series"`，也不会调用 ES 聚合查询标准清单。

---

#### 修改 2：明确标注不返回标准号

```python
options.append(OptimizationOption(
    id=i,
    label=opt.get("label", f"{query}优化选项{i}"),
    refined_query=opt.get("refined_query", query),
    standard_preview=None,  # 不返回标准号推荐
    doc_count=0,
    kb_verified=False  # 预处理阶段不验证标准
))
```

**效果**：所有澄清选项都不包含 `standard_preview`，前端不会显示标准号。

---

## 预处理功能范围

### ✅ 保留的功能

1. **术语标准化**：行业黑话 → 标准术语
2. **笼统度评估**：判断查询是否需要澄清
3. **类别识别**：配电/变电/继保/输电/通用
4. **维度缺失识别**：识别缺少的关键维度（电压等级、设备类型等）
5. **澄清选项生成**：为缺失维度生成补充选项
6. **路由建议**：fast/slow 车道建议

### ❌ 移除的功能

1. **标准号推荐**：不再返回 `standard_preview`
2. **知识库验证**：不再查询 ES 验证标准是否存在
3. **文档数量统计**：不再返回 `doc_count`

---

## 前端显示变化

### 修改前

```
预处理结果：
━━━━━━━━━━━━━━━━━━━━━━━━━
澄清选项：
○ 10kV配电室安全距离
  标准：GB 50053-2013 (245条) ✅
  
○ 35kV配电装置安全距离  
  标准：GB 12345-2020 (未验证) ⚠️
```

### 修改后

```
预处理结果：
━━━━━━━━━━━━━━━━━━━━━━━━━
澄清选项：
○ 10kV配电室安全距离
  
○ 35kV配电装置安全距离
```

**变化**：
- ✅ 不再显示标准号
- ✅ 不再显示"未验证"警告
- ✅ 界面更简洁，专注于维度澄清

---

## 相关标准推荐的正确位置

如果未来需要"推荐相关标准"功能，应该在以下位置实现：

### 方案 1：慢车道工具（已实现）

**位置**：`backend/app/core/retrieval/slow_lane.py`

**工具**：`list_related_standards`

**触发时机**：
- 用户明确问"有哪些标准涉及XX？"
- LLM 决策需要先列举标准再检索内容

**优势**：
- ✅ 基于知识库真实数据
- ✅ 只在需要时调用
- ✅ 可以作为多跳推理的一步

---

### 方案 2：生成后推荐（未实现）

**位置**：生成层之后

**触发时机**：生成答案后，根据引用的标准推荐相关标准

**示例**：
```
答案：...（基于 GB 50053-2013）

相关标准推荐：
- GB 50054-2011 低压配电设计规范
- DL/T 5352-2018 高压配电装置设计规范
```

---

## 测试验证

### 测试用例

**查询**："配电室安全距离"

**预期结果**：
```json
{
  "status": "need_clarification",
  "vagueness_score": 0.7,
  "clarification_options": [
    {
      "id": 1,
      "label": "10kV配电室",
      "refined_query": "10kV配电室安全距离要求",
      "standard_preview": null,  // ✅ 不返回标准号
      "doc_count": 0,
      "kb_verified": false
    },
    {
      "id": 2,
      "label": "35kV配电装置",
      "refined_query": "35kV配电装置安全距离要求",
      "standard_preview": null,  // ✅ 不返回标准号
      "doc_count": 0,
      "kb_verified": false
    }
  ]
}
```

---

## 回滚方法

如果需要恢复标准号推荐功能：

```python
# 取消注释
if "standard_series" in result.missing_dimension_keys and result.options:
    result = await self._fill_standard_series_options(query, result)
```

---

**修改时间**：2026-07-13  
**修改人员**：Claude  
**状态**：✅ 已完成
