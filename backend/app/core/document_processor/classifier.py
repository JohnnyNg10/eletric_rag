"""
文档分类器

支持：
- 专业分类（多标签）
- 电压等级识别
- 文档类型判断
"""
from typing import List, Dict, Optional
import re
import logging

logger = logging.getLogger(__name__)


class DocumentClassifier:
    """文档分类器"""

    def __init__(self):
        # 专业分类关键词（规则为主，模型为辅）
        self.category_keywords = {
            "电气安全": ["插头", "插座", "电气安全", "触电", "绝缘", "接地", "漏电"],
            "插头插座": ["插头", "插座", "连接器", "额定电流", "额定电压"],
            "电力设备": ["变压器", "开关", "断路器", "电力设备", "配电"],
            "电缆": ["电缆", "导线", "线缆", "电线"],
            "防护": ["防护", "防水", "防尘", "IP等级"],
            "测试": ["试验", "测试", "检验", "检测方法"],
        }

        # 电压等级关键词
        self.voltage_keywords = {
            "250V": ["250V", "250伏"],
            "380V": ["380V", "380伏"],
            "10kV": ["10kV", "10千伏"],
            "35kV": ["35kV", "35千伏"],
            "110kV": ["110kV", "110千伏"],
            "220kV": ["220kV", "220千伏"],
        }

    def classify(self, content: str, metadata: Dict, use_llm: bool = False) -> Dict:
        """
        文档分类

        Args:
            content: 文档内容
            metadata: 已有元数据
            use_llm: 是否使用 LLM 分类（更准确但成本高）

        Returns:
            分类结果 {
                "category": "电气安全",
                "sub_categories": ["插头插座"],
                "voltage_level": "250V",
                "doc_type": "standard",
                "knowledge_type": "规范"
            }
        """
        result = {}

        # 专业分类
        if use_llm:
            categories = self._classify_with_llm(content)
        else:
            categories = self._classify_category(content)

        result["category"] = categories[0] if categories else "未分类"
        result["sub_categories"] = categories[1:] if len(categories) > 1 else []

        # 电压等级识别（规则即可）
        result["voltage_level"] = self._detect_voltage_level(content)

        # 文档类型判断
        result["doc_type"] = self._detect_doc_type(content, metadata)

        # 知识类型
        result["knowledge_type"] = self._detect_knowledge_type(content, metadata)

        return result

    def _classify_category(self, content: str) -> List[str]:
        """
        专业分类（基于关键词匹配）

        返回多个可能的分类（按置信度排序）
        """
        category_scores = {}

        for category, keywords in self.category_keywords.items():
            score = 0
            for keyword in keywords:
                # 统计关键词出现次数
                count = len(re.findall(keyword, content, re.IGNORECASE))
                score += count

            if score > 0:
                category_scores[category] = score

        # 按分数排序
        sorted_categories = sorted(
            category_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # 返回前3个分类
        return [cat for cat, score in sorted_categories[:3]]

    def _detect_voltage_level(self, content: str) -> Optional[str]:
        """
        检测电压等级

        优先级：出现频率最高的电压等级
        """
        voltage_counts = {}

        for voltage, keywords in self.voltage_keywords.items():
            count = 0
            for keyword in keywords:
                count += len(re.findall(keyword, content, re.IGNORECASE))

            if count > 0:
                voltage_counts[voltage] = count

        if not voltage_counts:
            return None

        # 返回出现最多的电压等级
        return max(voltage_counts.items(), key=lambda x: x[1])[0]

    def _detect_doc_type(self, content: str, metadata: Dict) -> str:
        """
        检测文档类型

        标准/教材/手册/规范
        """
        # 从元数据判断
        if "standard_no" in metadata and metadata["standard_no"]:
            return "standard"

        # 从文件名判断
        if "ISBN" in content or "教材" in content[:500]:
            return "textbook"

        if "手册" in content[:500] or "指南" in content[:500]:
            return "manual"

        # 默认标准
        return "standard"

    def _detect_knowledge_type(self, content: str, metadata: Dict) -> str:
        """
        检测知识类型

        规范/技术/操作/理论
        """
        # 检测规范性内容
        if any(word in content[:1000] for word in ["应", "应当", "必须", "不得", "禁止"]):
            return "规范"

        # 检测技术性内容
        if any(word in content[:1000] for word in ["技术要求", "技术参数", "性能指标"]):
            return "技术"

        # 检测操作性内容
        if any(word in content[:1000] for word in ["操作", "步骤", "方法", "程序"]):
            return "操作"

        # 默认理论
        return "理论"

    def _classify_with_llm(self, content: str) -> List[str]:
        """
        使用 LLM 进行专业分类（多标签）

        使用豆包Pro few-shot 分类
        """
        try:
            from app.core.generation.llm_client import llm_client

            # 构建分类 prompt（few-shot）
            prompt = f"""你是一个电力标准文档分类专家。请根据文档内容判断其所属的专业分类（可多选）。

可选分类：
1. 电气安全
2. 插头插座
3. 电力设备
4. 电缆
5. 防护
6. 测试

文档内容（前2000字）：
{content[:2000]}

请直接输出分类名称，多个分类用逗号分隔。例如："电气安全,插头插座"
"""

            response = llm_client.chat(prompt, temperature=0.1)

            # 解析分类结果
            categories_str = response.strip()
            categories = [c.strip() for c in categories_str.split(",") if c.strip()]

            # 验证分类是否在可选列表中
            valid_categories = [
                c for c in categories
                if c in self.category_keywords.keys()
            ]

            logger.info(f"LLM classified: {valid_categories}")
            return valid_categories if valid_categories else self._classify_category(content)

        except Exception as e:
            logger.warning(f"LLM classification failed: {e}, falling back to rule-based")
            return self._classify_category(content)


# 全局实例
document_classifier = DocumentClassifier()
