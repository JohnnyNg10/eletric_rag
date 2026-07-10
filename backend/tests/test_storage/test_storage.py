"""
存储层集成测试

测试内容：
1. Qdrant 向量数据库连接与存储
2. Elasticsearch 全文检索连接与存储
3. MinIO 对象存储连接与存储
"""
import asyncio
import sys

from pathlib import Path

# 添加项目根目录到 Python 路径

from app.storage.vector_store import vector_store
from app.storage.search_engine import search_engine
from app.storage.object_store import object_store
from app.core.embedding.embedder import embedder
import logging
import time
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_storage_connections():
    """测试存储系统连接"""
    print("\n" + "="*60)
    print("1. 测试存储系统连接")
    print("="*60)

    # 测试 Qdrant
    try:
        vector_store.create_collection_if_not_exists()
        info = vector_store.get_collection_info()
        print(f"✓ Qdrant 连接成功")
        print(f"  - Collection: {info.get('name', 'N/A')}")
        print(f"  - Points count: {info.get('points_count', 0)}")
        print(f"  - Status: {info.get('status', 'N/A')}")
    except Exception as e:
        print(f"✗ Qdrant 连接失败: {e}")
        return False

    # 测试 Elasticsearch
    try:
        search_engine.create_index_if_not_exists()
        stats = search_engine.get_index_stats()
        print(f"✓ Elasticsearch 连接成功")
        print(f"  - Index: {stats.get('index_name', 'N/A')}")
        print(f"  - Docs count: {stats.get('docs_count', 0)}")
        print(f"  - Store size: {stats.get('store_size', 0)} bytes")
    except Exception as e:
        print(f"✗ Elasticsearch 连接失败: {e}")
        return False

    # 测试 MinIO
    try:
        object_store.create_buckets_if_not_exist()
        print(f"✓ MinIO 连接成功")
        print(f"  - PDF bucket: {object_store.pdf_bucket}")
        print(f"  - Markdown bucket: {object_store.markdown_bucket}")
        print(f"  - Image bucket: {object_store.image_bucket}")
    except Exception as e:
        print(f"✗ MinIO 连接失败: {e}")
        return False

    return True

async def test_parsed_content_storage():
    """测试解析内容的存储"""
    print("\n" + "="*60)
    print("2. 测试解析内容存储")
    print("="*60)

    # 读取已解析的内容
    parsed_file = Path("parsed_content.txt")
    if not parsed_file.exists():
        print(f"✗ 解析文件不存在: {parsed_file}")
        return False

    with open(parsed_file, 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"✓ 读取解析内容: {len(content)} 字符")

    # 简单分块（每500字符一块，用于测试）
    chunk_size = 500
    chunks = []

    for i in range(0, min(len(content), 3000), chunk_size):  # 只取前3000字符做测试
        chunk_text = content[i:i+chunk_size]
        if chunk_text.strip():
            chunks.append({
                "text": chunk_text,
                "chunk_index": len(chunks),
                "start_pos": i
            })

    print(f"✓ 分块完成: {len(chunks)} 个块")

    # 为每个块生成向量和存储
    doc_id = "GB7958-2014"
    stored_chunks = []

    print(f"\n开始存储测试（共 {len(chunks)} 个块）...")

    for idx, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}_chunk_{idx}"
        chunk_text = chunk["text"]

        print(f"\n处理块 {idx + 1}/{len(chunks)}...")
        print(f"  文本预览: {chunk_text[:100]}...")

        # 生成向量
        try:
            dense_vector = embedder.encode(chunk_text).tolist()
            print(f"  ✓ 生成稠密向量: {len(dense_vector)} 维")
        except Exception as e:
            print(f"  ✗ 生成向量失败: {e}")
            continue

        # 存入 Qdrant
        try:
            point = {
                "id": chunk_id,
                "dense_vector": dense_vector,
                "sparse_vector": {"indices": [], "values": []},  # 暂不使用稀疏向量
                "payload": {
                    "doc_id": doc_id,
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "standard_no": "GB 7958-2014",
                    "category": "safety_equipment",
                    "chunk_index": idx,
                    "char_count": len(chunk_text)
                }
            }

            success = vector_store.upsert_points([point])
            if success:
                print(f"  ✓ 存入 Qdrant")
            else:
                print(f"  ✗ 存入 Qdrant 失败")
        except Exception as e:
            print(f"  ✗ Qdrant 存储异常: {e}")

        # 存入 Elasticsearch
        try:
            doc = {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "text": chunk_text,
                "standard_no": "GB 7958-2014",
                "category": "safety_equipment",
                "page_number": idx + 1,
                "importance_score": 0.8,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
            }

            success = search_engine.bulk_index([doc])
            if success:
                print(f"  ✓ 存入 Elasticsearch")
            else:
                print(f"  ✗ 存入 Elasticsearch 失败")
        except Exception as e:
            print(f"  ✗ Elasticsearch 存储异常: {e}")

        stored_chunks.append({
            "chunk_id": chunk_id,
            "text": chunk_text
        })

    print(f"\n✓ 存储完成: {len(stored_chunks)} 个块")
    return stored_chunks

