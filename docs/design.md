# 工业级电力专业知识库RAG系统设计方案
本方案面向**国家标准+电力专业书籍**两类核心数据源，以「**高召回准确率、高事实一致性、生产级高可用、可运维可迭代**」为核心目标，采用工程化的分层架构与多路召回体系，从数据、检索、模型、运维四个维度系统性提升RAG命中率与专业可靠性，满足工业化落地标准。

## 一、项目目标与工业级量化指标
### 1.1 核心定位
面向电力设计、运维、检修、安监等场景的专业知识问答系统，所有答案严格溯源至国家标准与权威教材，**零臆测、可溯源、可校验**，替代传统人工查手册、查标准的低效模式。

### 1.2 量化验收指标（工业级标准）
| 指标类别 | 具体指标 | 目标值 |
|---------|---------|--------|
| 检索效果 | Top-5 块召回准确率 | ≥92% |
| 检索效果 | Top-3 条款精准命中率（标准类问题） | ≥95% |
| 生成质量 | 答案事实一致性（与原文无矛盾） | ≥95% |
| 生成质量 | 引用来源完整率 | 100% |
| 系统性能 | 单轮问答响应时间 P95 | ≤3s（采用流式输出时为首token延迟，非流式为完整响应时间；需配置足够LLM推理资源） |
| 系统性能 | 并发支持（QPS） | ≥50（可弹性扩展） |
| 系统可用性 | 全年服务可用性 | ≥99.9% |
| 数据合规 | 标准版本有效率 | 100%（无废止/过期标准） |

## 二、整体架构设计（分层解耦·生产级架构）
采用**七层解耦架构**，各模块独立部署、弹性扩展，避免单体架构的性能瓶颈与维护难题。

```
┌─────────────────────────────────────────────────────┐
│                  业务应用层                          │
│  Web端 / 移动端 / API接口 / 企业内部系统集成         │
├─────────────────────────────────────────────────────┤
│                  检索生成服务层                      │
│  查询路由 → [快车道]固定流水线检索 / [慢车道]自适应检索 → 答案生成 → 校验输出 │
├─────────────────────────────────────────────────────┤
│                  大模型引擎层                        │
│  生成大模型 / 嵌入模型 / 重排模型 / 术语标准化模型    │
├─────────────────────────────────────────────────────┤
│                  索引存储层                          │
│  向量库 / 全文检索库 / 结构化元数据库 / 原始文档库    │
├─────────────────────────────────────────────────────┤
│                  知识加工层                          │
│  文档解析 → 清洗去重 → 智能分块 → 术语增强 → 元数据挂载│
├─────────────────────────────────────────────────────┤
│                  数据源层                            │
│  国家标准库 / 电力专业书籍 / 行业规程 / 设备手册      │
├─────────────────────────────────────────────────────┤
│                  运维管控层                          │
│  监控告警 / 质量评测 / 版本管理 / 权限审计 / 日志链路  │
└─────────────────────────────────────────────────────┘
```

## 三、核心模块详细设计
### 3.1 知识加工层（命中率的基础：70%效果来自数据质量）
针对**国家标准**和**专业书籍**两类文档的结构差异，采用差异化解析与分块策略，避免一刀切导致的上下文断裂或语义混杂。

#### 3.1.1 两类数据源的差异化处理
1. **国家标准类文档（GB/GB/T/DL/NB）**
    - 结构特点：层级严谨（章-节-条-款-项）、条款独立、引用关系多、版本更替频繁、附表附录多。
    - 处理策略：
      - 结构化提取标准号、版本号、发布日期、实施日期、替代关系等元数据；
      - 按**条款粒度**拆分，单条独立成块，保留完整条款编号与上下文说明；
      - 对引用其他条款的内容，自动关联对应条款，形成关联块组；
      - 附录表格、参数表单独成块，保留表格结构与表头。

2. **电力专业书籍类文档**
    - 结构特点：章节体系、原理推导多、公式密集、图表配套、知识点连贯性强。
    - 处理策略：
      - 按目录层级提取章节结构，保留知识的逻辑递进关系；
      - 按**语义知识点**分块，公式+推导+适用条件整体成块，严禁截断公式；
      - 图表与对应文字说明绑定成块，图片单独建立图文索引；
      - 核心定义、定理、结论做标记加权，提升检索优先级。

#### 3.1.2 工业级文档解析流水线
```
原始PDF → 版面分析 → 文本提取 → 公式识别 → 表格还原 → 结构重建 → 清洗归一
```
- 文字版PDF：优先提取原生文本与排版结构，保留标题层级、列表、表格边框
- 扫描版PDF：OCR识别+版面还原，公式采用LaTeX格式识别输出
- 输出格式：统一为结构化Markdown，保留标题、公式、表格、引用标签

#### 3.1.3 智能分块策略（电力领域专属优化）
采用**父子块混合分块机制**，兼顾召回的广度与上下文的完整度，是提升命中率的核心手段之一。

| 块类型 | 粒度 | 作用 | 适用场景 |
|-------|------|------|---------|
| 父块 | 512~1024 token | 用于向量召回，保证语义完整性 | 章节、知识点组、关联条款组 |
| 子块 | 128~256 token | 用于精确定位，送入大模型生成 | 单条标准条款、单个公式、单个定义 |

- 召回时先命中父块，再定位到对应子块，既避免语义碎片化，又保证答案精准度；
- 所有块强制携带**完整元数据**，支持按维度过滤检索。

#### 3.1.4 元数据体系设计（精准过滤的核心）
每个文档块挂载以下元数据字段，检索时可前置过滤，大幅缩小检索空间，提升准确率。
- 基础属性：文档名称、标准号/ISBN、发布机构、版本号、发布日期、有效性状态
- 分类属性：专业分类（配电/变电/继保/高压/输电等）、电压等级、知识类型（规范/原理/参数/流程）
- 位置属性：页码、章节号、条款号
- 权重属性：权威等级（国标>行标>教材>手册）、引用频次

### 3.2 索引存储层（三库协同·多路召回底座）
采用「向量库+全文检索库+结构化库」三库并存架构，覆盖不同检索场景。

#### 3.2.1 向量数据库
- 存储所有父块的稠密向量与稀疏向量（BM42/SPLADE），支持语义相似度检索与关键词混合召回；
- 支持 Payload 字段过滤，可按专业分类、标准号、电压等级等维度缩小检索范围，支持嵌套条件与范围查询；
- 索引类型：HNSW（Qdrant 默认，高性能图索引），采用 Scalar Quantization 量化压缩内存占用；
- 原生支持稠密+稀疏混合检索，可在单次查询内融合语义召回与精确关键词匹配。

#### 3.2.2 全文检索引擎
- 存储所有子块的原始文本，支持关键词精确匹配、短语匹配、模糊检索；
- 对标准号、条款号、专业术语做分词优化，建立专用词库；
- 支持BM25排序，适配精确术语查询场景。

#### 3.2.3 结构化元数据库
- 存储文档台账、版本信息、引用关系、元数据标签；
- 支持标准号精确查询、条款号直接定位、版本有效性校验；
- 当用户明确提及标准编号时，直接命中原文，100%准确。

### 3.3 检索引擎层（命中率提升的核心）
采用**「路由分流 + 双通道检索 + 有界补救」**的混合架构，既保障延迟 SLA 和可审计性，又具备召回失败补救能力与多跳推理能力。

#### 3.3.0 整体架构：快慢双通道设计
针对电力专业问答的「高 SLA 要求 + 高准确性要求」双重约束，采用分层路由架构：

```
用户查询
    ↓
查询预处理（术语归一化、结构化识别）
    ↓
问题复杂度路由
    ├─→ [快车道 90%+流量] 固定流水线检索（单轮确定性）
    │      → 三路召回 → 两阶段重排 → 召回充分性判断
    │            ├─ 充分 → 直接生成
    │            └─ 不充分 → 二次改写重查（最多1次）→ 生成
    │
    └─→ [慢车道 <10%流量] 有界自适应检索（多跳推理）
           → 工具调用循环（最多3步）→ 生成
```

**设计原则**：
1. **默认快车道**：绝大多数「查标准条款/参数/定义」类问题走固定流水线，满足 `P95≤3s` 和 `QPS≥50` 的硬性 SLA；
2. **有界补救**：快车道内置召回充分性判断，首轮召回不足时触发最多 1 次二次检索，补救首轮漏召回问题，延迟上界可控（≤2 轮检索）；
3. **慢车道兜底**：仅对识别出的「跨标准引用、多条款对比、多跳推理」类复杂问题启用受限 agentic 检索（步数上限 2~3 步），单独配额，避免拖垮主链路；
4. **可审计优先**：所有检索路径可追溯，慢车道每步决策记录日志，满足「零臆测、可溯源、可校验」的核心定位。

#### 3.3.1 查询预处理流水线（双通道共用）
用户提问不直接检索，先经过多层标准化处理，消除表达差异并处理笼统提问。

##### 3.3.1.0 提问优化与澄清（核心用户体验优化）
电力专业用户常因不熟悉术语体系而提出笼统问题（如”配电室安全距离”缺少电压等级、”接地要求”存在多义），导致召回不准确或答非所问。通过**智能补全提示 + 自适应澄清对话**显著提升用户体验与召回精度。

**整体架构：大模型驱动 + 多级策略**

