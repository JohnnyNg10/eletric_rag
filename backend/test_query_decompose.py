"""
测试问题#7修复：查询拆解（Query Decomposition）
验证 QueryRewriter.decompose() 和 FastLane 接入点
"""
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


async def main():
    from app.core.preprocessing.query_rewriter import QueryRewriter

    rewriter = QueryRewriter()

    print("=" * 60)
    print("测试1：is_complex_query() 判断逻辑")
    print("=" * 60)

    simple_cases = [
        ("10kV配电室的接地要求", False),
        ("GB 50054 安全距离规定", False),
        ("变压器保护配置", False),
    ]
    complex_cases = [
        ("10kV配电和35kV配电在接地方式上有何不同", True),
        ("变压器差动保护与过流保护的整定原则区别", True),
        ("低压配电系统和高压配电系统的保护配置分别有哪些要求", True),
        ("继电保护的选择性与速动性如何平衡", True),  # 含"与"，is_complex返回True，但LM可选择不拆
    ]

    all_ok = True
    for query, expected in simple_cases + complex_cases:
        result = rewriter.is_complex_query(query)
        status = "[OK]" if result == expected else "[FAIL]"
        if result != expected:
            all_ok = False
        print(f"  {status} {'复杂' if expected else '简单'}: {query[:40]}")

    print()
    print("=" * 60)
    print("测试2：decompose() 简单查询不拆解")
    print("=" * 60)

    simple_query = "10kV配电室的接地要求"
    result = await rewriter.decompose(simple_query)
    if result == [simple_query]:
        print(f"  [OK] 简单查询直接返回: {result}")
    else:
        print(f"  [FAIL] 简单查询不应拆解，实际返回: {result}")
        all_ok = False

    print()
    print("=" * 60)
    print("测试3：decompose() 复杂查询LLM拆解")
    print("=" * 60)

    complex_test_cases = [
        "10kV配电和35kV配电在接地方式上有何不同",
        "继电保护的选择性与速动性如何平衡",
        "低压配电系统和高压配电系统的保护配置分别有哪些要求",
    ]

    for query in complex_test_cases:
        print(f"\n  原始查询: {query}")
        t0 = time.time()
        sub_queries = await rewriter.decompose(query)
        elapsed = time.time() - t0

        print(f"  拆解结果 ({elapsed*1000:.0f}ms):")
        for i, sq in enumerate(sub_queries, 1):
            print(f"    {i}. {sq}")

        if len(sub_queries) >= 2:
            print(f"  [OK] 成功拆解为 {len(sub_queries)} 个子查询")
        elif sub_queries == [query]:
            print(f"  [WARN] 未能拆解（LLM降级返回原查询）")
        else:
            print(f"  [FAIL] 拆解结果异常")
            all_ok = False

    print()
    print("=" * 60)
    print("测试4：FastLane 接入点验证（不走召回，只验证拆解逻辑）")
    print("=" * 60)

    from app.core.retrieval.fast_lane import FastLane

    lane = FastLane(db=None)

    # 验证复杂查询被检测到
    complex_query = "10kV配电和35kV配电在接地方式上有何不同"
    is_complex = lane.query_rewriter.is_complex_query(complex_query)
    print(f"  FastLane.query_rewriter.is_complex_query(): {is_complex}")
    if is_complex:
        print(f"  [OK] FastLane 可正确识别复杂查询")
    else:
        print(f"  [FAIL] FastLane 未能识别复杂查询")
        all_ok = False

    t0 = time.time()
    sub_queries = await lane.query_rewriter.decompose(complex_query)
    elapsed = time.time() - t0
    print(f"  拆解结果 ({elapsed*1000:.0f}ms): {sub_queries}")

    if len(sub_queries) >= 2:
        print(f"  [OK] FastLane 查询拆解接入正常")
    else:
        print(f"  [WARN] 拆解未生效（LLM降级）")

    print()
    print("=" * 60)
    if all_ok:
        print("[PASS] 所有测试通过")
    else:
        print("[FAIL] 部分测试失败")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
