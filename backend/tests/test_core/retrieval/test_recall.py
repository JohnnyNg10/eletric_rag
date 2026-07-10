"""
多路召回功能测试脚本

测试内容：
1. 向量召回 (VectorRecall - Qdrant)
2. 关键词召回 (KeywordRecall - Elasticsearch)
3. 结构化召回 (StructuredRecall - MySQL)
4. 多路融合召回 (MultiPathRecall)

前置条件：
- Qdrant 服务运行中
- Elasticsearch 服务运行中
- MySQL 数据库已初始化
- 已有索引数据
"""
import asyncio
import sys
import io
from typing import Dict, Any

# 强制UTF-8输出，避免Windows GBK编码错误

from app.core.retrieval.recall import (
    VectorRecall,
    KeywordRecall,
    StructuredRecall,
    MultiPathRecall
)
from app.core.embedding import Embedder
from app.storage.vector_store import vector_store
from app.storage.search_engine import search_engine
from app.db.session import SessionLocal

def print_section(title: str):
    """打印分隔标题"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def print_results(results: list, title: str):
    """打印召回结果"""
    print(f"\n{title} - 召回数量: {len(results)}")
    print("-" * 80)

    for i, chunk in enumerate(results[:5], 1):  # 只显示前5条
        print(f"\n[{i}] Score: {chunk.score:.4f} | Source: {chunk.recall_source}")
        print(f"    Chunk ID: {chunk.chunk_id} | Doc ID: {chunk.document_id}")
        if chunk.standard_no:
            print(f"    标准号: {chunk.standard_no}")
        if chunk.clause:
            print(f"    条款: {chunk.clause}")
        # 截取内容前100字符
        content_preview = chunk.content[:100] + "..." if len(chunk.content) > 100 else chunk.content
        print(f"    内容: {content_preview}")

    if len(results) > 5:
        print(f"\n... 还有 {len(results) - 5} 条结果未显示")

async def test_vector_recall():
    """测试向量召回"""
    print_section("测试 1: 向量召回 (Qdrant 混合检索)")

    try:
        vector_recall = VectorRecall()

        test_cases = [
            {
                "query": "配电房接地电阻要求",
                "filters": {},
                "top_k": 10
            },
            {
                "query": "35kV变压器安装规范",
                "filters": {"voltage_level": "35kV"},
                "top_k": 10
            }
        ]

        for idx, case in enumerate(test_cases, 1):
            print(f"\n测试用例 {idx}:")
            print(f"  查询: {case['query']}")
            print(f"  过滤条件: {case['filters']}")

            results = await vector_recall.search(
                query=case['query'],
                filters=case['filters'],
                top_k=case['top_k']
            )

            print_results(results, f"向量召回结果 {idx}")

        print("\n✓ 向量召回测试完成")
        return True

    except Exception as e:
        print(f"\n✗ 向量召回测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_keyword_recall():
    """测试关键词召回"""
    print_section("测试 2: 关键词召回 (Elasticsearch BM25)")

    try:
        keyword_recall = KeywordRecall()

        test_cases = [
            {
                "query": "配电房接地电阻",
                "filters": {},
                "top_k": 10
            },
            {
                "query": "变压器 安装 距离",
                "filters": {"category": "变电"},
                "top_k": 10
            }
        ]

        for idx, case in enumerate(test_cases, 1):
            print(f"\n测试用例 {idx}:")
            print(f"  查询: {case['query']}")
            print(f"  过滤条件: {case['filters']}")

            results = await keyword_recall.search(
                query=case['query'],
                filters=case['filters'],
                top_k=case['top_k']
            )

            print_results(results, f"关键词召回结果 {idx}")

        print("\n✓ 关键词召回测试完成")
        return True

    except Exception as e:
        print(f"\n✗ 关键词召回测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_structured_recall():
    """测试结构化召回"""
    print_section("测试 3: 结构化召回 (MySQL 精确查询)")

    try:
        db = SessionLocal()
        structured_recall = StructuredRecall(db)

        test_cases = [
            {
                "query": "GB 1002-2024 第5.3条",
                "filters": {},
                "top_k": 10
            },
            {
                "query": "DL/T 5352-2018",
                "filters": {},
                "top_k": 10
            },
            {
                "query": "查询标准 NB/T 42055-2015 的内容",
                "filters": {},
                "top_k": 10
            }
        ]

        for idx, case in enumerate(test_cases, 1):
            print(f"\n测试用例 {idx}:")
            print(f"  查询: {case['query']}")
            print(f"  过滤条件: {case['filters']}")

            results = await structured_recall.search(
                query=case['query'],
                filters=case['filters'],
                top_k=case['top_k']
            )

            print_results(results, f"结构化召回结果 {idx}")

        print("\n✓ 结构化召回测试完成")
        db.close()
        return True

    except Exception as e:
        print(f"\n✗ 结构化召回测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_multipath_recall():
    """测试多路融合召回"""
    print_section("测试 4: 多路融合召回 (三路并行 + 去重)")

    try:
        db = SessionLocal()

        multipath_recall = MultiPathRecall(db=db)

        test_cases = [
            {
                "query": "配电房接地电阻要求",
                "filters": {},
                "top_k": 50,
                "description": "通用查询 - 应该触发向量+关键词召回"
            },
            {
                "query": "GB 1002-2024 第5.3条的规定",
                "filters": {},
                "top_k": 50,
                "description": "结构化查询 - 应该触发所有三路召回"
            },
            {
                "query": "35kV变压器室避雷器安装标准",
                "filters": {"voltage_level": "35kV"},
                "top_k": 50,
                "description": "带过滤条件的查询"
            }
        ]

        for idx, case in enumerate(test_cases, 1):
            print(f"\n测试用例 {idx}: {case['description']}")
            print(f"  查询: {case['query']}")
            print(f"  过滤条件: {case['filters']}")

            results = await multipath_recall.recall(
                query=case['query'],
                filters=case['filters']
            )

            # 统计各召回源数量
            source_stats = {}
            for chunk in results:
                for source in chunk.recall_sources:
                    source_stats[source] = source_stats.get(source, 0) + 1

            print(f"\n召回源统计:")
            for source, count in source_stats.items():
                print(f"  - {source}: {count} 条")

            print_results(results, f"多路召回结果 {idx}")

        print("\n✓ 多路融合召回测试完成")
        db.close()
        return True

    except Exception as e:
        print(f"\n✗ 多路融合召回测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("  多路召回功能测试")
    print("=" * 80)
    print("\n注意: 此测试需要以下服务正在运行:")
    print("  - Qdrant (向量数据库)")
    print("  - Elasticsearch (全文检索)")
    print("  - MySQL (关系数据库)")
    print("  - 并且已有索引数据")
    print("\n开始测试...")

    results = []

    # 测试各个召回路径
    results.append(("向量召回", await test_vector_recall()))
    results.append(("关键词召回", await test_keyword_recall()))
    results.append(("结构化召回", await test_structured_recall()))
    results.append(("多路融合召回", await test_multipath_recall()))

    # 总结
    print_section("测试总结")
    for name, success in results:
        status = "✓ 通过" if success else "✗ 失败"
        print(f"  {name}: {status}")

    total = len(results)
    passed = sum(1 for _, success in results if success)
    print(f"\n总计: {passed}/{total} 测试通过")

if __name__ == "__main__":
    asyncio.run(main())
