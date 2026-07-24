"""
图片链接注入器

职责：
1. 为 image_description 类型的 Chunk 注入图片访问链接（路径 A）
2. 为 text/table Chunk 提取图号引用并注入 referenced_images（路径 B）
3. 图片伴随召回：将文本 Chunk 引用的图片对应的 image_description Chunk 拉入结果集
"""
import re
import asyncio
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session

from app.schemas.retrieval import ChunkResult, ImageRef
from app.db.models import Image, Chunk as DBChunk
from app.storage.object_store import object_store
import logging

logger = logging.getLogger(__name__)

# 图号正则：匹配 "图1"、"图5-2"、"图5.2"、"图 1"
_FIGURE_REF_RE = re.compile(r'图\s*(\d+(?:[.\-]\d+)*)')


def _build_image_url(minio_path: str, ttl: int) -> Optional[str]:
    """
    构建图片预签名 URL

    Args:
        minio_path: MinIO 路径，格式如 "images/GB20237-2006/p3_0.jpg"
        ttl: URL 过期时间（秒）

    Returns:
        预签名 URL，失败返回 None
    """
    try:
        return object_store.get_image_url(minio_path, expires_seconds=ttl)
    except Exception as e:
        logger.error(f"Failed to build image URL for {minio_path}: {e}")
        return None


async def inject_image_links(
    chunks: List[ChunkResult],
    db: Session,
    url_ttl: int = 3600,
) -> List[ChunkResult]:
    """
    为召回的 Chunk 注入图片链接

    路径 A：image_description Chunk → 查 chunk_id → Image → 注入单张图片字段
    路径 B：text/table Chunk → 提取图号引用 → 查 (document_id, figure_number) → 注入 referenced_images

    两路合并为一次函数调用，各做一次 batch DB 查询（在线程池中执行）

    Args:
        chunks: 召回的 Chunk 列表
        db: SQLAlchemy Session
        url_ttl: 预签名 URL 过期时间（秒）

    Returns:
        注入图片链接后的 Chunk 列表（原地修改）
    """
    if not chunks:
        return chunks

    # 在线程池中执行同步 DB 操作
    def _sync_inject():
        # ── 路径 A：image_description Chunk ──────────────────────────
        img_desc_chunks = [c for c in chunks if c.content_type == "image_description"]
        if img_desc_chunks:
            chunk_ids = [c.chunk_id for c in img_desc_chunks]
            imgs_by_chunk = {
                img.chunk_id: img
                for img in db.query(Image).filter(Image.chunk_id.in_(chunk_ids)).all()
            }
            for chunk in img_desc_chunks:
                img = imgs_by_chunk.get(chunk.chunk_id)
                if img and img.minio_path:
                    chunk.image_id = img.id
                    chunk.image_url = _build_image_url(img.minio_path, url_ttl)
                    chunk.image_page = img.page_number
                    chunk.image_figure_number = img.figure_number
                    chunk.image_caption = img.caption

        # ── 路径 B：text/table Chunk 的图号引用 ──────────────────────
        text_chunks = [c for c in chunks if c.content_type in ("text", "table")]
        if text_chunks:
            # 收集所有 (document_id, figure_number) 对
            refs: Dict[Tuple[int, str], List[ChunkResult]] = {}
            for chunk in text_chunks:
                for match in _FIGURE_REF_RE.finditer(chunk.content):
                    fig_no = f"图{match.group(1)}"
                    key = (chunk.document_id, fig_no)
                    refs.setdefault(key, []).append(chunk)

            if refs:
                # Batch 查询 Image 表
                doc_ids = list({k[0] for k in refs})
                fig_nos = list({k[1] for k in refs})
                found_imgs = (
                    db.query(Image)
                    .filter(
                        Image.document_id.in_(doc_ids),
                        Image.figure_number.in_(fig_nos),
                    )
                    .all()
                )
                imgs_by_key = {(img.document_id, img.figure_number): img for img in found_imgs}

                # 为每个引用注入 ImageRef
                for (doc_id, fig_no), target_chunks in refs.items():
                    img = imgs_by_key.get((doc_id, fig_no))
                    if img and img.minio_path:
                        url = _build_image_url(img.minio_path, url_ttl)
                        if url:
                            ref = ImageRef(
                                image_id=img.id,
                                image_url=url,
                                figure_number=img.figure_number,
                                caption=img.caption,
                                page_number=img.page_number,
                            )
                            for chunk in target_chunks:
                                # 去重：避免同一图片多次添加
                                if not any(r.image_id == ref.image_id for r in chunk.referenced_images):
                                    chunk.referenced_images.append(ref)

        return chunks

    # 在线程池中执行，避免阻塞事件循环
    return await asyncio.to_thread(_sync_inject)


