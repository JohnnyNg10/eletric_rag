"""
批量入库脚本

将指定目录下所有 .md 文件逐一入库，已存在的标准号自动跳过。
"""
import asyncio
import sys
import hashlib
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.db.models import Document

# 导入 ingest 主函数
from ingest_markdown import ingest, parse_markdown

MD_DIR = Path(r"D:\dl\测试数据\md")


def already_ingested(standard_no: str, doc_title: str) -> bool:
    """检查该标准是否已入库（按 standard_no 或 file_hash 判断）"""
    db = SessionLocal()
    try:
        if standard_no:
            exists = db.query(Document).filter(Document.standard_no == standard_no).first()
        else:
            fh = hashlib.md5(doc_title.encode()).hexdigest()
            exists = db.query(Document).filter(Document.file_hash == fh).first()
        return exists is not None
    finally:
        db.close()


async def batch_ingest():
    md_files = sorted(MD_DIR.glob("*.md"))
    total = len(md_files)
    print(f"发现 {total} 个 Markdown 文件，开始批量入库...\n{'='*60}")

    skipped = []
    success = []
    failed = []

    for idx, md_path in enumerate(md_files, 1):
        print(f"\n[{idx}/{total}] {md_path.name}")

        # 预读标题和标准号，判断是否跳过
        text = md_path.read_text(encoding='utf-8')
        doc_title, standard_no, _ = parse_markdown(text)
        print(f"  标题: {doc_title}")
        print(f"  标准号: {standard_no or '(未识别)'}")

        if already_ingested(standard_no, doc_title):
            print(f"  ⏭  已存在，跳过")
            skipped.append(md_path.name)
            continue

        try:
            await ingest(str(md_path))
            success.append(md_path.name)
        except Exception as e:
            print(f"  ❌ 入库失败: {e}")
            failed.append((md_path.name, str(e)))

    # 汇总
    print(f"\n{'='*60}")
    print(f"批量入库完成")
    print(f"  成功: {len(success)}")
    print(f"  跳过(已存在): {len(skipped)}")
    print(f"  失败: {len(failed)}")
    if failed:
        print(f"\n失败列表:")
        for name, err in failed:
            print(f"  {name}: {err}")


if __name__ == "__main__":
    asyncio.run(batch_ingest())
