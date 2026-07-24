"""
清理 ES 和 Qdrant 中的孤儿数据（orphaned data）

用于清理之前删除文档时因 bug 导致的残留数据：
- MySQL 中已删除的文档
- 但 ES/Qdrant 中仍存在的 chunks/vectors
"""
import asyncio
import logging
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Document
from app.storage.search_engine import search_engine
from app.storage.vector_store import vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_valid_doc_ids(db: Session) -> set[str]:
    """从 MySQL 获取所有有效的 document_id"""
    docs = db.query(Document.id).all()
    return {str(doc.id) for doc in docs}


def get_es_doc_ids() -> set[str]:
    """从 ES 获取所有 doc_id（通过聚合）"""
    try:
        body = {
            "size": 0,
            "aggs": {
                "unique_docs": {
                    "terms": {
                        "field": "doc_id",
                        "size": 10000  # 假设不超过 10k 个文档
                    }
                }
            }
        }
        response = search_engine.client.search(index=search_engine.index_name, body=body)
        buckets = response.get("aggregations", {}).get("unique_docs", {}).get("buckets", [])
        return {bucket["key"] for bucket in buckets}
    except Exception as e:
        logger.error(f"Failed to get ES doc_ids: {e}")
        return set()


def get_qdrant_doc_ids() -> set[str]:
    """从 Qdrant 获取所有 doc_id（通过 scroll）"""
    try:
        doc_ids = set()
        offset = None

        while True:
            # 使用 scroll 分批获取点
            result = vector_store.client.scroll(
                collection_name=vector_store.collection_name,
                limit=100,
                offset=offset,
                with_payload=["doc_id"],
                with_vectors=False
            )

            if not result[0]:  # 没有更多点了
                break

            for point in result[0]:
                if point.payload and "doc_id" in point.payload:
                    doc_ids.add(str(point.payload["doc_id"]))

            offset = result[1]  # 下一批的 offset
            if offset is None:
                break

        return doc_ids
    except Exception as e:
        logger.error(f"Failed to get Qdrant doc_ids: {e}")
        return set()


def cleanup_orphaned_data(dry_run: bool = True):
    """
    清理孤儿数据

    Args:
        dry_run: True 只打印要删除的内容，False 执行实际删除
    """
    db = SessionLocal()

    try:
        # 1. 获取所有有效的 doc_id
        logger.info("正在查询 MySQL 中的有效文档...")
        valid_doc_ids = get_valid_doc_ids(db)
        logger.info(f"MySQL 中有 {len(valid_doc_ids)} 个有效文档")

        # 2. 获取 ES 中的 doc_id
        logger.info("正在查询 Elasticsearch...")
        es_doc_ids = get_es_doc_ids()
        logger.info(f"ES 中有 {len(es_doc_ids)} 个不同的 doc_id")

        # 3. 获取 Qdrant 中的 doc_id
        logger.info("正在查询 Qdrant...")
        qdrant_doc_ids = get_qdrant_doc_ids()
        logger.info(f"Qdrant 中有 {len(qdrant_doc_ids)} 个不同的 doc_id")

        # 4. 找出孤儿数据
        orphaned_in_es = es_doc_ids - valid_doc_ids
        orphaned_in_qdrant = qdrant_doc_ids - valid_doc_ids

        logger.info(f"\n{'='*60}")
        logger.info(f"发现 {len(orphaned_in_es)} 个 ES 孤儿文档")
        logger.info(f"发现 {len(orphaned_in_qdrant)} 个 Qdrant 孤儿文档")
        logger.info(f"{'='*60}\n")

        if orphaned_in_es:
            logger.info(f"ES 孤儿 doc_id: {sorted(orphaned_in_es)}")

        if orphaned_in_qdrant:
            logger.info(f"Qdrant 孤儿 doc_id: {sorted(orphaned_in_qdrant)}")

        # 5. 删除孤儿数据
        if not dry_run:
            logger.info("\n开始清理...")

            # 删除 ES 孤儿数据
            for doc_id in orphaned_in_es:
                try:
                    search_engine.delete_by_doc_id(doc_id)
                    logger.info(f"✓ 已从 ES 删除 doc_id: {doc_id}")
                except Exception as e:
                    logger.error(f"✗ ES 删除失败 doc_id {doc_id}: {e}")

            # 删除 Qdrant 孤儿数据
            for doc_id in orphaned_in_qdrant:
                try:
                    vector_store.delete_by_doc_id(doc_id)
                    logger.info(f"✓ 已从 Qdrant 删除 doc_id: {doc_id}")
                except Exception as e:
                    logger.error(f"✗ Qdrant 删除失败 doc_id {doc_id}: {e}")

            logger.info("\n清理完成!")
        else:
            logger.info("\n这是 dry-run 模式，未执行实际删除")
            logger.info("如需执行删除，请运行: python cleanup_orphaned_data.py --execute")

    finally:
        db.close()


if __name__ == "__main__":
    import sys

    # 检查是否传入 --execute 参数
    execute = "--execute" in sys.argv
    skip_confirm = "--yes" in sys.argv or "-y" in sys.argv

    if not execute:
        logger.info("=" * 60)
        logger.info("DRY-RUN 模式（仅查看，不删除）")
        logger.info("=" * 60)
    else:
        logger.info("=" * 60)
        logger.info("执行模式（将实际删除数据）")
        logger.info("=" * 60)
        if not skip_confirm:
            confirm = input("\n确认要删除孤儿数据吗? (yes/no): ")
            if confirm.lower() != "yes":
                logger.info("已取消")
                sys.exit(0)

    cleanup_orphaned_data(dry_run=not execute)
