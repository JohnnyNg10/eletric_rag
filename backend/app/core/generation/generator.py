"""
答案生成器 (Answer Generator)

基于检索结果生成答案，包含引用溯源和事实校验
"""
from typing import List, Optional, AsyncIterator, Dict, Any
from dataclasses import dataclass
import logging
import time

from app.core.retrieval.rerank import RerankResult
from app.core.generation.llm_client import get_llm_client
from app.core.generation.citation import Citation, get_citation_extractor
from app.core.generation.validator import ValidationResult, get_validator

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """生成结果"""
    answer: str  # 生成的答案
    citations: List[Citation]  # 引用列表
    validation: Optional[ValidationResult]  # 事实校验结果
    generation_time: int  # 生成耗时（毫秒）
    token_count: int  # 生成的token数量
    model: str  # 使用的模型


class AnswerGenerator:
    """
    答案生成器

    核心功能：
    1. 构建Prompt（包含参考资料）
    2. 调用LLM生成答案
    3. 提取引用标注
    4. 事实一致性校验
    """

    def __init__(
        self,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        enable_validation: bool = False,  # 默认关闭验证以节省成本
        system_prompt: Optional[str] = None
    ):
        """
        Args:
            temperature: LLM温度参数（0.1较低，更确定性）
            max_tokens: 最大生成token数
            enable_validation: 是否启用事实校验
            system_prompt: 自定义系统提示词
        """
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_validation = enable_validation
        self.system_prompt = system_prompt or self._default_system_prompt()

        self.llm_client = get_llm_client()
        self.citation_extractor = get_citation_extractor()
        self.validator = get_validator()

    def _default_system_prompt(self) -> str:
        """默认系统提示词"""
        return """你是一个专业的电力工程领域知识助手，擅长解读国家标准和行业规范。

核心原则：
1. **基于资料**：答案参考资料，要自己进行完善和补充
2. **综合阐述**：不要简单罗列原文，整理格式后回答，不要直接把表格堆在答案，要理解后用专业语言进行综合、整理和解释，给出完整的专业回答
3. **引用溯源**：引用关键数据、规范条文或重要结论时，在句末标注来源编号，如[1]、[2]

回答格式要求：
- 针对问题的多个方面分别阐述，逻辑清晰
- 技术术语使用准确，对重要概念给出必要的解释
- 涉及具体数值、分级、限值时，完整列出并说明其含义
- 如参考资料涵盖多个相关方面，主动归纳总结
- 如参考资料确实不包含所问内容，明确说明"""

    def build_prompt(
        self,
        query: str,
        chunks: List[RerankResult]
    ) -> str:
        """
        构建生成Prompt

        Args:
            query: 用户问题
            chunks: 参考文档块列表（Top5~8）

        Returns:
            完整的prompt字符串
        """
        # 构建参考资料部分
        references = []
        for i, chunk in enumerate(chunks, 1):
            # 来源标识
            source_parts = [f"[{i}]"]
            if chunk.standard_no:
                source_parts.append(chunk.standard_no)
            if chunk.clause:
                source_parts.append(f"第{chunk.clause}条")
            elif chunk.chapter:
                source_parts.append(f"第{chunk.chapter}章")

            source_line = " ".join(source_parts)

            # 内容
            content = chunk.content if chunk.content else ""

            references.append(f"{source_line}\n{content}")

        references_text = "\n\n".join(references)

        # 构建完整prompt
        prompt = f"""参考资料：
{references_text}

用户问题：
{query}

请基于以上全部参考资料，对问题进行完整、专业的回答。要求：
- 涉及分类、分级、限值等具体数据时，完整列出所有类别及对应的技术指标
- 涉及多个方面时，每个方面都要展开说明
- 对重要数据或条款，在句末标注来源编号[1][2]等
- 不要简单摘抄原文，要理解后用专业语言综合表述
- 如果参考资料中包含表格，表格中的分类和数值应当体现在答案中

答案："""

        return prompt

    async def generate(
        self,
        query: str,
        chunks: List[RerankResult],
        stream: bool = False
    ) -> GenerationResult:
        """
        生成答案（非流式）

        Args:
            query: 用户问题
            chunks: 参考文档块
            stream: 是否流式输出（当前版本不支持，保留接口）

        Returns:
            GenerationResult
        """
        if not chunks:
            logger.warning("[AnswerGenerator] No chunks provided, returning empty answer")
            return GenerationResult(
                answer="抱歉，未找到相关参考资料，无法回答您的问题。",
                citations=[],
                validation=None,
                generation_time=0,
                token_count=0,
                model="none"
            )

        start_time = time.time()

        try:
            # 构建prompt
            prompt = self.build_prompt(query, chunks)
            logger.info(f"[AnswerGenerator] Prompt built, length={len(prompt)}")

            # 调用LLM生成答案
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ]

            answer = self.llm_client.chat(
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            logger.info(f"[AnswerGenerator] Answer generated, length={len(answer)}")

            # 提取引用
            citations = self.citation_extractor.extract(answer, chunks)
            logger.info(f"[AnswerGenerator] Extracted {len(citations)} citations")

            # 事实一致性校验（可选）
            validation = None
            if self.enable_validation:
                logger.info("[AnswerGenerator] Running fact validation")
                validation = await self.validator.validate(answer, chunks, query)
                logger.info(f"[AnswerGenerator] Validation: consistent={validation.consistent}, confidence={validation.confidence:.2f}")

            elapsed_ms = int((time.time() - start_time) * 1000)

            # 估算token数（粗略：中文按2字符/token，英文按4字符/token）
            token_count = self._estimate_tokens(answer)

            return GenerationResult(
                answer=answer,
                citations=citations,
                validation=validation,
                generation_time=elapsed_ms,
                token_count=token_count,
                model="doubao-pro"  # 从配置读取
            )

        except Exception as e:
            logger.error(f"[AnswerGenerator] Generation error: {e}", exc_info=True)
            elapsed_ms = int((time.time() - start_time) * 1000)

            return GenerationResult(
                answer=f"抱歉，生成答案时出现错误：{str(e)}",
                citations=[],
                validation=None,
                generation_time=elapsed_ms,
                token_count=0,
                model="error"
            )

    async def generate_stream(
        self,
        query: str,
        chunks: List[RerankResult]
    ) -> AsyncIterator[str]:
        """
        流式生成答案

        Args:
            query: 用户问题
            chunks: 参考文档块

        Yields:
            答案片段（delta）
        """
        if not chunks:
            yield "抱歉，未找到相关参考资料，无法回答您的问题。"
            return

        try:
            # 构建prompt
            prompt = self.build_prompt(query, chunks)

            # 调用LLM流式生成
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ]

            for delta in self.llm_client.chat_stream(
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            ):
                yield delta

        except Exception as e:
            logger.error(f"[AnswerGenerator] Stream generation error: {e}", exc_info=True)
            yield f"\n\n抱歉，生成答案时出现错误：{str(e)}"

    def _estimate_tokens(self, text: str) -> int:
        """
        估算token数量

        粗略规则：
        - 中文：1字 ≈ 1.5 token
        - 英文/数字/标点：4字符 ≈ 1 token
        """
        import re

        # 统计中文字符
        chinese_chars = len(re.findall(r'[一-鿿]', text))

        # 统计非中文字符
        non_chinese_chars = len(text) - chinese_chars

        # 估算
        tokens = int(chinese_chars * 1.5 + non_chinese_chars / 4)
        return tokens


# 全局单例
_generator_instance: Optional[AnswerGenerator] = None


def get_generator(enable_validation: bool = False) -> AnswerGenerator:
    """获取生成器单例"""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = AnswerGenerator(enable_validation=enable_validation)
    return _generator_instance
