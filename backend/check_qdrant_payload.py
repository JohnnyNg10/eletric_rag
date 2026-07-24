"""检查 Qdrant 中 doc_id 的实际类型"""
import logging
from app.storage.vector_store import vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 获取几个样本点，检查 doc_id 类型
result = vector_store.client.scroll(
    collection_name=vector_store.collection_name,
    limit=5,
    with_payload=True,
    with_vectors=False
)

logger.info("样本点的 payload 信息:")
for point in result[0]:
    doc_id = point.payload.get("doc_id")
    logger.info(f"Point ID: {point.id}")
    logger.info(f"  doc_id 值: {doc_id}")
    logger.info(f"  doc_id 类型: {type(doc_id)}")
    logger.info(f"  完整 payload: {point.payload}")
    logger.info("")
