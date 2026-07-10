# `reasoning_steps` 字段新增完成报告

> 执行时间：2026-07-10
> 数据库：electric_rag
> 表名：query_logs

---

## 执行的 SQL

```sql
ALTER TABLE query_logs ADD COLUMN reasoning_steps JSON COMMENT '慢车道推理步骤详情（工具调用链路）';
```

---

## 验证结果 ✅

### 新增字段详情

| 字段名 | 类型 | 可空 | 注释 |
|-------|------|------|------|
| `reasoning_steps` | JSON | YES | 慢车道推理步骤详情（工具调用链路） |

### 慢车道相关字段完整清单

以下字段均已在 `query_logs` 表中就位：

| 字段名 | 类型 | 用途 | 状态 |
|-------|------|------|------|
| `lane` | ENUM('fast','slow') | 标识快车道/慢车道 | ✅ 已存在 |
| `conversation_id` | VARCHAR(100) | 会话ID（多轮对话） | ✅ 已存在 |
| `retrieval_time` | INT | 检索耗时（ms） | ✅ 已存在 |
| `recall_count` | INT | 召回文档数 | ✅ 已存在 |
| `retrieved_chunk_ids` | JSON | 召回的 chunk IDs | ✅ 已存在 |
| `expanded_queries` | JSON | 各步骤查询文本列表 | ✅ 已存在 |
| `reasoning_steps` | JSON | 工具调用序列详情 | ✅ 新增成功 |
| `strategy` | VARCHAR(30) | 提问优化策略（保留原用途） | ✅ 已存在 |

---

## `reasoning_steps` 字段使用规范

### 数据结构

```json
[
  {
    "step": 1,
    "tool": "list_related_standards",
    "params": {
      "keyword": "功率因数",
      "category": null
    },
    "elapsed_ms": 150,
    "result_count": 3,
    "timeout": false
  },
  {
    "step": 2,
    "tool": "retrieve_standard",
    "params": {
      "query": "380V 异步发电机 功率因数要求",
      "standard_ids": ["GB/T 33593-2017"]
    },
    "elapsed_ms": 800,
    "result_count": 15,
    "timeout": false
  },
  {
    "step": 3,
    "tool": "retrieve_clause",
    "params": {
      "standard_id": "GB/T 33593-2017",
      "clause_number": "5.1"
    },
    "elapsed_ms": 120,
    "result_count": 1,
    "timeout": false
  }
]
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `step` | int | ✅ | 步骤序号（1-3） |
| `tool` | string | ✅ | 工具名称（retrieve_standard / retrieve_clause / list_related_standards） |
| `params` | object | ✅ | 传给工具的参数 |
| `elapsed_ms` | int | ✅ | 该步骤耗时（毫秒） |
| `result_count` | int | ✅ | 返回结果数量 |
| `timeout` | boolean | ✅ | 是否超时 |

---

## 与其他字段的配合使用

### `expanded_queries` vs `reasoning_steps`

| 字段 | 存储内容 | 用途 |
|------|---------|------|
| `expanded_queries` | 各步骤的查询文本（简化版） | 快速查看查询演变过程 |
| `reasoning_steps` | 完整的工具调用详情（详细版） | 深度追溯推理链路、性能分析 |

**示例**：
```json
{
  "expanded_queries": [
    "功率因数要求",
    "GB/T 33593 功率因数"
  ],
  "reasoning_steps": [
    {
      "step": 1,
      "tool": "list_related_standards",
      "params": {"keyword": "功率因数"},
      "elapsed_ms": 150,
      "result_count": 3
    },
    {
      "step": 2,
      "tool": "retrieve_standard",
      "params": {"query": "GB/T 33593 功率因数", "standard_ids": ["GB/T 33593-2017"]},
      "elapsed_ms": 800,
      "result_count": 15
    }
  ]
}
```

---

## 代码实现建议

### 记录推理步骤（`query_service.py`）

```python
# 在 SlowLane.execute() 返回后记录
reasoning_steps = []
for step_idx, step_record in enumerate(slow_lane_result.reasoning_steps, 1):
    reasoning_steps.append({
        "step": step_idx,
        "tool": step_record["tool"],
        "params": step_record["params"],
        "elapsed_ms": step_record["elapsed_ms"],
        "result_count": len(step_record["results"]),
        "timeout": step_record.get("timeout", False)
    })

# 写入数据库
query_log = QueryLog(
    lane="slow",
    retrieval_time=slow_lane_result.retrieval_time,
    recall_count=slow_lane_result.recall_count,
    retrieved_chunk_ids=json.dumps([c.chunk_id for c in slow_lane_result.retrieved_chunks]),
    expanded_queries=json.dumps([step["params"].get("query", "") for step in reasoning_steps if "query" in step["params"]]),
    reasoning_steps=json.dumps(reasoning_steps),  # 新增字段
    # ... 其他字段
)
```

### 查询日志分析（数据分析）

```python
# 统计慢车道最常用的工具组合
SELECT 
    JSON_EXTRACT(reasoning_steps, '$[*].tool') as tool_sequence,
    COUNT(*) as usage_count
FROM query_logs
WHERE lane = 'slow' AND reasoning_steps IS NOT NULL
GROUP BY tool_sequence
ORDER BY usage_count DESC
LIMIT 10;

# 统计各工具平均耗时
SELECT 
    tool_name,
    AVG(elapsed_ms) as avg_elapsed_ms,
    COUNT(*) as call_count
FROM (
    SELECT 
        JSON_EXTRACT(step_data, '$.tool') as tool_name,
        JSON_EXTRACT(step_data, '$.elapsed_ms') as elapsed_ms
    FROM query_logs, 
         JSON_TABLE(reasoning_steps, '$[*]' COLUMNS (
             step_data JSON PATH '$'
         )) as steps
    WHERE lane = 'slow'
) as tool_calls
GROUP BY tool_name;
```

---

## 数据库状态总结

### 表字段完整性 ✅

`query_logs` 表已完全符合慢车道设计文档（13-慢车道设计.md）的要求：

- ✅ 基础字段：lane, user_id, query, normalized_query
- ✅ 召回信息：recall_count, retrieved_chunk_ids, retrieval_time
- ✅ 查询演变：expanded_queries（简化版）
- ✅ 推理链路：reasoning_steps（详细版）← **新增**
- ✅ 多轮对话：conversation_id
- ✅ 性能指标：preprocessing_time, retrieval_time, generation_time, total_time
- ✅ 提问优化：strategy（保留原定义）

### 索引状态

当前 `query_logs` 表索引：
- ✅ idx_user_id
- ✅ idx_conversation_id
- ✅ idx_lane
- ✅ idx_recall_success
- ✅ idx_strategy
- ✅ idx_created_at

**建议**：`reasoning_steps` 字段为 JSON 类型，MySQL 8.0+ 支持虚拟列索引。如需按工具名或步数查询，可创建：

```sql
-- 可选：为 reasoning_steps 创建虚拟列索引（如有查询需求）
ALTER TABLE query_logs 
ADD COLUMN reasoning_step_count INT GENERATED ALWAYS AS (JSON_LENGTH(reasoning_steps)) VIRTUAL,
ADD INDEX idx_reasoning_step_count (reasoning_step_count);
```

---

## 相关文档

- [13-慢车道设计.md](./13-慢车道设计.md) — 慢车道架构设计
- [06-数据模型设计.md](./06-数据模型设计.md) — 数据库表定义
- [13-慢车道设计文档修复完成报告.md](./13-慢车道设计文档修复完成报告.md) — 文档修复记录
