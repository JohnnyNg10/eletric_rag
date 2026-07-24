"""
MinerU 本机直连测试脚本
测试主业务项目通过 127.0.0.1 调用 MinerU API
"""
import requests
import json

MINERU_URL = "http://127.0.0.1:8001"

def test_health():
    """测试健康检查接口"""
    print("=" * 50)
    print("测试 1: 健康检查")
    print("=" * 50)

    resp = requests.get(f"{MINERU_URL}/health")
    print(f"状态码: {resp.status_code}")
    print(f"响应: {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    print()

def test_sync_parse(file_path):
    """测试同步解析接口"""
    print("=" * 50)
    print("测试 2: 同步解析（file_parse）")
    print("=" * 50)

    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{MINERU_URL}/file_parse",
            files={"files": f},
            data={
                "backend": "pipeline",  # 使用纯 CPU 后端
                "return_md": "true",
                "return_content_list": "true",
            },
            timeout=120,
        )

    print(f"状态码: {resp.status_code}")

    if resp.status_code == 200:
        result = resp.json()
        print(f"任务ID: {result['task_id']}")
        print(f"状态: {result['status']}")
        print(f"后端: {result['backend']}")

        # 获取 Markdown 内容
        md_content = result["results"]["document"]["md_content"]
        print(f"\nMarkdown 内容预览（前 500 字符）：")
        print("-" * 50)
        print(md_content[:500])
        print("-" * 50)

        # 如果有 content_list，显示结构
        if "content_list" in result["results"]["document"]:
            content_list = result["results"]["document"]["content_list"]
            print(f"\n内容块数量: {len(content_list)}")
            print("内容块类型统计：")
            types = {}
            for item in content_list:
                item_type = item.get("type", "unknown")
                types[item_type] = types.get(item_type, 0) + 1
            for t, count in types.items():
                print(f"  - {t}: {count}")
    else:
        print(f"错误: {resp.text}")

    print()

def test_async_parse(file_path):
    """测试异步解析接口"""
    print("=" * 50)
    print("测试 3: 异步解析（tasks）")
    print("=" * 50)

    # 提交任务
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{MINERU_URL}/tasks",
            files={"files": f},
            data={"backend": "pipeline"},
        )

    print(f"提交状态码: {resp.status_code}")

    if resp.status_code == 202:
        task_info = resp.json()
        task_id = task_info["task_id"]
        print(f"任务ID: {task_id}")
        print(f"状态URL: {task_info['status_url']}")
        print(f"结果URL: {task_info['result_url']}")

        # 轮询状态
        import time
        print("\n轮询任务状态...")
        max_attempts = 30
        for i in range(max_attempts):
            status_resp = requests.get(f"{MINERU_URL}/tasks/{task_id}")
            status = status_resp.json()["status"]
            print(f"  [{i+1}/{max_attempts}] 状态: {status}")

            if status == "completed":
                print("\n任务完成！获取结果...")
                result_resp = requests.get(f"{MINERU_URL}/tasks/{task_id}/result")
                result = result_resp.json()
                md_content = result["results"]["document"]["md_content"]
                print(f"Markdown 内容预览（前 300 字符）：")
                print("-" * 50)
                print(md_content[:300])
                print("-" * 50)
                break
            elif status == "failed":
                print(f"\n任务失败: {status_resp.json().get('error')}")
                break

            time.sleep(2)
    else:
        print(f"错误: {resp.text}")

    print()

if __name__ == "__main__":
    # 测试健康检查
    test_health()

    # 提示用户提供测试文件
    print("=" * 50)
    print("文件解析测试")
    print("=" * 50)
    print("请提供要测试的 PDF 文件路径（相对路径或绝对路径）：")
    print("示例: GB+23313-2009.pdf")
    print()

    file_path = input("文件路径: ").strip()

    if file_path:
        try:
            # 测试同步解析
            test_sync_parse(file_path)

            # 测试异步解析
            user_input = input("是否测试异步接口？(y/n): ").strip().lower()
            if user_input == 'y':
                test_async_parse(file_path)
        except FileNotFoundError:
            print(f"错误: 文件不存在 - {file_path}")
        except Exception as e:
            print(f"错误: {e}")
    else:
        print("未提供文件路径，跳过文件解析测试")

    print("\n测试完成！")
    print(f"MinerU API 运行在: {MINERU_URL}")
    print(f"主业务项目可以直接使用此地址调用（无需鉴权）")
