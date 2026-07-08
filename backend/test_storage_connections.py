"""
测试Qdrant和Elasticsearch连接及数据召回
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.retrieval.recall import VectorRecall, KeywordRecall, StructuredRecall
from app.db.session import SessionLocal


async def test_vector_recall():
    """测试Qdrant向量召回"""
    print("\n" + "="*60)
    print("Test: Vector Recall (Qdrant)")
    print("="*60)

    vector_recall = VectorRecall()

    try:
        # 测试查询1: 10kV配电柜
        query = "10kV配电柜接地电阻"
        print(f"\nQuery: {query}")
        results = await vector_recall.search(query, {}, top_k=5)
        print(f"Results: {len(results)} chunks found")

        if results:
            print("\nTop 3 results:")
            for i, result in enumerate(results[:3], 1):
                content_preview = result.content[:50] if len(result.content) > 50 else result.content
                print(f"  [{i}] chunk_id={result.chunk_id}, score={result.score:.4f}")
                print(f"      {content_preview}...")
                print(f"      standard={result.standard_no}, clause={result.clause}")

        return len(results) > 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_keyword_recall():
    """测试Elasticsearch关键词召回"""
    print("\n" + "="*60)
    print("Test: Keyword Recall (Elasticsearch)")
    print("="*60)

    keyword_recall = KeywordRecall()

    try:
        # 测试查询
        query = "10kV配电柜接地电阻"
        print(f"\nQuery: {query}")
        results = await keyword_recall.search(query, {}, top_k=5)
        print(f"Results: {len(results)} chunks found")

        if results:
            print("\nTop 3 results:")
            for i, result in enumerate(results[:3], 1):
                content_preview = result.content[:50] if len(result.content) > 50 else result.content
                print(f"  [{i}] chunk_id={result.chunk_id}, score={result.score:.4f}")
                print(f"      {content_preview}...")
                print(f"      standard={result.standard_no}, clause={result.clause}")

        return len(results) > 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_structured_recall():
    """测试MySQL结构化召回"""
    print("\n" + "="*60)
    print("Test: Structured Recall (MySQL)")
    print("="*60)

    db = SessionLocal()
    structured_recall = StructuredRecall(db)

    try:
        # 测试查询: 包含标准号
        query = "GB 1002标准对插头的要求"
        print(f"\nQuery: {query}")
        results = await structured_recall.search(query, {}, top_k=5)
        print(f"Results: {len(results)} chunks found")

        if results:
            print("\nTop 3 results:")
            for i, result in enumerate(results[:3], 1):
                content_preview = result.content[:50] if len(result.content) > 50 else result.content
                print(f"  [{i}] chunk_id={result.chunk_id}, score={result.score:.4f}")
                print(f"      {content_preview}...")
                print(f"      standard={result.standard_no}, clause={result.clause}")

        db.close()
        return len(results) > 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.close()
        return False


async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("Storage Connections Test")
    print("="*60)

    results = []

    # 测试1: Qdrant向量召回
    results.append(("Qdrant", await test_vector_recall()))

    # 测试2: Elasticsearch关键词召回
    results.append(("Elasticsearch", await test_keyword_recall()))

    # 测试3: MySQL结构化召回
    results.append(("MySQL", await test_structured_recall()))

    # 汇总
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    for name, success in results:
        status = "OK" if success else "FAILED"
        print(f"  [{status}] {name}")

    all_passed = all(success for _, success in results)

    if all_passed:
        print("\n[SUCCESS] All storage connections working!")
        return 0
    else:
        print("\n[WARNING] Some storage connections failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
