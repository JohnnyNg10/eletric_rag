"""
重新提交pending状态的扫描件处理任务
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.db.models import Document
from app.tasks.scan_processor_tasks import process_scanned_pdf_task

def resubmit_pending_tasks():
    """重新提交所有pending状态的扫描件任务"""

    db = SessionLocal()
    try:
        # 查询所有pending状态的扫描件文档
        pending_docs = db.query(Document).filter(
            Document.is_scanned == True,
            Document.process_status == 'pending'
        ).all()

        print(f"找到 {len(pending_docs)} 个待处理文档")
        print("=" * 60)

        success_count = 0
        fail_count = 0

        for doc in pending_docs:
            print(f"\n[{doc.id}] {doc.title[:50]}...")
            print(f"  标准号: {doc.standard_no}")
            print(f"  文件路径: {doc.file_path}")

            # 构造完整路径
            base_dir = Path("../实际数据/DL")
            filename = doc.file_path.replace('scanned_pdfs/', '')
            full_path = base_dir / filename

            if not full_path.exists():
                print(f"  [ERROR] 文件不存在: {full_path}")
                fail_count += 1
                continue

            try:
                # 提交Celery任务
                task = process_scanned_pdf_task.delay(str(full_path.absolute()), doc.id)
                print(f"  [OK] 任务已提交: task_id={task.id}")
                success_count += 1
            except Exception as e:
                print(f"  [ERROR] 提交失败: {e}")
                fail_count += 1

        print("\n" + "=" * 60)
        print(f"提交完成:")
        print(f"  成功: {success_count}")
        print(f"  失败: {fail_count}")

    finally:
        db.close()


if __name__ == '__main__':
    resubmit_pending_tasks()
