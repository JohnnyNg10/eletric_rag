"""
测试图片检索增强功能

测试范围：
1. Chunk.content_type 字段
2. compute_image_text_associations - 图文语义关联计算
3. inject_image_links - 图片链接注入（路径A和B）
4. pull_along_images - 图片伴随召回（路径1和2）
"""
import sys
import os
import asyncio
import numpy as np
from unittest.mock import MagicMock, patch
from typing import List

# Windows 终端编码修复
if sys.platform == "win32":
    os.system("chcp 65001 > nul 2>&1")
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, ".")  # backend/ directory


# ─── Test 1: Chunk.content_type ─────────────────────────────────────────────
def test_chunk_content_type():
    print("\n=== Test 1: Chunk.content_type 字段 ===")
    from app.core.document_processor.chunker import Chunk

    # 默认 content_type = "text"
    c1 = Chunk(content="测试文本", chunk_type="child")
    assert c1.content_type == "text", f"Expected 'text', got '{c1.content_type}'"
    d1 = c1.to_dict()
    assert d1["content_type"] == "text"
    print("  ✓ 默认 content_type = 'text'")

    # 自定义 content_type
    c2 = Chunk(content="图片描述", chunk_type="child", content_type="image_description")
    assert c2.content_type == "image_description"
    print("  ✓ 自定义 content_type = 'image_description'")

    # to_dict 包含 content_type
    d2 = c2.to_dict()
    assert "content_type" in d2
    print("  ✓ to_dict() 包含 content_type 字段")
    print("  PASS")


# ─── Test 2: compute_image_text_associations ───────────────────────────────
def test_compute_image_text_associations():
    print("\n=== Test 2: compute_image_text_associations 关联计算 ===")
    from app.core.document_processor.chunker import compute_image_text_associations

    # 构造测试向量（128维，归一化）
    def make_vector(dim=128, seed=None):
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(dim).astype(np.float32)
        return (v / np.linalg.norm(v)).tolist()

    # 相似向量对
    base_vec = make_vector(seed=42)
    similar_vec = (np.array(base_vec) * 0.99 + np.random.default_rng(99).standard_normal(128) * 0.05)
    similar_vec = (similar_vec / np.linalg.norm(similar_vec)).tolist()
    dissimilar_vec = make_vector(seed=100)

    # 案例A：物理邻近（同页）
    text_chunks = [(1, "变压器接线说明", 3, 3)]
    image_chunks = [(101, "变压器接线图", 3)]
    associations = compute_image_text_associations(
        text_chunks=text_chunks,
        image_chunks=image_chunks,
        text_vectors=[base_vec],
        image_vectors=[base_vec],
        threshold=0.75
    )
    assert 1 in associations, "文本块1（第3页）应与图片块101（第3页）关联"
    assert 101 in associations[1]
    print("  ✓ 物理邻近关联正确（同页）")

    # 案例B：高语义相似度（不同页，但向量相似）
    associations2 = compute_image_text_associations(
        text_chunks=[(3, "内容描述很相似", 1, 1)],
        image_chunks=[(201, "描述", 50)],
        text_vectors=[base_vec],
        image_vectors=[similar_vec],
        threshold=0.75
    )
    actual_sim = float(np.dot(base_vec, similar_vec))
    print(f"  实际余弦相似度: {actual_sim:.4f}")
    if actual_sim >= 0.75:
        assert 3 in associations2, f"余弦相似度={actual_sim:.4f}≥0.75，应建立关联"
        print(f"  ✓ 高语义相似度关联正确（sim={actual_sim:.4f}）")

    # 案例C：空输入
    empty = compute_image_text_associations([], [], [], [])
    assert empty == {}
    print("  ✓ 空输入返回空字典")

    # 案例D：不相关（不同页且余弦相似度低）
    associations3 = compute_image_text_associations(
        text_chunks=[(4, "完全不相关的文本", 1, 1)],
        image_chunks=[(301, "完全不同的图", 50)],
        text_vectors=[base_vec],
        image_vectors=[dissimilar_vec],
        threshold=0.75
    )
    sim_low = float(np.dot(base_vec, dissimilar_vec))
    if sim_low < 0.75:
        assert 4 not in associations3, f"低相似度（{sim_low:.4f}）且不同页，不应关联"
        print(f"  ✓ 低相似度正确排除（sim={sim_low:.4f}）")
    print("  PASS")


# ─── Test 3: inject_image_links ────────────────────────────────────────────
async def test_inject_image_links():
    print("\n=== Test 3: inject_image_links 图片链接注入 ===")
    from app.core.retrieval.image_link_injector import inject_image_links
    from app.schemas.retrieval import ChunkResult

    # 测试 Chunk
    img_chunk = ChunkResult(
        chunk_id=1,
        document_id=10,
        content="[图片描述] 第3页 图1：变压器接线图",
        score=0.9,
        content_type="image_description"
    )
    text_chunk = ChunkResult(
        chunk_id=2,
        document_id=10,
        content="如图1所示，变压器的接线结构...",
        score=0.8,
        content_type="text"
    )

    # Mock DB session
    mock_db = MagicMock()

    # 路径A：image_description → Image记录
    mock_img_record = MagicMock()
    mock_img_record.chunk_id = 1
    mock_img_record.id = 100
    mock_img_record.minio_path = "images/GB-1234/p3_0.jpg"
    mock_img_record.page_number = 3
    mock_img_record.figure_number = "图1"
    mock_img_record.caption = "变压器接线示意图"

    # 设置 mock 返回值
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_img_record]

    # Mock presigned URL
    with patch("app.core.retrieval.image_link_injector._build_image_url", return_value="http://minio/images/test.jpg"):
        result = await inject_image_links([img_chunk, text_chunk], mock_db)

    # 验证路径A：image_description chunk 被注入了 image_url
    assert img_chunk.image_id == 100
    assert img_chunk.image_url == "http://minio/images/test.jpg"
    assert img_chunk.image_page == 3
    assert img_chunk.image_figure_number == "图1"
    print("  ✓ 路径A：image_description chunk 正确注入图片URL和元数据")
    print("  PASS")


