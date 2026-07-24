"""
测试图片字段注入功能

验证 inject_image_links 和 pull_along_images 是否正确工作
"""
import sys
import asyncio
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.retrieval.fast_lane import FastLane
from app.db.session import get_db

async def test_image_fields():
    """测试图片字段是否正确注入"""

    query = "电气控制系统的框图结构是什么样的？"

    db = next(get_db())
    fast_lane = FastLane(db=db)

    print("=" * 80)
    print(f"查询: {query}")
    print("=" * 80)

    # 执行快车道检索
    result = await fast_lane.execute(
        query=query,
        user_context={},
        strategy_params={
            "enable_hyde": False,
            "enable_retry": False,
            "enable_decompose": False,
        }
    )

    print(f"\n✅ 召回状态: {result.status}")
    print(f"✅ 召回块数: {result.recall_count}")
    print(f"✅ 重排后数量: {len(result.rerank_results)}")

    print("\n" + "=" * 80)
    print("检查 Top5 的图片字段:")
    print("=" * 80)

    for i, chunk in enumerate(result.rerank_results[:5], 1):
        print(f"\n[{i}] chunk_id={chunk.chunk_id}, score={chunk.score:.4f}")
        print(f"    content_type: {getattr(chunk, 'content_type', 'N/A')}")
        print(f"    标准号: {chunk.standard_no}")

        # 检查图片字段
        image_id = getattr(chunk, 'image_id', None)
        image_url = getattr(chunk, 'image_url', None)
        image_caption = getattr(chunk, 'image_caption', None)
        image_figure_number = getattr(chunk, 'image_figure_number', None)
        referenced_images = getattr(chunk, 'referenced_images', [])

        if image_id or image_url:
            print(f"    ✅ 场景A - image_description 类型:")
            print(f"       image_id: {image_id}")
            print(f"       image_url: {image_url[:60] if image_url else None}...")
            print(f"       image_caption: {image_caption}")
            print(f"       image_figure_number: {image_figure_number}")

        if referenced_images:
            print(f"    ✅ 场景B - referenced_images ({len(referenced_images)}张):")
            for j, ref_img in enumerate(referenced_images, 1):
                if isinstance(ref_img, dict):
                    print(f"       [{j}] figure_number: {ref_img.get('figure_number')}")
                    print(f"           image_id: {ref_img.get('image_id')}")
                    print(f"           url: {ref_img.get('image_url', '')[:50]}...")
                else:
                    # ImageRef 对象
                    print(f"       [{j}] figure_number: {ref_img.figure_number}")
                    print(f"           image_id: {ref_img.image_id}")
                    print(f"           url: {ref_img.image_url[:50]}...")

        if not image_id and not image_url and not referenced_images:
            print(f"    ⚠️  无图片信息")

        print(f"    内容片段: {chunk.content[:100]}...")

if __name__ == "__main__":
    asyncio.run(test_image_fields())
