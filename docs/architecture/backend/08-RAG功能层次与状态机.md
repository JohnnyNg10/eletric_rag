# RAG系统功能层次与状态机设计

## 与业务流程图的对应关系

本文档是对 [16-业务流程图.md](../flows/16-业务流程图.md) 的详细展开和状态机设计：

| 业务流程图节点 | 本文档对应层 | 说明 |
|--------------|------------|------|
| 术语标准化 | 预处理层 - TermNormalizer | 行业黑话转标准术语 |
| 提问优化判断 | 预处理层 - QueryOptimizer | 笼统度评估 + 澄清选项生成 |
| 复杂度路由 | 路由层 - Router | 快慢通道决策 |
| 元数据提取 + 查询扩展 | 预处理层 - MetadataExtractor + QueryRewriter | 快车道预处理 |
| 三路召回 | 召回层 - MultiPathRecall | 向量+关键词+结构化 |
| 两阶段重排 | 重排层 - TwoStageReranker | 粗排+精排 |
| 召回充分判断 | 重排层 - SufficiencyChecker | 充分性判断 + 二次检索 |
| 工具调用循环 | 慢车道 - SlowLane | 多跳推理 |
| LLM生成答案 | 生成层 - AnswerGenerator | 答案生成 |
| 引用溯源 | 生成层 - CitationExtractor | 提取引用标注 |
| 事实一致性校验 | 生成层 - FactValidator | 验证答案一致性 |

---

## 一、RAG系统功能分层

本文档按照RAG（检索增强生成）系统的功能模块，详细说明各层的职责、关联关系和状态转换机制。

### 1.1 功能分层总览

```
┌─────────────────────────────────────────────────────────┐
│                   接入层 (Access Layer)                  │
│  职责：请求接收、参数验证、认证鉴权、响应封装             │
├─────────────────────────────────────────────────────────┤
│                   预处理层 (Preprocessing)               │
│  职责：术语标准化、查询笼统度评估（提问优化）             │
├─────────────────────────────────────────────────────────┤
│                   路由层 (Routing Layer)                 │
│  职责：快慢通道决策、查询复杂度评估                      │
├─────────────────────────────────────────────────────────┤
│                   召回层 (Recall Layer)                  │
│  职责：查询改写与扩展（快车道）、元数据提取（快车道）、    │
│       多路召回（向量、关键词、结构化）                    │
├─────────────────────────────────────────────────────────┤
│                   重排层 (Reranking Layer)               │
│  职责：两阶段重排（粗排、精排）、召回充分性判断           │
├─────────────────────────────────────────────────────────┤
│                   生成层 (Generation Layer)              │
│  职责：LLM答案生成、引用溯源、事实校验                   │
├─────────────────────────────────────────────────────────┤
│                   存储层 (Storage Layer)                 │
│  职责：向量存储、全文索引、元数据存储、缓存              │
└─────────────────────────────────────────────────────────┘
```

### 1.2 数据流向

```
用户查询
  ↓
接入层：验证 + 鉴权
  ↓
预处理层：术语标准化 + 笼统度评估
  ↓(需要澄清则返回用户)
路由层：快车道 / 慢车道
  ↓
快车道：查询改写+扩展+元数据提取 → 三路召回 → 两阶段重排 → 充分性判断
慢车道：工具调用循环（最多3步）
  ↓
生成层：LLM生成 + 引用溯源
  ↓
返回答案
```

---

## 二、各功能层详细设计

### 2.1 接入层 (Access Layer)

#### 职责
- 接收HTTP请求，解析参数
- 用户认证和权限校验
- 请求限流和熔断
- 响应格式封装
- 日志记录

#### 关键组件
- **API Router**: 路由分发
- **Auth Middleware**: 认证中间件
- **Rate Limiter**: 限流器
- **Response Formatter**: 响应格式化

#### 输入/输出
- **输入**: HTTP Request (QueryRequest)
- **输出**: HTTP Response (QueryResponse) 或传递给预处理层

