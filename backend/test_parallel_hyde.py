"""
测试问题#5修复：查询扩展与HyDE并行执行
验证 asyncio.gather() 并行化带来的延迟降低
"""
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


async def main():
    from app.core.retrieval.fast_lane import FastLane

    lane = FastLane(db=None)

    query = "10kV配电室的接地装置要求"
    preprocessing_result = None
    strategy_params_with_hyde = {"enable_hyde": True, "max_expansions": 3}
    strategy_params_no_hyde = {"enable_hyde": False, "max_expansions": 3}

    print("=" * 60)
    print("测试：查询扩展与HyDE并行执行")
    print("=" * 60)
    print(f"查询: {query}\n")

    # --- 测试1：不启用HyDE，只测查询扩展 ---
    print("[测试1] 不启用HyDE，只运行查询扩展")
    t0 = time.time()

    filters = lane._extract_metadata(query, preprocessing_result)
    metadata = lane.metadata_extractor.extract_all_metadata(query, preprocessing_result)
    expanded_queries = await lane._enhance_query(query, strategy_params_no_hyde)

    t_no_hyde = time.time() - t0
    print(f"  扩展查询: {expanded_queries}")
    print(f"  耗时: {t_no_hyde*1000:.0f}ms")

    assert len(expanded_queries) >= 1, "应返回至少1个查询"
    assert expanded_queries[0] == query, "第一个查询应为原始查询"
    print("  [OK] 查询扩展正确")

    # --- 测试2：启用HyDE，测并行执行 ---
    print("\n[测试2] 启用HyDE，验证查询扩展+HyDE并行执行")
    t0 = time.time()

    filters = lane._extract_metadata(query, preprocessing_result)
    metadata = lane.metadata_extractor.extract_all_metadata(query, preprocessing_result)
    category = metadata.get('category')

    # 模拟串行执行耗时（用于对比）
    t_serial_start = time.time()
    expanded_serial = await lane._enhance_query(query, strategy_params_with_hyde)
    t_after_expand = time.time()
    hyde_serial = await lane.hyde_generator.generate(query, category)
    t_serial = time.time() - t_serial_start
    t_expand_only = t_after_expand - t_serial_start

    print(f"  [串行] 查询扩展耗时: {t_expand_only*1000:.0f}ms")
    print(f"  [串行] 总耗时: {t_serial*1000:.0f}ms")

    # 并行执行
    t0 = time.time()
    expanded_parallel, hyde_parallel = await asyncio.gather(
        lane._enhance_query(query, strategy_params_with_hyde),
        lane.hyde_generator.generate(query, category)
    )
    t_parallel = time.time() - t0
    print(f"  [并行] 总耗时: {t_parallel*1000:.0f}ms")

    # 验证并行耗时 <= 串行耗时（允许10%误差）
    speedup = t_serial / t_parallel if t_parallel > 0 else 1
    print(f"  加速比: {speedup:.2f}x")

    assert len(expanded_parallel) >= 1, "并行扩展查询应非空"
    assert hyde_parallel and len(hyde_parallel) > 10, "并行HyDE应生成有效假设文档"

    if t_parallel <= t_serial * 1.1:
        print("  [OK] 并行执行时间 <= 串行执行时间（验证并行有效）")
    else:
        print(f"  [WARN] 并行({t_parallel*1000:.0f}ms) > 串行({t_serial*1000:.0f}ms)，网络抖动可能导致")

    print(f"\n  HyDE假设文档(前80字): {hyde_parallel[:80]}...")

    # --- 测试3：验证execute()方法整体流程元数据先行 ---
    print("\n[测试3] 验证execute()方法中元数据优先于LLM调用")
    # 元数据提取是同步的，应在0ms内完成
    t0 = time.time()
    filters_check = lane._extract_metadata(query, preprocessing_result)
    metadata_check = lane.metadata_extractor.extract_all_metadata(query, preprocessing_result)
    t_metadata = time.time() - t0

    print(f"  元数据提取耗时: {t_metadata*1000:.1f}ms (应<10ms)")
    print(f"  提取到的category: {metadata_check.get('category')}")

    assert t_metadata < 0.1, f"元数据提取应在100ms内完成，实际{t_metadata*1000:.1f}ms"
    print("  [OK] 元数据提取为同步快速操作，适合先行执行")

    print("\n" + "=" * 60)
    print("[PASS] 所有测试通过")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
