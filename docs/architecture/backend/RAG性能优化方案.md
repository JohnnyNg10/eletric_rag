# RAG系统性能与准确率优化方案

## 一、当前实现状态评估

### ✅ 已完整实现的核心模块
1. **召回层**：三路并行召回（向量+关键词+结构化）已实现并真实调用存储层
2. **重排层**：两阶段重排（粗排+精排）完整实现
3. **生成层**：答案生成、引用提取、事实校验全部实现
4. **路由层**：快慢车道路由决策完整
5. **慢车道**：LLM驱动的3步工具调用循环实现
6. **预处理**：查询标准化、模糊度判断实现
7. **四级缓存**：L1 Embedding、L2 召回、L3 重排、L4 生成（commit 9dc1a9a）
8. **父子块扩展**：父块召回+子块相似度过滤（commit 当前）
9. **HyDE查询增强**：类别特定假设文档生成（`app/core/retrieval/hyde.py`，默认已启用）

### ⚠️ 部分实现/需优化的模块
1. **查询改写**：同义词扩展已实现但效果有限，子查询拆解待实现
2. **快车道二次检索**：充分性判断后的重试逻辑已实现但gap改写是字符串拼接
3. **向量化**：扫描件识别后未向量化入库
4. **存储层数据**：Qdrant/ES可能无数据

### ❌ 未实现的模块
1. **普通PDF ingestion**：文档处理pipeline未完整跑通
2. **监控指标**：缺少性能监控

---

## 二、已发现的Bug与架构问题（P0）

### 🐛 Bug #1：L2缓存键不含HyDE标记（导致HyDE失效）

**现状**：`app/storage/cache.py:167-169`

```python
def _recall_key(self, query: str, filters: Dict) -> str:
    raw = query + "|" + json.dumps(filters, sort_keys=True, ensure_ascii=False)
    return f"recall:{_md5(raw)}"  # hyde_query 不在 key 里
```

**问题**：
- 刚启用HyDE后，L2召回缓存键只包含 `query + filters`
- 如果历史缓存命中，返回的是没有HyDE的旧召回结果
- HyDE生成的假设文档完全不起作用，白白浪费1次LLM调用

**影响**：HyDE功能完全失效，召回准确率提升预期（10-15%）无法兑现

**修复方案**：
```python
def _recall_key(self, query: str, filters: Dict, hyde_enabled: bool = False) -> str:
    raw = query + "|" + json.dumps(filters, sort_keys=True, ensure_ascii=False) + f"|hyde={hyde_enabled}"
    return f"recall:{_md5(raw)}"
```

同时修改 `fast_lane.py:287` 和 `cache.py:153-165` 的调用点传入 `hyde_enabled=bool(hyde_query)`。

---

### 🐛 Bug #2：expanded_queries接受但未使用（查询扩展空转）

**现状**：`app/core/retrieval/recall.py:601-667`

```python
async def recall(
    self,
    query: str,
    filters: Dict[str, Any],
    expanded_queries: Optional[List[str]] = None,  # 接受但不用
    hyde_query: Optional[str] = None
) -> List[ChunkResult]:
    # 三路召回全部只用单一 query，expanded_queries 未被使用
    vector_task = self.vector_recall.search(vector_query, filters, top_k=20)
    keyword_task = self.keyword_recall.search(query, filters, top_k=20)
    structured_task = self.structured_recall.search(query, filters, top_k=10)
```

**问题**：
- `QueryRewriter` 花费1次LLM调用生成2-3个扩展查询（同义改写）
- `FastLane.execute()` 传递 `expanded_queries` 给召回层
- 但 `MultiPathRecall.recall()` 签名接受该参数后完全不使用
- 所有召回路径都只用单一的原始 query

**影响**：查询扩展的LLM成本无法兑现为召回率提升

**修复方案**：
```python
# 为每个扩展查询分别召回，然后RRF合并
all_results = []
for expanded_q in (expanded_queries or [query]):
    vector_chunks = await self.vector_recall.search(hyde_query or expanded_q, filters, top_k=20)
    keyword_chunks = await self.keyword_recall.search(expanded_q, filters, top_k=20)
    structured_chunks = await self.structured_recall.search(expanded_q, filters, top_k=10)
    all_results.extend([vector_chunks, keyword_chunks, structured_chunks])

# RRF 合并所有路径
merged = self._merge_deduplicate(all_results)
```

---

### ⚠️ 架构问题 #3：生成层System Prompt与零臆测目标矛盾