#### 状态转换
```
接收请求 → 参数验证 → 认证鉴权 → 限流检查 → 传递给预处理层
   ↓(失败)      ↓(失败)      ↓(失败)       ↓(超限)
返回400      返回401      返回403      返回429
```

---

### 2.2 预处理层 (Preprocessing Layer)

#### 职责
- 查询笼统度评估和优化
- 术语标准化（行业黑话 → 标准术语）

**注意**：查询改写、查询扩展、元数据提取属于**快车道召回层**的前置步骤，在路由决策后执行，不在预处理层完成。

#### 关键组件
1. **QueryOptimizer**: 提问优化器
   - 评估查询笼统度
   - 生成澄清选项
   - 决策：是否需要澄清

2. **TermNormalizer**: 术语标准化
   - PT → 电压互感器
   - 刀闸 → 隔离开关
   - 10千伏 → 10kV

**以下组件属于快车道召回层，在路由决策后执行**：

3. **QueryRewriter**: 查询改写（快车道专属）
   - 生成2-3个同义专业问法
   - HyDE：生成假设答案用于向量检索
   - 查询拆解（复杂问题 → 多个子问题）

4. **MetadataExtractor**: 元数据提取（快车道专属）
   - 提取电压等级、标准号、专业分类
   - 生成过滤条件（Qdrant Payload Filter）

#### 输入/输出
- **输入**: 原始查询字符串
- **输出**: 
  - 优化后的查询（标准化后的查询）
  - 或澄清选项（需要用户输入）

**注意**：查询扩展列表、元数据过滤条件由快车道在路由后生成

#### 状态转换

**注意**：预处理层的查询改写和元数据提取，在路由决策后根据通道类型执行：
- 快车道：执行查询扩展（2-3个变体）+ 元数据提取（用于过滤）
- 慢车道：跳过查询扩展，直接进入工具调用循环

```
原始查询 → 术语标准化 → 笼统度评估 → 清晰查询 → 传递给路由层
                            ↓(笼统)
                        生成澄清选项 → 返回用户

路由决策后：
  快车道 → 查询改写(扩展) + 元数据提取 → 召回层
  慢车道 → 直接进入推理循环
```

**处理顺序说明**（与业务流程图对齐）：
1. **术语标准化优先**：将行业黑话转为标准术语（刀闸→隔离开关，PT→电压互感器）
2. **笼统度评估**：基于标准化后的查询判断是否需要澄清（评估更准确）
3. **路由决策**：根据查询复杂度选择快车道或慢车道
4. **查询改写（仅快车道）**：路由到快车道后，对清晰查询生成2-3个同义专业问法
5. **元数据提取（仅快车道）**：在快车道中提取电压等级、标准号等过滤条件

---

### 2.3 路由层 (Routing Layer)

#### 职责
- 分析查询复杂度
- 决策快车道或慢车道
- 设置检索策略参数

#### 快慢通道路由规则

| 查询特征 | 通道 | 理由 |
|---------|------|------|
| 包含明确标准号/条款号 | 快车道 | 可精确定位，无需推理 |
| 单一维度查询 | 快车道 | 固定流水线即可满足 |
| 包含"对比"、"差异" | 慢车道 | 需要多次检索对比 |
| 包含"引用"、"涉及哪些标准" | 慢车道 | 需要多跳推理 |
| 多条件、多维度 | 慢车道 | 需要分步检索聚合 |

#### 路由决策算法
```python
def route_query(query: str, metadata: dict) -> str:
    """
    路由决策
    返回: "fast" 或 "slow"
    """
    # 规则1: 明确标准号/条款号 → 快车道
    if has_explicit_standard_clause(query):
        return "fast"
    
    # 规则2: 对比/引用关键词 → 慢车道
    if has_comparison_keywords(query):
        return "slow"
    
    # 规则3: 多跳推理关键词 → 慢车道
    if has_multihop_keywords(query):
        return "slow"
    
    # 默认: 快车道
    return "fast"
```

#### 输入/输出
- **输入**: 预处理后的查询 + 元数据
- **输出**: 路由决策（fast/slow）+ 检索参数

#### 状态转换
```
预处理完成 → 复杂度分析 → 快车道 / 慢车道
```

---

