"""
测试查询拆解功能 v2 - 验证快慢车道边界
"""
import asyncio
import sys
import time

sys.path.insert(0, "D:/dl/backend")


async def main():
    from app.core.preprocessing.query_rewriter import QueryRewriter
    from app.core.retrieval.router import Router

    rewriter = QueryRewriter()
    router = Router()

    print("=" * 60)
    print("测试1：查询分类边界")
    print("=" * 60)

    test_cases = [
        ("10kV配电室的接地要求", "简单查询", "fast"),
        ("GB 50054 安全距离规定", "单标准查询", "fast"),
        ("10kV配电系统的接地方式和保护配置要求", "同主题多方面(快车道可拆)", "fast"),
        ("10kV配电和35kV配电在接地方式上有何不同", "对比查询(慢车道)", "slow"),
        ("继电保护的选择性与速动性如何平衡", "平衡查询(慢车道)", "slow"),
        ("GB 50054和DL/T 5352在接地要求上的区别", "多标准对比(慢车道)", "slow"),
        ("变压器差动保护与过流保护的整定原则区别", "对比查询(慢车道)", "slow"),
        ("低压配电系统的保护配置和高压配电系统的保护配置分别是什么", "多方面(快车道可拆)", "fast"),
    ]

    all_ok = True
    for query, description, expected_lane in test_cases:
        is_comparison = rewriter.is_comparison_query(query)
        is_multi_aspect = rewriter.is_multi_aspect_query(query)
        decision = router.route(query)

        lane_match = decision.lane == expected_lane
        status = "[OK]" if lane_match else "[FAIL]"

        if not lane_match:
            all_ok = False

        print(f"  {status} {description}")
        print(f"      Query: {query}")
        print(f"      对比类: {is_comparison}, 多方面: {is_multi_aspect}")
        print(f"      路由: {decision.lane} (期望: {expected_lane})")
        print(f"      理由: {decision.reason}")
        print()

    print("=" * 60)
    print("测试2：快车道拆解范围验证")
    print("=" * 60)

    fast_decompose_cases = [
        ("10kV配电系统的接地方式和保护配置要求", True, "多方面-应拆"),
        ("10kV配电和35kV配电在接地方式上有何不同", False, "对比类-不拆"),
        ("继电保护的选择性与速动性如何平衡", False, "平衡类-不拆"),
        ("变压器保护配置", False, "简单查询-不拆"),
    ]

    for query, should_decompose, description in fast_decompose_cases:
        is_comparison = rewriter.is_comparison_query(query)
        is_multi_aspect = rewriter.is_multi_aspect_query(query)

        # 快车道拆解条件：is_multi_aspect且非is_comparison
        will_decompose = is_multi_aspect and not is_comparison

        status = "[OK]" if will_decompose == should_decompose else "[FAIL]"
        if will_decompose != should_decompose:
            all_ok = False

        print(f"  {status} {description}")
        print(f"      Query: {query}")
        print(f"      对比: {is_comparison}, 多方面: {is_multi_aspect}, 将拆解: {will_decompose}")
        print()

    print("=" * 60)
    print("测试3：实际拆解效果")
    print("=" * 60)

    decompose_cases = [
        "10kV配电系统的接地方式和保护配置要求",
        "低压配电系统和高压配电系统的保护配置分别有哪些要求",
    ]

    for query in decompose_cases:
        print(f"\n  原始查询: {query}")
        t0 = time.time()
        sub_queries = await rewriter.decompose(query)
        elapsed = time.time() - t0

        print(f"  拆解结果 ({elapsed*1000:.0f}ms):")
        for i, sq in enumerate(sub_queries, 1):
            print(f"    {i}. {sq}")

        if len(sub_queries) >= 2:
            print(f"  [OK] 成功拆解为 {len(sub_queries)} 个子查询")
        else:
            print(f"  [WARN] 未拆解")

    print()
    print("=" * 60)
    if all_ok:
        print("[PASS] 所有测试通过")
    else:
        print("[FAIL] 部分测试失败")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
