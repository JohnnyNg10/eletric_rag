"""
删除文档及其所有相关数据

删除范围：
1. MySQL: documents表（级联删除 chunks, images, tables）
2. Qdrant: 向量数据
3. Elasticsearch: BM25 索引
4. MinIO: PDF、Markdown、图片文件
"""
import asyncio
import sys
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.db.models import Document, Chunk, Image, Table
from app.storage.vector_store import vector_store
from app.storage.search_engine import search_engine
from app.storage.object_store import object_store
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def delete_document(doc_id: int):
    """删除文档及其所有相关数据"""

    db = SessionLocal()
    try:
        # 1. 查询文档信息
        logger.info(f"=== 查询文档 ID={doc_id} 的详细信息 ===")
        stmt = (
            select(Document)
            .options(
                selectinload(Document.chunks),
            )
            .where(Document.id == doc_id)
        )
        result = db.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            logger.error(f"文档 ID={doc_id} 不存在")
            return False

        logger.info(f"找到文档: {document.title}")
        logger.info(f"  - 标准号: {document.standard_no}")
        logger.info(f"  - 文件路径: {document.file_path}")
        logger.info(f"  - Markdown路径: {document.markdown_path}")
        logger.info(f"  - 图片前缀: {document.images_prefix}")
        logger.info(f"  - 关联的 chunks: {len(document.chunks)}")

        # 查询关联的图片和表格
        images = db.execute(select(Image).where(Image.document_id == doc_id)).scalars().all()
        tables = db.execute(select(Table).where(Table.document_id == doc_id)).scalars().all()
        logger.info(f"  - 关联的 images: {len(images)}")
        logger.info(f"  - 关联的 tables: {len(tables)}")

        # 2. 从 Qdrant 删除向量
        logger.info(f"\n=== 从 Qdrant 删除向量 ===")
        vector_deleted = vector_store.delete_by_doc_id(str(doc_id))
        if vector_deleted:
            logger.info(f"✓ Qdrant 向量删除成功")
        else:
            logger.warning(f"✗ Qdrant 向量删除失败（可能不存在）")

        # 3. 从 Elasticsearch 删除索引
        logger.info(f"\n=== 从 Elasticsearch 删除索引 ===")
        es_deleted = search_engine.delete_by_doc_id(str(doc_id))
        if es_deleted:
            logger.info(f"✓ Elasticsearch 索引删除成功")
        else:
            logger.warning(f"✗ Elasticsearch 索引删除失败（可能不存在）")

        # 4. 从 MinIO 删除文件
        logger.info(f"\n=== 从 MinIO 删除文件 ===")

        # 删除 PDF 文件
        if document.file_path:
            pdf_deleted = object_store.delete_object(
                bucket_name=object_store.pdf_bucket,
                object_name=document.file_path
            )
            if pdf_deleted:
                logger.info(f"✓ 删除 PDF: {document.file_path}")
            else:
                logger.warning(f"✗ 删除 PDF 失败: {document.file_path}")

        # 删除 Markdown 文件
        if document.markdown_path:
            md_deleted = object_store.delete_object(
                bucket_name=object_store.markdown_bucket,
                object_name=document.markdown_path
            )
            if md_deleted:
                logger.info(f"✓ 删除 Markdown: {document.markdown_path}")
            else:
                logger.warning(f"✗ 删除 Markdown 失败: {document.markdown_path}")

        # 删除图片文件
        if images:
            for img in images:
                if img.minio_path:
                    img_deleted = object_store.delete_object(
                        bucket_name=object_store.image_bucket,
                        object_name=img.minio_path
                    )
                    if img_deleted:
                        logger.info(f"✓ 删除图片: {img.minio_path}")
                    else:
                        logger.warning(f"✗ 删除图片失败: {img.minio_path}")

        # 删除表格文件（表格也存在 image_bucket 中）
        if tables:
            for tbl in tables:
                if tbl.minio_path:
                    tbl_deleted = object_store.delete_object(
                        bucket_name=object_store.image_bucket,
                        object_name=tbl.minio_path
                    )
                    if tbl_deleted:
                        logger.info(f"✓ 删除表格: {tbl.minio_path}")
                    else:
                        logger.warning(f"✗ 删除表格失败: {tbl.minio_path}")

        # 如果有图片前缀，尝试批量删除该前缀下的所有文件
        if document.images_prefix:
            logger.info(f"尝试删除前缀下的所有文件: {document.images_prefix}")
            objects = object_store.list_objects(
                bucket_name=object_store.image_bucket,
                prefix=document.images_prefix
            )
            logger.info(f"找到 {len(objects)} 个文件")
            for obj in objects:
                obj_deleted = object_store.delete_object(
                    bucket_name=object_store.image_bucket,
                    object_name=obj["object_name"]
                )
                if obj_deleted:
                    logger.info(f"✓ 删除: {obj['object_name']}")

        # 5. 从数据库删除文档（级联删除 chunks, images, tables）
        logger.info(f"\n=== 从数据库删除文档记录 ===")
        logger.info(f"数据库的 CASCADE 会自动删除:")
        logger.info(f"  - {len(document.chunks)} 个 chunks")
        logger.info(f"  - {len(images)} 个 images")
        logger.info(f"  - {len(tables)} 个 tables")

        db.delete(document)
        db.commit()
        logger.info(f"✓ 数据库记录删除成功")

        logger.info(f"\n=== 删除完成 ===")
        logger.info(f"文档 ID={doc_id} 及其所有相关数据已删除")
        return True

    except Exception as e:
        logger.error(f"删除失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        db.rollback()
        return False

    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python delete_document.py <doc_id>")
        print("示例: python delete_document.py 70")
        sys.exit(1)

    try:
        doc_id = int(sys.argv[1])
    except ValueError:
        print("错误: doc_id 必须是整数")
        sys.exit(1)

    print(f"准备删除文档 ID={doc_id} 及其所有相关数据...")
    print("这将删除:")
    print("  - 数据库记录（documents, chunks, images, tables）")
    print("  - Qdrant 向量数据")
    print("  - Elasticsearch 索引")
    print("  - MinIO 文件（PDF、Markdown、图片、表格）")
    print()

    confirm = input(f"确认删除文档 ID={doc_id}? (yes/no): ")
    if confirm.lower() != "yes":
        print("取消删除")
        sys.exit(0)

    asyncio.run(delete_document(doc_id))
