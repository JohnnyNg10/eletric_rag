"""
慢车道 (Slow Lane)

职责：
- 自适应多跳检索
- 工具调用循环
- 复杂查询处理

设计文档：docs/architecture/backend/13-慢车道设计.md
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import logging
import time
import json
import asyncio

from app.db.models import Document, Chunk
from app.schemas.retrieval import ChunkResult
from app.core.generation.llm_client import get_llm_client
from app.core.retrieval.recall import MultiPathRecall

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """工具调用记录"""
    step: int
    tool: str
    params: Dict[str, Any]
    elapsed_ms: int
    result_count: int
    timeout: bool = False


@dataclass
class SlowLaneResult:
    """慢车道检索结果"""
    status: str  # "success", "partial", or "failed"
    retrieved_chunks: List[ChunkResult]  # 召回的文档块
    reasoning_steps: List[ToolCallRecord]  # 推理链路
    retrieval_time: int  # 检索耗时(ms)
    steps_taken: int  # 实际执行步数
    recall_count: int = 0  # 召回数量


class SlowLane:
    """
    慢车道 - 自适应多跳检索

    适用场景：
    - 跨标准对比查询
    - 多跳推理查询
    - 复杂多维度查询

    处理流程：
    1. LLM决策：选择工具
    2. 工具调用：检索信息
    3. 信息聚合
    4. 充分性判断 → 继续或结束（最多3步）

    设计约束：
    - 最大推理步数：3 步
    - 单步超时：2000ms
    - 总延迟预算：8000ms
    - LLM 决策超时：1500ms
    """

    MAX_STEPS = 3
    STEP_TIMEOUT_MS = 120000   # 单步超时 2 分钟（含 LLM 决策 + 三路召回）
    TOTAL_TIMEOUT_MS = 600000  # 总超时 10 分钟
    LLM_DECISION_TIMEOUT_MS = 30000  # LLM 决策超时 30 秒

    def __init__(self, db: Session):
        """
        初始化慢车道

        Args:
            db: 数据库会话
        """
        self.db = db
        self.llm_client = get_llm_client()

        # 初始化工具（用于 retrieve_standard）
        self.multi_path_recall = MultiPathRecall(db=db)

        # 工具映射
        self.tools = {
            "retrieve_standard": self._retrieve_standard,
            "retrieve_clause": self._retrieve_clause,
            "list_related_standards": self._list_related_standards
        }

    async def execute(
        self,
        query: str,
        user_context: Dict[str, Any],
        strategy_params: Optional[Dict[str, Any]] = None
    ) -> SlowLaneResult:
        """
        执行慢车道流程

        Args:
            query: 预处理后的清晰查询
            user_context: 用户上下文
            strategy_params: 检索策略参数（可选）

        Returns:
            SlowLaneResult: 检索结果
        """
        start_time = time.time()
        strategy_params = strategy_params or {}

        max_steps = strategy_params.get("max_steps", self.MAX_STEPS)
        total_timeout = strategy_params.get("total_timeout", self.TOTAL_TIMEOUT_MS)
        step_timeout = strategy_params.get("step_timeout", self.STEP_TIMEOUT_MS) / 1000.0

        logger.info(f"[SlowLane] Start processing: {query}")
        logger.info(f"[SlowLane] Max steps: {max_steps}, Total timeout: {total_timeout}ms")

        reasoning_steps: List[ToolCallRecord] = []
        all_chunks: List[ChunkResult] = []
        accumulated_metadata: List[Dict[str, Any]] = []  # 记录每步工具返回的元信息（含标准清单）
        steps_taken = 0

        # 工具调用循环（最多 max_steps 步）
        for step_idx in range(max_steps):
            # 检查总延迟预算
            elapsed = int((time.time() - start_time) * 1000)
            if elapsed > total_timeout:
                logger.warning(f"[SlowLane] Total timeout exceeded: {elapsed}ms")
                break

            # LLM 决策：是否需要继续检索
            try:
                decision = await self._llm_decide(
                    query=query,
                    current_chunks=all_chunks,
                    step_number=step_idx + 1,
                    remaining_steps=max_steps - step_idx,
                    accumulated_metadata=accumulated_metadata
                )
            except asyncio.TimeoutError:
                logger.warning(f"[SlowLane] Step {step_idx + 1}: LLM decision timeout")
                # 超时则默认信息已充分，进入生成
                break

            # 如果 LLM 判断信息已充分
            if decision.get("action") == "sufficient":
                logger.info(f"[SlowLane] Step {step_idx + 1}: Information sufficient, stopping")
                break

            # 调用检索工具
            tool_name = decision.get("tool")
            tool_params = decision.get("params", {})

            if not tool_name or tool_name not in self.tools:
                logger.error(f"[SlowLane] Step {step_idx + 1}: Invalid tool '{tool_name}'")
                break

            # 执行工具调用（带超时）
            tool_start = time.time()
            try:
                tool_result = await asyncio.wait_for(
                    self._call_tool(tool_name, tool_params),
                    timeout=step_timeout
                )
                tool_elapsed_ms = int((time.time() - tool_start) * 1000)
                timeout = False
            except asyncio.TimeoutError:
                logger.warning(f"[SlowLane] Step {step_idx + 1}: Tool '{tool_name}' timeout")
                tool_result = {"chunks": [], "metadata": {}}
                tool_elapsed_ms = self.STEP_TIMEOUT_MS
                timeout = True

            # 提取结果
            new_chunks = tool_result.get("chunks", [])
            all_chunks.extend(new_chunks)

            # 保留元信息（list_related_standards 会返回标准清单，供下一步 LLM 决策使用）
            step_meta = tool_result.get("metadata", {})
            if step_meta:
                accumulated_metadata.append({"step": step_idx + 1, "tool": tool_name, **step_meta})

            # 记录推理步骤
            record = ToolCallRecord(
                step=step_idx + 1,
                tool=tool_name,
                params=tool_params,
                elapsed_ms=tool_elapsed_ms,
                result_count=len(new_chunks),
                timeout=timeout
            )
            reasoning_steps.append(record)
            steps_taken += 1

            logger.info(f"[SlowLane] Step {step_idx + 1}: {tool_name} returned {len(new_chunks)} chunks")

            # 如果工具返回空结果且超时，考虑提前终止
            if timeout and len(new_chunks) == 0:
                logger.warning(f"[SlowLane] Step {step_idx + 1}: Tool timeout with no results, stopping")
                break

        # 信息聚合与去重
        aggregated_chunks = self._aggregate_chunks(all_chunks)

        # 图片伴随召回 + 图片链接注入（与快车道一致，在重排之前）
        if aggregated_chunks:
            try:
                from app.core.retrieval.image_link_injector import pull_along_images, inject_image_links
                aggregated_chunks = await pull_along_images(aggregated_chunks, self.db)
                aggregated_chunks = await inject_image_links(aggregated_chunks, self.db)
                logger.info(f"[SlowLane] Image injection completed: {len(aggregated_chunks)} chunks")
            except Exception as e:
                logger.error(f"[SlowLane] Image injection error: {e}", exc_info=True)

        # 两阶段重排（与快车道一致）
        if aggregated_chunks:
            try:
                from app.core.retrieval.rerank import get_reranker
                reranker = get_reranker()
                reranked = await reranker.rerank(
                    query=query,
                    candidates=aggregated_chunks,
                    top_k=min(10, len(aggregated_chunks))
                )
                # 将 RerankResult 转回 ChunkResult
                final_chunks = []
                for r in reranked:
                    final_chunks.append(ChunkResult(
                        chunk_id=r.chunk_id,
                        content=r.content,
                        document_id=r.document_id,
                        score=r.score,
                        standard_no=r.standard_no,
                        doc_type=r.doc_type,
                        category=r.category,
                        voltage_level=r.voltage_level,
                        clause=r.clause,
                        chapter=r.chapter,
                        section=r.section,
                        page_start=r.page_start,
                        page_end=r.page_end,
                        recall_source=r.recall_source,
                        document_title=r.document_title,
                        content_type=r.content_type,
                        image_id=r.image_id,
                        image_url=r.image_url,
                        image_page=r.image_page,
                        image_figure_number=r.image_figure_number,
                        image_caption=r.image_caption,
                        referenced_images=[ImageRef(**img) for img in r.referenced_images] if r.referenced_images else [],
                    ))
                logger.info(f"[SlowLane] Reranked: {len(aggregated_chunks)} → {len(final_chunks)}")
                aggregated_chunks = final_chunks
            except Exception as e:
                logger.error(f"[SlowLane] Rerank error: {e}, using aggregated scores")

        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.info(f"[SlowLane] Completed in {elapsed_ms}ms, steps: {steps_taken}, chunks: {len(aggregated_chunks)}")

        return SlowLaneResult(
            status="success" if len(aggregated_chunks) > 0 else "failed",
            retrieved_chunks=aggregated_chunks,
            reasoning_steps=reasoning_steps,
            retrieval_time=elapsed_ms,
            steps_taken=steps_taken,
            recall_count=len(aggregated_chunks)
        )

    async def _llm_decide(
        self,
        query: str,
        current_chunks: List[ChunkResult],
        step_number: int,
        remaining_steps: int,
        accumulated_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        LLM 决策下一步动作

        Args:
            query: 原始查询
            current_chunks: 当前已获取的文档块
            step_number: 当前步骤号
            remaining_steps: 剩余步数

        Returns:
            决策结果: {"action": "continue" | "sufficient", "tool": str, "params": dict}
        """
        # 构建上下文摘要
        context_summary = self._build_context_summary(current_chunks)

        # 构建 prompt
        system_prompt = """你是一个专业的电力标准检索助手，负责决策是否需要继续检索以及使用什么工具。

可用工具：
1. retrieve_standard - 标准内容语义检索（主要工具）
   参数：{"query": "检索查询", "standard_ids": ["标准号1", "标准号2"] (可选)}
   用途：使用语义搜索在所有标准或指定标准中查找相关内容
   适用场景：
   - 用户提出技术问题，需要查找相关标准条款
   - 需要找到特定概念、要求、指标的具体规定
   - 比较不同标准对同一主题的规定

2. retrieve_clause - 精确条款定位
   参数：{"standard_id": "标准号", "clause_number": "条款号"}
   用途：精确获取某标准某条款的完整原文
   适用场景：
   - 用户明确提到"某标准第X条"或"X.X.X条款"
   - 需要补充完整条款内容

3. list_related_standards - 相关标准清单（辅助工具）
   参数：{"keyword": "关键词", "category": "分类" (可选)}
   用途：仅列出包含特定关键词的标准清单（不返回实际内容）
   适用场景：
   - 用户问"有哪些标准涉及XX"
   - 需要先确定相关标准范围，再用 retrieve_standard 检索内容

工具选择原则：
- 优先使用 retrieve_standard 进行语义搜索（最有效）
- 只有明确知道条款号时才用 retrieve_clause
- 只有需要"列举标准"而非"查找内容"时才用 list_related_standards
- list_related_standards 后通常需要跟随 retrieve_standard 获取实际内容

返回 JSON 格式（不要添加其他说明文字）：
{"action": "continue", "tool": "工具名", "params": {...}}  # 继续检索
或
{"action": "sufficient"}  # 信息已充分
"""

        # 构建已发现标准清单的提示（list_related_standards 的结果）
        standards_hint = ""
        if accumulated_metadata:
            for meta in accumulated_metadata:
                if meta.get("tool") == "list_related_standards" and meta.get("standards"):
                    std_lines = [
                        f"  - {s['standard_no']}: {s['title']}"
                        for s in meta["standards"][:5]
                    ]
                    standards_hint = "\n\n已发现相关标准（可用于下一步 retrieve_standard 的 standard_ids）：\n" + "\n".join(std_lines)

        user_prompt = f"""原始问题：{query}

当前步骤：第 {step_number} 步（还剩 {remaining_steps} 步可用）

已获取信息：
{context_summary}{standards_hint}

请决策下一步操作。

示例决策：
- 如果问题是"异步发电机与变流器型光伏的功率因数要求有无区别？"
  应选择：{{"action": "continue", "tool": "retrieve_standard", "params": {{"query": "异步发电机 变流器型光伏 功率因数"}}}}

- 如果问题是"GB/T 33593-2017 第 5.3 条说了什么？"
  应选择：{{"action": "continue", "tool": "retrieve_clause", "params": {{"standard_id": "GB/T 33593-2017", "clause_number": "5.3"}}}}

- 如果问题是"有哪些标准涉及光伏并网？"
  应选择：{{"action": "continue", "tool": "list_related_standards", "params": {{"keyword": "光伏并网"}}}}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # LLM 调用
        # 注意：LLM 响应较慢（约 8-10 秒），不设置单独超时，依赖外层总超时控制
        try:
            response = await asyncio.to_thread(
                self.llm_client.chat,
                messages=messages,
                temperature=0.1,
                max_tokens=500
            )

            # 解析 JSON 响应
            # 尝试提取 JSON（可能被包裹在代码块中）
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            decision = json.loads(response)
            return decision

        except json.JSONDecodeError as e:
            logger.error(f"[SlowLane] LLM decision parse error: {e}, response: {response}")
            # 默认认为信息已充分
            return {"action": "sufficient"}
        except asyncio.TimeoutError:
            logger.warning(f"[SlowLane] LLM decision timeout after {self.LLM_DECISION_TIMEOUT_MS}ms")
            return {"action": "sufficient"}
        except Exception as e:
            logger.error(f"[SlowLane] LLM decision error: {e}", exc_info=True)
            return {"action": "sufficient"}

    def _build_context_summary(self, chunks: List[ChunkResult]) -> str:
        """
        构建已获取信息的摘要

        Args:
            chunks: 已获取的文档块

        Returns:
            摘要文本
        """
        if not chunks:
            return "（尚未获取任何信息）"

        # 按来源标准分组
        by_standard: Dict[str, List[ChunkResult]] = {}
        for chunk in chunks:
            std_no = chunk.standard_no or "未知标准"
            if std_no not in by_standard:
                by_standard[std_no] = []
            by_standard[std_no].append(chunk)

        # 构建摘要
        summary_lines = []
        for std_no, std_chunks in by_standard.items():
            clauses = [c.clause for c in std_chunks if c.clause]
            clause_text = f"（条款：{', '.join(clauses[:3])}...）" if clauses else ""
            summary_lines.append(f"- {std_no}: {len(std_chunks)} 条相关内容 {clause_text}")

        return "\n".join(summary_lines[:5])  # 最多显示 5 个标准

    async def _call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用检索工具

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            {"chunks": List[ChunkResult], "metadata": dict}
        """
        if tool_name not in self.tools:
            logger.error(f"[SlowLane] Unknown tool: {tool_name}")
            return {"chunks": [], "metadata": {}}

        tool_func = self.tools[tool_name]
        try:
            result = await tool_func(**params)
            return result
        except Exception as e:
            logger.error(f"[SlowLane] Tool '{tool_name}' error: {e}", exc_info=True)
            return {"chunks": [], "metadata": {}}

    async def _retrieve_standard(
        self,
        query: str,
        standard_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        标准内容检索（复用快车道的 MultiPathRecall）

        Args:
            query: 检索查询
            standard_ids: 限定的标准号列表（可选）

        Returns:
            {"chunks": List[ChunkResult], "metadata": dict}
        """
        try:
            # 构建过滤条件
            filters = {}
            if standard_ids:
                filters["standard_no"] = standard_ids

            # 调用 MultiPathRecall（返回 Top50，无法自定义数量）
            results = await self.multi_path_recall.recall(
                query=query,
                filters=filters
            )

            # 慢车道单步限制返回 15 条
            results = results[:15]

            return {
                "chunks": results,
                "metadata": {"query": query, "standard_ids": standard_ids}
            }
        except Exception as e:
            logger.error(f"[SlowLane] retrieve_standard error: {e}", exc_info=True)
            return {"chunks": [], "metadata": {}}

    async def _retrieve_clause(
        self,
        standard_id: str,
        clause_number: str
    ) -> Dict[str, Any]:
        """
        精确条款定位（MySQL 精确查询）

        Args:
            standard_id: 标准号
            clause_number: 条款号

        Returns:
            {"chunks": List[ChunkResult], "metadata": dict}
        """
        try:
            # MySQL 精确查询
            chunk = self.db.query(Chunk).join(Document).filter(
                and_(
                    Document.standard_no == standard_id,
                    Chunk.clause == clause_number
                )
            ).first()

            if not chunk:
                logger.warning(f"[SlowLane] Clause not found: {standard_id} {clause_number}")
                return {"chunks": [], "metadata": {}}

            # 构建 ChunkResult
            chunk_result = ChunkResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                score=1.0,  # 精确匹配，评分为 1.0
                document_title=chunk.document.title if chunk.document else None,
                standard_no=chunk.document.standard_no if chunk.document else None,
                doc_type=chunk.document.doc_type if chunk.document else None,
                category=chunk.document.category if chunk.document else None,
                voltage_level=chunk.document.voltage_level if chunk.document else None,
                clause=chunk.clause,
                chapter=chunk.chapter,
                page_start=chunk.page_start,
                page_end=chunk.page_end
            )

            return {
                "chunks": [chunk_result],
                "metadata": {"standard_id": standard_id, "clause_number": clause_number}
            }

        except Exception as e:
            logger.error(f"[SlowLane] retrieve_clause error: {e}", exc_info=True)
            return {"chunks": [], "metadata": {}}

    async def _list_related_standards(
        self,
        keyword: str,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        列出相关标准清单（文档元信息，不返回内容）

        Args:
            keyword: 关键词
            category: 专业分类（可选）

        Returns:
            {"chunks": [], "metadata": {"standards": [...]}}
        """
        try:
            # 查询包含关键词的标准
            query = self.db.query(Document).filter(
                Document.process_status == "completed"
            )

            # 关键词过滤（标题、关键词字段、摘要）
            query = query.filter(
                or_(
                    Document.title.contains(keyword),
                    Document.keywords.contains(keyword),
                    Document.abstract.contains(keyword),
                )
            )

            # 分类过滤
            if category:
                query = query.filter(Document.category == category)

            # 限制返回数量
            documents = query.limit(10).all()

            # 构建标准清单
            standards = []
            for doc in documents:
                standards.append({
                    "standard_no": doc.standard_no,
                    "title": doc.title,
                    "doc_count": doc.chunk_count,
                    "doc_id": doc.id,
                    "category": doc.category
                })

            logger.info(f"[SlowLane] Found {len(standards)} related standards for keyword: {keyword}")

            # list_related_standards 不返回 chunks，仅返回元信息
            # 这些信息作为中间信息传给 LLM，辅助后续步骤的工具选择
            return {
                "chunks": [],  # 不参与 chunk 聚合
                "metadata": {"standards": standards, "keyword": keyword}
            }

        except Exception as e:
            logger.error(f"[SlowLane] list_related_standards error: {e}", exc_info=True)
            return {"chunks": [], "metadata": {"standards": []}}

    def _aggregate_chunks(self, chunks: List[ChunkResult]) -> List[ChunkResult]:
        """
        信息聚合与去重

        Args:
            chunks: 所有步骤返回的文档块

        Returns:
            去重排序后的文档块
        """
        if not chunks:
            return []

        # 按 chunk_id 去重（保留首次出现）
        seen_ids = set()
        unique_chunks = []
        for chunk in chunks:
            if chunk.chunk_id not in seen_ids:
                seen_ids.add(chunk.chunk_id)
                unique_chunks.append(chunk)

        # 按评分排序（高分优先）
        unique_chunks.sort(key=lambda c: c.score, reverse=True)

        # 限制最大返回数量（避免生成层 token 溢出）
        max_chunks = 20
        return unique_chunks[:max_chunks]
