# 阶段B实现总结

**实施时间**: 2026-07-10  
**状态**: ✅ 已完成

---

## 实现内容

### 1. 预定义维度表 (query_optimizer.py)

新增 `POWER_CLARIFICATION_DIMS` 常量，包含8个电力专业维度：

```python
POWER_CLARIFICATION_DIMS = {
    "voltage_level":      "电压等级",
    "equipment_type":     "设备类型", 
    "application_scene":  "应用场景",
    "neutral_grounding":  "中性点接地方式",
    "capacity_range":     "容量范围",
    "install_env":        "安装环境",
    "standard_series":    "标准系列",
    "protection_type":    "保护类型"
}
```

### 2. 一体化 LLM 输出 (query_optimizer.py)

扩展 `OptimizationResult` 和 `_llm_optimize()` 方法，单次 LLM 调用同时输出：

- **笼统度评估**: vagueness_score, strategy
- **澄清选项**: options, missing_dimension_keys（枚举键列表）
- **路由建议**: lane_suggestion, lane_confidence, lane_reason

LLM prompt 已更新，明确要求输出路由判断（fast/slow）。

### 3. 数据流传递

#### PreprocessingOutput 扩展

新增字段：
- `lane_suggestion`: str = "fast"
- `lane_confidence`: float = 0.7
- `lane_reason`: str = ""
- `missing_dimension_keys`: list = []
- `strategy`: Optional[str] = None

#### QueryService 路由覆盖逻辑

`execute_query()` 方法增加 `user_lane` 参数：
- 如果 `user_lane` 非空，覆盖系统路由
- 否则使用 `Router.route()` 的判断
- 记录 `predicted_lane` 用于数据飞轮

### 4. 数据库新字段 (query_logs 表)

| 字段 | 类型 | 说明 |
|------|------|------|
| `predicted_lane` | ENUM('fast','slow') NOT NULL | LLM 预测的车道 |
| `lane_confidence` | FLOAT | 路由置信度 0-1 |
| `user_lane` | ENUM('fast','slow') NULL | 用户选择的车道（覆盖系统建议时记录） |

**三字段关系**：
- `predicted_lane`: LLM/规则预测 → 写入日志
- `user_lane`: 用户前端选择 → 如果覆盖则写入，否则 NULL
- `lane`: 最终执行的车道 → 优先使用 user_lane，否则 predicted_lane

### 5. 新增 API 端点

#### `POST /api/v1/query/preprocess`

**用途**: 执行预处理但不触发检索，返回系统建议供用户确认

**响应** (`PreprocessResponse`):
```json
{
  "normalized_query": "标准化后的查询",
  "vagueness_score": 0.65,
  "strategy": "clarify_optional",
  "options": [...],
  "missing_dimension_keys": ["voltage_level"],
  "lane_suggestion": "fast",
  "lane_confidence": 0.85,
  "lane_reason": "包含明确电压等级，单一维度查询",
  "preprocessing_time": 4200
}
```

#### `POST /api/v1/query` 扩展

**请求新增字段**:
- `user_lane`: Optional[str] — 用户选择的车道（"fast" 或 "slow"）

**响应新增字段**:
- `lane_suggestion`: 系统建议的车道
- `lane_confidence`: 路由置信度
- `lane_reason`: 路由理由（给用户看）

### 6. Schema 更新

#### QueryRequest (app/schemas/query.py)
```python
user_lane: Optional[str] = Field(default=None, description="用户选择的车道（覆盖系统建议）")
```

#### QueryResponse
```python
lane_suggestion: Optional[str] = None
lane_confidence: Optional[float] = None
lane_reason: Optional[str] = None
```

#### OptimizeQueryResponse
```python
lane_suggestion: str = "fast"
lane_confidence: float = 0.7
lane_reason: str = ""
missing_dimension_keys: List[str] = []
```

#### 新增 PreprocessResponse (app/schemas/preprocessing.py)
完整预处理响应模型，包含所有阶段B字段。