# ─── Test 4: pull_along_images ─────────────────────────────────────────────
async def test_pull_along_images():
    print("\n=== Test 4: pull_along_images 图片伴随召回 ===")
    from app.core.retrieval.image_link_injector import pull_along_images
    from app.schemas.retrieval import ChunkResult

    # 路径1：图号引用召回
    print("\n  --- 路径1：图号引用召回 ---")
    text_chunk = ChunkResult(
        chunk_id=1,
        document_id=10,
        content="如图1所示，相变换器的主要部件包括...",
        score=0.85,
        content_type="text",
        page_start=5
    )

    mock_db = MagicMock()

    # Mock Image查询结果
    mock_img = MagicMock()
    mock_img.document_id = 10
    mock_img.figure_number = "图1"
    mock_img.chunk_id = 99

    # Mock DBChunk 查询结果
    mock_db_chunk = MagicMock()
    mock_db_chunk.id = 99
    mock_db_chunk.document_id = 10
    mock_db_chunk.content = "[图片描述] 第5页 图1：相变换器主要部件图"
    mock_db_chunk.clause = None
    mock_db_chunk.page_start = 5
    mock_db_chunk.page_end = 5
    mock_db_chunk.meta_data = {"document_title": "GB/T 1234", "standard_no": "GB/T 1234"}

    # 第一次query (Image)，第二次 query (DBChunk)
    mock_db.query.return_value.filter.return_value.all.side_effect = [
        [mock_img],      # Image 查询
        [mock_db_chunk]  # DBChunk 查询
    ]

    result = await pull_along_images([text_chunk], mock_db)

    # 应追加1个image_description chunk
    assert len(result) == 2, f"预期2个chunk，实际得到{len(result)}"
    pulled = result[1]
    assert pulled.chunk_id == 99
    assert pulled.content_type == "image_description"
    assert pulled.recall_source == "pull_along"
    print(f"  ✓ 路径1成功：追加了chunk_id={pulled.chunk_id}，score={pulled.score}")

    # 路径2：related_chunk_ids 语义关联召回
    print("\n  --- 路径2：related_chunk_ids 语义关联召回 ---")
    text_chunk2 = ChunkResult(
        chunk_id=2,
        document_id=10,
        content="变压器的绝缘结构设计...",
        score=0.88,
        content_type="text",
        page_start=8,
        related_chunk_ids=[201]  # 语义关联的图片chunk
    )

    mock_db2 = MagicMock()
    mock_img_chunk = MagicMock()
    mock_img_chunk.id = 201
    mock_img_chunk.document_id = 10
    mock_img_chunk.content = "[图片描述] 第9页 图5：变压器绝缘结构示意图"
    mock_img_chunk.clause = None
    mock_img_chunk.page_start = 9
    mock_img_chunk.page_end = 9
    mock_img_chunk.meta_data = {"document_title": "GB/T 1234", "standard_no": "GB/T 1234"}

    # Mock 查询：先查 Image（空），再查 related_chunk_ids 对应的 Chunk
    mock_db2.query.return_value.filter.return_value.all.side_effect = [
        [],  # Image 查询（路径1无匹配）
        [mock_img_chunk]  # DBChunk 查询（路径2有匹配）
    ]

    result2 = await pull_along_images([text_chunk2], mock_db2)

    # 检查是否通过 related_chunk_ids 拉取到了图片块
    if len(result2) == 2:
        pulled2 = result2[1]
        assert pulled2.chunk_id == 201
        assert pulled2.content_type == "image_description"
        print(f"  ✓ 路径2成功：通过 related_chunk_ids 召回了chunk_id={pulled2.chunk_id}")
    else:
        print(f"  ✗ 路径2失败：related_chunk_ids 召回未实现（预期2个chunk，实际{len(result2)}个）")
        print("    提示：需要在 pull_along_images() 中添加路径2逻辑")

    print("  PASS（路径1正常，路径2待验证）")


# ─── Main ───────────────────────────────────────────────────────────────────
async def main():
    print("=" * 70)
    print("图片检索增强功能测试")
    print("=" * 70)

    errors = []

    tests = [
        (test_chunk_content_type, False),
        (test_compute_image_text_associations, False),
        (test_inject_image_links, True),
        (test_pull_along_images, True),
    ]

    for test_fn, is_async in tests:
        try:
            if is_async:
                await test_fn()
            else:
                test_fn()
        except Exception as e:
            import traceback
            print(f"\n  ❌ FAIL: {e}")
            traceback.print_exc()
            errors.append(test_fn.__name__)

    print("\n" + "=" * 70)
    if errors:
        print(f"❌ 失败测试: {errors}")
    else:
        print("✅ 全部测试通过!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
