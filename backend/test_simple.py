"""
简化版测试 - 只检查 citations 中是否有 images 字段
"""
import asyncio
import httpx
import json

async def test():
    async with httpx.AsyncClient(timeout=120.0) as client:
        # 登录
        login_resp = await client.post(
            "http://localhost:8000/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        token = login_resp.json()["access_token"]

        # 查询
        query_resp = await client.post(
            "http://localhost:8000/api/v1/query/",
            json={
                "query": "GB 5226.6-2014 标准中典型建设机械的电气设备框图包含哪些主要模块？",
                "filters": {}
            },
            headers={"Authorization": f"Bearer {token}"}
        )

        data = query_resp.json()

        # 保存完整响应
        with open('response.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print("Response saved to response.json")
        print(f"Status: {data.get('status')}")
        print(f"Citations count: {len(data.get('citations', []))}")

        # 检查第一个引用是否有图片
        if data.get('citations'):
            first_citation = data['citations'][0]
            print(f"\nFirst citation chunk_id: {first_citation.get('chunk_id')}")
            print(f"Has images field: {'images' in first_citation}")
            if 'images' in first_citation:
                print(f"Images count: {len(first_citation['images'])}")
                if first_citation['images']:
                    print(f"First image has url: {'url' in first_citation['images'][0]}")

asyncio.run(test())
