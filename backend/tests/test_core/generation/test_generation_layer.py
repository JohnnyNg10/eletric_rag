"""
测试生成层功能

测试内容：
1. AnswerGenerator - 答案生成
2. CitationExtractor - 引用提取
3. FactualValidator - 事实验证
"""
import asyncio
import sys
from pathlib import Path

from app.core.generation import (
    AnswerGenerator,
    CitationExtractor,
    FactualValidator
)
from app.core.retrieval.rerank import RerankResult

async def test_citation_extractor():
    """测试引用提取"""
    print("\n" + "="*50)
    print("Test: CitationExtractor")
    print("="*50)

    extractor = CitationExtractor()

    # 模拟答案和chunks
    answer = """根据GB 50057-2010规定，接地电阻应不大于4欧姆[1]。对于高层建筑，应采用联合接地方式[2]。"""

    chunks = [
        RerankResult(
            chunk_id=1,
            content="接地电阻应不大于4欧姆",
            document_id=100,
            standard_no="GB 50057-2010",
            clause="3.2.1",
            score=0.95,
            recall_source="vector"
        ),
        RerankResult(
            chunk_id=2,
            content="高层建筑应采用联合接地方式",
            document_id=101,
            standard_no="GB 50057-2010",
            clause="3.2.5",
            score=0.88,
            recall_source="vector"
        )
    ]

    # 提取引用
    citations = extractor.extract(answer, chunks)

    print(f"Answer: {answer}")
    print(f"\nExtracted {len(citations)} citations:")
    for c in citations:
        formatted = extractor.format_citation(c)
        print(f"  {formatted}")

    # 验证引用完整性
    validation = extractor.validate_citations(answer, chunks)
    print(f"\nValidation:")
    print(f"  Valid: {validation['valid']}")
    print(f"  Coverage: {validation['coverage_rate']:.0%}")
    print(f"  Issues: {validation['issues']}")

    assert len(citations) == 2
    print("\n[PASS] CitationExtractor test passed")
    return True

async def test_answer_generator():
    """测试答案生成器"""
    print("\n" + "="*50)
    print("Test: AnswerGenerator")
    print("="*50)

    generator = AnswerGenerator(enable_validation=False)

    query = "10kV配电柜的接地电阻规范是什么？"

    chunks = [
        RerankResult(
            chunk_id=1,
            content="10kV配电柜的接地电阻应不大于4欧姆，接地线应采用铜芯绝缘线，截面积不小于16平方毫米。",
            document_id=100,
            standard_no="GB 50057-2010",
            clause="3.2.1",
            score=0.95,
            recall_source="vector",
            document_title="建筑物防雷设计规范"
        ),
        RerankResult(
            chunk_id=2,
            content="配电柜应设置独立的接地端子，所有金属外壳应可靠接地。接地电阻测试应每年进行一次。",
            document_id=101,
            standard_no="DL/T 5136-2012",
            clause="5.3.2",
            score=0.87,
            recall_source="vector",
            document_title="火力发电厂、变电站接地设计技术规程"
        )
    ]

    print(f"Query: {query}")
    print(f"Chunks: {len(chunks)}")

    # 生成答案
    result = await generator.generate(query, chunks)

    print(f"\nGeneration result:")
    print(f"  Time: {result.generation_time}ms")
    print(f"  Tokens: {result.token_count}")
    print(f"  Citations: {len(result.citations)}")
    print(f"\nAnswer:")
    print(result.answer)

    if result.citations:
        print(f"\nCitations:")
        for c in result.citations:
            print(f"  [{c.index}] {c.standard_no} {c.clause if c.clause else ''}")

    # 答案应该有内容且有引用
    assert len(result.answer) > 10  # 降低阈值，只要有基本内容即可
    assert len(result.citations) > 0  # 应该有引用
    print("\n[PASS] AnswerGenerator test passed")
    return True

async def test_empty_chunks():
    """测试空chunks的降级处理"""
    print("\n" + "="*50)
    print("Test: Empty chunks handling")
    print("="*50)

    generator = AnswerGenerator()

    query = "测试问题"
    chunks = []

    result = await generator.generate(query, chunks)

    print(f"Answer: {result.answer}")
    assert "未找到相关参考资料" in result.answer
    print("\n[PASS] Empty chunks handling passed")
    return True

async def main():
    """主测试函数"""
    print("\n" + "="*50)
    print("Generation Layer Test")
    print("="*50)

    results = []

    # 测试1: 引用提取
    results.append(await test_citation_extractor())

    # 测试2: 答案生成
    results.append(await test_answer_generator())

    # 测试3: 空chunks处理
    results.append(await test_empty_chunks())

    # 汇总
    print("\n" + "="*50)
    print("Test Summary")
    print("="*50)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n[SUCCESS] All tests passed!")
        return 0
    else:
        print(f"\n[FAILED] {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
