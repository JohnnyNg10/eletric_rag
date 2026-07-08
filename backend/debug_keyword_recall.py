"""
Debug KeywordRecall - 对比直接调用和通过KeywordRecall调用的区别
"""
import asyncio
import sys
sys.path.append('.')

from app.storage.search_engine import SearchEngine
from app.core.retrieval.recall import KeywordRecall


async def test_direct_search():
    """直接调用 search_engine.search()"""
    print("=" * 80)
    print("Test 1: Direct search_engine.search()")
    print("=" * 80)

    search_engine = SearchEngine()

    es_query = {
        'query': {
            'bool': {
                'must': [
                    {
                        'multi_match': {
                            'query': '电气安全',
                            'fields': ['text^2', 'clause^1.5'],
                            'type': 'best_fields',
                            'operator': 'or'
                        }
                    }
                ],
                'filter': []
            }
        },
        'size': 10
    }

    results = search_engine.search(es_query)
    print(f"Results: {len(results)}")
    if results:
        print(f"First result chunk_id: {results[0]['_source']['chunk_id']}")


async def test_keyword_recall():
    """通过 KeywordRecall 调用"""
    print("\n" + "=" * 80)
    print("Test 2: KeywordRecall.search()")
    print("=" * 80)

    keyword_recall = KeywordRecall()
    results = await keyword_recall.search('电气安全', {}, top_k=10)
    print(f"Results: {len(results)}")
    if results:
        print(f"First result chunk_id: {results[0].chunk_id}")


async def main():
    await test_direct_search()
    await test_keyword_recall()


if __name__ == "__main__":
    asyncio.run(main())
