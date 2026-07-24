"""
测试图片检索增强功能

验证点：
1. ChunkResult 扩展字段（related_chunk_ids, content_type）
2. compute_image_text_associations 图文关联计算
3. pull_along_images 图片伴随召回
4. inject_image_links 图片链接注入
5. reranker 类型提权
"""
import asyncio
import sys
import io
from pathlib import Path

# 解决 Windows 控制台编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.schemas.retrieval import ChunkResult
from app.core.document_processor.chunker import compute_image_text_associations
from app.core.retrieval.image_link_injector import pull_along_images, inject_image_links
from app.core.retrieval.rerank import TwoStageReranker


async def test_schema_extensions():
    """测试 ChunkResult 扩展字段"""
    print("\n=== 测试 1: ChunkResult 扩展字段 ===")

    chunk = ChunkResult(
        chunk_id=1,
        document_id=100,
        content="测试文本块",
        score=0.85,
        content_type="text",
        related_chunk_ids=[2, 3, 4]
    )

    assert chunk.content_type == "text"
    assert chunk.related_chunk_ids == [2, 3, 4]
    print("✓ ChunkResult 扩展字段测试通过")

    # 测试图片块
    image_chunk = ChunkResult(
        chunk_id=2,
        document_id=100,
        content="图 1-1 配电网结构示意图",
        score=0.90,
        content_type="image_description",
        related_chunk_ids=[]
    )

    assert image_chunk.content_type == "image_description"
    print("✓ 图片块类型测试通过")


def test_image_text_associations():
    """测试图文关联计算"""
    print("\n=== 测试 2: 图文关联计算 ===")

    import numpy as np

    # 模拟数据
    text_chunks = [
        (1, "配电网的电压等级包括 10kV、35kV 等", 1, 1),
        (2, "变压器是配电系统的核心设备", 2, 2),
    ]

    image_chunks = [
        (101, "图 1-1 配电网结构示意图", 1),
        (102, "图 2-1 变压器工作原理", 2),
    ]

    # 模拟向量（维度=4）
    text_vectors = [
        np.array([0.8, 0.2, 0.1, 0.1]),  # 与图101高度相似
        np.array([0.1, 0.9, 0.05, 0.05]),  # 与图102高度相似
    ]

    image_vectors = [
        np.array([0.85, 0.15, 0.05, 0.05]),  # 配电网
        np.array([0.05, 0.88, 0.02, 0.05]),  # 变压器
    ]

    associations = compute_image_text_associations(
        text_chunks=text_chunks,
        image_chunks=image_chunks,
        text_vectors=text_vectors,
        image_vectors=image_vectors,
        threshold=0.75
    )

    print(f"关联结果: {associations}")

    # 验证：文本块1应该关联图101（物理邻近 + 语义相似）
    assert 1 in associations, "文本块1应该有关联"
    assert 101 in associations[1], "文本块1应该关联图101"

    # 验证：文本块2应该关联图102
    assert 2 in associations
    assert 102 in associations[2], "文本块2应该关联图102"

    print("✓ 图文关联计算测试通过")


async def test_image_injection():
    """测试图片注入功能（需要数据库连接，这里只做接口测试）"""
    print("\n=== 测试 3: 图片注入接口 ===")

    # 模拟召回结果
    chunks = [
        ChunkResult(
            chunk_id=1,
            document_id=100,
            content="配电网的电压等级包括 10kV、35kV 等",
            score=0.85,
            content_type="text",
            related_chunk_ids=[101]
        ),
        ChunkResult(
            chunk_id=101,
            document_id=100,
            content="图 1-1 配电网结构示意图",
            score=0.75,
            content_type="image_description",
            related_chunk_ids=[]
        )
    ]

    # 注意：这里不能真实调用 pull_along_images 和 inject_image_links
    # 因为需要数据库连接，仅验证接口存在
    print("✓ pull_along_images 接口存在")
    print("✓ inject_image_links 接口存在")
    print("  (实际调用需要数据库连接，跳过)")


def test_type_boost():
    """测试类型提权"""
    print("\n=== 测试 4: 类型提权 ===")

    # 创建 reranker 实例（local 模式，但不加载模型）
    reranker = TwoStageReranker(
        coarse_model_path=None,
        fine_model_path=None
    )

    # 测试文本块（无提权）
    text_chunk = ChunkResult(
        chunk_id=1,
        document_id=100,
        content="测试文本",
        score=0.80,
        content_type="text"
    )
    boosted_text = reranker._apply_type_boost(text_chunk, 0.80)
    assert boosted_text == 0.80, f"文本块不应提权，期望 0.80，实际 {boosted_text}"
    print(f"✓ 文本块提权: 0.80 -> {boosted_text:.4f} (1.0x)")

    # 测试表格块（1.05x 提权）
    table_chunk = ChunkResult(
        chunk_id=2,
        document_id=100,
        content="表 1-1 电压等级对照表",
        score=0.80,
        content_type="table"
    )
    boosted_table = reranker._apply_type_boost(table_chunk, 0.80)
    expected_table = 0.80 * 1.05
    assert abs(boosted_table - expected_table) < 1e-6, f"表格块提权错误，期望 {expected_table}，实际 {boosted_table}"
    print(f"✓ 表格块提权: 0.80 -> {boosted_table:.4f} (1.05x)")

    # 测试图片块（1.08x 提权）
    image_chunk = ChunkResult(
        chunk_id=3,
        document_id=100,
        content="图 1-1 配电网结构示意图",
        score=0.80,
        content_type="image_description"
    )
    boosted_image = reranker._apply_type_boost(image_chunk, 0.80)
    expected_image = 0.80 * 1.08
    assert abs(boosted_image - expected_image) < 1e-6, f"图片块提权错误，期望 {expected_image}，实际 {boosted_image}"
    print(f"✓ 图片块提权: 0.80 -> {boosted_image:.4f} (1.08x)")


async def main():
    print("=" * 60)
    print("图片检索增强功能测试")
    print("=" * 60)

    try:
        # 测试 1: Schema 扩展
        await test_schema_extensions()

        # 测试 2: 图文关联
        test_image_text_associations()

        # 测试 3: 图片注入接口
        await test_image_injection()

        # 测试 4: 类型提权
        test_type_boost()

        print("\n" + "=" * 60)
        print("✓ 所有测试通过")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ 运行错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
