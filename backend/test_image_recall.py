"""
测试图片召回功能

测试文档: GB 5226.6-2014 (document_id=84, 包含5张图片)
图片内容:
1. 工业设备电气控制与安全体系框图
2. 控制回路示意图（控制变压器+过流保护）
3. 控制电路原理图（电源变压器+电磁阀）
4. 直流控制电路示意图（蓄电池+发电机）
5. 传感线路两级浪涌防护示意图
"""
import sys
import asyncio
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.retrieval.fast_lane import FastLane
from app.db.session import get_db

async def test_image_recall():
    """测试图片召回功能"""

    # 测试问题（针对文档中的图片内容）
    test_queries = [
        "电气控制系统的框图结构是什么样的？",
        "控制回路中如何设置过电流保护？",
        "直流控制电路的电源配置是怎样的？",
        "浪涌防护电路如何实现两级保护？",
        "控制变压器在控制电路中的作用是什么？",
    ]

    db = next(get_db())
    fast_lane = FastLane(db=db)

    for i, query in enumerate(test_queries, 1):
        print("=" * 80)
        print(f"\n测试 {i}: {query}\n")
        print("-" * 80)

        # 执行快车道检索
        result = await fast_lane.execute(
            query=query,
            user_context={},  # 空用户上下文
            strategy_params={
                "enable_hyde": False,
                "enable_retry": False,
                "enable_decompose": False,
            }
        )

        print(f"召回状态: {result.status}")
        print(f"召回块数: {result.recall_count}")
        print(f"重排后 Top5:")

        # 检查是否召回了图片
        image_count = 0
        text_with_images = 0

        for j, rerank_result in enumerate(result.rerank_results[:5], 1):
            chunk = rerank_result
            content_type = getattr(chunk, 'content_type', 'text')
            related_chunk_ids = getattr(chunk, 'related_chunk_ids', [])

            is_image = content_type == 'image_description'
            has_images = len(related_chunk_ids) > 0

            if is_image:
                image_count += 1
            if has_images:
                text_with_images += 1

            # 显示块信息
            print(f"\n  [{j}] chunk_id={chunk.chunk_id}, score={chunk.score:.4f}")
            print(f"      类型: {content_type}")
            print(f"      关联图片: {related_chunk_ids if has_images else '无'}")
            print(f"      内容前80字: {chunk.content[:80]}...")

            # 如果是图片块，显示完整描述
            if is_image:
                print(f"      [完整描述]: {chunk.content}")

        print(f"\n📊 统计:")
        print(f"  - 图片块: {image_count} / 5")
        print(f"  - 带关联图片的文本块: {text_with_images} / 5")

        if image_count > 0:
            print(f"  ✅ 成功召回图片块！")
        else:
            print(f"  ⚠️  未召回图片块")

        print()

if __name__ == "__main__":
    asyncio.run(test_image_recall())
