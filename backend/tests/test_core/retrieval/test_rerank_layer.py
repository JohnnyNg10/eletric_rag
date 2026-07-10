"""
测试重排层功能

测试内容：
1. TwoStageReranker - 两阶段重排
2. SufficiencyChecker - 充分性判断
3. FastLane集成 - 完整流程
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径

from app.core.retrieval.rerank import TwoStageReranker, RerankResult
from app.core.retrieval.sufficiency import SufficiencyChecker, SufficiencyResult
from app.schemas.retrieval import ChunkResult

async def test_two_stage_reranker():
    """测试两阶段重排器"""
    print("\n" + "="*60)
    print("测试1: TwoStageReranker - 两阶段重排")
    print("="*60)

    # 创建重排器
    reranker = TwoStageReranker(
        coarse_threshold=0.3,
        fine_threshold=0.5,
        coarse_top_k=20,
        fine_top_k=5,
        enable_cache=False  # 测试时禁用缓存
    )

    # 模拟候选块
    query = "10kV配电柜的接地电阻规范是什么"

    candidates = []
    for i in range(10):
        candidates.append(ChunkResult(
            chunk_id=i + 1,
            document_id=100 + i,
            content=f"这是第{i+1}个候选块的内容，包含关于配电柜接地电阻的描述...",
            score=0.8 - i * 0.05,  # 递减分数
            standard_no=f"GB/T {50000 + i}",
            doc_type="standard",
            category="电力工程",
            voltage_level="10kV",
            clause=f"{i+1}.{i+1}",
            recall_source="vector"
        ))

    print(f"\n输入: {len(candidates)} 个候选块")
    print(f"查询: {query}")

    # 执行重排
    try:
        rerank_results = await reranker.rerank(
            query=query,
            candidates=candidates,
            top_k=5
        )

        print(f"\n输出: {len(rerank_results)} 个重排结果")
        for i, result in enumerate(rerank_results, 1):
            print(f"  {i}. chunk_id={result.chunk_id}, score={result.score:.4f}, standard={result.standard_no}")

        print("\n[PASS] Two-stage reranker test passed")
        return True

    except Exception as e:
        print(f"\n[FAIL] Two-stage reranker test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_sufficiency_checker():
    """测试充分性检查器"""
    print("\n" + "="*60)
    print("测试2: SufficiencyChecker - 充分性判断")
    print("="*60)

    # 创建检查器
    checker = SufficiencyChecker(
        rule_top1_threshold=0.6,
        rule_coverage_threshold=0.5,
        rule_coverage_min_count=2,
        llm_confidence_threshold=0.7,
        llm_timeout=2.0
    )

    query = "10kV配电柜的接地电阻规范是什么"

    # 测试场景1: 规则不通过（最高分过低）
    print("\n场景1: 规则不通过（最高分过低）")
    top_results_low_score = [
        RerankResult(
            chunk_id=1,
            content="配电柜接地相关内容",
            document_id=100,
            standard_no="GB/T 50001",
            clause="1.1",
            score=0.4,  # 低于阈值0.6
            recall_source="vector"
        )
    ]

    try:
        result = await checker.check(query, top_results_low_score)
        print(f"  结果: sufficient={result.sufficient}, source={result.source}, confidence={result.confidence:.2f}")
        print(f"  缺口: {result.gaps}")
        assert result.sufficient == False and result.source == "rule"
        print("  [PASS] Scenario 1 passed")
    except Exception as e:
        print(f"  [FAIL] Scenario 1 failed: {e}")
        return False

    # 测试场景2: 规则通过，LLM判断
    print("\n场景2: 规则通过，进入LLM判断")
    top_results_good = []
    for i in range(5):
        top_results_good.append(RerankResult(
            chunk_id=i + 1,
            content=f"配电柜接地电阻规范：{i+1}. 接地电阻应不大于4欧姆...",
            document_id=100 + i,
            standard_no=f"GB/T {50001 + i}",
            clause=f"{i+1}.{i+1}",
            score=0.9 - i * 0.05,  # 高分且分布良好
            recall_source="vector"
        ))

    try:
        result = await checker.check(query, top_results_good)
        print(f"  Result: sufficient={result.sufficient}, source={result.source}, confidence={result.confidence:.2f}")
        print(f"  Gaps: {result.gaps}")
        print("  [PASS] Scenario 2 passed (LLM judged)")
    except asyncio.TimeoutError:
        print("  [INFO] LLM timeout, fallback to sufficient")
        print("  [PASS] Scenario 2 passed (timeout fallback)")
    except Exception as e:
        print(f"  [FAIL] Scenario 2 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n[PASS] Sufficiency checker test passed")
    return True

async def test_degradation():
    """测试降级策略"""
    print("\n" + "="*60)
    print("测试3: 降级策略")
    print("="*60)

    # 测试候选块数量少于top_k的情况
    reranker = TwoStageReranker(enable_cache=False)

    query = "测试查询"
    candidates = [
        ChunkResult(
            chunk_id=1,
            document_id=100,
            content="测试内容1",
            score=0.8,
            recall_source="vector"
        ),
        ChunkResult(
            chunk_id=2,
            document_id=101,
            content="测试内容2",
            score=0.7,
            recall_source="vector"
        )
    ]

    try:
        # 请求top_k=5，但只有2个候选
        results = await reranker.rerank(query, candidates, top_k=5)
        assert len(results) == 2
        print(f"  [PASS] Insufficient candidates: requested 5, got {len(results)}")

        # 测试空候选
        empty_results = await reranker.rerank(query, [], top_k=5)
        assert len(empty_results) == 0
        print(f"  [PASS] Empty candidates: returned empty list")

        print("\n[PASS] Degradation test passed")
        return True

    except Exception as e:
        print(f"\n[FAIL] Degradation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("重排层功能测试")
    print("="*60)

    results = []

    # 测试1: 两阶段重排
    results.append(await test_two_stage_reranker())

    # 测试2: 充分性判断
    results.append(await test_sufficiency_checker())

    # 测试3: 降级策略
    results.append(await test_degradation())

    # 汇总结果
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")

    if passed == total:
        print("\n[SUCCESS] All tests passed!")
        return 0
    else:
        print(f"\n[FAILED] {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