```python
def preprocess_with_clarification(query: str, user_context: dict):
    # 1. 大模型判断笼统程度（Few-shot，无需训练）
    vagueness_assessment = llm_assess_vagueness(query, user_context)
    # 返回：{
    #   “vagueness_score”: 0.7,  # 0-1，越高越笼统
    #   “strategy”: “clarify_optional”,  # none/suggest/clarify_optional/clarify_required
    #   “missing_dimensions”: [“voltage_level”],
    #   “ambiguous_terms”: [“接地”],
    #   “reason”: “缺少电压等级，'接地'存在多义”
    # }
    
    # 2. 根据策略分流
    if vagueness_assessment[“strategy”] == “none”:
        return {“action”: “retrieve”, “queries”: [query]}
    
    elif vagueness_assessment[“strategy”] == “suggest”:
        # 策略 1：智能补全提示（轻提示，不阻断）
        suggestions = generate_suggestions(query, vagueness_assessment)
        return {“action”: “suggest”, “suggestions”: suggestions, “query”: query}
    
    elif vagueness_assessment[“strategy”] in [“clarify_optional”, “clarify_required”]:
        # 策略 2：自适应澄清对话
        options = generate_clarification_options(query, vagueness_assessment)
        return {
            “action”: “clarify”,
            “block”: (vagueness_assessment[“strategy”] == “clarify_required”),
            “options”: options
        }
```

**策略 1：智能补全提示（轻度引导，笼统度 0.3-0.6）**

适用场景：提问基本明确，但补充关键信息能显著提升准确性。

工作流程：
1. **大模型识别缺失维度**：
   ```python
   prompt = f”””
   分析电力专业查询缺失的关键信息：
   查询：{query}
   
   判断是否缺少：
   - 电压等级（10kV/35kV/110kV/220kV等）
   - 设备类型（油浸式/干式/户内/户外等）
   - 应用场景（新建/改造/运维/检修等）
   
   输出 JSON：
   {{“missing”: [“voltage_level”], “severity”: “low”}}
   
   查询：配电室安全距离
   输出：
   “””
   ```

2. **从知识库动态生成补全选项**：
   ```python
   def generate_suggestions(query: str, assessment: dict) -> List[dict]:
       suggestions = []
       for dim in assessment[“missing_dimensions”]:
           if dim == “voltage_level”:
               # 查询该主题在知识库中涉及的电压等级
               voltages = vector_db.query(
                   query_text=query,
                   filter={“field”: “voltage_level”, “operator”: “exists”},
                   group_by=”voltage_level”,
                   limit=5
               )
               suggestions.append({
                   “dimension”: “电压等级”,
                   “values”: [{“label”: v[“value”], “doc_count”: v[“count”]} 
                             for v in voltages]
               })
       return suggestions
   ```

3. **前端交互**（非阻断）：
   ```
   用户输入：”配电室安全距离”              [搜索]
   系统显示：
   ┌──────────────────────────────────────┐
   │ 💡 补充电压等级可获得更准确答案：     │
   │  [10kV·32条] [35kV·18条] [110kV·9条] │  ← 显示文档数量
   │  或 [直接搜索通用要求]                │
   └──────────────────────────────────────┘
   ```

**策略 2：自适应澄清对话（中高度引导，笼统度 0.6-1.0）**

适用场景：提问严重笼统或存在多义，必须澄清后才能给出有效答案。

工作流程：
1. **大模型判断笼统度与类型**：
   ```python
   prompt = f”””
   判断电力专业查询的笼统程度：
   查询：{query}
   
   评估维度：
   1. 是否包含多义术语？（如”接地”可指接地电阻/接地装置/接地系统/接地方式）
   2. 是否缺少关键参数？（计算/选型类问题缺少输入条件）
   3. 是否过于宽泛？（单个术语，无明确问题）
   
   输出 JSON（严格格式）：
   {{
     “vagueness_score”: 0.0-1.0,
     “strategy”: “none/suggest/clarify_optional/clarify_required”,
     “issue_type”: “ambiguous_term/missing_params/too_broad”,
     “ambiguous_terms”: [“接地”],
     “reason”: “接地”存在多个专业含义，需明确具体方向”
   }}
   
   示例：
   查询：接地要求
   输出：{{“vagueness_score”: 0.75, “strategy”: “clarify_optional”, “issue_type”: “ambiguous_term”, “ambiguous_terms”: [“接地”], “reason”: “”接地”涉及多个方面”}}
   
   查询：{query}
   输出：
   “””
   ```

2. **动态生成澄清选项**（知识库驱动）：
   ```python
   def generate_clarification_options(query: str, assessment: dict) -> List[dict]:
       options = []
       
       # A. 多义词拆解（从术语库 + 向量检索结合）
       if assessment[“issue_type”] == “ambiguous_term”:
           for term in assessment[“ambiguous_terms”]:
               # 从术语库获取细分概念
               subconcepts = term_dict.get_subconcepts(term)
               
               # 从知识库查询每个概念的相关标准数量
               for concept in subconcepts:
                   doc_count = vector_db.count(
                       query_text=concept[“name”],
                       filter={“doc_type”: “standard”}
                   )
                   options.append({
                       “id”: len(options) + 1,
                       “label”: f”{concept['name']}（{concept['short_desc']}）”,
                       “refined_query”: f”{concept['name']} 要求”,
                       “standard_preview”: concept[“main_standard”],
                       “doc_count”: doc_count
                   })
       
       # B. 缺失维度补充（从知识库聚合）
       elif assessment[“issue_type”] == “missing_params”:
           for dim in assessment[“missing_dimensions”]:
               dim_values = get_dimension_values_from_kb(query, dim)
               options.extend([
                   {“label”: f”{v['value']} 相关要求”, 
                    “refined_query”: f”{v['value']} {query}”,
                    “doc_count”: v[“count”]}
                   for v in dim_values
               ])
       
       # C. 通用兜底选项
       options.append({
           “id”: 999,
           “label”: “查看所有相关要求（综合）”,
           “refined_query”: f”{query} 综合”,
           “is_fallback”: True
       })
       
       return options
   ```

3. **多级 UI 策略**：
   
   **clarify_optional（笼统度 0.6-0.8）**：非阻断式，结果上方嵌入卡片
   ```
   用户输入：”接地要求”
   系统响应：先显示通用结果，上方展示澄清卡片
   
   ┌────────────────────────────────────────┐
   │ 💬 “接地”有多个含义，选择后可获得更精准 │
   │    的答案：                            │
   │                                        │
   │ ○ 接地电阻的阻值要求（≤4Ω）·23条       │
   │   主要标准：GB 50057                   │
   │                                        │
   │ ○ 接地装置的材料与施工规范·18条         │
   │   主要标准：DL/T 621                   │
   │                                        │
   │ ○ 接地系统的类型选择（TN/TT/IT）·15条  │
   │   主要标准：GB/T 16895                 │
   │                                        │
   │      [查看选中内容] [忽略，继续浏览]    │
   └────────────────────────────────────────┘
   
   以下是”接地要求”的通用结果：
   [显示综合检索结果...]
   ```
   
   **clarify_required（笼统度 > 0.8）**：阻断式弹窗
   ```
   用户输入：”接地”
   系统响应：阻断检索，强制选择
   
   ┌────────────────────────────────────────┐
   │ 💬 请明确您关注的”接地”具体方向        │
   ├────────────────────────────────────────┤
   │ ○ 接地电阻的阻值要求（≤4Ω）           │
   │   标准：GB 50057 · 23条相关标准        │
   │                                        │
   │ ○ 接地装置的材料与施工规范             │
   │   标准：DL/T 621 · 18条相关标准        │
   │                                        │
   │ ○ 接地系统的类型选择（TN/TT/IT）      │
   │   标准：GB/T 16895 · 15条相关标准      │
   │                                        │
   │ ○ 以上都不是，让我自己输入             │
   │                                        │
   │              [确认选择]                 │
   └────────────────────────────────────────┘
   ```

**Prompt Engineering 优化（关键）**

为确保大模型判断的稳定性与准确性，采用以下 Prompt 工程技术：

1. **Few-shot 示例**（提供 3-5 个标注样本）：
   ```python
   few_shot_examples = “””
   查询：10kV配电室安全距离要求
   输出：{“vagueness_score”: 0.2, “strategy”: “none”, “reason”: “电压等级明确，问题具体”}
   
   查询：变压器要求
   输出：{“vagueness_score”: 0.65, “strategy”: “suggest”, “missing_dimensions”: [“voltage_level”, “type”], “reason”: “缺少电压等级和变压器类型”}
   
   查询：接地
   输出：{“vagueness_score”: 0.9, “strategy”: “clarify_required”, “issue_type”: “too_broad”, “ambiguous_terms”: [“接地”], “reason”: “过于宽泛且存在多义”}
   
   查询：{query}
   输出：
   “””
   ```

2. **Chain-of-Thought（COT）推理**：
   ```python
   prompt = f”””
   ...评估维度...
   
   逐步分析：
   1. 识别查询中的专业术语和实体
   2. 判断每个术语是否明确（电压等级？设备类型？）
   3. 判断查询是否包含明确问题（”要求是什么” vs “安全距离是多少”）
   4. 基于以上分析给出笼统度评分
   
   分析过程：
   “””
   ```

3. **Output Constraint（严格 JSON 格式）**：
   ```python
   prompt += “””
   
   【重要】必须严格输出 JSON 格式，不要有额外文字：
   {“vagueness_score”: 0.75, “strategy”: “clarify_optional”, ...}
   “””
   ```

**反馈闭环与持续优化**

1. **监控指标**（6.2 节）：
   - 笼统查询识别率（大模型判断为笼统的比例）
   - 各策略触发率分布（none/suggest/clarify_optional/clarify_required）
   - 智能补全点击率（策略 1 用户采纳率）
   - 澄清对话选择分布（识别高频缺失维度与多义词）
   - 用户跳过澄清比例（clarify_optional 模式下，目标 <15%）
   - **关键指标**：澄清前后召回率对比（验证收益）、误判率（用户跳过后仍成功 → 误判为笼统）

