"""测试图片注入逻辑"""
import asyncio
import logging
from app.db.session import SessionLocal
from app.db.models import Chunk
from app.schemas.retrieval import ChunkResult
from app.core.retrieval.image_link_injector import inject_image_links

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_inject():
    db = SessionLocal()

    try:
        # 模拟召回了 chunk 4334
        chunk_db = db.query(Chunk).filter(Chunk.id == 4334).first()

        # 构造 ChunkResult
        chunk_result = ChunkResult(
            chunk_id=chunk_db.id,
            document_id=chunk_db.document_id,
            content=chunk_db.content,
            content_type=chunk_db.content_type,
            score=0.85,
            recall_source="test",
            document_title="GB 3836.16-2024",
            standard_no="GB 3836.16-2024",
        )

        logger.info(f"Before injection:")
        logger.info(f"  chunk_id: {chunk_result.chunk_id}")
        logger.info(f"  content_type: {chunk_result.content_type}")
        logger.info(f"  image_url: {chunk_result.image_url}")

        # 调用注入逻辑
        results = await inject_image_links([chunk_result], db)

        logger.info(f"\nAfter injection:")
        logger.info(f"  image_url: {results[0].image_url}")
        logger.info(f"  image_id: {results[0].image_id}")
        logger.info(f"  image_figure_number: {results[0].image_figure_number}")
        logger.info(f"  image_caption: {results[0].image_caption}")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_inject())
