"""检查数据库和ES的编码问题"""
from app.db.session import SessionLocal
from app.db.models import Document, Chunk
from app.storage.search_engine import search_engine

db = SessionLocal()
try:
    # 1. 检查数据库字符集
    result = db.execute("SHOW VARIABLES LIKE 'character_set%'")
    print("=== Database Character Set ===")
    for row in result:
        print(f"  {row[0]}: {row[1]}")

    print("\n=== Table Character Set ===")
    result = db.execute("SHOW CREATE TABLE documents")
    for row in result:
        print(row[1][:500])

    # 2. 检查文档的 category 原始字节
    doc = db.query(Document).filter(Document.standard_no.like('%33982%')).first()
    if doc:
        print(f"\n=== Document Category ===")
        print(f"  Python repr: {repr(doc.category)}")
        print(f"  Bytes: {doc.category.encode('latin1') if doc.category else None}")

        # 尝试修复编码
        try:
            fixed = doc.category.encode('latin1').decode('utf-8')
            print(f"  Fixed (latin1->utf8): {fixed}")
        except:
            print(f"  Cannot fix with latin1->utf8")

    # 3. 检查所有唯一的 category 值
    print("\n=== All Categories in DB ===")
    categories = db.query(Document.category).distinct().all()
    for cat in categories:
        print(f"  {repr(cat[0])}")

finally:
    db.close()

# 4. 检查 ES 索引
print("\n=== Elasticsearch Index ===")
try:
    # 搜索文档
    es_result = search_engine.search(
        query={"match": {"standard_no": "33982"}},
        index="documents",
        size=1
    )
    if es_result:
        print(f"Found {len(es_result)} docs in ES")
        for hit in es_result:
            print(f"  category: {repr(hit.get('category'))}")
            print(f"  text preview: {hit.get('text', '')[:100]}")
except Exception as e:
    print(f"ES error: {e}")