**现状**：`app/core/generation/generator.py:69`

```python
return """你是一个专业的电力工程领域知识助手，擅长解读国家标准和行业规范。

核心原则：
1. **基于资料**：答案参考资料，要自己进行完善和补充  # ← 与零臆测矛盾
2. **综合阐述**：不要简单罗列原文，整理格式后回答...
```

**问题**：
- 项目目标是"零臆测、可溯源、可校验"
- System prompt 第一条明确鼓励模型"自己进行完善和补充"
- 与 User prompt "基于以上全部参考资料"的要求相矛盾
- 存在产生幻觉和无法溯源内容的风险

**修复方案**：
```python
核心原则：
1. **严格基于资料**：仅使用提供的参考资料回答，不得补充资料外的内容
2. **综合阐述**：整理参考资料后用专业语言表述，避免简单罗列原文
3. **引用溯源**：引用关键数据、规范条文时在句末标注来源编号[1][2]
4. **如实说明**：参考资料不包含所问内容时，明确说明而非臆测
```

---

## 三、性能优化方案（P1级）

### ✅ 0. 模型单例优化（已实现）

**现状**：~~模型重复加载导致初始化耗时严重~~ 已修复

**问题**：`app/core/retrieval/recall.py:31` 中 `VectorRecall` 直接实例化 `Embedder()`，导致每次创建 `VectorRecall` 时都重新加载 ~3.3GB 模型

**修复方案**：✅ **已实现**
- 将 `self.embedder = Embedder()` 改为 `self.embedder = get_embedder()`
- 所有组件共享同一个模型实例（单例模式）

**预期收益**：
- 启动时间从数分钟降至 **~3秒**
- 测试运行时间从可能的数分钟降至 **~13秒**
- 内存占用减少（避免多个模型副本）

---

### ✅ 1. 添加多层缓存机制（已实现）

**现状**：~~每次查询都重新调用embedding/LLM，重复计算严重~~ 已实现多级缓存层

**优化方案**：✅ **已实现**（commit 9dc1a9a）

实现了四级缓存架构：
- **L1 Embedding 缓存**（24h TTL）：`app/storage/cache.py` - `get_dense()`, `get_sparse()`, `get_dense_by_id()`
- **L2 召回缓存**（6h TTL）：`get_recall()`, `set_recall()`
- **L3 重排缓存**（4h TTL）：`get_rerank()`, `set_rerank()`
- **L4 生成缓存**（2h TTL）：`get_generation()`, `set_generation()`

集成点：
- `app/core/embedding/embedder.py:87-102` - Embedding 层集成 L1 缓存
- `app/core/retrieval/fast_lane.py:138-148` - FastLane 集成 L2 召回缓存和 L3 重排缓存
- `app/services/query_service.py` - QueryService 集成 L4 生成缓存

配置参数（`app/config.py:84-92`）：
```python
CACHE_EMBEDDING_ENABLED: bool = True
CACHE_RECALL_ENABLED: bool = True
CACHE_RERANK_ENABLED: bool = True
CACHE_GENERATION_ENABLED: bool = True
CACHE_EMBEDDING_TTL: int = 86400   # 24h
CACHE_RECALL_TTL: int = 21600      # 6h
CACHE_RERANK_TTL: int = 14400      # 4h
CACHE_GENERATION_TTL: int = 7200   # 2h
```

**原设计方案**：
```python
# 1. Embedding缓存（Redis，24小时过期）
class CachedEmbedder:
    def __init__(self, embedder, cache):
        self.embedder = embedder
        self.cache = cache
    
    async def encode(self, text: str) -> np.ndarray:
        cache_key = f"embed:dense:{hashlib.md5(text.encode()).hexdigest()}"
        
        # 尝试从缓存读取
        cached = await self.cache.get(cache_key)
        if cached:
            return np.frombuffer(base64.b64decode(cached), dtype=np.float32)
        
        # 未命中，计算并缓存
        vector = self.embedder.encode(text)
        await self.cache.set(
            cache_key,
            base64.b64encode(vector.tobytes()).decode(),
            ex=86400  # 24小时
        )
        return vector

# 2. 召回结果缓存（Redis，1小时过期）
class CachedRecall:
    async def recall(self, query: str, filters: dict):
        cache_key = f"recall:{hashlib.md5(f'{query}{filters}'.encode()).hexdigest()}"
        
        cached = await self.cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        results = await self.recall_engine.recall(query, filters)
        await self.cache.set(cache_key, json.dumps(results), ex=3600)
        return results

# 3. LLM生成缓存（Redis，12小时过期）
class CachedGenerator:
    async def generate(self, query: str, chunks: list):
        # 基于query+chunks内容hash作为key
        content_hash = hashlib.md5(
            f"{query}{''.join(c.content for c in chunks)}".encode()
        ).hexdigest()
        cache_key = f"gen:{content_hash}"
        
        cached = await self.cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        result = await self.generator.generate(query, chunks)
        await self.cache.set(cache_key, json.dumps(result), ex=43200)
        return result
```

