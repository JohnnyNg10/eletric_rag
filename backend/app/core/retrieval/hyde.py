"""
HyDE (Hypothetical Document Embeddings) 生成器

职责：
- 基于用户查询生成假设文档
- 支持类别特定的 HyDE（包含领域特征）
"""
import logging
from typing import Optional
from app.core.generation.llm_client import get_llm_client

logger = logging.getLogger(__name__)


class HyDEGenerator:
    """HyDE 生成器"""

    def __init__(self):
        self.llm_client = get_llm_client()

    async def generate(
        self,
        query: str,
        category: Optional[str] = None
    ) -> str:
        """
        生成假设文档

        Args:
            query: 用户查询
            category: 专业类别（可选，如"配电"/"变电"/"继保"）

        Returns:
            str: 假设文档文本
        """
        try:
            # 构建 prompt
            if category:
                prompt = self._build_category_specific_prompt(query, category)
            else:
                prompt = self._build_generic_prompt(query)

            # LLM 生成
            messages = [{"role": "user", "content": prompt}]
            hypothetical_doc = self.llm_client.chat(
                messages=messages,
                temperature=0.3,  # 适度创造性
                max_tokens=300
            )

            logger.info(f"[HyDE] Generated doc for query='{query[:50]}', category={category}")
            logger.debug(f"[HyDE] Hypothetical doc: {hypothetical_doc[:100]}...")

            return hypothetical_doc.strip()

        except Exception as e:
            logger.error(f"[HyDE] Generation failed: {e}", exc_info=True)
            # 降级：返回原查询
            return query

    def _build_category_specific_prompt(self, query: str, category: str) -> str:
        """
        构建类别特定的 HyDE prompt

        Args:
            query: 用户查询
            category: 专业类别

        Returns:
            str: prompt 文本
        """
        # 类别描述映射
        category_descriptions = {
            '配电': '配电系统、配电装置、配电室、配电柜、低压开关柜等领域',
            '变电': '变电站、变压器、变电设备、变电所等领域',
            '继保': '继电保护、保护装置、保护系统、整定计算等领域',
            '输电': '输电线路、架空线、电缆、输电设备等领域',
            '安全': '安全距离、安全措施、防护、接地、防雷等领域',
        }

        category_desc = category_descriptions.get(category, f'{category}领域')

        prompt = f"""你是电力专业标准文档专家。基于用户查询，生成一段假设的{category_desc}标准文档内容（100-150字）。

要求：
1. 使用该领域的专业术语和规范表达
2. 模仿国家标准的条款描述风格（如"应符合...""不应小于..."）
3. 包含相关的技术参数、要求或规定
4. 保持与查询主题的强相关性

用户查询：{query}

生成的假设文档内容："""

        return prompt

    def _build_generic_prompt(self, query: str) -> str:
        """
        构建通用 HyDE prompt（无类别信息时使用）

        Args:
            query: 用户查询

        Returns:
            str: prompt 文本
        """
        prompt = f"""你是电力专业标准文档专家。基于用户查询，生成一段假设的标准文档内容（100-150字）。

要求：
1. 使用电力专业术语和规范表达
2. 模仿国家标准的条款描述风格
3. 包含相关的技术参数或要求
4. 保持与查询主题的强相关性

用户查询：{query}

生成的假设文档内容："""

        return prompt


# 全局单例
_hyde_generator = None


def get_hyde_generator() -> HyDEGenerator:
    """获取 HyDE 生成器单例"""
    global _hyde_generator
    if _hyde_generator is None:
        _hyde_generator = HyDEGenerator()
    return _hyde_generator