2. **每周自动优化**（Airflow DAG）：
   ```python
   def weekly_clarification_optimization():
       # 分析误判 case
       false_positives = db.query(“””
           SELECT query, vagueness_score, user_action, recall_success
           FROM query_logs
           WHERE strategy IN ('clarify_optional', 'clarify_required')
             AND user_action = 'skip'
             AND recall_success = true
           ORDER BY created_at DESC LIMIT 500
       “””)
       
       # 生成 Few-shot 样本优化建议
       new_examples = analyze_and_generate_examples(false_positives)
       
       # 人工审核后更新 Prompt
       update_prompt_examples(new_examples)
       
       # A/B 测试新 Prompt（10% 流量）
       deploy_prompt_variant(“v2.1”, traffic=0.1)
   ```

3. **术语库与知识图谱持续更新**：
   - 从澄清选项的用户选择分布，识别高频多义词补充到术语库
   - 从”以上都不是，自行输入”的用户输入，挖掘新的细分概念

**降级策略与性能保障**

1. **大模型调用三级降级机制**（防止单点故障）：
   ```python
   class VaguenessDetector:
       def assess(self, query: str) -> VaguenessScore:
           # Level 1：优先从缓存读取
           cache_key = f”vagueness:{hash(query)}”
           if cached := redis.get(cache_key):
               return cached
           
           # Level 2：调用大模型（带超时和重试）
           try:
               result = llm_assess_with_timeout(query, timeout=200, max_retries=1)
               redis.setex(cache_key, 3600, result)
               return result
           
           except (Timeout, APIError) as e:
               log.warning(f”LLM degradation: {e}”)
               metrics.increment(“vagueness_llm_degradation”)
               
               # Level 3：降级到规则引擎
               return self.rule_based_fallback(query)
       
       def rule_based_fallback(self, query: str) -> VaguenessScore:
           “””规则引擎降级逻辑（确定性判断）”””
           score = 0.5  # 基础分
           
           # 规则 1：查询长度
           if len(query) < 5:
               score = 0.9  # 过短必然笼统
           elif len(query) > 20 and contains_specific_params(query):
               score = 0.2  # 长且具体
           
           # 规则 2：多义词词典（预定义 50+ 高频多义词）
           ambiguous_dict = {
               “接地”: 0.3, “距离”: 0.25, “保护”: 0.3, 
               “变压器”: 0.2, “开关”: 0.2, “电缆”: 0.15
           }
           for term, weight in ambiguous_dict.items():
               if term in query:
                   score = min(score + weight, 1.0)
           
           # 规则 3：关键维度缺失检测
           if not re.search(r'\d+kV', query):  # 缺少电压等级
               if any(kw in query for kw in [“配电”, “变压器”, “线路”, “开关柜”]):
                   score += 0.15
           
           # 规则 4：明确性加分
           if re.search(r'GB\s*\d+|DL/T\s*\d+', query):  # 包含标准号
               score -= 0.2
           
           return VaguenessScore(
               score=max(0.0, min(score, 1.0)),
               strategy=self._map_to_strategy(score),
               source=”rule_fallback”,  # 标记降级来源
               confidence=0.6  # 规则引擎置信度较低
           )
   ```
   
   **监控指标**（6.2 节新增）：
   - 大模型降级率（目标 <5%，告警阈值 >10%）
   - 降级后误判率 vs 正常误判率（通过 badcase 分析对比）
   - Redis 缓存命中率（目标 >60%，告警阈值 <40%）

2. **澄清选项生成的兜底机制**（防止空选项）：
   ```python
   def generate_clarification_options(query: str, assessment: dict) -> List[dict]:
       options = []
       
       # 尝试从知识库动态生成
       for dim in assessment[“missing_dimensions”]:
           if dim == “voltage_level”:
               voltages = vector_db.query(
                   query_text=query,
                   filter={“field”: “voltage_level”, “operator”: “exists”},
                   group_by=”voltage_level”,
                   limit=5
               )
               
               if voltages:
                   options.extend([
                       {“label”: f”{v['value']} 相关要求”, 
                        “refined_query”: f”{v['value']} {query}”,
                        “doc_count”: v[“count”],
                        “source”: “kb”}
                       for v in voltages
                   ])
               else:
                   # 降级：知识库无数据，使用预定义白名单
                   default_voltages = [“10kV”, “35kV”, “110kV”, “220kV”]
                   options.extend([
                       {“label”: f”{v} 相关要求”, 
                        “refined_query”: f”{v} {query}”,
                        “doc_count”: “未知”,
                        “source”: “fallback”,  # 标记降级来源
                        “is_fallback”: True}
                       for v in default_voltages
                   ])
       
       # 多义词拆解
       if assessment[“issue_type”] == “ambiguous_term”:
           for term in assessment[“ambiguous_terms”]:
               subconcepts = term_dict.get_subconcepts(term)
               if subconcepts:
                   options.extend([...])
               else:
                   # 降级：术语库中无此多义词，使用通用提示
                   options.append({
                       “label”: f”明确”{term}”的具体含义后重新搜索”,
                       “refined_query”: query,
                       “is_fallback”: True
                   })
       
       # 确保至少有两个选项（必须有兜底）
       if len(options) < 2:
           options.append({
               “id”: 998,
               “label”: “以当前查询直接检索”,
               “refined_query”: query,
               “is_fallback”: True
           })
           options.append({
               “id”: 999,
               “label”: “重新输入更具体的问题”,
               “refined_query”: None,  # 触发用户重新输入
               “is_fallback”: True
           })
       
       return options
   ```
   
   **预定义白名单维护**（配置文件）：
   ```yaml
   # config/fallback_dimensions.yaml
   voltage_levels:
     - “0.4kV”
     - “10kV”
     - “35kV”
     - “110kV”
     - “220kV”
     - “500kV”
   
   device_types:
     transformer: [“油浸式变压器”, “干式变压器”, “箱式变电站”]
     switchgear: [“高压开关柜”, “低压配电柜”, “环网柜”]
     cable: [“电力电缆”, “控制电缆”, “架空线路”]
   
   scenarios:
     - “新建工程”
     - “改造工程”
     - “运行维护”
     - “检修作业”
   ```

3. **Query扩展限制**（避免检索膨胀）：
   - 策略 1 补全建议最多生成 3 个维度 × 每个维度 Top-3 值
   - 用户未选择时，后台静默扩展**最多 3 个**最相关查询并行检索
   - 扩展查询按相关度排序，优先高频维度值

##### 3.3.1.1 术语归一化
调用电力术语词典（5000+ 词条），将口语、俗称、缩写统一为标准术语（如”PT”→”电压互感器”、”刀闸”→”隔离开关”），消除表达差异。

对于策略 1 补充的维度或策略 2 明确化的查询，同步进行术语归一化。

##### 3.3.1.2 结构化识别
识别问题中的标准号、条款号、电压等级等信息，用于前置过滤；同时识别查询类型（单点查询/多跳推理/对比分析）。

##### 3.3.1.3 复杂度路由判断
基于规则+轻量分类器识别复杂问题特征：
- 简单查询特征：明确标准号/条款号、单一参数查询、定义类问题 → 快车道
- 复杂查询特征：「对比」「引用」「同时满足」「哪些标准」等多跳关键词、跨领域交叉问题 → 慢车道
- 默认策略：不确定时走快车道，依靠召回充分性判断兜底。

**快车道专属预处理**（仅在路由到快车道时执行）：
- **查询扩展（静默增强）**：若提问仍较笼统（未触发澄清但缺少细节），并行生成多个专业问法
  - 示例：`”变压器绝缘要求”` → `[“10kV变压器绝缘要求”, “35kV变压器绝缘要求”, “油浸式变压器绝缘”, “干式变压器绝缘”]`
  - HyDE（假设文档嵌入）：原理类问题先生成假设答案，再用假设答案做向量检索
- **查询拆解**：复杂问题拆解为多个子问题，分别检索后合并答案（注：此拆解是预设式，非动态迭代）。

#### 3.3.2 快车道：固定流水线检索（默认主路径）
采用**「三路并行召回 → 两阶段重排 → 召回充分性判断 → 可选二次检索」**的确定性流水线，覆盖 90%+ 的标准查询场景。

##### 3.3.2.1 三路并行召回机制
| 召回通路 | 技术方案 | 覆盖场景 | 召回数量 |
|---------|---------|---------|---------|
| 语义向量召回 | 向量数据库稠密向量检索 | 原理类、概念类、模糊提问 | Top 20 |
| 关键词召回 | BM25全文检索（ES）+ 向量库稀疏向量（可选） | 术语、标准号、参数、设备型号 | Top 20 |
| 结构化精确召回 | 元数据库SQL/DSL查询 | 明确标准号、条款号的查询 | Top 10 |

三路召回并行执行，结果合并后去重，进入重排序阶段。

> **架构优化选项**：Qdrant 原生支持稠密+稀疏向量混合检索，可在向量库内直接完成语义召回与关键词召回的融合（使用 BM42 或 SPLADE 稀疏向量），从而简化架构、减少对 Elasticsearch 的依赖。生产阶段可评估是否将关键词召回迁移至 Qdrant，保留 ES 仅用于复杂全文查询与日志检索。

##### 3.3.2.2 两阶段重排序架构
1. **粗排阶段**：使用轻量级重排模型，对合并后的Top50结果快速排序，筛选出Top20，兼顾速度与精度。
2. **精排阶段**：使用高精度重排模型，结合查询与文档块的语义匹配度、权威等级、元数据匹配度综合打分，输出Top5~8候选块。

##### 3.3.2.3 动态权重融合
根据查询类型自动调整三路召回的权重：
- 原理类问题：向量召回权重更高；
- 规范条款类问题：关键词+结构化召回权重更高；
- 参数类问题：全文精确匹配权重最高。

##### 3.3.2.4 召回充分性判断与有界二次检索（补救机制）
在精排输出 Top5~8 后，**不直接送入生成**，而是先进行召回充分性判断，补救首轮召回失败的情况：

1. **充分性判断模型**：
   - 使用轻量级判别模型（或调用大模型快速判断），输入：查询 + Top5~8 块的标题/摘要；
   - 输出：二分类（充分/不充分）+ 置信度；
   - 判断标准：Top 块是否包含查询所需的核心信息（标准条款/参数值/定义/公式等）。