### 2.4 召回层 (Recall Layer)

#### 职责
- 多路并行召回
- 初步筛选相关文档
- 召回结果合并去重

#### 三路召回策略

**1. 向量召回 (Vector Recall)**
- **技术**: Qdrant 稠密向量 + 稀疏向量混合检索
- **模型**: 
  - 稠密向量：bge-large-zh-v1.5 (1024维)
  - 稀疏向量：efficient-splade (关键词增强)
- **召回量**: Top 20
- **优势**: 语义相似度高，适合模糊查询

**2. 关键词召回 (Keyword Recall)**
- **技术**: Elasticsearch BM25
- **召回量**: Top 20
- **优势**: 精确匹配，适合专业术语查询

**3. 结构化召回 (Structured Recall)**
- **技术**: MySQL 精确查询
- **查询目标**: 标准号、条款号、设备型号
- **召回量**: Top 10
- **优势**: 精确定位，零误差

#### 召回流程
```python
async def multi_path_recall(query: str, filters: dict, top_k: int = 20):
    """
    三路并行召回
    """
    # 并行执行三路召回
    vector_task = vector_recall(query, filters, top_k)
    keyword_task = keyword_recall(query, filters, top_k)
    structured_task = structured_recall(query, filters)
    
    # 等待所有任务完成
    vector_chunks, keyword_chunks, structured_chunks = await asyncio.gather(
        vector_task, keyword_task, structured_task
    )
    
    # 合并去重（按chunk_id）
    all_chunks = merge_deduplicate([
        vector_chunks, 
        keyword_chunks, 
        structured_chunks
    ])
    
    # 返回 Top 50
    return all_chunks[:50]
```

#### 输入/输出
- **输入**: 查询 + 元数据过滤条件
- **输出**: Top 50 候选文档块

#### 状态转换
```
路由决策 → 三路并行召回 → 结果合并 → 去重 → Top50 → 传递给重排层
```

---

### 2.5 重排层 (Reranking Layer)

#### 职责
- 对召回结果进行精细化排序
- 提升Top结果的准确性
- 减少生成层输入噪音

#### 两阶段重排策略

**阶段1: 粗排 (Coarse Reranking)**
- **目标**: Top 50 → Top 20
- **模型**: bge-reranker-base (轻量级)
- **延迟**: ~50ms
- **方法**: 计算查询与文档的相关性分数
- **优势**: 快速筛选，降低精排计算量

**阶段2: 精排 (Fine Reranking)**
- **目标**: Top 20 → Top 5
- **模型**: bge-reranker-large (重量级)
- **延迟**: ~100ms
- **方法**: 深度语义相关性评分
- **优势**: 高精度，确保Top5质量

#### 重排流程
```python
class TwoStageReranker:
    async def rerank(self, query: str, chunks: List[Chunk], top_k: int = 5):
        """
        两阶段重排
        """
        # 阶段1: 粗排 Top50 → Top20
        coarse_scores = await self.coarse_reranker.score(query, chunks)
        top20 = sorted(zip(chunks, coarse_scores), key=lambda x: x[1], reverse=True)[:20]
        top20_chunks = [c for c, _ in top20]
        
        # 阶段2: 精排 Top20 → Top5
        fine_scores = await self.fine_reranker.score(query, top20_chunks)
        top5 = sorted(zip(top20_chunks, fine_scores), key=lambda x: x[1], reverse=True)[:top_k]
        
        return [c for c, _ in top5]
```

#### 充分性判断 (Sufficiency Check)

在精排后，判断Top5是否包含足够信息：

```python
async def check_sufficiency(query: str, top5_chunks: List[Chunk]) -> bool:
    """
    召回充分性判断
    
    方法：
    - 轻量级判别模型或LLM快速判断
    - 输入：查询 + Top5标题/摘要
    - 输出：充分/不充分
    """
    summary = "\n".join([f"{i+1}. {c.title}" for i, c in enumerate(top5_chunks)])
    
    prompt = f"""
    查询：{query}
    召回结果：
    {summary}
    
    判断召回结果是否包含足够信息回答查询？
    回答：充分/不充分
    """
    
    result = await llm_judge(prompt)
    return result == "充分"
```