**预期收益**：
- 相同/相似查询响应时间降低 **60-80%**
- LLM API调用成本降低 **40-60%**
- 缓存命中率预计 **30-50%**（取决于用户查询重复度）

---

### 🚀 2. 批量向量化优化

**现状**：扫描件识别后单条向量化，效率低

**优化方案**：
```python
# 改进processor.py的向量化逻辑
async def _vectorize_and_index(self, doc_id: int):
    """批量向量化并异步入库"""
    db = SessionLocal()
    try:
        # 1. 批量获取chunks
        chunks = db.query(Chunk).filter(
            Chunk.document_id == doc_id,
            Chunk.content_type == 'image_description'
        ).all()
        
        if not chunks:
            return
        
        # 2. 批量生成向量（利用GPU并行）
        texts = [c.content for c in chunks]
        batch_size = 32  # 根据GPU显存调整
        
        all_dense_vectors = []
        all_sparse_vectors = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            dense = await self.embedder.encode_batch(batch_texts)
            sparse = await self.embedder.encode_sparse_batch(batch_texts)
            all_dense_vectors.extend(dense)
            all_sparse_vectors.extend(sparse)
        
        # 3. 批量写入Qdrant（减少网络往返）
        points = []
        for chunk, dense, sparse in zip(chunks, all_dense_vectors, all_sparse_vectors):
            points.append({
                'id': str(chunk.id),
                'dense_vector': dense.tolist(),
                'sparse_vector': {'indices': sparse.indices, 'values': sparse.values},
                'payload': {
                    'chunk_id': chunk.id,
                    'doc_id': doc_id,
                    'text': chunk.content,
                    'page_start': chunk.page_start,
                    'chunk_type': chunk.chunk_type,
                    'content_type': 'image_description',
                }
            })
        
        # 批量upsert（100个一批）
        await self.vector_store.upsert_points(points, batch_size=100)
        
        # 4. 批量写入ES
        es_docs = [
            {
                'chunk_id': chunk.id,
                'doc_id': doc_id,
                'text': chunk.content,
                'page_start': chunk.page_start,
            }
            for chunk in chunks
        ]
        await self.search_engine.bulk_index(es_docs)
        
        logger.info(f"向量化完成: doc_id={doc_id}, chunks={len(chunks)}")
        
    finally:
        db.close()
```

**预期收益**：
- 向量化速度提升 **5-10倍**
- GPU利用率提升 **80%+**
- 81页PDF从27分钟降至 **3-5分钟**

---

### 🚀 3. 并发控制与流控优化

**现状**：VLM API调用无并发限流，大量失败

**优化方案**：
```python
# 实现自适应流控
class AdaptiveRateLimiter:
    def __init__(self, initial_concurrency=5, max_concurrency=20):
        self.semaphore = asyncio.Semaphore(initial_concurrency)
        self.current_concurrency = initial_concurrency
        self.max_concurrency = max_concurrency
        self.success_rate = 1.0
        self.recent_results = deque(maxlen=100)
    
    async def acquire(self):
        await self.semaphore.acquire()
    
    def release(self, success: bool):
        self.semaphore.release()
        self.recent_results.append(success)
        
        # 动态调整并发度
        if len(self.recent_results) >= 20:
            self.success_rate = sum(self.recent_results) / len(self.recent_results)
            
            if self.success_rate > 0.95 and self.current_concurrency < self.max_concurrency:
                # 成功率高，增加并发
                self.current_concurrency += 1
                self.semaphore._value += 1
            elif self.success_rate < 0.80 and self.current_concurrency > 1:
                # 成功率低，降低并发
                self.current_concurrency -= 1
                self.semaphore._value -= 1

# 在processor中使用
rate_limiter = AdaptiveRateLimiter(initial_concurrency=5)

async def _process_page_with_vlm(self, image, page_num, doc_id):
    await rate_limiter.acquire()
    try:
        result = await self._call_vlm_api(image, page_num)
        rate_limiter.release(success=True)
        return result
    except Exception as e:
        rate_limiter.release(success=False)
        raise
```