2. **分支逻辑**：
   ```
   if 召回充分（置信度 > 阈值，如 0.75）:
       直接送入生成层 → 3.4 节
   else:
       触发二次检索（最多 1 次）:
           - 基于 Top5~8 块的内容，生成改写查询（补充缺失的关键信息维度）
           - 重新执行三路召回 + 重排（复用 3.3.2.1~3.3.2.2 流程）
           - 合并首轮 Top5 + 二次 Top5，去重后重排，输出最终 Top8
           - 送入生成层（不再判断，避免无限循环）
   ```

3. **延迟控制**：
   - 充分性判断耗时 < 100ms（轻量模型推理）；
   - 二次检索触发率预期 < 15%；
   - 即使触发二次检索，总延迟仍可控在 P95 < 3s 范围内（1 轮检索 ~1.2s，2 轮 ~2.4s + 生成 ~0.5s）。

4. **监控指标**：
   - 二次检索触发率（按周统计）；
   - 二次检索后命中率提升幅度（A/B 对比）；
   - 充分性判断准确率（人工抽样标注）。

#### 3.3.3 慢车道：有界自适应检索（复杂问题兜底）
针对路由识别出的**多跳推理、跨标准引用、对比分析**类问题，启用模型主动调用检索工具的 agentic 模式，但严格限制步数与延迟上界。

##### 3.3.3.1 适用场景识别
- 跨标准引用：「GB 50057 和 DL/T 621 对接地电阻要求有何差异」
- 多条款对比：「10kV 和 35kV 配电室的安全距离分别是多少」
- 多跳推理：「某设备需满足 IP54 防护等级，应遵循哪些国家标准的哪些条款」
- 交叉领域：「继保装置的电磁兼容性要求涉及哪些标准」

##### 3.3.3.2 工具调用循环架构（带完整错误处理）
```python
class AgenticRetriever:
    def retrieve(self, query: str, max_steps=3, timeout_per_step=2000, total_timeout=7000):
        """
        有界自适应检索（严格控制步数与延迟）
        
        Args:
            max_steps: 最多工具调用次数（默认 3）
            timeout_per_step: 单步超时（毫秒，默认 2000ms）
            total_timeout: 总延迟预算（毫秒，默认 7000ms，留 1s 给生成）
        
        Returns:
            {
                "status": "success" | "partial" | "failed",
                "results": [...],  # 召回的文档块
                "steps": int,  # 实际执行步数
                "reasoning": str,  # 推理链路（可选）
                "message": str  # 用户提示（部分/失败时）
            }
        """
        results = []
        reasoning_steps = []
        total_elapsed = 0
        
        for step in range(max_steps):
            # 检查总延迟预算
            if total_elapsed > total_timeout:
                log.warning(f"Total timeout exceeded: {total_elapsed}ms")
                break
            
            step_start = time.time()
            
            try:
                # 模型决策：是否需要继续检索
                decision = llm_decide_next_action(
                    query=query,
                    current_results=results,
                    timeout=500  # 决策快速完成
                )
                
                if decision["action"] == "sufficient":
                    # 模型判断信息已充分，提前退出
                    reasoning_steps.append(f"步骤 {step+1}：信息已充分，准备生成答案")
                    return {
                        "status": "success",
                        "results": results,
                        "steps": step + 1,
                        "reasoning": "\n".join(reasoning_steps)
                    }
                
                elif decision["action"] == "retrieve":
                    # 调用检索工具
                    tool_name = decision["tool"]
                    tool_params = decision["params"]
                    
                    reasoning_steps.append(
                        f"步骤 {step+1}：调用 {tool_name}，参数：{tool_params}"
                    )
                    
                    tool_result = self.call_tool(
                        tool_name, 
                        tool_params, 
                        timeout=timeout_per_step
                    )
                    
                    if tool_result.get("error"):
                        # 工具调用失败（超时/无结果）
                        reasoning_steps.append(
                            f"  → 检索失败：{tool_result['error']}"
                        )
                        results.append({
                            "step": step + 1,
                            "status": "failed",
                            "error": tool_result["error"]
                        })
                    else:
                        # 工具调用成功
                        reasoning_steps.append(
                            f"  → 检索成功：找到 {len(tool_result['docs'])} 条相关内容"
                        )
                        results.append({
                            "step": step + 1,
                            "status": "success",
                            "docs": tool_result["docs"]
                        })
            
            except Timeout as e:
                # 决策超时
                reasoning_steps.append(f"步骤 {step+1}：决策超时，终止检索")
                log.error(f"Decision timeout at step {step+1}: {e}")
                break
            
            except Exception as e:
                # 其他异常
                reasoning_steps.append(f"步骤 {step+1}：发生错误 {type(e).__name__}")
                log.error(f"Unexpected error at step {step+1}: {e}")
                break
            
            finally:
                step_elapsed = (time.time() - step_start) * 1000
                total_elapsed += step_elapsed
        
        # 循环结束（步数耗尽或超时）：评估结果
        successful_results = [r for r in results if r.get("status") == "success"]
        
        if not successful_results:
            # 完全失败：所有步骤都失败
            return {
                "status": "failed",
                "results": [],
                "steps": len(results),
                "reasoning": "\n".join(reasoning_steps),
                "message": "未找到相关信息。建议：\n1. 简化查询，使用单个标准号\n2. 改用快车道查询单个方面"
            }
        
        elif len(successful_results) < len(reasoning_steps) or total_elapsed > total_timeout:
            # 部分成功：有些步骤失败或超时
            return {
                "status": "partial",
                "results": successful_results,
                "steps": len(results),
                "reasoning": "\n".join(reasoning_steps),
                "message": f"找到部分信息（{len(successful_results)}/{max_steps}），可能不完整"
            }
        
        else:
            # 完全成功
            return {
                "status": "success",
                "results": successful_results,
                "steps": len(results),
                "reasoning": "\n".join(reasoning_steps)
            }
    
    def call_tool(self, tool_name: str, params: dict, timeout: int):
        """调用检索工具（带超时控制）"""
        try:
            if tool_name == "retrieve_standard":
                return self._retrieve_standard(**params, timeout=timeout)
            elif tool_name == "retrieve_clause":
                return self._retrieve_clause(**params, timeout=timeout)
            elif tool_name == "list_related_standards":
                return self._list_related_standards(**params, timeout=timeout)
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        
        except Timeout:
            return {"error": "timeout"}
        except Exception as e:
            return {"error": str(e)}
```

**工具定义**：
- `retrieve_standard(query: str, standard_ids: list = None, voltage_level: str = None, top_k: int = 5)`：调用快车道的三路召回机制，返回文档块
- `retrieve_clause(standard_id: str, clause_number: str)`：精确定位某标准某条款，调用结构化库直接命中
- `list_related_standards(keyword: str, category: str = None)`：返回包含某关键词的相关标准清单（元数据库查询）

##### 3.3.3.3 控制策略与降级处理
1. **步数上限**：最多 3 次工具调用（实测多跳问题 2~3 步即可覆盖）；
2. **延迟上限**：慢车道总延迟预算 8s（检索 3×2s + 生成 2s），超时则截断并返回当前最佳结果 + 「信息不完整」提示；
3. **单独配额**：慢车道独立限流（如 QPS=10），避免拖垮快车道的 SLA；
4. **降级策略**：当慢车道队列积压时，自动将新请求降级到快车道 + 提示「简化回答」。

##### 3.3.3.4 可审计性保障
- 每次工具调用记录：调用时间、查询参数、返回块数、相关度评分；
- 最终答案附上完整推理链路：「步骤 1：检索到 GB 50057 条款 X → 步骤 2：检索到 DL/T 621 条款 Y → 对比结论...」；
- 用户界面展示「展开推理过程」按钮，透明化决策链路。

### 3.4 大模型生成层（专业可靠·可溯源）
#### 3.4.1 领域化提示词工程
核心提示词遵循「**依据优先、溯源强制、安全兜底**」原则，示例框架：
```
你是资深电力专业知识助手，必须严格基于下方【参考资料】回答用户问题。
核心规则：
1. 所有结论必须来自参考资料，禁止编造参数、条款、公式；无法回答时明确说明"暂无权威资料支撑"。
2. 引用国家标准需标注「标准号+条款号」，引用教材需标注「书名+章节」。
3. 涉及计算公式需注明符号含义与适用条件；涉及安全操作必须前置安全警示。
4. 专业术语使用行业规范表述，英文缩写首次出现标注全称。
5. 若参考资料存在多个版本，默认采用最新有效版本，并标注版本号。

【参考资料】
{context}

【用户问题】
{query}
```

#### 3.4.2 答案生成与引用溯源
- 答案中每个论断对应标注引用编号，文末附完整来源列表（文档名、版本、页码/条款号）；
- 标准类内容优先原文引用条款，再补充解释，避免二次转述失真；
- 公式采用LaTeX格式渲染，附带参数说明与适用边界。

#### 3.4.3 事实一致性校验与安全风控
- 生成后调用校验模型，比对答案与召回原文的事实一致性，识别幻觉内容并修正；
- 高危场景（带电作业、倒闸操作、安全距离）自动插入通用安全警示；
- 违规、违法类问题直接拒答，返回合规提示。

## 四、全栈技术选型（工业级生产就绪）
### 4.1 知识加工与数据处理
| 模块 | 技术选型 | 选型理由 |
|------|---------|---------|
| PDF版面解析 | PyMuPDF + LayoutLMv3 | 精准提取文字、表格、标题层级，还原文档结构 |
| 扫描件OCR | PaddleOCR 企业版 | 中文专业文档识别率高，支持表格、公式检测 |
| 公式识别 | Mathpix 自建服务 / SimpleTex | 公式转LaTeX准确率高，适配电力公式符号 |
| 文档处理流水线 | Prefect / 脚本+Cron（MVP）→ Apache Airflow（生产） | MVP阶段轻量部署，生产阶段升级为Airflow实现定时任务、流程编排、失败重试，适配批量入库 |
| 术语标准化 | 自定义电力术语词典 + 同义词映射 | 行业专属，可控可维护，避免通用分词偏差 |

