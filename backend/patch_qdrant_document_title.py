"""
一次性脚本：为 Qdrant 中已有的向量点补写 document_title payload 字段

通过 standard_no → MySQL documents.title 映射，批量 set_payload。
运行一次即可，后续新入库的文档已在 ingest_markdown.py 中写入。
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
sys.stdout.reconfigure(encoding='utf-8')

from app.db.session import SessionLocal
from app.db.models import Document
from app.storage.vector_store import VectorStore
from qdrant_client.models import Filter, FieldCondition, MatchValue


def build_standard_no_to_title() -> dict:
    """从 MySQL 读取 standard_no → title 映射"""
    db = SessionLocal()
    try:
        rows = db.query(Document.standard_no, Document.title).filter(
            Document.standard_no.isnot(None)
        ).all()
        return {row.standard_no: row.title for row in rows}
    finally:
        db.close()


def patch_qdrant_titles(mapping: dict):
    """遍历 Qdrant 所有点，按 standard_no 补写 document_title"""
    vs = VectorStore()
    client = vs.client
    collection = vs.collection_name

    for standard_no, title in mapping.items():
        print(f"\n处理标准：{standard_no} → {title}")

        offset = None
        updated = 0

        while True:
            result = client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="standard_no", match=MatchValue(value=standard_no))]
                ),
                limit=200,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points, next_offset = result

            if not points:
                break

            # 筛出 document_title 缺失或为空的点
            ids_to_update = [
                p.id for p in points
                if not p.payload.get("document_title")
            ]

            if ids_to_update:
                client.set_payload(
                    collection_name=collection,
                    payload={"document_title": title},
                    points=ids_to_update,
                )
                updated += len(ids_to_update)

            if next_offset is None:
                break
            offset = next_offset

        print(f"  更新了 {updated} 个向量点")


if __name__ == "__main__":
    print("读取 MySQL 标准号 → 标题映射...")
    mapping = build_standard_no_to_title()
    print(f"共 {len(mapping)} 条标准：{list(mapping.keys())}")

    print("\n开始更新 Qdrant payload...")
    patch_qdrant_titles(mapping)

    print("\n✅ 完成")
