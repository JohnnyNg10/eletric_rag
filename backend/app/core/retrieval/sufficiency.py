"""
充分性判断 (Sufficiency Check)

双重判断机制：
1. 规则判断（快速路径）：最高分、覆盖度、空结果过滤
2. LLM判断（精准路径）：豆包Pro评估信息充分性
"""
from typing import List, Optional
from dataclasses import dataclass
import logging
import asyncio
import json

from app.core.retrieval.rerank import RerankResult
from app.core.generation.llm_client import get_llm_client

logger = logging.getLogger(__name__)


@dataclass
class SufficiencyResult:
    """充分性判断结果"""
    sufficient: bool  # 是否充分
    source: str  # "rule" / "llm" / "timeout_fallback"
    confidence: float  # LLM置信度 [0.0, 1.0]
    gaps: List[str]  # 信息缺口列表


class SufficiencyChecker:
    """
    充分性检查器

    判断Top5结果是否包含足够信息回答用户问题
    """

    def __init__(
        self,
        rule_top1_threshold: float = 0.3,
        rule_coverage_threshold: float = 0.2,
        rule_coverage_min_count: int = 2,
        llm_confidence_threshold: float = 0.7,
        llm_timeout: float = 1.5,  # 1.5秒超时
    ):
        """
        初始化充分性检查器

        Args:
            rule_top1_threshold: 规则-最高分阈值
            rule_coverage_threshold: 规则-覆盖度分数阈值
            rule_coverage_min_count: 规则-覆盖度最小块数
            llm_confidence_threshold: LLM置信度阈值
            llm_timeout: LLM判断超时时间（秒）
        """
        self.rule_top1_threshold = rule_top1_threshold
        self.rule_coverage_threshold = rule_coverage_threshold
        self.rule_coverage_min_count = rule_coverage_min_count
        self.llm_confidence_threshold = llm_confidence_threshold
        self.llm_timeout = llm_timeout

        self.llm_client = get_llm_client()

    async def check(
        self,
        query: str,
        top_results: List[RerankResult],
    ) -> SufficiencyResult:
        """
        充分性判断（双重机制）

        Args:
            query: 用户原始问题
            top_results: 精排后的Top5结果

        Returns:
            SufficiencyResult: 充分性判断结果
        """
        logger.info(f"[SufficiencyCheck] query='{query}', top_results_count={len(top_results)}")

        # 第一关：规则判断（快速路径）
        rule_passed, rule_reason = self._rule_check(top_results)

        if not rule_passed:
            logger.info(f"[SufficiencyCheck] Rule check FAILED: {rule_reason}")
            return SufficiencyResult(
                sufficient=False,
                source="rule",
                confidence=0.0,
                gaps=[rule_reason]
            )

        logger.info("[SufficiencyCheck] Rule check PASSED, proceeding to LLM check")

        # 第二关：LLM判断（精准路径）
        try:
            llm_result = await asyncio.wait_for(
                self._llm_check(query, top_results),
                timeout=self.llm_timeout
            )

            # 判断LLM置信度
            if llm_result.sufficient and llm_result.confidence >= self.llm_confidence_threshold:
                logger.info(f"[SufficiencyCheck] LLM check PASSED (confidence={llm_result.confidence:.2f})")
                return SufficiencyResult(
                    sufficient=True,
                    source="llm",
                    confidence=llm_result.confidence,
                    gaps=[]
                )
            else:
                logger.info(f"[SufficiencyCheck] LLM check FAILED (confidence={llm_result.confidence:.2f}, gaps={llm_result.gaps})")
                return SufficiencyResult(
                    sufficient=False,
                    source="llm",
                    confidence=llm_result.confidence,
                    gaps=llm_result.gaps
                )

        except asyncio.TimeoutError:
            logger.warning(f"[SufficiencyCheck] LLM check TIMEOUT (>{self.llm_timeout}s), defaulting to sufficient")
            return SufficiencyResult(
                sufficient=True,
                source="timeout_fallback",
                confidence=0.0,
                gaps=[]
            )

        except Exception as e:
            logger.error(f"[SufficiencyCheck] LLM check ERROR: {e}", exc_info=True)
            # 异常时默认充分，避免阻塞
            return SufficiencyResult(
                sufficient=True,
                source="error_fallback",
                confidence=0.0,
                gaps=[]
            )

    def _rule_check(self, top_results: List[RerankResult]) -> tuple[bool, str]:
        """
        规则判断（快速路径）

        三条规则：
        1. 空结果过滤：Top5非空
        2. 最高分过滤：Top1分数 >= 0.6
        3. 覆盖度过滤：score >= 0.5 的块数 >= 2

        Returns:
            (是否通过, 失败原因)
        """
        # 规则1: 空结果过滤
        if not top_results:
            return False, "召回结果为空"

        # 规则2: 最高分过滤
        top1_score = top_results[0].score
        if top1_score < self.rule_top1_threshold:
            return False, f"最相关块分数过低 ({top1_score:.3f} < {self.rule_top1_threshold})"

        # 规则3: 覆盖度过滤
        high_score_count = sum(1 for r in top_results if r.score >= self.rule_coverage_threshold)
        if high_score_count < self.rule_coverage_min_count:
            return False, f"高相关块数量不足 ({high_score_count} < {self.rule_coverage_min_count})"

        return True, ""

    async def _llm_check(
        self,
        query: str,
        top_results: List[RerankResult],
    ) -> SufficiencyResult:
        """
        LLM充分性判断（精准路径）

        Args:
            query: 用户问题
            top_results: Top5结果

        Returns:
            SufficiencyResult
        """
        # 生成摘要（每块截断至200字）
        summaries = []
        for i, result in enumerate(top_results, 1):
            content_preview = result.content[:200]
            source_info = f"【来源: {result.standard_no or '未知'}】" if result.standard_no else ""
            summaries.append(f"{i}. {source_info}\n{content_preview}...")

        context_summary = "\n\n".join(summaries)

        # 构造提示词
        prompt = f"""你是一个专业的电力领域知识库助手。请判断以下检索结果是否包含足够的信息来回答用户的问题。

用户问题：
{query}

检索到的文档块（Top5）：
{context_summary}

请以JSON格式返回判断结果，包含以下字段：
- sufficient: true（充分）或 false（不充分）
- confidence: 置信度（0.0-1.0）
- gaps: 信息缺口列表（如果不充分，列出缺少哪些关键信息；如果充分，返回空数组）

示例输出：
{{"sufficient": true, "confidence": 0.85, "gaps": []}}
或
{{"sufficient": false, "confidence": 0.45, "gaps": ["缺少低压配电盘的具体接线规范", "未提及验收标准"]}}

请直接返回JSON，不要包含其他文字。"""

        try:
            # 调用LLM
            messages = [
                {"role": "system", "content": "你是一个专业的电力领域知识库助手，擅长评估检索结果的充分性。"},
                {"role": "user", "content": prompt}
            ]

            response = self.llm_client.chat(
                messages=messages,
                temperature=0.3,  # 低温度，更确定性
                max_tokens=500
            )

            # 解析JSON响应
            result_json = self._extract_json(response)

            if result_json:
                return SufficiencyResult(
                    sufficient=result_json.get("sufficient", False),
                    source="llm",
                    confidence=float(result_json.get("confidence", 0.0)),
                    gaps=result_json.get("gaps", [])
                )
            else:
                logger.error(f"[LLMCheck] Failed to parse JSON from response: {response}")
                return SufficiencyResult(
                    sufficient=False,
                    source="llm_parse_error",
                    confidence=0.0,
                    gaps=["LLM响应格式错误"]
                )

        except Exception as e:
            logger.error(f"[LLMCheck] Error: {e}", exc_info=True)
            raise

    def _extract_json(self, text: str) -> Optional[dict]:
        """
        从文本中提取JSON

        处理LLM可能返回的各种格式：
        - 纯JSON
        - ```json ... ```
        - 带其他文字的JSON
        """
        text = text.strip()

        # 尝试1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试2: 提取```json ... ```
        import re
        json_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_block:
            try:
                return json.loads(json_block.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试3: 提取第一个完整的{}
        json_obj = re.search(r'\{.*?\}', text, re.DOTALL)
        if json_obj:
            try:
                return json.loads(json_obj.group(0))
            except json.JSONDecodeError:
                pass

        # 所有尝试失败
        return None


# 全局单例
_sufficiency_checker_instance: Optional[SufficiencyChecker] = None


def get_sufficiency_checker() -> SufficiencyChecker:
    """获取充分性检查器单例"""
    global _sufficiency_checker_instance
    if _sufficiency_checker_instance is None:
        _sufficiency_checker_instance = SufficiencyChecker()
    return _sufficiency_checker_instance
