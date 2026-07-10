"""测试查询优化器的 LLM 笼统度评估功能"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from app.core.preprocessing.query_optimizer import QueryOptimizer

# 测试用例（覆盖不同笼统度）
test_cases = [
    # 明确查询（0.0-0.3）
    ("GB 50057-2010第3.2.1条关于接地电阻的规定", 0.0, 0.3),
    ("10kV架空线路与建筑物的最小水平距离是多少", 0.1, 0.4),

    # 轻度笼统（0.3-0.6）
    ("10kV配电装置与建筑物距离", 0.3, 0.6),
    ("继电保护整定原则", 0.3, 0.6),

    # 中度笼统（0.6-0.8）
    ("隔离开关技术要求", 0.6, 0.8),
    ("配电装置安装规范", 0.6, 0.8),

    # 严重笼统（0.8-1.0）
    ("配电规定", 0.8, 1.0),
    ("继保要求", 0.8, 1.0),
]

async def main():
    optimizer = QueryOptimizer()

    print("=" * 80)
    print("查询优化器 - LLM 笼统度评估测试")
    print("=" * 80)
    print()

    results = []

    for query, expected_min, expected_max in test_cases:
        print(f"查询: {query}")
        print(f"预期范围: {expected_min:.1f} - {expected_max:.1f}")

        # 评估笼统度
        score = await optimizer.assess_vagueness(query)

        # 判断是否在预期范围
        in_range = expected_min <= score <= expected_max
        status = "PASS" if in_range else "FAIL"

        print(f"实际得分: {score:.2f} [{status}]")

        # 决策策略
        if score > 0.7:
            strategy = "clarify_required (必须澄清)"
        elif score > 0.5:
            strategy = "clarify_optional (建议澄清)"
        elif score > 0.3:
            strategy = "suggest (智能补全)"
        else:
            strategy = "none (直接检索)"

        print(f"策略: {strategy}")
        print("-" * 80)

        results.append({
            "query": query,
            "expected": (expected_min, expected_max),
            "actual": score,
            "in_range": in_range,
            "strategy": strategy
        })

    # 统计
    print()
    print("=" * 80)
    print("测试总结")
    print("=" * 80)

    total = len(results)
    passed = sum(1 for r in results if r["in_range"])

    print(f"总用例数: {total}")
    print(f"通过数: {passed}")
    print(f"准确率: {passed/total*100:.1f}%")
    print()

    # 详细结果
    print("详细结果:")
    for i, r in enumerate(results, 1):
        status = "PASS" if r["in_range"] else "FAIL"
        print(f"{i}. [{status}] {r['query']}")
        print(f"   预期: {r['expected'][0]:.1f}-{r['expected'][1]:.1f}, 实际: {r['actual']:.2f}")
        print(f"   策略: {r['strategy']}")

    print()
    print("测试完成！")

if __name__ == "__main__":
    asyncio.run(main())
