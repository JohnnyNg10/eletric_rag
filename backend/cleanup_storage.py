"""
清理存储层测试数据

清理内容：
1. Qdrant 向量数据库中的 doc_id="GB7958-2014" 数据
2. Elasticsearch 全文索引中的数据
3. MinIO 对象存储中的测试文件
4. MySQL 数据库中的相关记录（如果有）
"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.storage.vector_store import vector_store
from app.storage.search_engine import search_engine
from app.storage.object_store import object_store
from app.db.session import SessionLocal
from app.db.models import Document, Chunk
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def cleanup_all():
    """清理所有测试数据"""
    print("\n" + "="*60)
    print("清理存储层测试数据")
    print("="*60)

    doc_id = "GB7958-2014"

    # 1. 清理 Qdrant
    print("\n1. 清理 Qdrant 向量数据...")
    try:
        # 获取当前点数
        info_before = vector_store.get_collection_info()
        points_before = info_before.get('points_count', 0)
        print(f"  当前点数: {points_before}")

        # 删除数据
        vector_store.delete_by_doc_id(doc_id)

        # 验证删除结果
        await asyncio.sleep(1)  # 等待删除生效
        info_after = vector_store.get_collection_info()
        points_after = info_after.get('points_count', 0)
        deleted_count = points_before - points_after

        print(f"  ✓ 已删除 {deleted_count} 个点")
        print(f"  剩余点数: {points_after}")
    except Exception as e:
        print(f"  ✗ Qdrant 清理失败: {e}")

    # 2. 清理 Elasticsearch
    print("\n2. 清理 Elasticsearch 索引...")
    try:
        # 获取当前文档数
        stats_before = search_engine.get_index_stats()
        docs_before = stats_before.get('docs_count', 0)
        print(f"  当前文档数: {docs_before}")

        # 删除数据
        search_engine.delete_by_doc_id(doc_id)

        # 验证删除结果
        await asyncio.sleep(1)  # 等待索引刷新
        stats_after = search_engine.get_index_stats()
        docs_after = stats_after.get('docs_count', 0)
        deleted_count = docs_before - docs_after

        print(f"  ✓ 已删除 {deleted_count} 个文档")
        print(f"  剩余文档数: {docs_after}")
    except Exception as e:
        print(f"  ✗ Elasticsearch 清理失败: {e}")

    # 3. 清理 MinIO
    print("\n3. 清理 MinIO 对象存储...")
    try:
        # 列出测试目录下的所有文件
        markdown_objects = object_store.list_objects(
            bucket_name=object_store.markdown_bucket,
            prefix="test/"
        )

        deleted_count = 0
        for obj in markdown_objects:
            try:
                object_store.delete_object(
                    bucket_name=object_store.markdown_bucket,
                    object_name=obj['object_name']
                )
                deleted_count += 1
                print(f"  删除: {obj['object_name']}")
            except Exception as e:
                print(f"  ✗ 删除失败 {obj['object_name']}: {e}")

        print(f"  ✓ 已删除 {deleted_count} 个对象")
    except Exception as e:
        print(f"  ✗ MinIO 清理失败: {e}")

    # 4. 清理 MySQL
    print("\n4. 清理 MySQL 数据库...")
    try:
        db = SessionLocal()
        try:
            # 查找文档
            document = db.query(Document).filter(
                Document.standard_no == "GB 7958-2014"
            ).first()

            if document:
                doc_uuid = document.doc_id

                # 删除 chunks
                chunks = db.query(Chunk).filter(Chunk.doc_id == doc_uuid).all()
                chunk_count = len(chunks)
                for chunk in chunks:
                    db.delete(chunk)

                # 删除 document
                db.delete(document)
                db.commit()

                print(f"  ✓ 已删除文档记录: {document.title}")
                print(f"  ✓ 已删除 {chunk_count} 个chunk记录")
            else:
                print(f"  未找到 GB 7958-2014 的文档记录")

        finally:
            db.close()

    except Exception as e:
        print(f"  ✗ MySQL 清理失败: {e}")

    # 5. 汇总报告
    print("\n" + "="*60)
    print("清理完成汇总")
    print("="*60)

    # 最终状态检查
    try:
        qdrant_info = vector_store.get_collection_info()
        es_stats = search_engine.get_index_stats()

        print(f"\n最终状态：")
        print(f"  Qdrant 剩余点数: {qdrant_info.get('points_count', 0)}")
        print(f"  Elasticsearch 剩余文档数: {es_stats.get('docs_count', 0)}")
        print(f"\n✅ 所有测试数据已清理")

    except Exception as e:
        print(f"  状态检查失败: {e}")


async def cleanup_specific_doc(doc_id: str):
    """清理指定doc_id的数据"""
    print(f"\n清理 doc_id: {doc_id}")

    # Qdrant
    try:
        vector_store.delete_by_doc_id(doc_id)
        print(f"  ✓ Qdrant")
    except Exception as e:
        print(f"  ✗ Qdrant: {e}")

    # Elasticsearch
    try:
        search_engine.delete_by_doc_id(doc_id)
        print(f"  ✓ Elasticsearch")
    except Exception as e:
        print(f"  ✗ Elasticsearch: {e}")


if __name__ == "__main__":
    # 运行清理
    asyncio.run(cleanup_all())
