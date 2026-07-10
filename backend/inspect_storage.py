"""查看知识库中存储的内容"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.storage.vector_store import vector_store
from app.storage.search_engine import search_engine
from app.db.session import SessionLocal
from app.db.models import Document, Chunk
import logging
logging.basicConfig(level=logging.WARNING)


def inspect():
    print("\n" + "="*60)
    print("知识库内容检查")
    print("="*60)

    # 1. MySQL 概览
    print("\n【MySQL】")
    db = SessionLocal()
    try:
        docs = db.query(Document).all()
        print(f"  文档数：{len(docs)}")
        for doc in docs:
            chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
            parents  = [c for c in chunks if c.chunk_type == 'parent']
            children = [c for c in chunks if c.chunk_type == 'child']
            tables   = [c for c in chunks if c.meta_data and c.meta_data.get('is_table')]
            print(f"\n  ┌ 文档 ID={doc.id}: {doc.title}")
            print(f"  │ 标准号：{doc.standard_no}  状态：{doc.status}")
            print(f"  │ chunk总数：{len(chunks)}（父块{len(parents)} / 子块{len(children)} / 表格{len(tables)}）")

            # 抽样父块
            print(f"  │ 父块（前5）：")
            for c in parents[:5]:
                preview = (c.content or "")[:80].replace('\n', ' ')
                print(f"  │   [{c.chapter}] {preview}...")

            # 表格块
            if tables:
                print(f"  │ 表格块（全部）：")
                for c in tables:
                    title = c.meta_data.get('table_title', '')
                    preview = (c.content or "")[:60].replace('\n', ' ')
                    print(f"  │   {title} → {preview}...")

            # 抽样子块
            print(f"  │ 子块（前5）：")
            for c in children[:5]:
                preview = (c.content or "")[:80].replace('\n', ' ')
                print(f"  │   [{c.clause}] {preview}...")
            print(f"  └──")

    finally:
        db.close()

    # 2. Qdrant 概览
    print("\n【Qdrant】")
    info = vector_store.get_collection_info()
    print(f"  collection: {info.get('name')}  点数: {info.get('points_count')}  状态: {info.get('status')}")

    # 抽取几个点看 payload 结构
    try:
        sample = vector_store.client.scroll(
            collection_name=vector_store.collection_name,
            limit=3,
            with_payload=True,
            with_vectors=False,
        )[0]
        print(f"  抽样payload（前3条）：")
        for pt in sample:
            p = pt.payload
            preview = (p.get('text') or '')[:80].replace('\n', ' ')
            print(f"    id={str(pt.id)[:8]}… type={p.get('chunk_type')} clause={p.get('clause')} is_table={p.get('is_table')}")
            print(f"    text: {preview}...")
    except Exception as e:
        print(f"  抽样失败: {e}")

    # 3. Elasticsearch 概览
    print("\n【Elasticsearch】")
    try:
        # 强制刷新再查
        search_engine.client.indices.refresh(index=search_engine.index_name)
        stats = search_engine.get_index_stats()
        print(f"  index: {stats.get('index_name')}  文档数: {stats.get('docs_count')}  大小: {stats.get('store_size')} bytes")

        # 按 chunk_type 统计
        agg_resp = search_engine.client.search(
            index=search_engine.index_name,
            body={
                "size": 0,
                "aggs": {
                    "by_type": {"terms": {"field": "chunk_type"}},
                    "by_table": {"terms": {"field": "is_table"}}
                }
            }
        )
        for bucket in agg_resp["aggregations"]["by_type"]["buckets"]:
            print(f"    chunk_type={bucket['key']}: {bucket['doc_count']} 条")
        for bucket in agg_resp["aggregations"]["by_table"]["buckets"]:
            print(f"    is_table={bucket['key']}: {bucket['doc_count']} 条")
    except Exception as e:
        print(f"  查询失败: {e}")

    print("\n" + "="*60)


if __name__ == "__main__":
    inspect()
