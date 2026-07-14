"""检查 category 字段的实际字节"""
from app.db.session import SessionLocal
from app.db.models import Document

db = SessionLocal()
try:
    doc = db.query(Document).filter(
        Document.standard_no.like('%33982%')
    ).first()

    if doc:
        print(f"Standard No: {doc.standard_no}")
        print(f"Category (str): {doc.category}")
        print(f"Category (repr): {repr(doc.category)}")
        print(f"Category (hex): {doc.category.encode('utf-8').hex() if doc.category else 'None'}")
        print(f"Expected '继保' (hex): {'继保'.encode('utf-8').hex()}")

        # 检查是否相等
        print(f"\nEquals '继保': {doc.category == '继保'}")

        # 检查所有文档的 category
        print("\n=== All unique categories ===")
        categories = db.query(Document.category).distinct().all()
        for cat, in categories:
            if cat:
                print(f"{cat} | hex: {cat.encode('utf-8').hex()}")

finally:
    db.close()
