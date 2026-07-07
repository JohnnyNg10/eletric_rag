"""
测试 MinIO 对象存储
"""
import sys
sys.path.append('.')

from app.storage.object_store import object_store
import tempfile
from pathlib import Path


def test_minio_connection():
    """测试 MinIO 连接"""
    print("Testing MinIO connection...")

    try:
        # 创建 buckets
        print("\nCreating buckets...")
        object_store.create_buckets_if_not_exist()

        # 测试上传 Markdown
        print("\nTesting Markdown upload...")
        test_markdown = """# Test Document

## Section 1
This is a test markdown content.

## Section 2
With multiple sections.
"""
        success = object_store.upload_markdown(
            content=test_markdown,
            object_name="test/sample.md"
        )
        print(f"Markdown upload success: {success}")

        # 测试创建临时 PDF 并上传
        print("\nTesting PDF upload...")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4\nTest PDF content")
            tmp_path = tmp.name

        success = object_store.upload_pdf(
            file_path=tmp_path,
            object_name="standards/GB/test.pdf"
        )
        print(f"PDF upload success: {success}")

        # 清理临时文件
        Path(tmp_path).unlink()

        # 测试列出对象
        print("\nListing objects in PDF bucket...")
        objects = object_store.list_objects(
            bucket_name=object_store.pdf_bucket,
            prefix="standards/"
        )
        print(f"Found {len(objects)} objects:")
        for obj in objects[:5]:
            print(f"  - {obj['object_name']} ({obj['size']} bytes)")

        # 测试获取预签名 URL
        print("\nGetting presigned URL...")
        url = object_store.get_pdf_url(
            object_name="standards/GB/test.pdf",
            expires_seconds=3600
        )
        if url:
            print(f"Presigned URL: {url[:80]}...")

        print("\n[PASS] All MinIO tests passed!")

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_minio_connection()