async def pull_along_images(
    chunks: List[ChunkResult],
    db: Session,
    parent_score_ratio: float = 0.8,
) -> List[ChunkResult]:
    """
    图片伴随召回：确保生成层能看到配图，不依赖 image_description Chunk 是否被向量召回

    两种触发路径：
    1. 显式图号引用：text/table Chunk content 中含 "图N"，正则提取后查 Image 表
    2. 语义关联（入库预计算）：读取 Chunk.related_chunk_ids，直接拉取关联的 image_description Chunk

    Args:
        chunks: 召回的 Chunk 列表
        db: SQLAlchemy Session
        parent_score_ratio: 子块分数 = 父块分数 × 该比例（默认 0.8）

    Returns:
        追加了 image_description Chunk 的列表
    """
    if not chunks:
        return chunks

    # 在线程池中执行同步 DB 操作
    def _sync_pull():
        # 已在结果集中的 chunk_id，用于去重
        existing_ids = {c.chunk_id for c in chunks}

        # ── 路径1：显式图号引用 ────────────────────────────────────────
        refs: Dict[Tuple[int, str], float] = {}  # (doc_id, fig_no) → 父 chunk 最高分
        for chunk in chunks:
            if chunk.content_type not in ("text", "table"):
                continue
            for match in _FIGURE_REF_RE.finditer(chunk.content):
                fig_no = f"图{match.group(1)}"
                key = (chunk.document_id, fig_no)
                refs[key] = max(refs.get(key, 0.0), chunk.score)

        if refs:
            doc_ids = list({k[0] for k in refs})
            fig_nos = list({k[1] for k in refs})
            images = (
                db.query(Image)
                .filter(Image.document_id.in_(doc_ids), Image.figure_number.in_(fig_nos))
                .all()
            )
            img_chunk_to_fig = {
                img.chunk_id: (img.document_id, img.figure_number)
                for img in images if img.chunk_id and img.chunk_id not in existing_ids
            }
            if img_chunk_to_fig:
                db_chunks = db.query(DBChunk).filter(DBChunk.id.in_(list(img_chunk_to_fig.keys()))).all()
                for dbc in db_chunks:
                    key = img_chunk_to_fig.get(dbc.id)
                    parent_score = refs.get(key, 0.5) if key else 0.5
                    meta = dbc.meta_data or {}
                    chunks.append(ChunkResult(
                        chunk_id=dbc.id,
                        document_id=dbc.document_id,
                        content=dbc.content,
                        content_type="image_description",
                        score=round(parent_score * parent_score_ratio, 4),
                        recall_source="pull_along",
                        document_title=meta.get("document_title", ""),
                        standard_no=meta.get("standard_no"),
                        clause=dbc.clause,
                        page_start=dbc.page_start,
                        page_end=dbc.page_end,
                    ))
                    existing_ids.add(dbc.id)

        # ── 路径2：related_chunk_ids 语义关联 ─────────────────────────
        related_ids_map: Dict[int, float] = {}  # chunk_id → 父分数
        for chunk in chunks:
            if chunk.content_type not in ("text", "table"):
                continue
            if not chunk.related_chunk_ids:
                continue
            for rel_id in chunk.related_chunk_ids:
                if rel_id not in existing_ids:
                    related_ids_map[rel_id] = max(related_ids_map.get(rel_id, 0.0), chunk.score)

        if related_ids_map:
            db_chunks = (
                db.query(DBChunk)
                .filter(
                    DBChunk.id.in_(list(related_ids_map.keys())),
                    DBChunk.content_type == "image_description"
                )
                .all()
            )
            for dbc in db_chunks:
                parent_score = related_ids_map.get(dbc.id, 0.5)
                meta = dbc.meta_data or {}
                chunks.append(ChunkResult(
                    chunk_id=dbc.id,
                    document_id=dbc.document_id,
                    content=dbc.content,
                    content_type="image_description",
                    score=round(parent_score * parent_score_ratio, 4),
                    recall_source="pull_along_semantic",
                    document_title=meta.get("document_title", ""),
                    standard_no=meta.get("standard_no"),
                    clause=dbc.clause,
                    page_start=dbc.page_start,
                    page_end=dbc.page_end,
                ))
                existing_ids.add(dbc.id)

        return chunks

    # 在线程池中执行，避免阻塞事件循环
    return await asyncio.to_thread(_sync_pull)