#### 二次检索（补救机制）

如果充分性判断为"不充分"，触发二次检索：

```python
if not is_sufficient:
    # 改写查询（补充缺失维度）
    refined_query = await query_rewriter.refine(query, top5_chunks)
    
    # 重新召回
    retry_chunks = await recall(refined_query, top_k=10)
    
    # 合并结果并重新精排
    all_chunks = top5_chunks + retry_chunks
    final_top = await reranker.rerank(query, all_chunks, top_k=8)
```

#### 输入/输出
- **输入**: Top 50 候选块 + 查询
- **输出**: Top 5~8 高质量文档块
- **副产物**: 充分性判断结果

#### 状态转换
```
召回Top50 → 粗排(→Top20) → 精排(→Top5) → 充分性判断
                                              ↓(充分)    ↓(不充分)
                                          传递给生成层  二次检索 → 重新精排 → Top8
```

---

### 2.6 生成层 (Generation Layer)

#### 职责
- 基于检索结果生成答案
- 引用溯源标注
- 事实一致性校验
- 流式输出（可选）

#### 核心组件

**1. Prompt构建**
```python
def build_prompt(query: str, chunks: List[Chunk]) -> str:
    """
    构建生成Prompt
    """
    context = "\n\n".join([
        f"[{i+1}] {c.standard_no} {c.clause_no}\n{c.content}"
        for i, c in enumerate(chunks)
    ])
    
    prompt = f"""
你是电力专业知识助手。基于以下参考资料回答用户问题。

参考资料：
{context}

用户问题：{query}

要求：
1. 答案必须基于参考资料，不要编造
2. 引用时使用[1]、[2]等标注，格式：[编号] 标准号 条款号
3. 如果参考资料不包含答案，明确说明
4. 答案要专业、准确、简洁

答案：
"""
    return prompt
```

**2. LLM调用**
```python
class LLMClient:
    async def generate(
        self, 
        prompt: str, 
        stream: bool = False,
        temperature: float = 0.1
    ):
        """
        调用LLM生成答案
        
        - 支持流式/非流式
        - 自动重试（3次）
        - 降级策略（主模型 → 备用模型）
        """
        for attempt in range(3):
            try:
                response = await self.client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    stream=stream
                )
                return response
            except Exception as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
```

**3. 引用溯源 (Citation Extraction)**
```python
def extract_citations(answer: str, chunks: List[Chunk]) -> List[Citation]:
    """
    从答案中提取引用标注
    
    格式：[1] GB 50057-2010 第3.2.1条
    """
    citations = []
    
    # 正则匹配 [数字]
    pattern = r'\[(\d+)\]'
    matches = re.finditer(pattern, answer)
    
    for match in matches:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(chunks):
            chunk = chunks[idx]
            citations.append(Citation(
                index=idx + 1,
                standard_no=chunk.standard_no,
                clause_no=chunk.clause_no,
                content=chunk.content,
                position=match.start()
            ))
    
    return citations
```

**4. 事实一致性校验 (Factual Consistency Check)**
```python
async def validate_facts(answer: str, chunks: List[Chunk]) -> dict:
    """
    校验答案中的事实是否与参考资料一致
    
    方法：
    - NLI模型判断蕴含关系
    - 或LLM二次验证
    """
    # 提取答案中的事实陈述
    facts = extract_factual_statements(answer)
    
    # 逐个验证
    results = []
    for fact in facts:
        is_consistent = await check_entailment(fact, chunks)
        results.append({
            "fact": fact,
            "consistent": is_consistent
        })
    
    return {
        "all_consistent": all(r["consistent"] for r in results),
        "details": results
    }
```

#### 输入/输出
- **输入**: 查询 + Top5~8 文档块
- **输出**: 
  - 答案文本
  - 引用列表
  - 一致性校验结果

#### 状态转换
```
重排Top5 → Prompt构建 → LLM调用 → 答案生成 → 引用溯源 → 事实校验 → 返回结果
                                    ↓(流式)
                                 流式输出 → 引用溯源 → 返回
```