### 4.2 索引与存储
| 模块 | 技术选型 | 选型理由 |
|------|---------|---------|
| 向量数据库 | Qdrant | Rust实现，原生支持稠密+稀疏混合检索，Payload过滤表达力强，单二进制部署，生产阶段启用3节点Raft分布式模式 |
| 全文检索引擎 | Elasticsearch 8.x | 成熟稳定，8.x支持原生向量KNN、改进的安全机制，分词可定制，支持复杂查询，运维生态完善 |
| 结构化元数据库 | MySQL 8.0 + Redis | MySQL存台账元数据，Redis缓存热点标准与高频查询 |
| 原始文档存储 | MinIO 对象存储 | 私有化部署，兼容S3协议，存储原始PDF与图片资源 |

### 4.3 模型层
| 模块 | 技术选型 | 选型理由 |
|------|---------|---------|
| 嵌入模型基座 | bge-large-zh-v1.5 | 中文语义效果领先，1024维，开源可商用，适配垂直领域微调 |
| 重排模型 | bge-reranker-large | 中文重排效果最优，精排阶段大幅提升命中率 |
| 生成大模型（公有云） | 豆包 Pro / 通义千问 Turbo | 中文专业领域理解强，长上下文支持好，幻觉率低（生产部署时需锁定具体模型版本号如 doubao-pro-32k、qwen-turbo-latest） |
| 生成大模型（私有化） | Qwen2.5-72B-Instruct | 开源可商用，性能接近闭源模型，支持电力领域继续微调，128K上下文窗口 |

> 进阶优化：使用电力标准+教材语料对嵌入模型做**LoRA小样本微调**，专业术语召回率可提升10%~15%。

### 4.4 服务与运维
| 模块 | 技术选型 | 选型理由 |
|------|---------|---------|
| 后端服务 | FastAPI + Pydantic | 高性能异步接口，自动生成API文档，类型安全 |
| **提问优化模块** | **大模型 Few-shot（豆包/通义千问）+ Redis 缓存** | **无需训练数据即可上线，Few-shot + COT 保证判断准确性，高频查询缓存降低成本（缓存命中率预期 >60%）** |
| 服务编排 | Kubernetes + Docker | 容器化部署，弹性扩缩容，滚动更新，保障高可用 |
| 网关与限流 | Nginx + APISIX | 流量控制、权限校验、限流熔断 |
| 监控告警 | Prometheus + Grafana | 全链路指标监控，检索耗时、召回率、QPS、提问优化触发率可视化 |
| 日志链路 | ELK + Jaeger | 日志归集、分布式链路追踪，问题排查可追溯 |
| 质量评测 | RAGAS + 自定义电力测试集 | 自动化评估召回率、事实一致性，定期跑批巡检 |

### 4.5 成本管理与优化策略

#### 4.5.1 大模型成本预估（基线场景：QPS=50）

| 调用场景 | 触发条件 | 日调用量估算 | 平均 Token | 日成本（豆包 Pro） | 月成本 |
|---------|---------|-------------|-----------|------------------|--------|
| 提问优化（笼统度判断） | 每次查询，60%缓存命中 | 432万 × 40% = 173万 | 输入200 + 输出50 | 433元 | 1.3万 |
| 查询改写（快车道） | 非笼统查询，50%触发 | 432万 × 50% = 216万 | 输入150 + 输出100 | 540元 | 1.6万 |
| 召回充分性判断 | 快车道所有查询 | 432万 | 输入300 + 输出20 | 1382元 | 4.1万 |
| 慢车道工具调用 | 10%查询，平均2.5步 | 43万 × 2.5 = 108万 | 输入200 + 输出100 | 324元 | 0.97万 |
| Loop Engineering | 每周自动分析 | 250次/周 | 输入500 + 输出200 | 2.5元 | 0.08万 |
| **总计** | - | - | - | **2682元/天** | **8.05万/月** |

**成本说明**：
- 价格基于豆包 Pro（0.001元/1K token），通义千问 Turbo 价格类似
- 实际成本会因缓存命中率、触发率波动而变化
- 如缓存命中率从 60% 降至 40%，月成本将增加约 30%（+2.4万/月）

#### 4.5.2 成本优化策略（四级优化）

**Level 1：缓存优化（第二阶段立即实施）**

目标：将缓存命中率从 60% 提升至 75%，降低成本 20%

```python
# 多级缓存架构
class MultiLevelCache:
    def __init__(self):
        self.l1 = {}  # 本地内存（超高频，5分钟TTL）
        self.l2 = redis_client  # Redis（高频，1小时TTL）
        self.l3 = redis_client  # Redis（中频，24小时TTL）
    
    def get(self, key: str):
        # L1: 进程内存
        if key in self.l1:
            return self.l1[key]
        
        # L2: Redis 短期缓存
        if value := self.l2.get(f"hot:{key}"):
            self.l1[key] = value  # 回填 L1
            return value
        
        # L3: Redis 长期缓存
        if value := self.l3.get(f"warm:{key}"):
            self.l2.setex(f"hot:{key}", 3600, value)  # 提升到 L2
            return value
        
        return None
    
    def set(self, key: str, value, frequency: str = "medium"):
        """根据访问频率设置不同 TTL"""
        if frequency == "high":
            self.l1[key] = value
            self.l2.setex(f"hot:{key}", 3600, value)
        elif frequency == "medium":
            self.l2.setex(f"hot:{key}", 3600, value)
        else:
            self.l3.setex(f"warm:{key}", 86400, value)
```

**预期收益**：月成本从 8.05万 降至 6.4万（-20%）

---

**Level 2：选择性降级（高峰时段）**

触发条件：QPS >80 或 日成本 >3500元

```python
# 高峰时段自动降级规则
class CostControlPolicy:
    def should_degrade(self) -> dict:
        current_qps = get_current_qps()
        daily_cost = get_daily_cost()
        
        if current_qps > 80:
            return {
                "vagueness_detection": "rule_engine",  # 提问优化降级到规则
                "query_rewrite": "disabled",  # 禁用查询改写
                "sufficiency_check": "simplified"  # 简化充分性判断
            }
        
        if daily_cost > 3500:
            return {
                "slow_lane": "throttle",  # 慢车道限流到 QPS=3
                "cache_ttl": "extend"  # 缓存 TTL 延长到 3小时
            }
        
        return {}  # 正常模式
```

**预期收益**：高峰时段成本降低 40%，对体验影响 <10%

---

**Level 3：轻量模型替代（第三阶段）**

目标：关键模块切换到自训练轻量模型，成本降低 80%

| 模块 | 现状（第二阶段） | 优化（第三阶段） | 成本降幅 |
|------|----------------|----------------|---------|
| 提问优化 | 豆包 Pro Few-shot | 微调 BERT 分类器（本地部署） | -95% |
| 召回充分性判断 | 豆包 Pro | 蒸馏 DistilBERT（本地部署） | -90% |
| 查询改写 | 豆包 Pro | 小型 Seq2Seq 模型（本地） | -85% |

**实施成本**：
- 数据标注：1000+ 样本 × 5元/样本 = 0.5万
- 模型训练：GPU 租用 + 人力 = 1万
- 一次性投入 1.5万，预期 2 个月回本

**预期收益**：月成本从 6.4万 降至 2.5万（-61%）

---

**Level 4：批量调用与异步化（持续优化）**

```python
# Loop Engineering 批量调用优化
def weekly_term_analysis_batch():
    """术语分析改为批量调用（50条/次）"""
    candidates = get_term_candidates(limit=50)
    
    # 构造批量 Prompt
    batch_prompt = f"""
    分析以下 {len(candidates)} 个术语候选：
    
    {json.dumps(candidates, indent=2, ensure_ascii=False)}
    
    对每个候选，输出：是否为有效专业术语、推荐映射关系
    """
    
    # 单次调用处理 50 个，成本降低 80%
    results = llm_call_batch(batch_prompt)
    
    # 后处理
    for candidate, result in zip(candidates, results):
        if result["is_valid"]:
            add_to_term_dict(candidate, result["mapping"])
```

**预期收益**：Loop Engineering 成本降低 70%

---

#### 4.5.3 成本监控与告警

**实时监控指标**：
- 每小时 LLM 调用量（按场景分类）
- 每小时 Token 消耗（输入/输出分别统计）
- 累计日成本（实时更新）
- 缓存命中率（L1/L2/L3 分别统计）

**告警阈值**：
- 日成本 >3500元（超预算 30%）
- 缓存命中率 <50%（低于预期）
- 单小时调用量环比增长 >50%（异常流量）
- 大模型降级率 >10%（服务质量下降）

**月度预算管理**：
- 设定月预算上限：12万/月（含 50% 冗余）
- 超预算自动降级：累计成本达 10万时触发 Level 2 降级
- 预算预警：累计成本达 8万时发送预警通知

**成本优化决策树**：
```
当前月成本 ?
├─ <6万 → 正常模式，无需优化
├─ 6-8万 → 观察模式，分析高成本原因
├─ 8-10万 → 预警模式，启动 Level 1 优化
├─ 10-12万 → 告警模式，启动 Level 2 降级
└─ >12万 → 熔断模式，暂停非核心功能
```

#### 4.5.4 MVP 与生产版本成本对比

| 阶段 | QPS | 大模型调用场景 | 月成本估算 | 备注 |
|------|-----|--------------|-----------|------|
| MVP（1.5个月） | 10 | 仅生成大模型 | 0.8万 | 无提问优化、无充分性判断 |
| 生产版本（初期） | 50 | 全功能，60%缓存命中 | 8.05万 | 本方案第二阶段 |
| 生产版本（优化后） | 50 | Level 1+2 优化 | 4.5万 | 缓存优化+选择性降级 |
| 深度运营（第三阶段） | 100 | Level 3 轻量模型替代 | 6万 | QPS翻倍但单位成本降低 |

