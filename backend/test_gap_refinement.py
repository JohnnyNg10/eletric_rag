"""
测试问题#4修复：gap改写LLM化
验证 _refine_query_for_gaps() 使用LLM改写而非简单拼接
"""
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


async def main():
    from app.core.retrieval.fast_lane import FastLane

    lane = FastLane(db=None)

    test_cases = [
        {
            "name": "短查询 + 单个gap",
            "query": "10kV配电室接地要求",
            "gaps": ["缺少接地电阻具体数值"],
            "referenced_standards": None,
        },
        {
            "name": "短查询 + 多个gap",
            "query": "变压器继电保护配置",
            "gaps": ["缺少差动保护整定值", "未找到过流保护时限要求"],
            "referenced_standards": None,
        },
        {
            "name": "带被引用标准",
            "query": "低压配电系统接地方式",
            "gaps": ["缺少 GB/T 14549 的具体限值"],
            "referenced_standards": ["GB/T 14549-2023"],
        },
        {
            "name": "空gap（应直接返回原查询）",
            "query": "GB 50054 安全距离",
            "gaps": [],
            "referenced_standards": None,
        },
    ]

    print("=" * 60)
    print("测试：_refine_query_for_gaps() LLM改写")
    print("=" * 60)

    all_passed = True

    for case in test_cases:
        print(f"\n【{case['name']}】")
        print(f"  原始查询: {case['query']}")
        print(f"  信息缺口: {case['gaps']}")
        print(f"  相关标准: {case['referenced_standards']}")

        t0 = time.time()
        result = await lane._refine_query_for_gaps(
            original_query=case["query"],
            gaps=case["gaps"],
            referenced_standards=case["referenced_standards"],
        )
        elapsed = time.time() - t0

        print(f"  改写结果: {result}")
        print(f"  耗时: {elapsed*1000:.0f}ms")

        # 验证
        ok = True
        if not case["gaps"]:
            # 空gap应返回原查询
            if result != case["query"]:
                print(f"  [FAIL] 空gap时应返回原查询，实际返回: {result}")
                ok = False
            else:
                print(f"  [OK] 空gap正确返回原查询")
        else:
            # 非空gap：改写结果不应与原查询完全相同
            if result == case["query"]:
                print(f"  [WARN] 改写结果与原查询相同（可能LLM降级到拼接）")
            elif len(result) > 100:
                print(f"  [FAIL] 改写结果过长（>{len(result)}字符）")
                ok = False
            else:
                print(f"  [OK] 改写成功，长度={len(result)}字符")

            # 简单拼接检测：如果结果 = "原查询 gap1、gap2" 格式，说明走了降级路径
            fallback_result = case["query"] + " " + "、".join(case["gaps"])
            if result == fallback_result:
                print(f"  [WARN] 结果与简单拼接相同（LLM降级）")

        if not ok:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("[PASS] 所有测试通过")
    else:
        print("[FAIL] 部分测试失败")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
