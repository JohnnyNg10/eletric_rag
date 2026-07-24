"""调试 chunk 4334 的图片注入问题"""
import logging
from app.db.session import SessionLocal
from app.db.models import Chunk, Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = SessionLocal()

try:
    # 查询 chunk
    chunk = db.query(Chunk).filter(Chunk.id == 4334).first()
    if chunk:
        logger.info(f"Chunk 4334:")
        logger.info(f"  content_type: {chunk.content_type}")
        logger.info(f"  content (first 200): {chunk.content[:200]}")
        logger.info(f"  document_id: {chunk.document_id}")

    # 查询关联的图片
    images = db.query(Image).filter(Image.chunk_id == 4334).all()
    logger.info(f"\nImages for chunk 4334: {len(images)} found")
    for img in images:
        logger.info(f"  Image {img.id}:")
        logger.info(f"    figure_number: {img.figure_number}")
        logger.info(f"    caption: {img.caption}")
        logger.info(f"    minio_path: {img.minio_path}")
        logger.info(f"    page_number: {img.page_number}")

finally:
    db.close()
