"""
简单召回测试 - 使用现有数据
"""
import asyncio
import sys
import io

sys.path.append('D:/dl/backend')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.retrieval.recall import MultiPathRecall
from app.db.session import SessionLocal


async def test_simple_recall():
    """测试基本召回功能"""
    print("=" * 80)
    print("  简单召回测试 - 使用现有数据")
    print("=" * 80)

    db = SessionLocal()
    multipath_recall = MultiPathRecall(db=db)

    # 测试用例
    test_queries = [
        "电气安全",
        "插头插座",
        "接地要求",
        "GB 1002",
    ]

    for query in test_queries:
        print(f"\n查询: {query}")
        print("-" * 80)

        try:
            results = await multipath_recall.recall(
                query=query,
                filters={}
            )

            # 统计各召回源
            source_stats = {}
            for chunk in results:
                for source in chunk.recall_sources:
                    source_stats[source] = source_stats.get(source, 0) + 1

            print(f"召回数量: {len(results)}")
            print(f"召回源统计: {source_stats}")

            # 显示前3条结果
            for i, chunk in enumerate(results[:3], 1):
                print(f"\n  [{i}] Score: {chunk.score:.4f} | Sources: {chunk.recall_sources}")
                print(f"      Chunk ID: {chunk.chunk_id}")
                content = chunk.content[:80] + "..." if len(chunk.content) > 80 else chunk.content
                print(f"      内容: {content}")

        except Exception as e:
            print(f"召回失败: {e}")
            import traceback
            traceback.print_exc()

    db.close()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_simple_recall())
