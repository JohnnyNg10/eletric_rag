"""
测试慢车道路由判断

目标：验证 LLM 能够正确判断以下查询应该走慢车道：
1. 对比查询（比较多个标准/参数）
2. 多跳推理查询（需要关联多个标准）
3. 复杂关联查询（涉及多个维度的交叉分析）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.preprocessing import Preprocessor, PreprocessingInput


async def test_slow_lane_queries():
    """测试应该路由到慢车道的查询"""
    print("=" * 70)
    print("慢车道路由判断测试")
    print("=" * 70)

    preprocessor = Preprocessor()

    test_cases = [
        {
            "name": "对比查询（电压等级对比）",
            "query": "10kV和35kV配电装置的安全距离有什么区别",
            "expected_lane": "slow",
            "reason": "包含对比关键词'区别'，需要检索两个电压等级的标准并对比"
        },
        {
            "name": "对比查询（设备类型对比）",
            "query": "GIS和常规开关柜在接地方面的差异",
            "expected_lane": "slow",
            "reason": "包含对比关键词'差异'，需要对比两种设备"
        },
        {
            "name": "多标准关联查询",
            "query": "继电保护装置需要同时满足哪些国家标准和行业标准",
            "expected_lane": "slow",
            "reason": "包含'同时满足''哪些标准'，需要多跳检索多个标准"
        },
        {
            "name": "多跳推理查询",
            "query": "35kV变电站的防雷接地引用了哪些其他标准的条款",
            "expected_lane": "slow",
            "reason": "包含'引用了哪些'，需要先找主标准，再找引用关系"
        },
        {
            "name": "交叉关联查询",
            "query": "高海拔地区的10kV配电装置需要满足哪些特殊要求，涉及哪些相关标准",
            "expected_lane": "slow",
            "reason": "交叉维度（高海拔+电压等级）且需要关联多个标准"
        },
        {
            "name": "对比分析查询",
            "query": "比较直接接地和消弧线圈接地方式的适用场景",
            "expected_lane": "slow",
            "reason": "包含'比较'关键词，需要对比两种接地方式"
        },
        {
            "name": "范围枚举查询",
            "query": "电缆敷设有哪些方式，分别对应哪些标准规范",
            "expected_lane": "slow",
            "reason": "包含'有哪些''分别对应'，需要枚举并关联"
        },
        {
            "name": "复杂条件查询",
            "query": "当110kV变电站采用GIS设备且位于地下时，接地电阻和防雷措施有什么特殊要求",
            "expected_lane": "slow",
            "reason": "多重条件（电压+设备+环境），需要综合多个标准"
        }
    ]

    results = []
    for i, case in enumerate(test_cases, 1):
        print(f"\n[测试 {i}/{len(test_cases)}] {case['name']}")
        print(f"查询: {case['query']}")
        print(f"预期路由: {case['expected_lane']}")
        print(f"理由: {case['reason']}")

        try:
            input_data = PreprocessingInput(
                query=case['query'],
                user_context={'user_id': 1},
                enable_optimization=True
            )

            output = await preprocessor.preprocess(input_data)

            print(f"\n结果:")
            print(f"  笼统度: {output.vagueness_score:.2f}")
            print(f"  策略: {output.strategy}")
            print(f"  路由建议: {output.lane_suggestion} (置信度: {output.lane_confidence:.2f})")
            print(f"  路由理由: {output.lane_reason}")

            # 判断是否符合预期
            is_correct = output.lane_suggestion == case['expected_lane']
            status = "[PASS]" if is_correct else "[FAIL]"

            print(f"\n  {status}")

            if not is_correct:
                print(f"  预期: {case['expected_lane']}, 实际: {output.lane_suggestion}")

            results.append({
                'name': case['name'],
                'query': case['query'],
                'expected': case['expected_lane'],
                'actual': output.lane_suggestion,
                'confidence': output.lane_confidence,
                'correct': is_correct
            })

        except Exception as e:
            print(f"  [ERROR] 错误: {e}")
            results.append({
                'name': case['name'],
                'query': case['query'],
                'expected': case['expected_lane'],
                'actual': 'error',
                'confidence': 0.0,
                'correct': False
            })

    # 统计结果
    print("\n" + "=" * 70)
    print("测试统计")
    print("=" * 70)

    total = len(results)
    correct = sum(1 for r in results if r['correct'])
    accuracy = (correct / total * 100) if total > 0 else 0

    print(f"\n总测试数: {total}")
    print(f"通过数: {correct}")
    print(f"准确率: {accuracy:.1f}%")

    # 详细结果表
    print("\n详细结果:")
    print("-" * 70)
    for r in results:
        status_symbol = "[OK]" if r['correct'] else "[NO]"
        print(f"{status_symbol} {r['name']}")
        print(f"   预期: {r['expected']}, 实际: {r['actual']}, 置信度: {r['confidence']:.2f}")

    # 失败案例分析
    failed = [r for r in results if not r['correct']]
    if failed:
        print("\n" + "=" * 70)
        print("失败案例分析")
        print("=" * 70)
        for r in failed:
            print(f"\n查询: {r['query']}")
            print(f"  预期路由: {r['expected']}")
            print(f"  实际路由: {r['actual']}")
            print(f"  可能原因: LLM 可能认为该查询虽有对比/关联关键词，但仍可单路检索完成")

    print("\n" + "=" * 70)


async def test_mixed_queries():
    """混合测试：快车道 vs 慢车道边界案例"""
    print("\n" + "=" * 70)
    print("快慢车道边界测试")
    print("=" * 70)

    preprocessor = Preprocessor()

    # 边界案例：虽有某些关键词，但应该是快车道
    boundary_cases = [
        {
            "query": "GB 50057-2010 和 DL/T 621-1997 关于接地电阻的要求",
            "expected": "fast",
            "reason": "虽提到两个标准，但只是简单并列查询，非对比"
        },
        {
            "query": "10kV配电装置接地电阻应满足哪些要求",
            "expected": "fast",
            "reason": "'哪些要求'是单一标准内的枚举，非多标准关联"
        },
        {
            "query": "配电装置安全距离的相关标准有哪些",
            "expected": "slow",
            "reason": "'有哪些标准'需要枚举多个标准"
        }
    ]

    print("\n测试边界案例（区分快慢车道的能力）:\n")

    for i, case in enumerate(boundary_cases, 1):
        print(f"[边界测试 {i}] {case['query']}")
        print(f"  预期: {case['expected']} ({case['reason']})")

        try:
            input_data = PreprocessingInput(
                query=case['query'],
                user_context={'user_id': 1},
                enable_optimization=True
            )

            output = await preprocessor.preprocess(input_data)

            is_correct = output.lane_suggestion == case['expected']
            status = "[OK]" if is_correct else "[NO]"

            print(f"  实际: {output.lane_suggestion} (置信度: {output.lane_confidence:.2f}) {status}")
            print(f"  LLM理由: {output.lane_reason}")
            print()

        except Exception as e:
            print(f"  [ERROR] 错误: {e}\n")


async def main():
    """运行所有测试"""
    print("\n开始测试慢车道路由判断能力...\n")

    # 测试1: 明确应该走慢车道的查询
    await test_slow_lane_queries()

    # 测试2: 边界案例
    await test_mixed_queries()

    print("\n测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