---

### 2.7 存储层 (Storage Layer)

#### 职责
- 向量数据存储与检索
- 全文索引与关键词搜索
- 元数据结构化存储
- 缓存管理

#### 存储组件

**1. 向量存储 (Vector Store) - Qdrant**
```python
class VectorStore:
    async def search(
        self, 
        query_vector: np.ndarray,
        filters: dict = None,
        top_k: int = 20
    ) -> List[Chunk]:
        """
        向量相似度搜索
        
        - 支持稠密向量 + 稀疏向量混合检索
        - 支持元数据过滤（电压等级、标准号等）
        """
        search_request = models.SearchRequest(
            vector=models.NamedVector(
                name="dense",
                vector=query_vector.tolist()
            ),
            filter=self._build_filter(filters),
            limit=top_k,
            with_payload=True
        )
        
        results = await self.client.search(
            collection_name=self.collection,
            search_request=search_request
        )
        
        return [self._to_chunk(r) for r in results]
```

**2. 全文索引 (Search Engine) - Elasticsearch**
```python
class SearchEngine:
    async def search(
        self,
        query: str,
        filters: dict = None,
        top_k: int = 20
    ) -> List[Chunk]:
        """
        BM25关键词搜索
        """
        body = {
            "query": {
                "bool": {
                    "must": {
                        "match": {"content": query}
                    },
                    "filter": self._build_filter(filters)
                }
            },
            "size": top_k
        }
        
        results = await self.client.search(
            index=self.index_name,
            body=body
        )
        
        return [self._to_chunk(hit) for hit in results["hits"]["hits"]]
```

**3. 元数据库 (Metadata DB) - MySQL**
```python
class MetadataRepository:
    async def query_by_standard(
        self,
        standard_no: str,
        clause_no: Optional[str] = None
    ) -> List[Chunk]:
        """
        精确查询：标准号 + 条款号
        """
        query = select(Chunk).where(Chunk.standard_no == standard_no)
        
        if clause_no:
            query = query.where(Chunk.clause_no == clause_no)
        
        result = await self.session.execute(query)
        return result.scalars().all()
```

**4. 缓存 (Cache) - Redis**
```python
class CacheStore:
    async def get(self, key: str) -> Optional[dict]:
        """获取缓存"""
        data = await self.redis.get(key)
        return json.loads(data) if data else None
    
    async def set(self, key: str, value: dict, ttl: int = 3600):
        """设置缓存，TTL默认1小时"""
        await self.redis.setex(
            key,
            ttl,
            json.dumps(value, ensure_ascii=False)
        )
```

#### 数据流
```
查询请求
  ↓
缓存检查 (Redis)
  ↓(未命中)
并行查询：
  - Qdrant (向量检索)
  - Elasticsearch (关键词检索)
  - MySQL (结构化查询)
  ↓
合并结果 → 写入缓存 → 返回
```

---

## 三、快慢双通道详解

### 3.1 快车道 (Fast Lane)

#### 适用场景
- 单一维度查询
- 明确标准号/条款号
- 常规问答

#### 处理流程（固定流水线）
```
路由到快车道 → 查询改写+扩展+元数据提取 → 三路召回 → 两阶段重排 → 充分性判断
                                                             ↓(充分)    ↓(不充分)
                                                           生成答案   二次检索 → 生成
```

**流程说明**：
1. **路由决策后进入**：快车道从路由层接收标准化后的清晰查询
2. **查询增强**：执行查询改写（2-3个变体）+ 元数据提取（电压等级、标准号等过滤条件）
3. **召回与重排**：三路并行召回 → 粗排 → 精排
4. **充分性判断**：评估召回结果是否充分，不充分则触发二次检索（最多1次）

#### 特点
- ✅ 延迟可控（P99 < 3s）
- ✅ 流程确定，易于优化
- ✅ 适合90%的查询