**预期收益**：
- VLM调用成功率从60%提升至 **95%+**
- 自动适应API限流，避免手动调参
- 处理速度提升 **30-50%**

## 四、召回准确率优化方案（P2级）

### ⚠️ 问题 #4：二次检索的gap改写是字符串拼接

**现状**：`app/core/retrieval/fast_lane.py:320-333`

```python
async def _refine_query_for_gaps(self, original_query: str, gaps: List[str]) -> str:
    if not gaps:
        return original_query
    
    gaps_text = "、".join(gaps)
    refined_query = f"{original_query} {gaps_text}"  # 直接拼接
    # TODO: 可以用LLM更智能地改写
    return refined_query
```

**问题**：
- 充分性检查做了LLM判断并给出 `gaps` 列表
- 但二次检索的查询只是把缺口词直接追加在原查询后
- 对短查询（如"GB 50053接地要求"）会产生语法奇怪的查询

**修复方案**：
```python
async def _refine_query_for_gaps(self, original_query: str, gaps: List[str]) -> str:
    if not gaps:
        return original_query
    
    prompt = f"""原始查询：{original_query}
信息缺口：{', '.join(gaps)}

请基于原始查询和信息缺口，生成一个更完整的查询（保持简洁，30字内）："""
    
    refined = await self.query_rewriter.llm_client.generate(prompt, max_tokens=50, temperature=0.3)
    return refined.strip() or original_query  # 降级返回原查询
```

---

### ⚠️ 问题 #5：HyDE与查询扩展串行执行

**现状**：`app/core/retrieval/fast_lane.py:104-119`

```python
# 步骤1: 查询增强（查询改写 + 元数据提取）
expanded_queries = await self._enhance_query(query, strategy_params)  # LLM调用
filters = self._extract_metadata(query, preprocessing_result)
metadata = self.metadata_extractor.extract_all_metadata(query, preprocessing_result)

# 步骤1.5: 可选的类别特定 HyDE 生成
hyde_query = None
enable_hyde = strategy_params.get("enable_hyde", False)
if enable_hyde:
    category = metadata.get('category')
    hyde_query = await self.hyde_generator.generate(query, category)  # LLM调用
```

**问题**：
- 查询扩展（`_enhance_query`）和HyDE生成（`hyde_generator.generate`）是两次独立的LLM调用
- 顺序执行增加约 1-1.5s 延迟
- 两者无依赖关系，可以并行

**修复方案**：
```python
# 步骤1: 并行执行查询增强和HyDE生成
import asyncio

tasks = [
    self._enhance_query(query, strategy_params),
    self.metadata_extractor.extract_all_metadata(query, preprocessing_result),
]

hyde_task = None
enable_hyde = strategy_params.get("enable_hyde", False)
if enable_hyde:
    # 元数据提取需要先完成以获取category，保持串行
    # 或者让HyDE支持无category的通用prompt
    hyde_task = asyncio.create_task(self.hyde_generator.generate(query, None))
    tasks.append(hyde_task)

results = await asyncio.gather(*tasks)
expanded_queries = results[0]
metadata = results[1]
hyde_query = results[2] if hyde_task else None

filters = self._extract_metadata(query, preprocessing_result)
```

**预期收益**：快车道延迟降低 **0.8-1.2s**

---

### 📈 未实现 #6：MMR多样性优化（架构设计已包含）

---

### ✅ 父子块混合检索（已实现）

**现状**：~~Chunk表有parent/child关系，但未使用~~ 已实现父子块扩展层

**策略**：✅ **已实现**（commit 当前）
- 召回阶段：检索**父块**（512-1024 token，语义完整）
- 重排阶段：精排父块（Top-8）
- **扩展阶段**：展开**子块**（128-256 token，精确匹配）- 新增
- 生成阶段：使用**父块+高相关子块**（减少上下文噪音）

**实现方案**：✅ **已实现**

核心文件：
- `app/core/retrieval/child_expander.py` - 子块扩展器（新增）
  - `ChildChunkExpander.expand()` - 批量获取子块并过滤
  - `_get_children_batch()` - 批量查询避免 N+1
  - `_get_child_vectors_batch()` - 三层向量获取（缓存→Qdrant→计算）
- `app/schemas/retrieval.py:58-64` - `ExpandedChunkResult` 模型（新增）
- `app/core/retrieval/fast_lane.py:190-201` - FastLane 集成子块扩展
- `app/config.py:95-98` - 配置参数（新增）