**关键结论**：
- 第二阶段全功能上线时成本最高（8万/月），需提前准备预算
- 通过 Level 1+2 优化，可在 3 个月内将成本降至 4.5万/月
- 第三阶段投入轻量模型训练（1.5万），2个月回本，长期成本可控

## 五、RAG检索命中率专项提升方案（核心手段）
### 1. 快慢双通道路由，按需分配检索策略
通过轻量级分类器识别问题复杂度，简单查询走快车道（固定流水线，低延迟），复杂多跳问题走慢车道（自适应检索，高准确性），兼顾效率与效果。

### 2. 召回充分性判断 + 有界二次检索，补救首轮漏召回
快车道内置召回充分性判断，首轮召回不足时触发改写重查（最多 1 次），在不破坏延迟 SLA 的前提下，大幅降低「答非所问」的漏召回问题。

### 3. 有界 agentic 检索，攻克多跳推理难题
慢车道启用模型主动调用检索工具，支持跨标准引用、多条款对比等复杂场景，但严格限制步数（≤3 步）与延迟（≤8s），避免无界循环。

### 4. 向量库原生混合检索，一次查询融合稠密+稀疏召回
Qdrant 原生支持在单次查询中融合稠密向量（语义）+ 稀疏向量（BM42/SPLADE关键词），通过 RRF（Reciprocal Rank Fusion）自动融合排序，减少多路召回的网络开销与融合复杂度，提升响应速度与召回一致性。

### 5. 领域化嵌入微调，缩小语义鸿沟
用电力国家标准、教材、术语词典构建领域语料，对bge嵌入模型做LoRA微调，让向量空间更贴合电力专业语义，解决通用嵌入模型对专业术语区分度不足的问题。

### 6. 父子块混合召回，兼顾精度与上下文
粗粒度父块保证语义完整，细粒度子块保证定位精准，召回时父子联动，既避免漏召回，又减少无关上下文干扰。

### 7. 电力术语标准化，消除表达差异
构建覆盖5000+词条的电力术语映射库（别名、缩写、俗称、新旧名称），查询侧与文档侧双向归一化，从根源解决”问法不同但意思一致”的召回失败问题。

### 8. 多Query改写+HyDE，扩展召回维度
- 对原始问题生成2~3个同义专业问法，分别检索后合并结果；
- 对原理类问题使用HyDE（假设文档嵌入）：先生成一段假设的专业解答，再用该解答做向量检索，大幅提升模糊问题的召回率。

### 9. 三路混合召回 + 两阶段重排，覆盖全匹配场景
向量召回解决语义匹配，BM25解决精确术语匹配，结构化召回解决标准号/条款号精确查询，三路互补；粗排保速度、精排保质量，确保送入大模型的Top5块高相关。

### 10. 元数据前置过滤，缩小检索空间
根据问题识别出的专业分类、电压等级、标准类型等维度，先过滤掉无关文档块，再在子集中做相似度检索，大幅降低噪声干扰，提升精准度。

### 11. 难例挖掘闭环，持续迭代效果
- 收集用户反馈的”答非所问”问题，分析是分块问题、嵌入问题还是召回策略问题；
- 定期补充难例到测试集，针对性优化分块规则、术语库与模型权重，形成迭代闭环。

### 12. 量化评测体系，效果可度量
构建200+条覆盖不同场景的电力专业测试集，每月自动跑批，输出Recall@3、Recall@5、MRR、事实一致性等指标，用数据驱动优化，而非凭感觉调整。

## 六、工业级非功能保障设计
### 6.1 高可用与弹性扩展
- 所有服务无状态化，K8s部署，支持水平扩缩容；
- 向量库、数据库采用主从+分片架构，避免单点故障；
- 配置降级策略：高峰时段自动减少召回数量，保障核心接口可用。

### 6.2 全链路可观测性
- 核心指标：
  - 检索链路：快慢车道流量分布、检索耗时、召回数量、重排耗时、生成耗时、二次检索触发率、错误率、命中率
  - **提问优化**：笼统查询识别率、智能补全触发率与点击率、澄清对话触发率、用户选择分布、澄清前后召回率对比、用户跳过澄清比例
- 全链路追踪：单次请求从查询到返回的每个节点耗时、召回结果、路由决策、提问优化决策（是否触发澄清/补全）、工具调用链路可回溯；
- 告警机制：命中率下降、响应超时、慢车道队列积压、二次检索触发率异常、澄清触发率过高（>25%，说明笼统判断过于激进）、服务异常自动告警。

### 6.3 标准版本全生命周期管理
- 建立标准台账，同步国标委、能源局最新标准发布/废止信息；
- 支持多版本并存，查询默认返回最新有效版本，标注替代关系；
- 知识库版本化，支持回滚与增量更新，避免更新导致效果波动。

### 6.4 质量保障与审核机制
- 高风险问题（安全、设计选型）默认标记人工复核；
- 用户反馈的错误答案进入审核队列，修正后回流优化知识库；
- 每月专家抽检，评估回答专业准确性。

### 6.5 Loop Engineering：闭环工程提升系统可靠性
采用**「监控 → 分析 → 优化 → 验证」**的自动化闭环机制，持续提升系统召回率与用户体验，避免系统效果随时间衰退。

#### 6.5.1 核心理念
Loop Engineering（闭环工程）不同于传统的"上线后被动修 bug"模式，而是**主动构建数据驱动的持续优化循环**，将线上问题自动转化为优化动力。

```
用户反馈 → 数据采集 → 问题诊断 → 自动优化 → A/B 验证 → 灰度上线 → 用户反馈（循环）
```

#### 6.5.2 五大闭环机制（含自动化率优化）

**自动化分级策略**（解决人工审核瓶颈）

Loop Engineering 的每个闭环都包含**自动筛选 + 人工审核**两阶段，通过置信度评分将高置信度候选自动处理，仅将边界 case 送入人工审核，确保每周审核工作量 <3 小时。

| 闭环 | 自动化目标 | 人工审核触发条件 | 预期审核量/周 | 审核耗时 |
|------|-----------|-----------------|-------------|---------|
| 闭环 1：Prompt 优化 | 置信度 <0.7 自动过滤 | 置信度 ≥0.7 且样本数 ≥10 | 5-10 个样本 | 50-100 分钟 |
| 闭环 2：术语扩展 | 频次 ≥5 自动加入，≤2 自动丢弃 | 频次 3-4 的边界 case | 5-8 个术语 | 25-40 分钟 |
| 闭环 3：难例优化 | 根因明确的自动归类 | 根因不明的复杂 case | 3-5 个 case | 30-50 分钟 |
| 闭环 4：测试集扩充 | 正样本（用户好评）自动加入 | 边界 case、争议样本 | 2-3 个样本 | 10-15 分钟 |
| 闭环 5：A/B 决策 | 显著差异（>5%）自动全量/下线 | 微弱差异（2-5%）需人工判断 | 1-2 个实验/月 | 30-60 分钟/月 |
| **总计** | - | - | **15-25 items/周** | **2-3 小时/周** |

---

**闭环 1：提问优化 Prompt 自动迭代**

目标：降低笼统度判断的误判率，提升澄清选项的相关性。

流程（含自动筛选）：
```python
# Airflow DAG：每周执行
def prompt_optimization_loop():
    # 1. 数据采集（过去 7 天）
    logs = collect_clarification_logs(days=7)
    
    # 2. 问题诊断
    issues = {
        "false_positive": [],  # 误判为笼统，用户跳过后成功
        "false_negative": [],  # 未识别笼统，二次检索才成功
        "bad_options": []      # 澄清选项不符合用户需求
    }
    
    for log in logs:
        if log["clarified"] and log["user_skipped"] and log["recall_success"]:
            issues["false_positive"].append(log)
        elif not log["clarified"] and log["required_retry"]:
            issues["false_negative"].append(log)
        elif log["clarified"] and log["user_choice"] == "other":
            issues["bad_options"].append(log)
    
    # 3. 自动筛选高质量负样本
    if len(issues["false_positive"]) > 20:
        # 3.1 提取候选样本
        candidate_examples = []
        for case in issues["false_positive"]:
            # 使用 LLM 判断样本质量
            quality_score = llm_assess_example_quality(case)
            candidate_examples.append({
                "query": case["query"],
                "label": "not_vague",  # 负样本
                "quality_score": quality_score,
                "frequency": case["frequency"]  # 该查询出现频次
            })
        
        # 3.2 自动过滤
        auto_approved = [e for e in candidate_examples 
                        if e["quality_score"] > 0.7 and e["frequency"] >= 3]
        
        needs_review = [e for e in candidate_examples 
                       if 0.5 <= e["quality_score"] <= 0.7 or e["frequency"] == 2]
        
        auto_rejected = [e for e in candidate_examples 
                        if e["quality_score"] < 0.5 or e["frequency"] < 2]
        
        # 3.3 自动处理高置信度样本
        if len(auto_approved) >= 5:
            # 自动注入 Prompt
            updated_prompt = inject_examples_to_prompt(
                current_prompt, 
                auto_approved[:5]  # 最多加 5 个
            )
            
            # A/B 验证（10% 流量）
            variant_id = deploy_prompt_variant(updated_prompt, traffic=0.1)
            schedule_evaluation(variant_id, days=7)
            
            log.info(f"Auto-deployed prompt variant with {len(auto_approved)} examples")
        
        # 3.4 人工审核队列（仅边界 case）
        if needs_review:
            send_to_review_dashboard({
                "type": "prompt_optimization",
                "samples": needs_review[:10],  # 最多 10 个
                "estimated_time": f"{len(needs_review) * 10} 分钟",
                "priority": "medium"
            })
    
    # 4. 生成周报
    report = {
        "auto_approved": len(auto_approved) if 'auto_approved' in locals() else 0,
        "needs_review": len(needs_review) if 'needs_review' in locals() else 0,
        "auto_rejected": len(auto_rejected) if 'auto_rejected' in locals() else 0,
        "false_positive_rate": len(issues["false_positive"]) / len(logs),
        "false_negative_rate": len(issues["false_negative"]) / len(logs)
    }
    send_weekly_report(report)
```