async def test_retrieval(stored_chunks):
    """测试检索功能"""
    print("\n" + "="*60)
    print("3. 测试检索功能")
    print("="*60)

    # 测试向量检索
    print("\n3.1 测试向量检索")
    test_query = "电容式发爆器"

    try:
        query_vector = embedder.encode(test_query).tolist()
        results = vector_store.hybrid_search(
            dense_vector=query_vector,
            limit=3
        )

        print(f"✓ 向量检索成功，返回 {len(results)} 条结果")
        for i, result in enumerate(results, 1):
            text_preview = result['payload'].get('text', '')[:100]
            print(f"  {i}. [Score: {result['score']:.4f}] {text_preview}...")
    except Exception as e:
        print(f"✗ 向量检索失败: {e}")

    # 测试 BM25 检索
    print("\n3.2 测试 BM25 全文检索")
    try:
        results = search_engine.bm25_search(
            query=test_query,
            size=3
        )

        print(f"✓ BM25 检索成功，返回 {len(results)} 条结果")
        for i, result in enumerate(results, 1):
            text_preview = result['source'].get('text', '')[:100]
            print(f"  {i}. [Score: {result['score']:.4f}] {text_preview}...")
    except Exception as e:
        print(f"✗ BM25 检索失败: {e}")

async def test_minio_storage():
    """测试 MinIO 文件存储"""
    print("\n" + "="*60)
    print("4. 测试 MinIO 文件存储")
    print("="*60)

    # 测试 Markdown 上传
    print("\n4.1 测试 Markdown 上传")
    test_content = """# GB 7958-2014 煤矿用电容式发爆器

## 摘要
本标准规定了煤矿用电容式发爆器的技术要求、试验方法等。

## 适用范围
适用于有甲烷和煤尘爆炸性气体混合物的煤矿井下。
"""

    try:
        success = object_store.upload_markdown(
            content=test_content,
            object_name="test/GB7958-2014.md"
        )
        if success:
            print("✓ Markdown 上传成功")
        else:
            print("✗ Markdown 上传失败")
    except Exception as e:
        print(f"✗ Markdown 上传异常: {e}")

    # 测试文件列表
    print("\n4.2 测试文件列表")
    try:
        objects = object_store.list_objects(
            bucket_name=object_store.markdown_bucket,
            prefix="test/"
        )
        print(f"✓ 列出文件成功: {len(objects)} 个文件")
        for obj in objects:
            print(f"  - {obj['object_name']} ({obj['size']} bytes)")
    except Exception as e:
        print(f"✗ 列出文件失败: {e}")

async def test_cleanup():
    """清理测试数据"""
    print("\n" + "="*60)
    print("5. 清理测试数据")
    print("="*60)

    doc_id = "GB7958-2014"

    # 清理 Qdrant
    try:
        vector_store.delete_by_doc_id(doc_id)
        print(f"✓ 清理 Qdrant 数据")
    except Exception as e:
        print(f"✗ 清理 Qdrant 失败: {e}")

    # 清理 Elasticsearch
    try:
        search_engine.delete_by_doc_id(doc_id)
        print(f"✓ 清理 Elasticsearch 数据")
    except Exception as e:
        print(f"✗ 清理 Elasticsearch 失败: {e}")

    # 清理 MinIO
    try:
        object_store.delete_object(
            bucket_name=object_store.markdown_bucket,
            object_name="test/GB7958-2014.md"
        )
        print(f"✓ 清理 MinIO 数据")
    except Exception as e:
        print(f"✗ 清理 MinIO 失败: {e}")

async def main():
    """主测试流程"""
    print("\n" + "="*60)
    print("存储层集成测试")
    print("="*60)

    # 1. 测试连接
    if not test_storage_connections():
        print("\n存储系统连接失败，请检查配置和服务状态")
        return

    # 2. 测试存储
    stored_chunks = await test_parsed_content_storage()
    if not stored_chunks:
        print("\n内容存储失败")
        return

    # 等待索引刷新
    print("\n等待索引刷新...")
    await asyncio.sleep(2)

    # 3. 测试检索
    await test_retrieval(stored_chunks)

    # 4. 测试 MinIO
    await test_minio_storage()

    # 5. 清理（非交互模式下跳过）
    await test_cleanup()

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
