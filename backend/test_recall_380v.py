"""
测试 380V 配网查询的召回问题
"""
import asyncio
import logging
from app.core.retrieval.recall import VectorRecall, KeywordRecall, StructuredRecall

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_recall():
    query = "分布式电源接入380V配网时的保护配置及技术要求"

    print(f"\n{'='*60}")
    print(f"查询: {query}")
    print(f"{'='*60}\n")

    # 1. 测试向量召回
    print("1. 向量召回测试:")
    print("-" * 60)
    try:
        vector_recall = VectorRecall()
        vector_results = await vector_recall.search(query, filters={}, top_k=10)
        print(f"召回数量: {len(vector_results)}")
        for i, result in enumerate(vector_results[:5], 1):
            print(f"\n[{i}] Score: {result.score:.4f}")
            print(f"    标准号: {result.standard_no}")
            print(f"    章节: {result.clause or result.chapter or 'N/A'}")
            print(f"    内容片段: {result.content[:100]}...")
    except Exception as e:
        print(f"向量召回失败: {e}")
        import traceback
        traceback.print_exc()

    # 2. 测试关键词召回
    print("\n\n2. 关键词召回测试 (Elasticsearch):")
    print("-" * 60)
    try:
        keyword_recall = KeywordRecall()
        keyword_results = await keyword_recall.search(query, filters={}, top_k=10)
        print(f"召回数量: {len(keyword_results)}")
        for i, result in enumerate(keyword_results[:5], 1):
            print(f"\n[{i}] Score: {result.score:.4f}")
            print(f"    标准号: {result.standard_no}")
            print(f"    章节: {result.clause or result.chapter or 'N/A'}")
            print(f"    内容片段: {result.content[:100]}...")
    except Exception as e:
        print(f"关键词召回失败: {e}")
        import traceback
        traceback.print_exc()

    # 3. 测试结构化召回（标准号过滤）
    print("\n\n3. 结构化召回测试 (GB/T 33982):")
    print("-" * 60)
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
        structured_recall = StructuredRecall(db)

        # 先测试是否能找到标准
        filters = {"standard_no": "GB/T 33982-2017"}
        structured_results = await structured_recall.search(query, filters, top_k=10)
        print(f"召回数量: {len(structured_results)}")
        for i, result in enumerate(structured_results[:5], 1):
            print(f"\n[{i}] Score: {result.score:.4f}")
            print(f"    标准号: {result.standard_no}")
            print(f"    章节: {result.clause or result.chapter or 'N/A'}")
            print(f"    内容片段: {result.content[:100]}...")

        db.close()
    except Exception as e:
        print(f"结构化召回失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_recall())