配置参数：
```python
CHILD_EXPANSION_ENABLED: bool = True        # 是否启用子块扩展
CHILD_SIMILARITY_THRESHOLD: float = 0.7     # 子块相似度阈值
MAX_CHILDREN_PER_PARENT: int = 5            # 每个父块最多保留的子块数
```

优化措施：
- ✅ 批量查询避免 N+1：`WHERE parent_chunk_id IN (...)`
- ✅ ID-based 缓存避免内容冲突：`get_dense_by_id(chunk_id)`
- ✅ 优先从 Qdrant 获取已存储向量，减少重复计算
- ✅ 余弦相似度过滤低相关子块（threshold > 0.7）

测试验证：`backend/test_child_expander.py`
- ✅ 批量获取子块成功（5个父块73个子块）
- ✅ 缓存命中率监控
- ✅ FastLane 集成成功
- ✅ 相似度阈值调整生效

**原设计方案**：
```python
# fast_lane.py
async def execute(self, query: str, preprocessing_result):
    # 1. 召回父块
    recalled_chunks = await self._multi_path_recall(
        queries=[query],
        filters={**filters, 'chunk_type': 'parent'},  # 只召回父块
        hyde_query=hyde_query
    )
    
    # 2. 展开子块
    expanded_chunks = []
    for parent_chunk in recalled_chunks:
        # 获取父块的所有子块
        children = self.db.query(Chunk).filter(
            Chunk.parent_chunk_id == parent_chunk.chunk_id
        ).all()
        
        if children:
            expanded_chunks.extend(children)
        else:
            expanded_chunks.append(parent_chunk)  # 无子块时保留父块
    
    # 3. 重排子块
    reranked = await self.reranker.rerank(query, expanded_chunks, top_k=8)
    
    # 4. 充分性判断（基于子块）
    sufficiency = await self.sufficiency_checker.check(query, reranked[:5])
```

**预期收益**：
- Top-5准确率提升 **12-18%**
- 生成答案质量提升（更精确的上下文）
- 召回召回数量增加30%，但重排后保持Top-5

---

### 📈 未实现 #7：查询拆解（Query Decomposition）

**现状**：`app/core/preprocessing/query_rewriter.py:85-98`

```python
async def decompose(self, query: str) -> List[str]:
    """
    查询拆解（复杂问题→多个子问题）
    
    TODO: 使用LLM识别并拆解复杂查询
    """
    # 当前不拆解
    return [query]
```

**问题**：
- 架构文档描述的子查询分解完全未实现
- 对"10kV配电和35kV配电在接地方式上有何不同"这类复合查询，只走一路召回
- 两个子话题可能各自召回不足

**修复方案**（架构文档已设计）：
```python
async def decompose_query(self, query: str) -> List[str]:
    """复杂查询拆解为子问题"""
    
    # 简单查询直接返回
    if len(query) < 20 or '和' not in query and '以及' not in query:
        return [query]
    
    prompt = f"""将复杂问题拆解为2-3个可独立回答的子问题：

问题：{query}

要求：
- 每个子问题应该独立、具体
- 覆盖原问题的所有方面
- 输出JSON数组格式

示例：
问题：10kV配电系统的接地方式和保护配置有哪些要求？
子问题：["10kV配电系统有哪些接地方式？", "10kV配电系统的保护装置如何配置？"]

子问题："""
    
    response = await self.llm_client.generate(prompt, max_tokens=200)
    
    try:
        sub_queries = json.loads(response)
        return sub_queries[:3]  # 最多3个
    except:
        return [query]  # 解析失败时用原查询
```

**预期收益**：
- 复杂查询召回率提升 **15-25%**
- 适用于"A和B"、"从X到Y"类组合查询
- 额外成本：1次LLM调用 + N次并行召回

---

### ⚠️ 问题 #8：路由器只做精确词匹配

**现状**：`app/core/retrieval/router.py:32-37`

```python
# 慢车道关键词（多跳推理、对比分析）
SLOW_LANE_KEYWORDS = [
    '对比', '差异', '区别', '比较',
    '引用', '涉及哪些', '有哪些标准',
    '同时满足', '交叉', '关联'
]
```

**问题**：
- "GB 50053 和 GB 50054 有什么不同"——"不同"不在关键词列表，会进快车道
- "哪些标准涉及"——"涉及哪些"在列表但"哪些标准涉及"不匹配
- 精确词匹配容易漏掉语义相同的表达

