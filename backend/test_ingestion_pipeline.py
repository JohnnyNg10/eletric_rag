"""
测试文档入库流水线
"""
import sys
import io
sys.path.append('.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.ingestion_pipeline import ingestion_pipeline
from pathlib import Path


def test_single_document_ingestion():
    """测试单个文档入库"""
    print("=== Testing Single Document Ingestion ===\n")

    # 查找测试 PDF
    pdf_dir = Path("../电力国标PDF")
    if not pdf_dir.exists():
        print(f"PDF directory not found: {pdf_dir}")
        return

    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print("No PDF files found")
        return

    # 选择第一个文件测试
    test_pdf = pdf_files[0]
    print(f"Testing with: {test_pdf.name}\n")

    # 执行入库
    result = ingestion_pipeline.ingest_document(
        pdf_path=str(test_pdf),
        use_llm_classification=False  # 使用规则分类
    )

    # 打印结果
    print("\n=== Ingestion Result ===")
    print(f"Success: {result['success']}")
    if result['success']:
        print(f"Document ID: {result['document_id']}")
        print(f"Chunks Count: {result['chunks_count']}")
        print(f"Message: {result['message']}")
    else:
        print(f"Error: {result.get('error')}")
        print(f"Message: {result['message']}")

    print("\n[PASS] Test completed!")


def test_batch_ingestion():
    """测试批量入库（前3个文件）"""
    print("=== Testing Batch Document Ingestion ===\n")

    # 查找测试 PDF
    pdf_dir = Path("../电力国标PDF")
    if not pdf_dir.exists():
        print(f"PDF directory not found: {pdf_dir}")
        return

    pdf_files = list(pdf_dir.glob("*.pdf"))[:3]  # 只测试前3个
    if not pdf_files:
        print("No PDF files found")
        return

    print(f"Testing with {len(pdf_files)} files:\n")
    for pdf in pdf_files:
        print(f"  - {pdf.name}")

    print("\nStarting batch ingestion...\n")

    # 创建临时测试目录
    import tempfile
    import shutil
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 复制测试文件
        for pdf in pdf_files:
            shutil.copy(pdf, tmp_path / pdf.name)

        # 执行批量入库
        result = ingestion_pipeline.batch_ingest(
            pdf_dir=str(tmp_path),
            use_llm_classification=False
        )

    # 打印结果
    print("\n=== Batch Ingestion Result ===")
    print(f"Total: {result['total']}")
    print(f"Success: {result['success']}")
    print(f"Failed: {result['failed']}")

    print("\nDetails:")
    for detail in result['details']:
        status = "✓" if detail['success'] else "✗"
        print(f"  {status} {detail['file']}: ", end="")
        if detail['success']:
            print(f"ID={detail['document_id']}, Chunks={detail['chunks_count']}")
        else:
            print(f"Error: {detail.get('error')}")

    print("\n[PASS] Batch test completed!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Test document ingestion pipeline')
    parser.add_argument('--mode', choices=['single', 'batch'], default='single',
                        help='Test mode: single or batch')
    args = parser.parse_args()

    if args.mode == 'single':
        test_single_document_ingestion()
    else:
        test_batch_ingestion()