---

## 测试结果

### 测试1: QueryOptimizer 一体化输出 ✅

**明确查询** ("GB 50057-2010 第 5.2.1 条的接地要求"):
- 笼统度: 0.20
- 策略: none
- 路由建议: fast (置信度: 0.70)
- 缺失维度: []

**笼统查询** ("隔离开关的技术参数要求"):
- 笼统度: 0.70
- 策略: clarify_optional
- 路由建议: slow (置信度: 0.90)
- 路由理由: "原始查询缺少多个关键维度，多维度抽象需要精准检索"
- 缺失维度: ['voltage_level', 'equipment_type', 'application_scene']
- 澄清选项: 3个（10kV/户内/变电站场景）

### 测试2: Preprocessor 传递路由字段 ✅

所有路由字段（lane_suggestion/lane_confidence/lane_reason/missing_dimension_keys）正确传递到 PreprocessingOutput。

### 测试3: 数据库字段 ✅

三个新字段（predicted_lane, lane_confidence, user_lane）已成功添加到 query_logs 表。

---

## 前端集成指南

### 场景1: 后确认模式（推荐）

1. **调用预处理接口**:
   ```javascript
   POST /api/v1/query/preprocess
   { "query": "隔离开关的技术参数" }
   ```

2. **展示系统建议**:
   ```
   系统建议: 慢车道 (多维度推理)
   置信度: 90%
   理由: 原始查询缺少多个关键维度
   
   建议澄清:
   [1] 10kV隔离开关参数
   [2] 户内隔离开关参数
   [3] 变电站隔离开关参数
   ```

3. **用户操作**:
   - 接受默认 → `POST /api/v1/query` (不传 user_lane)
   - 切换车道 → `POST /api/v1/query { user_lane: "fast" }`
   - 选择澄清 → `POST /api/v1/query { refined_query: "..." }`

### 场景2: 兼容现有流程

现有的 `POST /api/v1/query` 接口保持向后兼容：
- 不传 `user_lane` → 系统自动路由（与之前行为一致）
- 响应增加 `lane_suggestion` 等字段，前端可选择性展示

---

## 数据飞轮

用户行为自动记录为训练信号：

| 用户行为 | 记录字段 | 用于训练 |
|---------|---------|---------|
| 接受系统路由 | user_lane = NULL | predicted_lane 正样本 |
| 切换 fast → slow | user_lane = "slow" | predicted_lane 负样本 / slow 正样本 |
| 切换 slow → fast | user_lane = "fast" | predicted_lane 负样本 / fast 正样本 |

**SQL 提取误判样本**:
```sql
SELECT query, normalized_query, predicted_lane, user_lane
FROM query_logs
WHERE user_lane IS NOT NULL
  AND user_lane != predicted_lane;
```

积累 1000+ 条后可启动阶段C（微调小模型）。

---

## 后续优化方向

### 近期（1-2周）
- [ ] 接入 ES 知识库填充澄清选项具体值（目前 LLM 凭空生成）
- [ ] Redis 缓存结构更新（增加 lane_suggestion 字段）

### 中期（1-3个月）
- [ ] 前端实现后确认交互 UI
- [ ] 积累路由反馈数据（目标 1000 条）

### 长期（3-6个月）
- [ ] 标注训练数据
- [ ] 微调 Qwen2.5-7B 替换 LLM 调用
- [ ] A/B 测试验证效果

---

## 相关文档

- [15-阶段B-预处理路由一体化设计.md](../docs/architecture/backend/15-阶段B-预处理路由一体化设计.md) — 阶段B完整设计
- [14-预处理路由优化分析.md](../docs/architecture/backend/14-预处理路由优化分析.md) — 三阶段优化路线图
- [06-数据模型设计.md](../docs/architecture/backend/06-数据模型设计.md) — 数据库设计

---

**实现者**: Claude Code  
**审核状态**: 待人工验收
