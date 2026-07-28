"""
答案生成器 (Answer Generator)

基于检索结果生成答案，包含引用溯源和事实校验
"""
from typing import List, Optional, AsyncIterator, Dict, Any
from dataclasses import dataclass
import logging
import time
import re

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
1. **以资料为事实依据**：所有具体数值、标准条文、技术参数必须来源于参考资料，不得引入资料之外的具体结论。可以用专业知识组织表达、解释概念；但如果参考资料完全不涉及所问内容，须明确说明"现有参考资料未包含该内容"，不得凭训练数据给出具体答案
2. **综合阐述**：不要简单罗列原文，整理格式后回答，给出完整的专业回答
3. **引用溯源**：引用关键数据、规范条文或重要结论时，在句末标注来源编号，如[1]、[2]
4. **配图提示**：如果参考资料中标注了【包含图片】或【涉及图片】，在答案相应位置明确提示用户"详见引用来源[N]中的配图"或"流程图见参考资料[N]"

表格处理规则（优先级最高）：
- 当用户明确要求"展示...表"、"给我看...表"、"列出...表"、"一览表"、"参数表"等，必须直接以结构化表格（Markdown 表格）原样输出表格内容，不得转述为散文
- 其他情况下，可以理解表格内容后用专业语言综合表述，但数值/分级/限值必须完整列出

