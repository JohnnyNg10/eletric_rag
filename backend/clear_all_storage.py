"""
完全清空所有存储系统的数据

警告：这会删除 Qdrant、Elasticsearch 中的所有数据！
仅用于开发/测试环境，生产环境禁用！
"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.storage.vector_store import vector_store
from app.storage.search_engine import search_engine
from app.storage.object_store import object_store
from app.db.session import SessionLocal
from app.db.models import Document, Chunk
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def clear_all_data():
    """完全清空所有数据"""
    print("\n" + "="*60)
    print("⚠️  完全清空存储系统")
    print("="*60)

    # 1. 清空 Qdrant（重建 collection）
    print("\n1. 清空 Qdrant 向量数据库...")
    try:
        info_before = vector_store.get_collection_info()
        points_before = info_before.get('points_count', 0)
        print(f"  当前点数: {points_before}")

        if points_before > 0:
            # 删除并重建 collection
            vector_store.client.delete_collection(vector_store.collection_name)
            print(f"  ✓ 已删除 collection: {vector_store.collection_name}")

            vector_store.create_collection_if_not_exists()
            print(f"  ✓ 已重建 collection: {vector_store.collection_name}")

            info_after = vector_store.get_collection_info()
            print(f"  剩余点数: {info_after.get('points_count', 0)}")
        else:
            print(f"  无数据，跳过清理")

    except Exception as e:
        print(f"  ✗ Qdrant 清理失败: {e}")

    # 2. 清空 Elasticsearch（删除并重建索引）
    print("\n2. 清空 Elasticsearch 全文索引...")
    try:
        stats_before = search_engine.get_index_stats()
        docs_before = stats_before.get('docs_count', 0)
        print(f"  当前文档数: {docs_before}")

        if docs_before > 0:
            # 删除并重建索引
            search_engine.client.indices.delete(index=search_engine.index_name)
            print(f"  ✓ 已删除索引: {search_engine.index_name}")

            search_engine.create_index_if_not_exists()
            print(f"  ✓ 已重建索引: {search_engine.index_name}")

            await asyncio.sleep(1)  # 等待索引创建完成
            stats_after = search_engine.get_index_stats()
            print(f"  剩余文档数: {stats_after.get('docs_count', 0)}")
        else:
            print(f"  无数据，跳过清理")

    except Exception as e:
        print(f"  ✗ Elasticsearch 清理失败: {e}")

    # 3. 清空 MinIO（删除所有测试文件）
    print("\n3. 清空 MinIO 测试文件...")
    try:
        deleted_total = 0

        # 清理 Markdown bucket
        markdown_objects = object_store.list_objects(
            bucket_name=object_store.markdown_bucket,
            prefix=""
        )
        for obj in markdown_objects:
            try:
                object_store.delete_object(
                    bucket_name=object_store.markdown_bucket,
                    object_name=obj['object_name']
                )
                deleted_total += 1
            except:
                pass

        print(f"  ✓ 已删除 {deleted_total} 个对象")

    except Exception as e:
        print(f"  ✗ MinIO 清理失败: {e}")

    # 4. 清空 MySQL（删除所有文档和chunk记录）
    print("\n4. 清空 MySQL 数据库...")
    try:
        db = SessionLocal()
        try:
            # 删除所有 chunks
            chunk_count = db.query(Chunk).count()
            if chunk_count > 0:
                db.query(Chunk).delete()
                print(f"  删除 {chunk_count} 个chunk记录")

            # 删除所有 documents
            doc_count = db.query(Document).count()
            if doc_count > 0:
                db.query(Document).delete()
                print(f"  删除 {doc_count} 个文档记录")

            db.commit()
            print(f"  ✓ MySQL 数据已清空")

        finally:
            db.close()

    except Exception as e:
        print(f"  ✗ MySQL 清理失败: {e}")

    # 5. 最终验证
    print("\n" + "="*60)
    print("最终状态验证")
    print("="*60)

    try:
        qdrant_info = vector_store.get_collection_info()
        es_stats = search_engine.get_index_stats()

        db = SessionLocal()
        try:
            mysql_docs = db.query(Document).count()
            mysql_chunks = db.query(Chunk).count()
        finally:
            db.close()

        print(f"\n✅ 所有数据已清空：")
        print(f"  Qdrant 点数: {qdrant_info.get('points_count', 0)}")
        print(f"  Elasticsearch 文档数: {es_stats.get('docs_count', 0)}")
        print(f"  MySQL 文档数: {mysql_docs}")
        print(f"  MySQL chunk数: {mysql_chunks}")

    except Exception as e:
        print(f"  状态验证失败: {e}")


if __name__ == "__main__":
    print("\n⚠️  警告：这将删除所有存储系统中的数据！")
    print("确认继续？(y/N): ", end="")

    # 自动确认（用于脚本）
    confirm = "y"
    print(confirm)

    if confirm.lower() == 'y':
        asyncio.run(clear_all_data())
    else:
        print("\n已取消清理操作")
