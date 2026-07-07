"""
测试 Qdrant 向量存储
"""
import sys
sys.path.append('.')

from app.storage.vector_store import vector_store
import asyncio


def test_qdrant_connection():
    """测试 Qdrant 连接"""
    print("Testing Qdrant connection...")

    try:
        # 创建 collection
        vector_store.create_collection_if_not_exists()

        # 获取 collection 信息
        info = vector_store.get_collection_info()
        print(f"\nCollection Info:")
        print(f"  Name: {info.get('name')}")
        print(f"  Points Count: {info.get('points_count')}")
        print(f"  Vectors Count: {info.get('vectors_count')}")
        print(f"  Status: {info.get('status')}")

        # 测试插入一个向量点
        import numpy as np
        test_point = {
            "id": "test_001",
            "dense_vector": np.random.rand(1024).tolist(),
            "sparse_vector": {
                "indices": [1, 5, 10],
                "values": [0.5, 0.3, 0.2]
            },
            "payload": {
                "doc_id": "doc_test",
                "doc_title": "Test Document",
                "standard_no": "GB 1002-2024",
                "category": "electrical_safety",
                "voltage_level": "250V",
                "text": "This is a test text"
            }
        }

        print("\nInserting test point...")
        success = vector_store.upsert_points([test_point])
        print(f"Upsert success: {success}")

        # 测试检索
        print("\nTesting hybrid search...")
        query_vector = np.random.rand(1024).tolist()
        results = vector_store.hybrid_search(
            dense_vector=query_vector,
            sparse_vector={"indices": [1, 5], "values": [0.5, 0.3]},
            filter_conditions={
                "must": [
                    {"key": "category", "match": {"value": "electrical_safety"}}
                ]
            },
            limit=5
        )

        print(f"Search results: {len(results)} found")
        for i, result in enumerate(results):
            print(f"  {i+1}. ID: {result['id']}, Score: {result['score']:.4f}")
            print(f"     Title: {result['payload'].get('doc_title')}")

        print("\n[PASS] All tests passed!")

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_qdrant_connection()
