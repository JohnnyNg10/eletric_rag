from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List
import logging

from app.db.session import get_db
from app.db.models import Document
from app.storage.vector_store import VectorStore
from app.storage.search_engine import SearchEngine
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/orphan-data/scan")
async def scan_orphan_data(db: Session = Depends(get_db)) -> Dict:
    """
    扫描 Qdrant 和 Elasticsearch 中的孤儿数据

    Returns:
        {
            "mysql_doc_count": int,
            "qdrant": {"total": int, "orphans": [doc_id, ...]},
            "elasticsearch": {"total": int, "orphans": [doc_id, ...]}
        }
    """
    try:
        # 1. 获取 MySQL 中所有有效文档 ID
        valid_doc_ids = {str(doc.id) for doc in db.query(Document.id).all()}
        logger.info(f"MySQL 有效文档数: {len(valid_doc_ids)}")

        result = {
            "mysql_doc_count": len(valid_doc_ids),
            "qdrant": {"total": 0, "orphans": []},
            "elasticsearch": {"total": 0, "orphans": []}
        }

        # 2. 扫描 Qdrant
        try:
            vector_store = VectorStore()
            qdrant_doc_ids = set()
            offset = None

            while True:
                response = vector_store.client.scroll(
                    collection_name=settings.QDRANT_COLLECTION,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )

                if not response[0]:
                    break

                for point in response[0]:
                    doc_id = str(point.payload.get('doc_id'))
                    qdrant_doc_ids.add(doc_id)

                offset = response[1]
                if offset is None:
                    break

            result["qdrant"]["total"] = len(qdrant_doc_ids)
            result["qdrant"]["orphans"] = sorted([
                int(doc_id) for doc_id in qdrant_doc_ids - valid_doc_ids
            ])
            logger.info(f"Qdrant 总文档数: {len(qdrant_doc_ids)}, 孤儿: {len(result['qdrant']['orphans'])}")

        except Exception as e:
            logger.error(f"扫描 Qdrant 失败: {e}")
            result["qdrant"]["error"] = str(e)

        # 3. 扫描 Elasticsearch
        try:
            search_engine = SearchEngine()
            query = {
                "size": 0,
                "aggs": {
                    "doc_ids": {
                        "terms": {
                            "field": "doc_id",
                            "size": 10000
                        }
                    }
                }
            }

            es_result = search_engine.client.search(
                index=search_engine.index_name,
                body=query
            )

            es_doc_ids = {
                str(bucket['key'])
                for bucket in es_result['aggregations']['doc_ids']['buckets']
            }

            result["elasticsearch"]["total"] = len(es_doc_ids)
            result["elasticsearch"]["orphans"] = sorted([
                int(doc_id) for doc_id in es_doc_ids - valid_doc_ids
            ])
            logger.info(f"ES 总文档数: {len(es_doc_ids)}, 孤儿: {len(result['elasticsearch']['orphans'])}")

        except Exception as e:
            logger.error(f"扫描 ES 失败: {e}")
            result["elasticsearch"]["error"] = str(e)

        return result

    except Exception as e:
        logger.error(f"扫描孤儿数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/orphan-data/cleanup")
async def cleanup_orphan_data(db: Session = Depends(get_db)) -> Dict:
    """
    清理 Qdrant 和 Elasticsearch 中的孤儿数据

    Returns:
        {
            "qdrant": {"deleted": int, "failed": int},
            "elasticsearch": {"deleted": int, "failed": int}
        }
    """
    try:
        # 1. 先扫描
        scan_result = await scan_orphan_data(db)

        qdrant_orphans = scan_result["qdrant"].get("orphans", [])
        es_orphans = scan_result["elasticsearch"].get("orphans", [])

        result = {
            "qdrant": {"deleted": 0, "failed": 0},
            "elasticsearch": {"deleted": 0, "failed": 0}
        }

        # 2. 清理 Qdrant
        if qdrant_orphans:
            vector_store = VectorStore()
            for doc_id in qdrant_orphans:
                try:
                    vector_store.delete_by_doc_id(str(doc_id))
                    result["qdrant"]["deleted"] += 1
                    logger.info(f"已删除 Qdrant 孤儿数据: doc_id={doc_id}")
                except Exception as e:
                    logger.error(f"删除 Qdrant doc_id={doc_id} 失败: {e}")
                    result["qdrant"]["failed"] += 1

        # 3. 清理 Elasticsearch
        if es_orphans:
            search_engine = SearchEngine()
            for doc_id in es_orphans:
                try:
                    search_engine.delete_by_doc_id(str(doc_id))
                    result["elasticsearch"]["deleted"] += 1
                    logger.info(f"已删除 ES 孤儿数据: doc_id={doc_id}")
                except Exception as e:
                    logger.error(f"删除 ES doc_id={doc_id} 失败: {e}")
                    result["elasticsearch"]["failed"] += 1

        logger.info(f"清理完成: {result}")
        return result

    except Exception as e:
        logger.error(f"清理孤儿数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
