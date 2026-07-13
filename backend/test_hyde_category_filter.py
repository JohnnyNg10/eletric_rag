"""
测试 HyDE + 类别特定过滤

目标：验证类别特定 HyDE 是否能减少跨类别误召回
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.core.retrieval.fast_lane import FastLane


async def test_hyde_category_filter():
    """
    测试场景：
    1. 查询"继电保护整定"（继保类别）
    2. 对比启用/不启用 HyDE 的召回结果
    3. 观察是否减少了配电/变电类别的误召回
    """

    test_queries = [
        {
            "query": "继电保护整定计算",
            "expected_category": "继保",
            "description": "典型继保查询，应该召回继保类文档"
        },
        {
            "query": "配电室安全距离要求",
            "expected_category": "配电",
            "description": "典型配电查询，应该召回配电类文档"
        },
        {
            "query": "变压器接地电阻",
            "expected_category": "变电",
            "description": "典型变电查询，应该召回变电类文档"
        }
    ]

    db = SessionLocal()
    fast_lane = FastLane(db=db)

    for test_case in test_queries:
        query = test_case["query"]
        expected_category = test_case["expected_category"]

        print(f"\n{'='*80}")
        print(f"测试查询: {query}")
        print(f"预期类别: {expected_category}")
        print(f"说明: {test_case['description']}")
        print(f"{'='*80}")

        # 测试1: 不启用 HyDE
        print(f"\n【测试1】不启用 HyDE")
        print("-" * 80)
        result_without_hyde = await fast_lane.execute(
            query=query,
            user_context={},
            strategy_params={"enable_hyde": False, "enable_retry": False}
        )

        print(f"召回数量: {len(result_without_hyde.retrieved_chunks)}")
        print(f"\nTop 5 召回结果（类别分布）:")
        category_count_without = {}
        for i, chunk in enumerate(result_without_hyde.retrieved_chunks[:5]):
            category = chunk.get('category', 'unknown')
            category_count_without[category] = category_count_without.get(category, 0) + 1
            print(f"  [{i+1}] {chunk.get('standard_no', 'N/A'):20s} | "
                  f"类别: {category:6s} | "
                  f"评分: {chunk.get('score', 0):.3f} | "
                  f"{chunk.get('content', '')[:50]}...")

        print(f"\n类别统计（Top 5）: {category_count_without}")
        correct_ratio_without = category_count_without.get(expected_category, 0) / 5
        print(f"正确类别占比: {correct_ratio_without:.1%}")

        # 测试2: 启用 HyDE
        print(f"\n【测试2】启用 HyDE")
        print("-" * 80)
        result_with_hyde = await fast_lane.execute(
            query=query,
            user_context={},
            strategy_params={"enable_hyde": True, "enable_retry": False}
        )

        if result_with_hyde.hyde_query:
            print(f"HyDE 生成的假设文档:")
            print(f"  {result_with_hyde.hyde_query[:150]}...")

        print(f"\n召回数量: {len(result_with_hyde.retrieved_chunks)}")
        print(f"\nTop 5 召回结果（类别分布）:")
        category_count_with = {}
        for i, chunk in enumerate(result_with_hyde.retrieved_chunks[:5]):
            category = chunk.get('category', 'unknown')
            category_count_with[category] = category_count_with.get(category, 0) + 1
            print(f"  [{i+1}] {chunk.get('standard_no', 'N/A'):20s} | "
                  f"类别: {category:6s} | "
                  f"评分: {chunk.get('score', 0):.3f} | "
                  f"{chunk.get('content', '')[:50]}...")

        print(f"\n类别统计（Top 5）: {category_count_with}")
        correct_ratio_with = category_count_with.get(expected_category, 0) / 5
        print(f"正确类别占比: {correct_ratio_with:.1%}")

        # 对比
        print(f"\n【对比分析】")
        print(f"  不启用 HyDE 正确率: {correct_ratio_without:.1%}")
        print(f"  启用 HyDE 正确率:   {correct_ratio_with:.1%}")
        improvement = correct_ratio_with - correct_ratio_without
        if improvement > 0:
            print(f"  ✅ HyDE 提升了 {improvement:.1%}")
        elif improvement < 0:
            print(f"  ❌ HyDE 降低了 {abs(improvement):.1%}")
        else:
            print(f"  ➖ 无明显变化")

    db.close()
    print(f"\n{'='*80}")
    print("测试完成")


if __name__ == "__main__":
    asyncio.run(test_hyde_category_filter())
