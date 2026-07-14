"""
查看MinIO中的扫描件图片
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.storage.object_store import object_store
from minio.error import S3Error

def list_scanned_images(doc_id: int):
    """列出指定文档的所有扫描图片"""

    bucket = object_store.image_bucket
    prefix = f"scanned_pages/doc_{doc_id}/"

    print(f"\n查看文档 {doc_id} 的扫描图片:")
    print(f"Bucket: {bucket}")
    print(f"路径: {prefix}")
    print("=" * 60)

    try:
        objects = object_store.client.list_objects(
            bucket,
            prefix=prefix,
            recursive=True
        )

        count = 0
        for obj in objects:
            count += 1
            size_mb = obj.size / 1024 / 1024
            print(f"\n{count}. {obj.object_name}")
            print(f"   大小: {size_mb:.2f} MB")
            print(f"   访问: http://localhost:9000/{bucket}/{obj.object_name}")

        if count == 0:
            print("\n未找到图片文件")
        else:
            print(f"\n总计: {count} 个文件")

    except S3Error as e:
        print(f"\n错误: {e}")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        doc_id = int(sys.argv[1])
    else:
        doc_id = 52  # 默认查看doc_id=52

    list_scanned_images(doc_id)