**修复方案**：
```python
def route(self, query: str, metadata: Dict[str, Any] = None) -> RouteDecision:
    # ... 现有规则保持 ...
    
    # 规则2增强：对比/引用关键词（正则扩展）
    comparison_patterns = [
        r'(对比|差异|区别|比较|不同|相同)',
        r'(引用|涉及|包含|提到).{0,5}(哪些|什么).*标准',
        r'(同时|都|均).{0,5}(满足|符合|达到)',
    ]
    if any(re.search(pattern, query) for pattern in comparison_patterns):
        return RouteDecision(lane="slow", reason="包含对比/引用关键词", ...)
    
    # 规则3增强：多标准号查询 → 慢车道
    standard_matches = re.findall(r'GB[/\s]*[T]?\s*\d+|DL[/\s]*T\s*\d+|NB[/\s]*T\s*\d+', query)
    if len(standard_matches) >= 2:
        return RouteDecision(lane="slow", reason="查询涉及多个标准，需对比分析", ...)
```

**预期收益**：路由准确率提升 **8-12%**

---

### 📈 未实现 #9：多查询融合召回（与Bug #2重复）

**现状**：见 Bug #2，`expanded_queries` 接受但未使用

**问题**：架构文档描述的多查询融合召回已由 `QueryRewriter.rewrite()` 生成扩展查询，但召回层未实际使用

**修复方案**：见 Bug #2 修复方案

---

### 📈 未实现 #10：MMR多样性优化（与问题 #6重复内容，此处删除）

**实现方案**：见问题 #6

---

## 五、优化实施优先级与时间估算

### P0：Bug修复（必须立即修复）

| 编号 | 问题 | 改动量 | 预期收益 | 估时 |
|------|------|--------|---------|------|
| Bug #1 | L2缓存键不含HyDE标记 | 小（3处修改） | HyDE实际生效，召回率+10-15% | 30分钟 |
| Bug #2 | expanded_queries未使用 | 中（召回层重构） | 查询扩展LLM成本兑现为召回率 | 2小时 |
| Bug #3 | System Prompt与零臆测矛盾 | 极小（1行） | 减少幻觉风险 | 5分钟 |

**里程碑**：HyDE和查询扩展真正生效，幻觉风险降低

---

### P1：性能与体验优化

| 编号 | 问题 | 改动量 | 预期收益 | 估时 |
|------|------|--------|---------|------|
| #4 | gap改写字符串拼接 | 小 | 二次检索质量提升 | 1小时 |
| #5 | HyDE与查询扩展串行 | 小 | 快车道延迟-0.8~1.2s | 1小时 |
| #8 | 路由器精确词匹配 | 小 | 路由准确率+8-12% | 1.5小时 |

**里程碑**：用户体验流畅度显著提升

---

### P2：召回准确率提升

| 编号 | 问题 | 改动量 | 预期收益 | 估时 |
|------|------|--------|---------|------|
| #6 | MMR多样性优化 | 中 | 覆盖面+20-30% | 3小时 |
| #7 | 查询拆解未实现 | 大 | 复合查询召回率+15-25% | 4小时 |

**里程碑**：复杂查询准确率达到工业级标准

---

### P3：生产化（架构文档已覆盖）

- 批量向量化优化（文档2.2节）
- VLM并发控制（文档2.3节）
- 监控指标采集（文档4节）

---

## 六、总结与建议

### 立即行动项（本周完成）
1. **修复Bug #1**（30分钟）：L2缓存加入hyde标记，让HyDE真正生效
2. **修复Bug #2**（2小时）：让expanded_queries进入召回，避免LLM成本浪费
3. **修复Bug #3**（5分钟）：修改system prompt，消除幻觉风险

**预期总收益**：
- HyDE召回率提升10-15%实际生效
- 查询扩展LLM成本不再空转
- 零臆测目标风险消除

### 下一步优化（下周）
4. 实现问题#4、#5、#8的性能与路由优化
5. 评估MMR和查询拆解的ROI后选择性实现