#### 配置参数
```python
FAST_LANE_CONFIG = {
    "query_expansion": True,        # 是否查询扩展
    "expansion_count": 2,           # 扩展查询数量
    "recall_top_k": 20,             # 每路召回数量
    "rerank_coarse_top": 20,        # 粗排Top数
    "rerank_fine_top": 5,           # 精排Top数
    "enable_retry": True,           # 是否启用二次检索
    "max_retry": 1,                 # 最大重试次数
    "timeout": 2500                 # 超时时间(ms)
}
```

---

### 3.2 慢车道 (Slow Lane)

#### 适用场景
- 跨标准对比查询
- 多跳推理查询
- 复杂多维度查询

#### 处理流程（自适应多跳）
```
查询 → LLM决策 → 工具调用 → 信息聚合 → 充分性判断
         ↓                                    ↓(充分)    ↓(不充分)
       选择工具                              生成答案   继续推理
       (retrieve_standard,                            (最多3步)
        retrieve_clause,
        list_related_standards)
```

#### 工具集
```python
TOOLS = {
    "retrieve_standard": {
        "desc": "从指定标准中检索内容",
        "params": ["query", "standard_ids"],
        "action": lambda q, ids: fast_lane_recall(q, filters={"standard_no": ids})
    },
    "retrieve_clause": {
        "desc": "精确定位某标准某条款",
        "params": ["standard_id", "clause_number"],
        "action": lambda std, clause: db_query(std, clause)
    },
    "list_related_standards": {
        "desc": "列出包含关键词的相关标准",
        "params": ["keyword", "category"],
        "action": lambda kw, cat: db_aggregate(kw, cat)
    }
}
```

#### 特点
- ✅ 灵活自适应
- ✅ 处理复杂查询
- ⚠️ 延迟较高（P99 < 8s）
- ⚠️ 适合10%的查询

#### 配置参数
```python
SLOW_LANE_CONFIG = {
    "max_steps": 3,                 # 最大推理步数
    "step_timeout": 2000,           # 单步超时(ms)
    "total_timeout": 8000,          # 总超时(ms)
    "enable_reasoning_trace": True  # 是否记录推理链路
}
```

---

## 四、状态机设计

### 4.1 查询处理状态机

#### 状态定义
```python
class QueryState(Enum):
    """查询状态（简化设计，14个核心状态）"""
    PENDING = "pending"                    # 待处理
    PREPROCESSING = "preprocessing"         # 预处理中
    NEED_CLARIFICATION = "need_clarification"  # 需要澄清
    ROUTING = "routing"                    # 路由决策中
    RECALLING = "recalling"                # 召回中
    RERANKING = "reranking"                # 重排中
    SUFFICIENCY_CHECK = "sufficiency_check" # 充分性判断
    RETRY_RECALL = "retry_recall"          # 二次召回
    REASONING = "reasoning"                # 推理中（慢车道）
    GENERATING = "generating"              # 生成中
    CITING = "citing"                      # 引用溯源
    VALIDATING = "validating"              # 事实校验
    COMPLETED = "completed"                # 完成
    ERROR = "error"                        # 错误
```

**状态设计说明**：
- **简化原则**：将接入层的验证/认证、缓存检查等合并到 `PENDING` 阶段
- **粒度平衡**：既能追踪关键节点，又不过于细化导致维护复杂
- **核心关注**：重点监控RAG核心环节（召回、重排、生成）
- **扩展性**：如需更细粒度监控，可在日志中记录子状态

#### 状态转换图
```
PENDING
  ↓
PREPROCESSING
  ↓
NEED_CLARIFICATION? → (是) 返回澄清选项
  ↓(否)
ROUTING
  ↓
快车道                      慢车道
  ↓                          ↓
RECALLING                  REASONING
  ↓                          ↓
RERANKING                  (工具调用循环)
  ↓                          ↓
SUFFICIENCY_CHECK          REASONING完成
  ↓(充分)    ↓(不充分)         ↓
  ↓        RETRY_RECALL    ↓
  ↓          ↓              ↓
  └──────→ GENERATING ←────┘
            ↓
          CITING
            ↓
          VALIDATING
            ↓
          COMPLETED
```

#### 状态持久化

