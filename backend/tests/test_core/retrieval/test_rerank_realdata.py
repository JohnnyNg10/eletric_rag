"""
使用真实知识库数据测试重排层
"""
import asyncio
import sys
import logging
from pathlib import Path

# 关闭SQLAlchemy日志
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

from app.db.session import SessionLocal
from app.db.models import Chunk, Document
from app.schemas.retrieval import ChunkResult
from app.core.retrieval.rerank import TwoStageReranker
from app.core.retrieval.sufficiency import SufficiencyChecker

async def main():
    db = SessionLocal()

    try:
        # 从数据库取真实的chunks
        chunks_with_docs = db.query(Chunk, Document).join(
            Document, Chunk.document_id == Document.id
        ).limit(50).all()

        if not chunks_with_docs:
            print("No chunks found in database")
            return

        print(f"Loaded {len(chunks_with_docs)} real chunks from database")

        # 转换为ChunkResult
        candidates = []
        for chunk, doc in chunks_with_docs:
            if chunk.content and len(chunk.content) > 10:
                candidates.append(ChunkResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content[:500],
                    score=0.75,
                    document_title=doc.title,
                    standard_no=doc.standard_no,
                    doc_type=doc.doc_type,
                    clause=chunk.clause,
                    chapter=chunk.chapter,
                    recall_source="vector"
                ))

        print(f"Valid candidates with content: {len(candidates)}")
        if candidates:
            print(f"Sample: chunk_id={candidates[0].chunk_id}, doc={candidates[0].document_title[:30] if candidates[0].document_title else 'N/A'}")
            content_preview = candidates[0].content[:60].encode('ascii', errors='replace').decode('ascii')
            print(f"  content: {content_preview}...")

        # 测试1: 两阶段重排
        print("\n" + "="*50)
        print("Test: Two-Stage Reranker with real data")
        print("="*50)

        query = "GB 1002 standard requirements for plugs and sockets"

        reranker = TwoStageReranker(
            coarse_threshold=0.1,  # 低阈值以保证有结果
            fine_threshold=0.1,
            coarse_top_k=20,
            fine_top_k=5,
            enable_cache=False
        )

        import time
        start = time.time()
        results = await reranker.rerank(
            query=query,
            candidates=candidates,
            top_k=5
        )
        elapsed = int((time.time() - start) * 1000)

        print(f"\nQuery: {query}")
        print(f"Input: {len(candidates)} candidates")
        print(f"Output: {len(results)} reranked results")
        print(f"Time: {elapsed}ms")
        print("\nTop results:")
        for i, r in enumerate(results, 1):
            print(f"  {i}. chunk_id={r.chunk_id}, score={r.score:.4f}")
            content = r.content[:60].encode('ascii', errors='replace').decode('ascii')
            print(f"     content: {content}...")

        # 测试2: 充分性判断
        print("\n" + "="*50)
        print("Test: SufficiencyChecker with real data")
        print("="*50)

        if results:
            checker = SufficiencyChecker(
                rule_top1_threshold=0.05,  # 很低的阈值以便进入LLM判断
                llm_timeout=5.0
            )

            suf_result = await checker.check(query, results)
            print(f"\nSufficiency result:")
            print(f"  sufficient: {suf_result.sufficient}")
            print(f"  source: {suf_result.source}")
            print(f"  confidence: {suf_result.confidence:.2f}")
            print(f"  gaps: {suf_result.gaps}")

        print("\n[SUCCESS] Real data test completed")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