**自动质量评估**（LLM）：
```python
def llm_assess_example_quality(case: dict) -> float:
    """使用 LLM 判断 Few-shot 样本质量"""
    prompt = f"""
    判断以下查询是否适合作为"不笼统"的负样本：
    
    查询：{case["query"]}
    用户行为：跳过澄清 → 召回成功
    
    评估标准：
    1. 查询是否足够明确？（包含电压等级、设备类型等关键信息）
    2. 是否是常见查询模式？（代表性强）
    3. 是否容易引起误判？（边界 case）
    
    输出 JSON：
    {{"quality_score": 0.0-1.0, "reason": "..."}}
    
    输出：
    """
    
    result = llm_call(prompt)
    return result["quality_score"]
```

关键指标：
- 误判率（False Positive Rate）：触发澄清但用户跳过后成功 → 目标 <10%
- 漏判率（False Negative Rate）：未触发澄清但召回失败 → 目标 <5%
- 自动化率：自动处理比例 → 目标 >60%
- Prompt 迭代频率：每周自动生成优化建议，2周内上线

---

**闭环 2：术语库动态扩展**（含自动验证）

目标：从用户输入中挖掘新术语、俗称、缩写，持续扩充术语标准化词典。

流程：
```python
def terminology_expansion_loop():
    # 1. 采集"自行输入"的用户澄清结果
    custom_inputs = db.query("""
        SELECT user_input, original_query, final_recall_success, COUNT(*) as frequency
        FROM clarification_logs
        WHERE user_choice = 'custom_input'
          AND created_at > NOW() - INTERVAL 7 DAY
        GROUP BY user_input, original_query
    """)
    
    # 2. 使用大模型批量分析（50条/次，降低成本）
    term_candidates = []
    for batch in chunk(custom_inputs, 50):
        prompt = f"""
        批量分析用户如何明确化了笼统查询：
        {json.dumps(batch, ensure_ascii=False)}
        
        对每个 case，识别用户补充的关键信息（专业术语、参数、场景）
        输出 JSON 数组：[{{"original": "...", "added_term": "...", "type": "术语/参数/场景"}}]
        """
        
        results = llm_call_batch(prompt)
        term_candidates.extend(results)
    
    # 3. 自动验证与分级
    for candidate in term_candidates:
        # 3.1 计算置信度
        confidence = calculate_term_confidence(candidate)
        
        # 3.2 自动分级决策
        if candidate["frequency"] >= 5 and confidence > 0.8:
            # 高频高置信 → 自动加入术语库
            add_to_term_dict(candidate, source="auto")
            log.info(f"Auto-added term: {candidate['added_term']}")
        
        elif candidate["frequency"] <= 2 or confidence < 0.3:
            # 低频低置信 → 自动丢弃
            log.debug(f"Auto-rejected term: {candidate['added_term']}")
        
        else:
            # 边界 case → 人工审核
            send_to_review_dashboard({
                "type": "term_expansion",
                "term": candidate["added_term"],
                "mapping": f"{candidate['original']} → {candidate['added_term']}",
                "frequency": candidate["frequency"],
                "confidence": confidence,
                "estimated_time": "5 分钟"
            })

def calculate_term_confidence(candidate: dict) -> float:
    """计算术语候选的置信度"""
    score = 0.0
    
    # 因素 1：频次（出现越多越可信）
    if candidate["frequency"] >= 5:
        score += 0.4
    elif candidate["frequency"] >= 3:
        score += 0.2
    
    # 因素 2：召回成功率（用户采纳后成功率高）
    success_rate = candidate.get("recall_success_rate", 0)
    score += success_rate * 0.3
    
    # 因素 3：是否在现有术语库中有相似项
    if has_similar_term_in_dict(candidate["added_term"]):
        score += 0.2
    
    # 因素 4：是否符合电力术语命名规范
    if matches_naming_pattern(candidate["added_term"]):
        score += 0.1
    
    return min(score, 1.0)
```