```python
class QueryStateManager:
    async def update_state(
        self,
        query_id: str,
        state: QueryState,
        metadata: dict = None
    ):
        """
        更新查询状态
        
        - 内存：实时状态（查询进行中）
        - Redis：长查询状态（>30s）
        - MySQL：历史记录（查询完成后）
        """
        # 更新内存状态
        self.in_memory_states[query_id] = {
            "state": state,
            "timestamp": datetime.now(),
            "metadata": metadata
        }
        
        # 如果查询时间>30s，持久化到Redis
        if self._is_long_running(query_id):
            await self.redis.setex(
                f"query_state:{query_id}",
                3600,
                json.dumps({
                    "state": state.value,
                    "metadata": metadata
                })
            )
        
        # 完成后写入MySQL
        if state in [QueryState.COMPLETED, QueryState.ERROR]:
            await self._persist_to_db(query_id, state, metadata)
```

---

### 4.2 文档处理状态机

#### 状态定义

**数据库存储状态** (与数据库设计对齐):
```python
class DocumentDBStatus(Enum):
    """数据库存储的简化状态"""
    PENDING = "pending"        # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
```

**应用层详细状态** (用于业务逻辑和前端展示):
```python
class DocumentDetailState(Enum):
    """应用层详细状态"""
    UPLOADING = "uploading"                      # 上传中 → DB: pending
    UPLOADED = "uploaded"                        # 已上传 → DB: pending
    PARSING = "parsing"                          # 解析中 → DB: processing
    EXTRACTING = "extracting"                    # 文本提取 → DB: processing
    CHUNKING = "chunking"                        # 分块中 → DB: processing
    EXTRACTING_METADATA = "extracting_metadata"  # 元数据提取 → DB: processing
    VECTORIZING = "vectorizing"                  # 向量化中 → DB: processing
    INDEXING = "indexing"                        # 建立索引 → DB: processing
    COMPLETED = "completed"                      # 完成 → DB: completed
    FAILED = "failed"                            # 失败 → DB: failed
```

**状态映射关系**:
```python
# 应用层状态到数据库状态的映射
STATE_TO_DB_STATUS = {
    "uploading": "pending",
    "uploaded": "pending",
    "parsing": "processing",
    "extracting": "processing",
    "chunking": "processing",
    "extracting_metadata": "processing",
    "vectorizing": "processing",
    "indexing": "processing",
    "completed": "completed",
    "failed": "failed"
}
```

#### 状态转换流程
```
UPLOADING → UPLOADED → PARSING → EXTRACTING → CHUNKING 
                                                  ↓
                                          EXTRACTING_METADATA
                                                  ↓
                                            VECTORIZING
                                                  ↓
                                             INDEXING
                                                  ↓
                                            COMPLETED

任何阶段出错 → FAILED
```

**存储策略**:
- **数据库 (documents.process_status)**: 存储简化状态 (4个值)
- **Redis (doc_state:{doc_id})**: 存储详细状态 + 进度信息
- **前端展示**: 使用详细状态显示处理进度

---

## 五、层间数据流与接口

### 5.1 标准数据模型

#### Chunk (文档块)
```python
@dataclass
class Chunk:
    chunk_id: str                  # 唯一ID
    document_id: str               # 所属文档ID
    standard_no: str               # 标准号 (GB 50057-2010)
    clause_no: Optional[str]       # 条款号 (3.2.1)
    title: str                     # 标题
    content: str                   # 内容
    content_type: str              # 类型 (text/table/image)
    metadata: dict                 # 元数据 (电压等级、专业分类等)
    dense_vector: np.ndarray       # 稠密向量 (1024维)
    sparse_vector: dict            # 稀疏向量
    created_at: datetime
```

#### RetrievalResult (检索结果)
```python
@dataclass
class RetrievalResult:
    chunks: List[Chunk]            # 召回的文档块
    lane: str                      # 通道 (fast/slow)
    steps: int                     # 推理步数（慢车道）
    reasoning: List[str]           # 推理链路（慢车道）
    metrics: dict                  # 性能指标
```

#### Answer (答案)
```python
@dataclass
class Answer:
    text: str                      # 答案文本
    citations: List[Citation]      # 引用列表
    consistency_score: float       # 一致性得分
    confidence: float              # 置信度
    metadata: dict                 # 元数据
```

