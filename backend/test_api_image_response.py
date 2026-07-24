"""
测试 API 是否返回图片信息
"""
import asyncio
import httpx
import json
import sys
import io

# 设置 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def test_query_with_image():
    async with httpx.AsyncClient(timeout=120.0) as client:
        # 先登录获取 token
        print("登录获取 token...")
        login_response = await client.post(
            "http://localhost:8000/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"}
        )

        if login_response.status_code != 200:
            print(f"登录失败: {login_response.text}")
            return

        token = login_response.json()["access_token"]
        print(f"Token 获取成功: {token[:20]}...")

        # 发送查询请求
        url = "http://localhost:8000/api/v1/query/"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload = {
            "query": "GB 5226.6-2014 标准中典型建设机械的电气设备框图包含哪些主要模块？",
            "filters": {},
            "skip_preprocessing": True  # 跳过预处理直接检索
        }

        print("\n发送查询请求...")
        response = await client.post(url, json=payload, headers=headers)

        print(f"\n状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            print(f"\n回答: {data.get('answer', 'None')[:100] if data.get('answer') else 'None'}...")
            print(f"\n引用数量: {len(data.get('citations', []))}")

            # 检查每个引用是否包含图片
            for i, citation in enumerate(data.get('citations', []), 1):
                print(f"\n=== 引用 {i} ===")
                print(f"chunk_id: {citation.get('chunk_id')}")
                print(f"标准号: {citation.get('standard_no')}")
                print(f"内容片段: {citation.get('content', '')[:80]}...")

                images = citation.get('images', [])
                if images:
                    print(f"✅ 包含 {len(images)} 张图片:")
                    for j, img in enumerate(images, 1):
                        print(f"   图片 {j}:")
                        print(f"     image_id: {img.get('image_id')}")
                        print(f"     url: {img.get('url')}")
                        print(f"     caption: {img.get('caption')}")
                        print(f"     figure_number: {img.get('figure_number')}")
                else:
                    print("❌ 无图片信息")

            # 保存完整响应
            with open('api_response_debug.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print("\n完整响应已保存到 api_response_debug.json")
        else:
            print(f"请求失败: {response.text}")

if __name__ == "__main__":
    asyncio.run(test_query_with_image())
