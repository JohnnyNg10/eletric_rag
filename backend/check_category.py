"""检查 GB/T 33982-2017 的 category"""
from app.db.session import SessionLocal
from app.db.models import Document

db = SessionLocal()
try:
    # 查找文档
    doc = db.query(Document).filter(
        Document.standard_no.like('%33982%')
    ).first()

    if doc:
        print(f"Document found:")
        print(f"  ID: {doc.id}")
        print(f"  Standard No: {doc.standard_no}")
        print(f"  Title: {doc.title}")
        print(f"  Category: {doc.category}")
        print(f"  Status: {doc.status}")
        print(f"  Chunk count: {doc.chunk_count}")
    else:
        print("Document not found")

        # 列出所有文档的 category
        print("\nAll document categories:")
        docs = db.query(Document.standard_no, Document.category).limit(20).all()
        for d in docs:
            print(f"  {d.standard_no}: {d.category}")

finally:
    db.close()