回答格式要求：
- 针对问题的多个方面分别阐述，逻辑清晰
- 技术术语使用准确，对重要概念给出必要的解释
- 涉及具体数值、分级、限值时，完整列出并说明其含义
- 如参考资料涵盖多个相关方面，主动归纳总结
- 如参考资料确实不包含所问内容，明确说明
- 当用户明确要求"展示图片"或"给我看图"时，直接回答"该流程图/示意图见引用来源[N]，请在引用来源中查看配图"""

    def build_prompt(
        self,
        query: str,
        chunks: List[RerankResult],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        构建生成Prompt

        Args:
            query: 用户问题
            chunks: 参考文档块列表（Top5~8）
            history: 多轮对话历史，格式 [{"query": ..., "answer": ...}]，升序排列

        Returns:
            完整的prompt字符串
        """
        # 构建参考资料部分
        references = []
        for i, chunk in enumerate(chunks, 1):
            source_parts = [f"[{i}]"]
            if chunk.standard_no:
                source_parts.append(chunk.standard_no)
            if chunk.clause:
                source_parts.append(f"第{chunk.clause}条")
            elif chunk.chapter:
                source_parts.append(f"第{chunk.chapter}章")

            source_line = " ".join(source_parts)
            content = chunk.content if chunk.content else ""

            # 表格 chunk：加标注提示 LLM 直接输出
            if chunk.content_type == "table":
                content = f"【结构化表格内容，用户要求展示时直接以 Markdown 表格格式输出，不得转述】\n{content}"
            # 如果 chunk 有配图，在参考资料中标注
            elif chunk.content_type == "image_description" and chunk.image_url:
                content += f"\n\n【此参考资料包含图片，请在答案中明确提示用户查看引用来源[{i}]中的配图】"
            elif chunk.referenced_images:
                fig_numbers = [img.get('figure_number') or '图片' for img in chunk.referenced_images if isinstance(img, dict)]
                if fig_numbers:
                    content += f"\n\n【此参考资料涉及{', '.join(fig_numbers)}，请在答案中提示用户查看引用来源[{i}]中的相关配图】"

            references.append(f"{source_line}\n{content}")

        references_text = "\n\n".join(references)

        # 构建对话历史段（按 token 预算截断）
        history_section = self._build_history_section(history)

        prompt = f"""参考资料：
{references_text}{history_section}

用户问题：
{query}

请基于以上全部参考资料，对问题进行完整、专业的回答。要求：
- 涉及分类、分级、限值等具体数据时，完整列出所有类别及对应的技术指标
- 涉及多个方面时，每个方面都要展开说明
- 引用资料时，严格使用上方标注的编号[1][2][3]等，不要自行创造或跳号
- 不要简单摘抄原文，要理解后用专业语言综合表述
- 如果参考资料中包含表格，表格中的分类和数值应当体现在答案中

答案："""

        return prompt

    def _build_history_section(
        self,
        history: Optional[List[Dict[str, str]]],
    ) -> str:
        """
        将对话历史转换为 prompt 中的历史段，并按 token 预算（MAX_HISTORY_TOKENS）截断。
        从最旧轮次开始丢弃，优先保留最近轮次。
        """
        if not history:
            return ""

        from app.config import settings

        # 截断每轮 answer，防止单轮过长
        MAX_ANSWER_CHARS = 500
        turns = [
            {"query": h["query"], "answer": h["answer"][:MAX_ANSWER_CHARS]}
            for h in history
        ]

        # 按 token 预算从旧到新丢弃（粗估：字符数 / 1.5）
        token_budget = settings.MAX_HISTORY_TOKENS
        while turns:
            total_chars = sum(len(t["query"]) + len(t["answer"]) for t in turns)
            estimated_tokens = int(total_chars / 1.5)
            if estimated_tokens <= token_budget:
                break
            turns.pop(0)  # 丢弃最旧的一轮

        if not turns:
            return ""

        lines = []
        for t in turns:
            lines.append(f"用户：{t['query']}")
            lines.append(f"助手：{t['answer']}")

        return (
            "\n\n对话历史（仅供理解上下文，不作为答案依据）：\n"
            + "\n".join(lines)
        )

    async def generate(
        self,
        query: str,
        chunks: List[RerankResult],
        stream: bool = False,
        history: Optional[List[Dict[str, str]]] = None,
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
            prompt = self.build_prompt(query, chunks, history)
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

            # 提取引用（保留答案里的 [1][2] 标记，用于前端点击跳转）
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
        chunks: List[RerankResult],
        history: Optional[List[Dict[str, str]]] = None,
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
            prompt = self.build_prompt(query, chunks, history)

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

    async def generate_related_queries(
        self,
        query: str,
        answer: str,
        max_queries: int = 5
    ) -> List[str]:
        """
        基于当前问答生成相关问题推荐

        Args:
            query: 用户原始问题
            answer: 生成的答案
            max_queries: 最大推荐问题数量

        Returns:
            List[str]: 相关问题列表（3-5个）
        """
        # 截断答案以控制prompt长度
        answer_snippet = answer[:400] if len(answer) > 400 else answer

        prompt = f"""基于以下问答，生成3-5个相关的后续问题，帮助用户深入了解该领域。

用户问题：{query}

已回答内容（部分）：
{answer_snippet}

要求：
1. 生成的问题应该是用户可能感兴趣的相关主题
2. 可以是深入探讨、扩展应用、对比标准、实践案例等方向
3. 每个问题应该具体、可独立回答
4. 只输出JSON数组格式，不要其他文字

示例输出格式：
["相关问题1", "相关问题2", "相关问题3"]

输出："""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.llm_client.chat(
                messages=messages,
                temperature=0.7,  # 稍高温度以增加多样性
                max_tokens=300
            )

            # 提取JSON数组
            related_queries = self._extract_json_array(response)
            if related_queries and len(related_queries) >= 3:
                logger.info(f"[AnswerGenerator] Generated {len(related_queries)} related queries")
                return related_queries[:max_queries]

            logger.warning(f"[AnswerGenerator] Related queries generation returned invalid result")
            return []

        except Exception as e:
            logger.error(f"[AnswerGenerator] Related queries generation error: {e}")
            return []

    def _extract_json_array(self, text: str) -> List[str]:
        """从LLM响应中提取JSON数组"""
        import json
        import re

        text = text.strip()

        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, list) and all(isinstance(s, str) for s in result):
                return result
        except json.JSONDecodeError as e:
            logger.warning(f"生成器 JSON 数组直接解析失败: {e}")

        # 提取 [ ... ]
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                if isinstance(result, list) and all(isinstance(s, str) for s in result):
                    return result
            except json.JSONDecodeError as e:
                logger.warning(f"生成器 JSON 数组提取失败: {e}")

        logger.error(f"生成器 JSON 数组提取完全失败，原始文本: {text[:200]}")
        return []


# 全局单例
_generator_instance: Optional[AnswerGenerator] = None


def get_generator(enable_validation: bool = False) -> AnswerGenerator:
    """获取生成器单例"""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = AnswerGenerator(enable_validation=enable_validation)
    return _generator_instance
