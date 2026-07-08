"""
端到端RAG流程测试

测试完整的查询流程：预处理 → 路由 → 召回 → 重排 → 生成
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.services.query_service import QueryService


async def test_end_to_end_query():
    """测试端到端查询流程"""
    print("\n" + "="*60)
    print("End-to-End RAG Pipeline Test")
    print("="*60)

    db = SessionLocal()
    query_service = QueryService(db=db)

    # 测试查询
    test_queries = [
        "10kV配电柜的接地电阻规范是什么？",
        "GB 1002标准对插头和插座有什么要求？",
        "高压配电系统的安全要求"
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n{'='*60}")
        print(f"Test Query {i}: {query}")
        print("="*60)

        try:
            result = await query_service.execute_query(
                query=query,
                user_id=1,
                conversation_id=f"test_conv_{i}"
            )

            if result['status'] == 'need_clarification':
                print(f"[Vagueness Score]: {result.get('vagueness_score', 'N/A')}")
                print(f"[Clarification Options]: {len(result.get('clarification_options', []))}")
                print("\nClarification needed - skipping generation")
                continue

            # 只有status=success时才有lane字段
            print(f"[Lane]: {result.get('lane', 'N/A')}")
            print(f"[Route Reason]: {result.get('route_reason', 'N/A')}")

            print(f"\n[Timing]:")
            print(f"  Retrieval: {result.get('retrieval_time', 0)}ms")
            print(f"  Generation: {result.get('generation_time', 0)}ms")
            print(f"  Total: {result.get('total_time', 0)}ms")

            print(f"\n[Recall]:")
            print(f"  Count: {result.get('recall_count', 0)}")
            print(f"  Retry: {result.get('retry_triggered', False)}")

            print(f"\n[Answer]:")
            answer = result.get('answer', '')
            # 显示前200个字符
            answer_preview = answer[:200] if len(answer) > 200 else answer
            print(f"  {answer_preview}")
            if len(answer) > 200:
                print(f"  ... ({len(answer)} chars total)")

            citations = result.get('citations', [])
            print(f"\n[Citations]: {len(citations)}")
            for cite in citations[:3]:  # 只显示前3个
                std = cite.get('standard_no', 'N/A')
                clause = cite.get('clause', 'N/A')
                print(f"  [{cite.get('index')}] {std} {clause}")

            print(f"\n[Query Log ID]: {result.get('query_log_id', 0)}")

        except Exception as e:
            print(f"\n[ERROR]: {e}")
            import traceback
            traceback.print_exc()

    db.close()
    print("\n" + "="*60)
    print("End-to-End Test Completed")
    print("="*60)


async def test_pipeline_components():
    """测试各组件是否正确连接"""
    print("\n" + "="*60)
    print("Pipeline Components Check")
    print("="*60)

    db = SessionLocal()
    query_service = QueryService(db=db)

    checks = {
        "Preprocessor": hasattr(query_service, 'preprocessor'),
        "Router": hasattr(query_service, 'router'),
        "FastLane": hasattr(query_service, 'fast_lane'),
        "SlowLane": hasattr(query_service, 'slow_lane'),
        "Generator": hasattr(query_service, 'generator'),
        "Database": query_service.db is not None
    }

    # 检查FastLane的子组件
    if checks["FastLane"]:
        fast_lane = query_service.fast_lane
        checks["FastLane.Reranker"] = hasattr(fast_lane, 'reranker')
        checks["FastLane.SufficiencyChecker"] = hasattr(fast_lane, 'sufficiency_checker')
        checks["FastLane.QueryRewriter"] = hasattr(fast_lane, 'query_rewriter')
        checks["FastLane.MetadataExtractor"] = hasattr(fast_lane, 'metadata_extractor')

    # 检查Generator的子组件
    if checks["Generator"]:
        generator = query_service.generator
        checks["Generator.LLMClient"] = hasattr(generator, 'llm_client')
        checks["Generator.CitationExtractor"] = hasattr(generator, 'citation_extractor')
        checks["Generator.Validator"] = hasattr(generator, 'validator')

    print("\nComponent Status:")
    for name, status in checks.items():
        status_mark = "[OK]" if status else "[MISSING]"
        print(f"  {status_mark} {name}")

    all_ok = all(checks.values())
    db.close()

    if all_ok:
        print("\n[SUCCESS] All components connected")
        return True
    else:
        print("\n[WARNING] Some components missing")
        return False


async def main():
    print("\n" + "="*60)
    print("RAG Pipeline Integration Test")
    print("="*60)

    # 1. 检查组件连接
    components_ok = await test_pipeline_components()

    if not components_ok:
        print("\n[SKIP] Component check failed, skipping E2E test")
        return 1

    # 2. 端到端测试
    await test_end_to_end_query()

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
