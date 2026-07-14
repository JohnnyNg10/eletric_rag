"""
测试VLM API连接
用于验证豆包多模态API配置是否正确
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.vlm.vlm_client import vlm_client
from app.config import settings


async def test_vlm_connection():
    """测试VLM连接"""

    print("=" * 60)
    print("VLM API 连接测试")
    print("=" * 60)

    # 1. 检查配置
    print("\n1. 配置检查:")
    print(f"   ENABLE_VLM_DESCRIPTION: {settings.ENABLE_VLM_DESCRIPTION}")
    print(f"   VLM_PROVIDER: {settings.VLM_PROVIDER}")
    print(f"   DOUBAO_API_KEY: {settings.DOUBAO_API_KEY[:20]}..." if settings.DOUBAO_API_KEY else "   DOUBAO_API_KEY: 未配置")
    print(f"   DOUBAO_MODEL: {settings.DOUBAO_MODEL}")
    print(f"   DOUBAO_API_ENDPOINT: {settings.DOUBAO_API_ENDPOINT}")

    if not settings.ENABLE_VLM_DESCRIPTION:
        print("\n❌ ENABLE_VLM_DESCRIPTION=False，请在.env中设置为true")
        return

    if not settings.DOUBAO_API_KEY:
        print("\n❌ DOUBAO_API_KEY未配置")
        return

    # 2. 创建测试图片
    print("\n2. 创建测试图片...")
    try:
        from PIL import Image, ImageDraw, ImageFont

        # 创建一个简单的测试图片
        img = Image.new('RGB', (800, 600), color='white')
        draw = ImageDraw.Draw(img)

        # 绘制一些文字
        text = """第3章 设计原则

3.1 总则
    水工建筑物的设计应符合国家相关标准。

3.2 安全系数
    3.2.1 混凝土坝的安全系数不应小于1.5
    3.2.2 土石坝的安全系数不应小于1.3

[图3-1: 水坝横截面示意图]"""

        # 使用默认字体
        draw.text((50, 50), text, fill='black')

        # 保存
        test_image_path = Path("/tmp/test_vlm_image.png")
        test_image_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(test_image_path)

        print(f"   ✓ 测试图片已创建: {test_image_path}")

    except Exception as e:
        print(f"   ✗ 创建测试图片失败: {e}")
        return

    # 3. 调用VLM API
    print("\n3. 调用VLM API识别图片...")
    print("   (这可能需要几秒钟...)")

    try:
        result = await vlm_client.generate_description(
            str(test_image_path),
            prompt="请识别这张图片中的全部文字内容，保持原有格式和结构。"
        )

        if result.get('error'):
            print(f"\n❌ API调用失败:")
            print(f"   错误: {result['error']}")
            return

        print("\n✓ API调用成功!")
        print(f"\n4. 识别结果:")
        print(f"   模型: {result.get('model', 'N/A')}")
        print(f"   置信度: {result.get('confidence', 0.0)}")
        print(f"\n   识别内容:")
        print("   " + "-" * 56)

        description = result.get('description', '')
        for line in description.split('\n'):
            print(f"   {line}")

        print("   " + "-" * 56)

        print("\n✅ VLM配置正确，可以开始处理扫描件PDF!")

    except Exception as e:
        print(f"\n❌ VLM调用失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(test_vlm_connection())