---
        # 1. RRF融合得到候选集
        candidates = self._merge_deduplicate(chunk_lists)
        
        # 2. MMR选择
        selected = []
        remaining = candidates.copy()
        
        # 先选择得分最高的
        if remaining:
            selected.append(remaining.pop(0))
        
        # 迭代选择：平衡相关性与已选chunks的差异性
        while remaining and len(selected) < 50:
            best_score = -1
            best_idx = 0
            
            for i, candidate in enumerate(remaining):
                # 相关性得分（RRF分数）
                relevance = candidate.score
                
                # 多样性得分（与已选chunks的最小距离）
                max_similarity = max([
                    self._compute_similarity(candidate, s)
                    for s in selected
                ])
                diversity = 1 - max_similarity
                
                # MMR得分
                mmr_score = lambda_param * relevance + (1 - lambda_param) * diversity
                
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i
            
            selected.append(remaining.pop(best_idx))
        
        return selected
    
    def _compute_similarity(self, chunk1: ChunkResult, chunk2: ChunkResult) -> float:
        """计算两个chunk的相似度"""
        # 1. 同文档同页 → 高相似
        if chunk1.document_id == chunk2.document_id:
            if abs(chunk1.page_start - chunk2.page_start) <= 1:
                return 0.9
            elif abs(chunk1.page_start - chunk2.page_start) <= 3:
                return 0.7
            else:
                return 0.3
        
        # 2. 不同文档 → 低相似
        return 0.1
```

**预期收益**：
- 召回内容覆盖面提升 **20-30%**
- 避免Top-10都来自同一文档的同一章节
- 对多文档综合类问题效果显著

---

## 四、系统性能监控方案（P2级）

### 📊 1. 关键指标采集

```python
# 在query_service.py中添加
import time
from dataclasses import dataclass, asdict
import json

@dataclass
class QueryMetrics:
    query_id: str
    query: str
    route: str  # fast/slow
    
    # 召回指标
    recall_count: int
    recall_time_ms: int
    vector_recall_count: int
    keyword_recall_count: int
    structured_recall_count: int
    
    # 重排指标
    rerank_time_ms: int
    rerank_top1_score: float
    rerank_top5_avg_score: float
    
    # 充分性指标
    sufficiency_result: bool
    sufficiency_source: str  # rule/llm/timeout
    sufficiency_confidence: float
    
    # 生成指标
    generation_time_ms: int
    generation_tokens: int
    citations_count: int
    
    # 总体指标
    total_time_ms: int
    cache_hit: bool
    
    timestamp: str

class QueryService:
    async def execute_query(self, request: QueryRequest) -> QueryResponse:
        query_id = str(uuid.uuid4())
        start_time = time.time()
        metrics = QueryMetrics(query_id=query_id, query=request.query, ...)
        
        try:
            # ... 执行查询流程 ...
            
            # 记录召回指标
            recall_start = time.time()
            recalled = await recall_engine.recall(...)
            metrics.recall_time_ms = int((time.time() - recall_start) * 1000)
            metrics.recall_count = len(recalled)
            
            # 记录重排指标
            rerank_start = time.time()
            reranked = await reranker.rerank(...)
            metrics.rerank_time_ms = int((time.time() - rerank_start) * 1000)
            metrics.rerank_top1_score = reranked[0].score if reranked else 0
            
            # ... 其他指标 ...
            
            metrics.total_time_ms = int((time.time() - start_time) * 1000)
            
            # 写入日志/时序数据库
            await self._record_metrics(metrics)
            
            return response
        
        finally:
            pass
    
    async def _record_metrics(self, metrics: QueryMetrics):
        """记录指标到Redis Stream + 文件日志"""
        # 1. Redis Stream（实时监控）
        await self.redis.xadd(
            'metrics:queries',
            asdict(metrics),
            maxlen=10000  # 保留最近1万条
        )
        
        # 2. 文件日志（持久化）
        logger.info(f"[METRICS] {json.dumps(asdict(metrics))}")
```

---

### 📊 2. 实时监控Dashboard

```python
# 创建监控API端点
@router.get("/metrics/summary")
async def get_metrics_summary():
    """获取最近1小时的指标摘要"""
    
    # 从Redis Stream读取最近1小时数据
    stream_data = await redis.xrange(
        'metrics:queries',
        min=f"{int(time.time() * 1000) - 3600000}",
        max='+'
    )
    
    metrics_list = [json.loads(data['data']) for _, data in stream_data]
    
    return {
        "total_queries": len(metrics_list),
        "avg_latency_ms": np.mean([m['total_time_ms'] for m in metrics_list]),
        "p95_latency_ms": np.percentile([m['total_time_ms'] for m in metrics_list], 95),
        "p99_latency_ms": np.percentile([m['total_time_ms'] for m in metrics_list], 99),
        "fast_lane_rate": sum(1 for m in metrics_list if m['route'] == 'fast') / len(metrics_list),
        "avg_recall_count": np.mean([m['recall_count'] for m in metrics_list]),
        "avg_rerank_top1_score": np.mean([m['rerank_top1_score'] for m in metrics_list]),
        "sufficiency_pass_rate": sum(1 for m in metrics_list if m['sufficiency_result']) / len(metrics_list),
        "cache_hit_rate": sum(1 for m in metrics_list if m.get('cache_hit')) / len(metrics_list),
    }

