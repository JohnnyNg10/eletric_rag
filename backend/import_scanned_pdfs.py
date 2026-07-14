"""
导入扫描件PDF脚本
示例用法: python import_scanned_pdfs.py --dir "实际数据/DL" --doc-type standard
"""
import argparse
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal, init_db
from app.db.models import Document
from app.tasks.scan_processor_tasks import process_scanned_pdf_task
from app.config import settings


async def import_single_pdf(pdf_path: Path, doc_type: str = 'standard'):
    """
    导入单个扫描件PDF

    Args:
        pdf_path: PDF文件路径
        doc_type: 文档类型
    """
    print(f"\n处理文件: {pdf_path.name}")

    db = SessionLocal()
    try:
        # 1. 创建文档记录
        doc = Document(
            title=pdf_path.stem,  # 文件名作为标题
            doc_type=doc_type,
            file_path=f"scanned_pdfs/{pdf_path.name}",
            file_size=pdf_path.stat().st_size,
            process_status='pending',
            is_scanned=True
        )

        # 提取标准号（如 DL_T_5806-2020）
        if doc_type == 'standard':
            # DL/T 5806-2020 或 DL_T_5806-2020
            filename = pdf_path.stem
            standard_no = filename.replace('_', '/').replace(' ', '')
            doc.standard_no = standard_no

        db.add(doc)
        db.commit()
        doc_id = doc.id

        print(f"✓ 文档记录已创建: doc_id={doc_id}, standard_no={doc.standard_no}")

        # 2. 提交异步处理任务
        if settings.ENABLE_SCANNED_PDF:
            print(f"  提交处理任务...")
            task = process_scanned_pdf_task.delay(str(pdf_path.absolute()), doc_id)
            print(f"  任务ID: {task.id}")
            print(f"  状态: 已提交到Celery队列")
        else:
            print(f"  警告: ENABLE_SCANNED_PDF=False，跳过处理")

    except Exception as e:
        db.rollback()
        print(f"✗ 导入失败: {e}")
        raise
    finally:
        db.close()


async def import_directory(directory: Path, doc_type: str = 'standard'):
    """
    批量导入目录下的所有PDF

    Args:
        directory: 目录路径
        doc_type: 文档类型
    """
    pdf_files = list(directory.glob("*.pdf"))

    if not pdf_files:
        print(f"未找到PDF文件: {directory}")
        return

    print(f"\n找到 {len(pdf_files)} 个PDF文件")
    print(f"目录: {directory}")
    print(f"文档类型: {doc_type}")
    print("-" * 60)

    for pdf_path in pdf_files:
        try:
            await import_single_pdf(pdf_path, doc_type)
        except Exception as e:
            print(f"处理 {pdf_path.name} 失败: {e}")
            continue

    print("\n" + "=" * 60)
    print(f"导入完成: {len(pdf_files)} 个文件")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='导入扫描件PDF到系统')
    parser.add_argument('--dir', required=True, help='PDF文件目录')
    parser.add_argument('--doc-type', default='standard', choices=['standard', 'textbook', 'manual', 'regulation'],
                        help='文档类型（默认: standard）')
    parser.add_argument('--init-db', action='store_true', help='初始化数据库（首次运行时使用）')

    args = parser.parse_args()

    directory = Path(args.dir)
    if not directory.exists():
        print(f"错误: 目录不存在 - {directory}")
        sys.exit(1)

    # 检查配置
    print("\n" + "=" * 60)
    print("配置检查")
    print("=" * 60)
    print(f"ENABLE_SCANNED_PDF: {settings.ENABLE_SCANNED_PDF}")
    print(f"ENABLE_VLM_DESCRIPTION: {settings.ENABLE_VLM_DESCRIPTION}")
    print(f"VLM_PROVIDER: {settings.VLM_PROVIDER}")
    print(f"VLM API Key配置: {'✓' if settings.DOUBAO_API_KEY or settings.QWEN_API_KEY else '✗ 未配置'}")

    if not settings.ENABLE_SCANNED_PDF:
        print("\n警告: ENABLE_SCANNED_PDF=False，文档将创建但不会被处理")
        print("请在 .env 中设置: ENABLE_SCANNED_PDF=true")

    if not settings.ENABLE_VLM_DESCRIPTION:
        print("\n警告: ENABLE_VLM_DESCRIPTION=False，将无法生成图片描述")
        print("请在 .env 中设置:")
        print("  ENABLE_VLM_DESCRIPTION=true")
        print("  VLM_PROVIDER=doubao")
        print("  DOUBAO_API_KEY=your_key")

    # 初始化数据库
    if args.init_db:
        print("\n初始化数据库...")
        init_db()
        print("✓ 数据库初始化完成")

    # 导入PDF
    asyncio.run(import_directory(directory, args.doc_type))


if __name__ == '__main__':
    main()