#### Citation (引用)
```python
@dataclass
class Citation:
    index: int                     # 引用编号 [1]
    chunk_id: str                  # 文档块ID
    standard_no: str               # 标准号
    clause_no: Optional[str]       # 条款号
    content: str                   # 引用内容
    position: int                  # 在答案中的位置
```

---

### 5.2 层间接口规范

#### 接入层 → 预处理层
```python
class PreprocessingInput:
    query: str
    user_context: dict
    options: QueryOptions

class PreprocessingOutput:
    status: str  # "ready" or "need_clarification"
    optimized_query: str
    expanded_queries: List[str]
    filters: dict
    clarification_options: Optional[List[Option]]
```

#### 预处理层 → 路由层
```python
class RoutingInput:
    optimized_query: str
    expanded_queries: List[str]
    filters: dict

class RoutingOutput:
    lane: str  # "fast" or "slow"
    strategy: dict  # 检索策略参数
```

#### 路由层 → 召回层
```python
class RecallInput:
    query: str
    filters: dict
    top_k: int

class RecallOutput:
    chunks: List[Chunk]
    recall_sources: dict  # {"vector": 20, "keyword": 18, "structured": 5}
```

#### 召回层 → 重排层
```python
class RerankInput:
    query: str
    chunks: List[Chunk]
    top_k: int

class RerankOutput:
    chunks: List[Chunk]  # Top5~8
    is_sufficient: bool
    retry_needed: bool
```

#### 重排层 → 生成层
```python
class GenerationInput:
    query: str
    chunks: List[Chunk]
    stream: bool

class GenerationOutput:
    answer: Answer
    generation_time: float
```

---

## 六、性能指标与监控

### 6.1 各层性能目标

| 层级 | P50延迟 | P99延迟 | 吞吐量 |
|-----|---------|---------|--------|
| 接入层 | <10ms | <50ms | 1000 QPS |
| 预处理层 | <100ms | <300ms | - |
| 路由层 | <5ms | <20ms | - |
| 召回层 | <200ms | <500ms | - |
| 重排层 | <150ms | <400ms | - |
| 生成层 | <1000ms | <2500ms | - |
| **端到端(快车道)** | **<2s** | **<3s** | **100 QPS** |
| **端到端(慢车道)** | **<5s** | **<8s** | **20 QPS** |

### 6.2 监控指标

**业务指标**
- 查询成功率
- 缓存命中率
- 快慢通道分流比例
- 召回充分性比例
- 答案引用覆盖率

**技术指标**
- 各层延迟分布
- 模型推理时间
- 数据库查询时间
- 缓存读写时间
- 错误率和类型分布

**资源指标**
- CPU/内存使用率
- GPU利用率
- 数据库连接数
- 缓存内存使用
- 网络带宽

---

## 七、总结

### 7.1 架构优势

1. **清晰分层**：各层职责明确，易于维护和扩展
2. **快慢双通道**：兼顾性能和复杂查询处理能力
3. **多路召回**：向量+关键词+结构化，互补优势
4. **两阶段重排**：粗排+精排，平衡精度和性能
5. **充分性判断**：二次检索补救，提升召回质量
6. **引用溯源**：每个答案可追溯到原始文档

### 7.2 扩展方向

1. **召回层扩展**：增加图谱召回、时序召回
2. **重排层优化**：引入多目标排序（相关性+多样性+新鲜度）
3. **生成层增强**：多模态生成（文本+表格+图片）
4. **智能路由**：基于历史数据的自适应路由策略

### 7.3 相关文档

- [后端架构设计](./04-后端架构设计.md) - 详细技术实现
- [API接口设计](./05-API接口设计.md) - 接口规范
- [数据模型设计](./06-数据模型设计.md) - 数据库设计
- [模型自动下载指南](./07-模型自动下载指南.md) - AI模型配置
- [模型使用总结](../modules/22-模型使用总结.md) - 模型调用详解
- [业务流程图](../flows/16-业务流程图.md) - 端到端流程