@router.get("/metrics/slow_queries")
async def get_slow_queries(threshold_ms: int = 5000):
    """获取慢查询列表"""
    stream_data = await redis.xrange('metrics:queries', '-', '+', count=1000)
    metrics_list = [json.loads(data['data']) for _, data in stream_data]
    
    slow_queries = [
        m for m in metrics_list
        if m['total_time_ms'] > threshold_ms
    ]
    
    return sorted(slow_queries, key=lambda x: x['total_time_ms'], reverse=True)[:20]
```

---

## 五、实施优先级与时间规划

### 第一阶段（3-5天）- 核心性能优化
1. **P0-1**: 扫描件向量化实现（2-3小时）
2. **P0-2**: 批量向量化优化（3-4小时）
3. **P0-3**: VLM并发控制优化（1-2小时）
4. **P1-1**: Embedding缓存层（4-5小时）

**里程碑**：扫描件处理速度提升5倍，重复查询响应时间降低70%

---

### 第二阶段（5-7天）- 召回准确率提升
5. **P1-2**: HyDE查询增强（3-4小时）
6. **P1-3**: 父子块混合检索（4-5小时）
7. **P1-4**: 多查询融合召回（3-4小时）
8. **P1-5**: MMR多样性优化（2-3小时）

**里程碑**：召回准确率提升15-20%，复杂查询支持度显著提升

---

### 第三阶段（3-5天）- 生产就绪
9. **P2-1**: 监控指标采集（4-5小时）
10. **P2-2**: 实时监控Dashboard（4-5小时）
11. **P2-3**: LLM生成缓存（2-3小时）
12. **P2-4**: 失败重试机制（2-3小时）

**里程碑**：系统可观测性完备，故障可快速定位

---

## 六、量化收益预估

| 指标 | 当前 | 第一阶段后 | 第二阶段后 | 第三阶段后 |
|------|------|-----------|-----------|-----------|
| 扫描件处理速度 | 27min/81页 | **3-5min** | 3-5min | 3-5min |
| 重复查询延迟 | 3-5s | **1-1.5s** | 1-1.5s | **0.5-1s** |
| 新查询延迟 | 3-5s | 2.5-4s | 2.5-4s | 2.5-4s |
| 向量召回准确率 | 70-75% | 70-75% | **82-88%** | 82-88% |
| Top-5命中率 | 75-80% | 75-80% | **88-92%** | 88-92% |
| VLM成功率 | 60% | **95%+** | 95%+ | **98%+** |
| 缓存命中率 | 0% | **35-45%** | 35-45% | **45-60%** |
| API调用成本 | 基准 | **↓40%** | ↓40% | **↓55%** |

---

## 七、技术风险与缓解措施

### 风险1：缓存一致性问题
- **风险**：文档更新后缓存未失效
- **缓解**：文档更新时主动清除相关缓存，缓存TTL不超过24小时

### 风险2：HyDE质量不稳定
- **风险**：假设答案偏离导致召回变差
- **缓解**：AB测试对比，仅在向量召回使用，保留原query的关键词召回作为兜底

### 风险3：MMR计算开销
- **风险**：相似度计算增加延迟
- **缓解**：仅对Top-50候选应用MMR，使用简化的相似度计算（基于元数据）

### 风险4：监控数据量膨胀
- **风险**：Redis Stream数据过多
- **缓解**：maxlen限制+定期归档到时序数据库/文件

---

## 八、总结

**核心策略**：
1. **性能优先**：缓存层（P0）→ 批量化（P0）→ 并发控制（P0）
2. **准确率提升**：HyDE（P1）→ 父子块（P1）→ 多查询（P1）→ MMR（P1）
3. **可观测性**：指标采集（P2）→ 监控面板（P2）

**预期总收益**：
- 性能提升 **3-5倍**（含缓存命中场景）
- 准确率提升 **12-18个百分点**
- 成本降低 **40-55%**
- 可观测性从无到有

**投入时间**：约 **15-20人天**（2-3周），核心开发1人即可完成。
