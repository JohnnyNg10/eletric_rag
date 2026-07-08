"""
事实一致性校验器 (Factual Consistency Validator)

校验LLM生成的答案是否与参考资料一致
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging
import re

from app.core.retrieval.rerank import RerankResult
from app.core.generation.llm_client import get_llm_client

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """验证结果"""
    consistent: bool  # 是否一致
    confidence: float  # 置信度 [0.0, 1.0]
    issues: List[str]  # 发现的问题
    details: List[Dict[str, Any]]  # 详细验证结果


class FactualValidator:
    """
    事实一致性校验器

    使用LLM验证生成答案中的事实陈述是否与参考资料一致
    """

    def __init__(
        self,
        consistency_threshold: float = 0.7,
        enable_validation: bool = True,
        timeout: float = 3.0
    ):
        """
        Args:
            consistency_threshold: 一致性阈值
            enable_validation: 是否启用验证（可关闭以节省成本）
            timeout: 验证超时时间（秒）
        """
        self.consistency_threshold = consistency_threshold
        self.enable_validation = enable_validation
        self.timeout = timeout
        self.llm_client = get_llm_client()

    async def validate(
        self,
        answer: str,
        chunks: List[RerankResult],
        query: Optional[str] = None
    ) -> ValidationResult:
        """
        验证答案的事实一致性

        Args:
            answer: LLM生成的答案
            chunks: 参考的文档块
            query: 用户问题（可选，用于上下文）

        Returns:
            ValidationResult
        """
        if not self.enable_validation:
            logger.info("[FactualValidator] Validation disabled, skipping")
            return ValidationResult(
                consistent=True,
                confidence=1.0,
                issues=[],
                details=[]
            )

        if not answer or not chunks:
            logger.warning("[FactualValidator] Empty answer or chunks, skipping validation")
            return ValidationResult(
                consistent=True,
                confidence=0.0,
                issues=["Empty input"],
                details=[]
            )

        try:
            # 提取答案中的事实陈述
            facts = self._extract_factual_statements(answer)

            if not facts:
                logger.info("[FactualValidator] No factual statements found")
                return ValidationResult(
                    consistent=True,
                    confidence=1.0,
                    issues=[],
                    details=[]
                )

            # 构建参考上下文
            context = self._build_context(chunks)

            # LLM验证
            validation_result = await self._llm_validate(facts, context, query)

            return validation_result

        except Exception as e:
            logger.error(f"[FactualValidator] Validation error: {e}", exc_info=True)
            return ValidationResult(
                consistent=True,  # 验证失败时默认通过，避免阻塞
                confidence=0.0,
                issues=[f"Validation error: {str(e)}"],
                details=[]
            )

    def _extract_factual_statements(self, answer: str) -> List[str]:
        """
        提取答案中的事实陈述

        简单实现：按句子分割，过滤掉疑问句和太短的句子
        """
        # 按句号、问号、感叹号分割
        sentences = re.split(r'[。！？\.\!\?]', answer)

        facts = []
        for sent in sentences:
            sent = sent.strip()

            # 过滤条件
            if len(sent) < 10:  # 太短
                continue
            if sent.endswith('吗') or sent.endswith('？') or sent.endswith('?'):  # 疑问句
                continue
            if sent.startswith('如果') or sent.startswith('假设'):  # 假设性陈述
                continue

            facts.append(sent)

        logger.info(f"[FactualValidator] Extracted {len(facts)} factual statements")
        return facts[:5]  # 最多验证5条，避免成本过高

    def _build_context(self, chunks: List[RerankResult]) -> str:
        """构建参考上下文"""
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            source = f"[{i}]"
            if chunk.standard_no:
                source += f" {chunk.standard_no}"
            if chunk.clause:
                source += f" 第{chunk.clause}条"

            content = chunk.content[:300] if chunk.content else ""
            context_parts.append(f"{source}\n{content}")

        return "\n\n".join(context_parts)

    async def _llm_validate(
        self,
        facts: List[str],
        context: str,
        query: Optional[str]
    ) -> ValidationResult:
        """
        使用LLM验证事实一致性

        Args:
            facts: 事实陈述列表
            context: 参考上下文
            query: 用户问题

        Returns:
            ValidationResult
        """
        # 构造验证提示词
        facts_text = "\n".join([f"{i+1}. {fact}" for i, fact in enumerate(facts)])

        prompt = f"""你是一个事实一致性验证助手。请判断以下答案中的事实陈述是否与参考资料一致。

参考资料：
{context}

待验证的事实陈述：
{facts_text}

请以JSON格式返回验证结果：
{{
  "consistent": true/false,  // 整体是否一致
  "confidence": 0.0-1.0,     // 置信度
  "details": [
    {{"fact_index": 1, "consistent": true, "reason": "与参考资料[1]一致"}},
    ...
  ]
}}

只返回JSON，不要其他文字。"""

        try:
            messages = [
                {"role": "system", "content": "你是一个严谨的事实验证助手。"},
                {"role": "user", "content": prompt}
            ]

            response = self.llm_client.chat(
                messages=messages,
                temperature=0.1,  # 低温度，更确定性
                max_tokens=800
            )

            # 解析JSON
            import json
            result_json = self._extract_json(response)

            if not result_json:
                logger.error(f"[FactualValidator] Failed to parse JSON: {response}")
                return ValidationResult(
                    consistent=True,
                    confidence=0.0,
                    issues=["Failed to parse validation result"],
                    details=[]
                )

            # 构造结果
            consistent = result_json.get("consistent", True)
            confidence = float(result_json.get("confidence", 0.0))
            details = result_json.get("details", [])

            issues = []
            for detail in details:
                if not detail.get("consistent", True):
                    fact_idx = detail.get("fact_index", 0)
                    reason = detail.get("reason", "Unknown")
                    issues.append(f"Fact {fact_idx}: {reason}")

            logger.info(f"[FactualValidator] Validation result: consistent={consistent}, confidence={confidence:.2f}")

            return ValidationResult(
                consistent=consistent and confidence >= self.consistency_threshold,
                confidence=confidence,
                issues=issues,
                details=details
            )

        except Exception as e:
            logger.error(f"[FactualValidator] LLM validation error: {e}", exc_info=True)
            return ValidationResult(
                consistent=True,  # 验证失败时默认通过
                confidence=0.0,
                issues=[f"LLM validation error: {str(e)}"],
                details=[]
            )

    def _extract_json(self, text: str) -> Optional[dict]:
        """从文本中提取JSON"""
        import json
        text = text.strip()

        # 尝试1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试2: 提取```json ... ```
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

        return None


# 全局单例
_validator_instance: Optional[FactualValidator] = None


def get_validator() -> FactualValidator:
    """获取验证器单例"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = FactualValidator()
    return _validator_instance