关键指标：
- 每周新增术语数（自动 + 人工）：目标 8-12 个
- 自动化率：目标 >70%
- 术语库规模：第二阶段结束时达 6000+ 词条
- 术语覆盖率：用户查询命中术语库的比例 → 目标 >85%
        用户输入：{record["user_input"]}
        
        识别用户补充的信息：
        - 新的专业术语
        - 特定的参数值
        - 明确的应用场景
        
        输出 JSON：
        {{"补充信息类型": "专业术语", "值": "油浸式变压器", "映射关系": "变压器 → 油浸式变压器"}}
        """
        
        analysis = llm_call(prompt)
        
        # 3. 提取高频模式
        if analysis["type"] == "专业术语" and record["final_recall_success"]:
            term_candidates.append(analysis)
    
    # 4. 聚合高频术语（出现 ≥3 次）
    high_freq_terms = aggregate_by_frequency(term_candidates, min_count=3)
    
    # 5. 人工审核后加入术语库
    for term in high_freq_terms:
        review_queue.add({
            "term": term["value"],
            "mapping": term["mapping"],
            "frequency": term["count"],
            "status": "pending_review"
        })
```

关键指标：
- 每周新增术语数（目标：5-10 条）
- 术语覆盖率：用户查询中命中术语库的比例（目标 >85%）
- 术语库规模增长曲线

---

**闭环 3：难例驱动的检索优化**

目标：从召回失败的 badcase 中定位根因（分块、嵌入、重排），针对性优化。

流程：
```python
def badcase_analysis_loop():
    # 1. 采集召回失败 case（Top-5 未命中正确文档）
    badcases = db.query("""
        SELECT query, retrieved_docs, expected_doc, user_feedback
        FROM query_logs
        WHERE recall_success = false
          AND user_feedback = 'not_relevant'
          AND created_at > NOW() - INTERVAL 7 DAY
        LIMIT 100
    """)
    
    # 2. 根因分类
    root_causes = {"chunking": [], "embedding": [], "reranking": [], "missing_doc": []}
    
    for case in badcases:
        # 2.1 检查期望文档是否在知识库中
        if not exists_in_kb(case["expected_doc"]):
            root_causes["missing_doc"].append(case)
            continue
        
        # 2.2 检查是否召回了期望文档所在的父块
        parent_chunks = get_parent_chunks(case["expected_doc"])
        if not any(chunk in case["retrieved_docs"] for chunk in parent_chunks):
            # 向量召回失败 → 嵌入问题
            root_causes["embedding"].append(case)
        else:
            # 召回了但排序低 → 重排问题
            root_causes["reranking"].append(case)
    
    # 3. 针对性优化
    # 3.1 嵌入问题：补充到微调数据集（第三阶段）
    if len(root_causes["embedding"]) > 10:
        for case in root_causes["embedding"][:10]:
            finetune_dataset.add({
                "query": case["query"],
                "positive_doc": case["expected_doc"],
                "negative_docs": case["retrieved_docs"][:5]
            })
    
    # 3.2 重排问题：分析特征权重
    if len(root_causes["reranking"]) > 10:
        # 统计这些 case 中，正确文档的元数据特征
        feature_analysis = analyze_metadata_features(root_causes["reranking"])
        # 建议：如果正确文档总是权威等级高但排序低，调整元数据权重
        send_optimization_suggestion(feature_analysis)
    
    # 3.3 分块问题：人工审查
    if len(root_causes["chunking"]) > 5:
        for case in root_causes["chunking"]:
            review_queue.add({
                "type": "chunking_issue",
                "doc": case["expected_doc"],
                "query": case["query"]
            })
```

关键指标：
- 每周 badcase 根因分布（分块/嵌入/重排/缺失文档）
- 优化后召回率提升幅度（通过测试集验证）
- 难例库规模（持续积累，用于回归测试）

---

**闭环 4：测试集自动扩充与回归测试**

目标：从真实流量中挖掘高质量测试用例，确保迭代不退化。

流程：
```python
def test_set_expansion_loop():
    # 1. 采集高置信度的正样本
    positive_samples = db.query("""
        SELECT query, top_retrieved_docs, user_feedback
        FROM query_logs
        WHERE recall_success = true
          AND user_feedback IN ('very_helpful', 'helpful')
          AND clarification_count = 0  -- 无需澄清即成功
        ORDER BY RANDOM() LIMIT 50
    """)
    
    # 2. 采集已修复的难例
    fixed_badcases = db.query("""
        SELECT query, expected_doc, fixed_at
        FROM badcase_tracking
        WHERE status = 'fixed'
          AND fixed_at > NOW() - INTERVAL 7 DAY
    """)
    
    # 3. 人工标注后加入测试集
    for sample in positive_samples:
        test_set.add({
            "query": sample["query"],
            "expected_docs": sample["top_retrieved_docs"][:3],
            "source": "positive_sample",
            "confidence": "high"
        })
    
    for case in fixed_badcases:
        test_set.add({
            "query": case["query"],
            "expected_docs": [case["expected_doc"]],
            "source": "fixed_badcase",
            "confidence": "high"
        })
    
    # 4. 每周自动回归测试
    test_results = run_ragas_evaluation(test_set)
    
    # 5. 对比上周结果，检测退化
    if test_results["recall@5"] < last_week_results["recall@5"] - 0.02:
        send_alert("召回率退化警告", details=test_results)
```

关键指标：
- 测试集规模增长（目标：第二阶段结束时 >500 条）
- 每周新增测试用例数（目标：20-30 条）
- 回归测试通过率（目标 >95%）

---

**闭环 5：A/B 测试自动决策**

目标：自动评估 A/B 实验效果，显著优势时自动全量上线。

流程：
```python
def ab_test_auto_decision():
    # 1. 获取所有运行中的 A/B 实验
    experiments = get_running_experiments()
    
    for exp in experiments:
        if exp["duration_days"] >= 7:  # 运行满 7 天
            # 2. 计算关键指标差异
            control = get_metrics(exp["control_variant"])
            treatment = get_metrics(exp["treatment_variant"])
            
            metrics_comparison = {
                "recall@5_lift": treatment["recall@5"] - control["recall@5"],
                "user_satisfaction_lift": treatment["satisfaction"] - control["satisfaction"],
                "latency_p95_diff": treatment["latency_p95"] - control["latency_p95"]
            }
            
            # 3. 自动决策规则
            if (metrics_comparison["recall@5_lift"] > 0.03 and  # 召回率提升 >3%
                metrics_comparison["user_satisfaction_lift"] > 0.05 and  # 满意度提升 >5%
                metrics_comparison["latency_p95_diff"] < 200):  # 延迟增加 <200ms
                
                # 显著优势 → 自动全量上线
                rollout_to_100_percent(exp["treatment_variant"])
                notify_team(f"实验 {exp['name']} 自动全量上线")
                
            elif (metrics_comparison["recall@5_lift"] < -0.02 or  # 召回率下降 >2%
                  metrics_comparison["latency_p95_diff"] > 500):  # 延迟增加 >500ms
                
                # 显著劣势 → 自动下线
                rollback_experiment(exp["id"])
                send_alert(f"实验 {exp['name']} 效果不佳，已自动下线")
                
            else:
                # 无显著差异 → 人工决策
                send_review_request(exp["id"], metrics_comparison)
```

关键指标：
- 同时运行的 A/B 实验数（目标：2-3 个）
- 实验成功率（提升指标且自动上线的比例，目标 >40%）
- 平均决策周期（从启动到全量/下线的天数，目标 <10 天）

#### 6.5.3 Loop Engineering 基础设施

**数据采集层**：
- 全量日志：查询、召回结果、用户行为（点击/跳过/反馈）、耗时
- 采样策略：正常查询 10% 采样，异常查询（召回失败/用户负反馈）100% 采样
- 存储：Elasticsearch（7 天热数据） + S3（长期归档）

**分析引擎**：
- Jupyter Notebook + Pandas：人工探索性分析
- Airflow DAG：自动化周/月分析任务
- 大模型分析：根因诊断、模式识别

**优化执行**：
- Prompt 版本管理：Git + 配置中心（Apollo/Nacos）
- 模型版本管理：MLflow
- A/B 实验平台：自研（基于 APISIX 流量分流）

**效果验证**：
- 离线评估：RAGAS + 自定义测试集
- 在线评估：A/B 实验 + 实时监控
- 用户反馈：满意度评分 + 文本反馈

#### 6.5.4 预期收益

| 闭环机制 | 优化周期 | 预期提升 |
|---------|---------|---------|
| Prompt 自动迭代 | 每周 | 笼统判断准确率提升 5-10% |
| 术语库动态扩展 | 每周 | 术语覆盖率每月提升 2-3% |
| 难例驱动优化 | 每周 | 召回率每月提升 1-2% |
| 测试集自动扩充 | 每周 | 测试覆盖度每月提升 10% |
| A/B 自动决策 | 持续 | 优化迭代速度提升 3 倍 |

**长期效果**：通过持续闭环优化，系统召回率在上线后 6 个月内可从 92% 提升至 95%+，用户满意度提升 15%+，且无需大规模人工介入。

## 七、落地实施路线图
### 第一阶段：MVP原型验证（1.5个月）
- 数据源：10本核心国家标准 + 3本经典专业教材
- 架构：**仅实现快车道**，基础三路召回+两阶段重排+生成，基础引用溯源，暂不启用召回充分性判断与慢车道
- 产出：可演示的问答原型，初步验证专业问答效果
- 核心目标：跑通全流程，验证数据处理与基础检索可行性

### 第二阶段：工业级生产版本（2.5个月）
- 数据源：扩充至50+核心标准 + 10+专业教材，覆盖配电、变电、继保、安全核心领域
- 架构核心升级：
  - **提问优化模块**：基于大模型 Few-shot（豆包 Pro/通义千问）实现笼统度判断 + 动态澄清选项生成，支持智能补全提示（策略 1）+ 多级澄清对话（策略 2），显著降低笼统查询导致的召回失败
  - **召回补救机制**：快车道加入召回充分性判断 + 二次检索（最多 1 次），补救首轮漏召回
  - **检索优化**：完善术语标准化词库（5000+ 词条）、查询扩展策略（最多 3 个并行查询）、元数据前置过滤
  - **分布式部署**：Qdrant 启用 3 节点 Raft 分布式模式 + Scalar Quantization 量化
- 工程化：
  - Kubernetes 容器化部署，弹性扩缩容
  - Prometheus + Grafana 监控告警（新增：笼统查询识别率、各策略触发率分布、澄清前后召回率对比、误判率、二次检索触发率）
  - **Loop Engineering 基础设施搭建**：
    - 全量日志采集（Elasticsearch + S3 归档）
    - Airflow 自动化分析任务（每周执行 5 大闭环）
    - A/B 测试平台（基于 APISIX 流量分流）
    - Prompt 版本管理（Git + 配置中心）
  - RAGAS 质量评测体系（周跑批 + 自动回归测试）
  - 标准版本管理与自动更新
  - Apache Airflow 流水线编排
- 前端开发：
  - 搜索框智能补全提示组件（显示文档数量）
  - 多级澄清对话交互（clarify_optional 非阻断卡片 + clarify_required 阻断弹窗）
  - 多轮对话上下文支持（conversation_id + Redis 状态管理）
  - 用户反馈收集组件（满意度评分 + 文本反馈）
- 核心目标：
  - Top5 召回率≥92%（含二次检索与提问优化后）
  - 快车道 P95≤3s
  - 笼统查询经澄清后召回率提升≥15%
  - 提问优化误判率 <10%（触发澄清但用户跳过后成功）
  - 大模型调用缓存命中率 >60%（降低成本）
  - **Loop Engineering 闭环运转**：Prompt 自动迭代、术语库动态扩展、难例驱动优化每周执行

### 第三阶段：深度领域化运营（持续迭代）
- 数据源：扩充设备手册、规程规范、典型案例，建设知识图谱
- 架构：**上线慢车道（有界 agentic 检索）**，支持跨标准引用、多条款对比等复杂场景，慢车道独立监控与限流
- 优化：嵌入模型领域微调，多模态图文问答，公式计算能力
- 企业化：权限管理、审计日志、组织架构、与内部系统集成
- 核心目标：覆盖全业务场景，慢车道复杂问题准确率≥85%，打造行业标杆级电力专业知识库

## 八、方案核心总结
电力专业RAG的工业化落地，**核心不是模型有多强，而是数据处理的专业度、检索架构的工程化与持续优化的闭环机制**。国家标准与专业书籍的结构化程度高、权威性强，是极佳的知识库底座。

本方案采用**「快慢双通道 + 有界补救 + 提问优化 + 闭环工程」四位一体架构**：

### 架构核心优势

1. **确定性优先，兜底多元化**
   - 快车道固定流水线保障 P95≤3s 与 QPS≥50，满足生产级 SLA（覆盖 90%+ 查询）
   - 有界补救（召回充分性判断 + 最多 1 次二次检索）补救首轮漏召回，延迟可控
   - 慢车道 agentic 检索攻克多跳推理（跨标准引用、多条款对比），严格限制步数（≤3）与延迟（≤8s）

2. **大模型驱动的提问优化**
   - 基于 Few-shot + COT 的大模型判断笼统度（无需训练数据，上线即用）
   - 多级策略（none/suggest/clarify_optional/clarify_required）避免过度干预
   - 动态澄清选项生成（知识库驱动），自动适配知识库更新
   - Redis 缓存高频查询（命中率 >60%），大幅降低 LLM 调用成本

3. **Loop Engineering 持续进化**
   - **5 大闭环机制**每周自动运转：Prompt 自动迭代、术语库动态扩展、难例驱动优化、测试集自动扩充、A/B 自动决策
   - 从线上流量自动挖掘优化动力，无需大规模人工介入
   - 预期上线后 6 个月内召回率从 92% 提升至 95%+，用户满意度提升 15%+

4. **可审计性与合规性**
   - 所有检索路径可追溯，慢车道每步决策记录日志
   - 提问优化决策透明（显示笼统度评分、缺失维度、推理过程）
   - 满足「零臆测、可溯源、可校验」的核心定位

### 技术选型亮点

- **Qdrant 向量数据库**：原生混合检索（稠密+稀疏向量融合）、灵活的 Payload 过滤、轻量化部署，在百万级向量规模下提供卓越性能
- **大模型 Few-shot 提问优化**：无需训练数据，通过精心设计的 Prompt 工程（Few-shot 示例 + COT 推理 + 严格格式约束）实现高准确率笼统度判断
- **Airflow 自动化闭环**：5 大 Loop Engineering 机制自动执行，从数据采集、问题诊断到优化验证全流程自动化

### 实施路径清晰

- **MVP 阶段**（1.5 个月）：快车道基础流水线，验证可行性
- **生产版本**（2.5 个月）：提问优化 + 召回补救 + Loop Engineering 基础设施，达到工业级标准
- **深度运营**（持续）：慢车道上线 + 嵌入模型微调 + 多模态能力，打造行业标杆

本方案通过「精细化分块 + 术语标准化 + 三路召回 + 两阶段重排 + 路由分流 + 提问优化 + 持续闭环」的组合拳，完全可以实现 92% 以上的检索命中率并持续提升，满足工业级应用要求。适合中小团队快速落地且能持续进化的工业级 RAG 系统。
