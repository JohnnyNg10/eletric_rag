"""
MinIO 对象存储客户端

支持：
- 原始 PDF 文件存储
- Markdown 文件存储
- 图片文件存储
"""
from typing import Optional, BinaryIO
from minio import Minio
from minio.error import S3Error
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class ObjectStore:
    """MinIO 对象存储封装"""

    def __init__(self):
        self.client = Minio(
            f"{settings.MINIO_HOST}:{settings.MINIO_PORT}",
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False  # 本地开发使用 HTTP
        )

        # 三个 bucket
        self.pdf_bucket = "electric-rag-pdfs"
        self.markdown_bucket = "electric-rag-markdown"
        self.image_bucket = "electric-rag-images"

    def create_buckets_if_not_exist(self):
        """创建所有必要的 buckets"""
        buckets = [self.pdf_bucket, self.markdown_bucket, self.image_bucket]

        for bucket in buckets:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                    logger.info(f"Bucket {bucket} created")
                else:
                    logger.info(f"Bucket {bucket} already exists")
            except S3Error as e:
                logger.error(f"Failed to create bucket {bucket}: {e}")
                raise

    def upload_pdf(
        self,
        file_path: str,
        object_name: Optional[str] = None
    ) -> bool:
        """
        上传 PDF 文件

        Args:
            file_path: 本地文件路径
            object_name: 对象名称（如 "standards/GB/GB_1002-2024.pdf"）
                        如果不指定，使用文件名

        Returns:
            bool: 是否成功
        """
        try:
            if object_name is None:
                object_name = Path(file_path).name

            self.client.fput_object(
                bucket_name=self.pdf_bucket,
                object_name=object_name,
                file_path=file_path,
                content_type="application/pdf"
            )

            logger.info(f"Uploaded PDF: {object_name}")
            return True

        except S3Error as e:
            logger.error(f"Failed to upload PDF: {e}")
            return False

    def upload_markdown(
        self,
        content: str,
        object_name: str
    ) -> bool:
        """
        上传 Markdown 文件

        Args:
            content: Markdown 内容
            object_name: 对象名称（如 "standards/GB/GB_1002-2024/full.md"）

        Returns:
            bool: 是否成功
        """
        try:
            from io import BytesIO

            content_bytes = content.encode('utf-8')
            content_stream = BytesIO(content_bytes)

            self.client.put_object(
                bucket_name=self.markdown_bucket,
                object_name=object_name,
                data=content_stream,
                length=len(content_bytes),
                content_type="text/markdown"
            )

            logger.info(f"Uploaded Markdown: {object_name}")
            return True

        except S3Error as e:
            logger.error(f"Failed to upload Markdown: {e}")
            return False

    def upload_image(
        self,
        file_path: str,
        object_name: str
    ) -> bool:
        """
        上传图片文件

        Args:
            file_path: 本地图片路径
            object_name: 对象名称（如 "GB_1002-2024/page_015_fig_01.png"）

        Returns:
            bool: 是否成功
        """
        try:
            # 根据文件扩展名确定 content type
            ext = Path(file_path).suffix.lower()
            content_type_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".svg": "image/svg+xml"
            }
            content_type = content_type_map.get(ext, "application/octet-stream")

            self.client.fput_object(
                bucket_name=self.image_bucket,
                object_name=object_name,
                file_path=file_path,
                content_type=content_type
            )

            logger.info(f"Uploaded image: {object_name}")
            return True

        except S3Error as e:
            logger.error(f"Failed to upload image: {e}")
            return False

    def download_pdf(
        self,
        object_name: str,
        file_path: str
    ) -> bool:
        """
        下载 PDF 文件

        Args:
            object_name: 对象名称
            file_path: 本地保存路径

        Returns:
            bool: 是否成功
        """
        try:
            self.client.fget_object(
                bucket_name=self.pdf_bucket,
                object_name=object_name,
                file_path=file_path
            )

            logger.info(f"Downloaded PDF: {object_name} -> {file_path}")
            return True

        except S3Error as e:
            logger.error(f"Failed to download PDF: {e}")
            return False

    def get_pdf_url(
        self,
        object_name: str,
        expires_seconds: int = 3600
    ) -> Optional[str]:
        """
        获取 PDF 预签名 URL（用于临时访问）

        Args:
            object_name: 对象名称
            expires_seconds: 过期时间（秒）

        Returns:
            str: 预签名 URL
        """
        try:
            from datetime import timedelta

            url = self.client.presigned_get_object(
                bucket_name=self.pdf_bucket,
                object_name=object_name,
                expires=timedelta(seconds=expires_seconds)
            )
            return url

        except S3Error as e:
            logger.error(f"Failed to get PDF URL: {e}")
            return None

    def delete_object(
        self,
        bucket_name: str,
        object_name: str
    ) -> bool:
        """删除对象"""
        try:
            self.client.remove_object(
                bucket_name=bucket_name,
                object_name=object_name
            )

            logger.info(f"Deleted object: {bucket_name}/{object_name}")
            return True

        except S3Error as e:
            logger.error(f"Failed to delete object: {e}")
            return False

    def list_objects(
        self,
        bucket_name: str,
        prefix: Optional[str] = None
    ) -> list:
        """
        列出对象

        Args:
            bucket_name: bucket 名称
            prefix: 前缀过滤（如 "standards/GB/"）

        Returns:
            对象列表
        """
        try:
            objects = self.client.list_objects(
                bucket_name=bucket_name,
                prefix=prefix,
                recursive=True
            )

            return [
                {
                    "object_name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified
                }
                for obj in objects
            ]

        except S3Error as e:
            logger.error(f"Failed to list objects: {e}")
            return []


# 全局实例
object_store = ObjectStore()
