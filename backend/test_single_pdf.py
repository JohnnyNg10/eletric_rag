"""
测试单个PDF处理
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal, init_db
from app.db.models import Document
from app.core.scan_processor.processor import ScannedPDFProcessor
from app.config import settings


async def test_single_pdf(pdf_path: str):
    """测试处理单个PDF"""

    print("=" * 60)
    print("测试扫描件PDF处理")
    print("=" * 60)

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"\n❌ 文件不存在: {pdf_path}")
        return

    print(f"\n文件: {pdf_file.name}")
    print(f"大小: {pdf_file.stat().st_size / 1024 / 1024:.2f} MB")

    # 1. 检查配置
    print("\n1. 配置检查:")
    print(f"   ENABLE_SCANNED_PDF: {settings.ENABLE_SCANNED_PDF}")
    print(f"   ENABLE_VLM_DESCRIPTION: {settings.ENABLE_VLM_DESCRIPTION}")
    print(f"   VLM_PROVIDER: {settings.VLM_PROVIDER}")
    print(f"   DOUBAO_MODEL: {settings.DOUBAO_MODEL}")

    if not settings.ENABLE_SCANNED_PDF:
        print("\n❌ ENABLE_SCANNED_PDF=False")
        return

    if not settings.ENABLE_VLM_DESCRIPTION:
        print("\n❌ ENABLE_VLM_DESCRIPTION=False")
        return

    # 2. 初始化数据库
    print("\n2. 初始化数据库...")
    try:
        init_db()
        print("   [OK] 数据库已就绪")
    except Exception as e:
        print(f"   [ERROR] 数据库初始化失败: {e}")
        return

    # 3. 创建文档记录
    print("\n3. 创建文档记录...")
    db = SessionLocal()
    try:
        doc = Document(
            title=pdf_file.stem,
            doc_type='standard',
            standard_no='DL/T 5255-2010',
            file_path=f"scanned_pdfs/{pdf_file.name}",
            file_size=pdf_file.stat().st_size,
            process_status='pending',
            is_scanned=True
        )
        db.add(doc)
        db.commit()
        doc_id = doc.id
        print(f"   [OK] 文档记录已创建: doc_id={doc_id}")
    except Exception as e:
        db.rollback()
        print(f"   [ERROR] 创建文档记录失败: {e}")
        return
    finally:
        db.close()

    # 4. 处理PDF（仅处理前3页作为测试）
    print(f"\n4. 开始处理PDF (仅前3页测试)...")
    print("   这可能需要几分钟，请耐心等待...\n")

    processor = ScannedPDFProcessor()

    try:
        # 临时修改处理器，只处理前3页
        original_process = processor.process_document

        async def process_first_3_pages(pdf_path, doc_id):
            # 转换PDF为图片
            page_images = await processor._pdf_to_images(pdf_path)
            print(f"   PDF总页数: {len(page_images)}")
            print(f"   测试处理: 前3页\n")

            # 只取前3页
            page_images = page_images[:3]

            # 上传原始PDF
            await processor._upload_original_pdf(pdf_path, doc_id)

            # 处理每一页
            page_results = []
            for page_num, img in enumerate(page_images, start=1):
                print(f"   处理第 {page_num} 页...")
                result = await processor._process_page_with_vlm(img, page_num, doc_id)
                page_results.append(result)

                if result.get('full_text'):
                    print(f"   [OK] 识别成功: {len(result['full_text'])} 字符")
                    print(f"     前100字: {result['full_text'][:100]}...")
                else:
                    print(f"   [WARN] 识别失败")
                print()

            # 保存结果
            print("   保存结果到数据库...")
            await processor._save_pages_as_image_chunks(page_results, doc_id)
            await processor._update_document_metadata(doc_id, page_results)

            # 生成Markdown
            full_markdown = processor._merge_pages_to_markdown(page_results)
            await processor._save_markdown(full_markdown, doc_id)

            return {
                'page_count': len(page_results),
                'image_count': len(page_results),
                'table_count': 0
            }

        result = await process_first_3_pages(str(pdf_file), doc_id)

        print("\n" + "=" * 60)
        print("[SUCCESS] 处理完成!")
        print("=" * 60)
        print(f"处理页数: {result['page_count']}")
        print(f"图片数量: {result['image_count']}")
        print(f"\n文档ID: {doc_id}")
        print("\n可以在数据库中查看结果:")
        print(f"  - documents 表: doc_id={doc_id}")
        print(f"  - images 表: document_id={doc_id}")
        print(f"  - chunks 表: document_id={doc_id}, content_type='image_description'")

    except Exception as e:
        print(f"\n[ERROR] 处理失败: {e}")
        import traceback
        traceback.print_exc()

        # 更新文档状态
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                doc.process_status = 'failed'
                doc.process_error = str(e)
                db.commit()
        finally:
            db.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python test_single_pdf.py <pdf文件路径>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    asyncio.run(test_single_pdf(pdf_path))
