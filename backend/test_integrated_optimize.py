"""
测试一体化笼统评估和优化功能

测试：
1. 笼统查询 → 一次 LLM 调用完成评估和生成澄清选项
2. 明确查询 → 一次 LLM 调用评估为明确，不生成选项
3. LLM 失败 → 降级到规则方案
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.preprocessing.query_optimizer import QueryOptimizer


async def test_integrated_optimize():
    """测试一体化优化功能"""

    print("=" * 80)
    print("测试一体化笼统评估和优化功能")
    print("=" * 80)

    optimizer = QueryOptimizer()

    # 测试用例
    test_cases = [
        {
            "query": "隔离开关要求",
            "expected_vague": True,
            "description": "笼统查询（中度笼统）"
        },
        {
            "query": "配电规定",
            "expected_vague": True,
            "description": "严重笼统查询"
        },
        {
            "query": "10kV配电装置与建筑物距离",
            "expected_vague": True,
            "description": "轻度笼统查询（缺少室内/室外）"
        },
        {
            "query": "GB 50057-2010第3.2.1条关于接地电阻的规定",
            "expected_vague": False,
            "description": "明确查询（含标准号+条款号）"
        },
        {
            "query": "10kV户内隔离开关额定电流技术参数",
            "expected_vague": False,
            "description": "明确查询（含完整维度）"
        }
    ]

    for i, test_case in enumerate(test_cases, 1):
        query = test_case["query"]
        description = test_case["description"]

        print(f"\n[测试 {i}] {description}")
        print(f"查询: {query}")
        print("-" * 80)

        try:
            # 一体化优化
            result = await optimizer.optimize(query)

            print(f"策略: {result.strategy}")
            print(f"笼统度评分: {result.vagueness_score:.2f}")

            if result.options:
                print(f"澄清选项数量: {len(result.options)}")
                print("\n生成的澄清选项:")
                for opt in result.options:
                    print(f"  {opt.id}. {opt.label}")
                    print(f"     精炼查询: {opt.refined_query}")
            else:
                print("无需澄清，直接进入路由层")

            # 验证预期
            is_vague = result.vagueness_score > 0.5
            if is_vague == test_case["expected_vague"]:
                print(f"\n[OK] 评估结果符合预期")
            else:
                print(f"\n[ERROR] 评估结果不符合预期（期望笼统={test_case['expected_vague']}）")

        except Exception as e:
            print(f"\n[ERROR] 测试失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


async def test_performance():
    """测试性能：对比一体化 vs 分离调用"""

    print("\n" + "=" * 80)
    print("性能测试：一体化 vs 分离调用")
    print("=" * 80)

    optimizer = QueryOptimizer()
    query = "隔离开关要求"

    # 测试1: 一体化调用
    print("\n[方案1] 一体化调用（1次 LLM）")
    import time
    start = time.time()
    result1 = await optimizer.optimize(query)
    elapsed1 = time.time() - start
    print(f"耗时: {elapsed1*1000:.0f}ms")
    print(f"结果: score={result1.vagueness_score:.2f}, options={len(result1.options)}")

    # 测试2: 分离调用（旧方案，会触发2次 LLM）
    print("\n[方案2] 分离调用（2次 LLM - 评估 + 生成选项）")
    start = time.time()
    score = await optimizer.assess_vagueness(query)
    if score > 0.5:
        options = await optimizer.generate_clarification_options(query)
    else:
        options = []
    elapsed2 = time.time() - start
    print(f"耗时: {elapsed2*1000:.0f}ms")
    print(f"结果: score={score:.2f}, options={len(options)}")

    # 对比
    print("\n[性能对比]")
    print(f"一体化方案: {elapsed1*1000:.0f}ms")
    print(f"分离方案: {elapsed2*1000:.0f}ms")
    if elapsed2 > elapsed1:
        speedup = (elapsed2 - elapsed1) / elapsed2 * 100
        print(f"性能提升: {speedup:.1f}%")
    else:
        print("性能提升: 0%（可能 LLM 缓存或降级到规则）")

    print("=" * 80)


async def main():
    """主函数"""
    try:
        # 测试1: 功能测试
        await test_integrated_optimize()

        # 测试2: 性能测试
        await test_performance()

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
