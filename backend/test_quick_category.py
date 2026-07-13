"""
快速测试：LLM 类别识别功能

只测试类别识别，不涉及召回
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.preprocessing.query_optimizer import QueryOptimizer


async def test_llm_category_recognition():
    """测试 LLM 类别识别"""

    optimizer = QueryOptimizer()

    test_cases = [
        {
            "query": "整定计算原则",
            "expected": "继保",
            "reason": "无'继电保护'关键词，测试 LLM 隐含识别"
        },
        {
            "query": "继电保护配置要求",
            "expected": "继保",
            "reason": "含'继电保护'显式关键词"
        },
        {
            "query": "配电室安全距离",
            "expected": "配电",
            "reason": "配电类别"
        },
        {
            "query": "变压器接地要求",
            "expected": "变电",
            "reason": "变电类别"
        },
        {
            "query": "功率因数要求",
            "expected": "通用",
            "reason": "跨类别，应识别为通用"
        }
    ]

    print("="*80)
    print("LLM 类别识别测试")
    print("="*80)

    correct_count = 0
    total_count = len(test_cases)

    for i, case in enumerate(test_cases, 1):
        query = case["query"]
        expected = case["expected"]

        print(f"\n[{i}/{total_count}] 查询: {query}")
        print(f"预期类别: {expected}")
        print(f"说明: {case['reason']}")

        try:
            result = await optimizer.optimize(query)

            category = result.category if hasattr(result, 'category') else None
            confidence = result.category_confidence if hasattr(result, 'category_confidence') else 0.0

            is_correct = (category == expected)
            if is_correct:
                correct_count += 1

            status = "[OK]" if is_correct else "[WRONG]"
            print(f"识别结果: {category} (置信度: {confidence:.2f}) {status}")

            # 显示其他识别信息
            print(f"笼统度: {result.vagueness_score:.2f}")
            print(f"路由建议: {result.lane_suggestion} (置信度: {result.lane_confidence:.2f})")

        except Exception as e:
            print(f"[ERROR]: {e}")

    print("\n" + "="*80)
    print(f"总体准确率: {correct_count}/{total_count} ({correct_count/total_count:.1%})")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_llm_category_recognition())
