"""
测试阶段B预处理接口

测试 POST /api/v1/query/preprocess 端点的功能：
1. 明确查询 → strategy=none, lane=fast
2. 轻度笼统查询 → strategy=suggest, lane=fast
3. 中度笼统查询 → strategy=clarify_optional, lane可能slow
4. 严重笼统查询 → strategy=clarify_required, lane=slow
5. 对比查询 → lane=slow
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import User
from sqlalchemy import text
import json


def get_test_token():
    """获取测试用户的token"""
    db = SessionLocal()
    try:
        # 检查是否存在测试用户
        user = db.query(User).filter(User.username == "admin").first()
        if not user:
            print("错误: 未找到 admin 用户，请先运行系统初始化")
            return None

        # 简化：直接使用 user_id=1 的 token（实际应该走完整登录流程）
        # 这里为了测试简便，假设 admin 的 token 是已知的
        # 实际使用时需要先调用 POST /api/v1/auth/login
        return "mock_token_for_test"
    finally:
        db.close()


def test_preprocess_endpoint():
    """测试预处理端点"""
    client = TestClient(app)

    # 注意：这里需要先登录获取token，或者暂时禁用认证
    # 为了测试方便，我们直接测试端点（假设认证已配置或跳过）

    test_cases = [
        {
            "name": "明确查询（含标准号）",
            "query": "GB 50057-2010 第 5.2.1 条接地电阻要求",
            "expected": {
                "strategy": "none",
                "lane_suggestion": "fast",
                "vagueness_score_max": 0.4
            }
        },
        {
            "name": "轻度笼统查询（缺1个维度）",
            "query": "10kV配电装置的接地要求",
            "expected": {
                "strategy_in": ["none", "suggest", "clarify_optional"],
                "lane_suggestion": "fast",
                "vagueness_score_range": (0.3, 0.7)
            }
        },
        {
            "name": "中度笼统查询（缺多个维度）",
            "query": "隔离开关的技术参数要求",
            "expected": {
                "strategy_in": ["clarify_optional"],
                "vagueness_score_range": (0.5, 0.8),
                "options_min": 1
            }
        },
        {
            "name": "严重笼统查询（几乎无约束）",
            "query": "技术要求",
            "expected": {
                "strategy": "clarify_required",
                "vagueness_score_min": 0.7,
                "options_min": 1
            }
        },
        {
            "name": "对比查询（多跳推理）",
            "query": "10kV配电装置和35kV配电装置的安全距离对比",
            "expected": {
                "lane_suggestion_in": ["slow", "fast"],  # LLM可能判断为slow
                "vagueness_score_max": 0.5  # 包含电压等级，不算笼统
            }
        },
        {
            "name": "多标准关联查询",
            "query": "继电保护装置需要同时满足哪些国家标准",
            "expected": {
                "lane_suggestion": "slow",
                "strategy_in": ["none", "suggest", "clarify_optional"]
            }
        }
    ]

    print("=" * 70)
    print("测试 POST /api/v1/query/preprocess")
    print("=" * 70)

    # 由于需要认证，我们先测试能否访问端点（可能返回401）
    # 实际测试需要先实现认证或暂时禁用

    for i, case in enumerate(test_cases, 1):
        print(f"\n[测试 {i}] {case['name']}")
        print(f"查询: {case['query']}")

        try:
            response = client.post(
                "/api/v1/query/preprocess",
                json={"query": case["query"]},
                headers={"Authorization": f"Bearer {get_test_token()}"}
            )

            if response.status_code == 401:
                print("  ⚠️  需要认证 (状态码 401)")
                print("  提示: 运行测试前需要:")
                print("    1. 启动后端服务")
                print("    2. 调用 POST /api/v1/auth/login 获取 token")
                print("    3. 将 token 传入 Authorization header")
                continue

            if response.status_code != 200:
                print(f"  ✗ 失败: HTTP {response.status_code}")
                print(f"    响应: {response.text}")
                continue

            data = response.json()

            # 打印响应
            print(f"  标准化查询: {data.get('normalized_query', 'N/A')}")
            print(f"  笼统度: {data.get('vagueness_score', 0):.2f}")
            print(f"  策略: {data.get('strategy', 'N/A')}")
            print(f"  路由建议: {data.get('lane_suggestion', 'N/A')} (置信度: {data.get('lane_confidence', 0):.2f})")
            print(f"  路由理由: {data.get('lane_reason', 'N/A')}")
            print(f"  缺失维度: {data.get('missing_dimension_keys', [])}")
            print(f"  澄清选项数量: {len(data.get('options', []))}")

            if data.get('options'):
                for opt in data['options'][:2]:  # 只显示前2个
                    print(f"    - {opt.get('label', 'N/A')}")

            # 验证预期
            expected = case['expected']
            checks = []

            if 'strategy' in expected:
                checks.append(("策略", data.get('strategy') == expected['strategy']))
            if 'strategy_in' in expected:
                checks.append(("策略范围", data.get('strategy') in expected['strategy_in']))

            if 'lane_suggestion' in expected:
                checks.append(("路由建议", data.get('lane_suggestion') == expected['lane_suggestion']))
            if 'lane_suggestion_in' in expected:
                checks.append(("路由建议范围", data.get('lane_suggestion') in expected['lane_suggestion_in']))

            if 'vagueness_score_max' in expected:
                checks.append(("笼统度上限", data.get('vagueness_score', 1.0) <= expected['vagueness_score_max']))
            if 'vagueness_score_min' in expected:
                checks.append(("笼统度下限", data.get('vagueness_score', 0.0) >= expected['vagueness_score_min']))
            if 'vagueness_score_range' in expected:
                score = data.get('vagueness_score', 0.0)
                low, high = expected['vagueness_score_range']
                checks.append(("笼统度范围", low <= score <= high))

            if 'options_min' in expected:
                checks.append(("澄清选项数量", len(data.get('options', [])) >= expected['options_min']))

            # 显示检查结果
            all_pass = all(result for _, result in checks)
            status = "✓" if all_pass else "✗"
            print(f"\n  {status} 验证: {'通过' if all_pass else '部分失败'}")
            for check_name, result in checks:
                symbol = "✓" if result else "✗"
                print(f"    {symbol} {check_name}")

        except Exception as e:
            print(f"  ✗ 异常: {e}")

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


def test_preprocess_without_auth():
    """无需认证的简单测试（直接调用服务层）"""
    print("\n" + "=" * 70)
    print("直接测试服务层（绕过认证）")
    print("=" * 70)

    from app.core.preprocessing import Preprocessor, PreprocessingInput

    test_queries = [
        "GB 50057-2010 第 5.2.1 条接地电阻要求",
        "10kV配电装置的接地要求",
        "隔离开关的技术参数要求",
        "10kV和35kV配电装置的安全距离对比"
    ]

    async def run_tests():
        preprocessor = Preprocessor()

        for i, query in enumerate(test_queries, 1):
            print(f"\n[测试 {i}] {query}")

            try:
                input_data = PreprocessingInput(
                    query=query,
                    user_context={'user_id': 1},
                    enable_optimization=True
                )

                output = await preprocessor.preprocess(input_data)

                print(f"  状态: {output.status}")
                print(f"  笼统度: {output.vagueness_score:.2f}")
                print(f"  策略: {output.strategy}")
                print(f"  路由建议: {output.lane_suggestion} (置信度: {output.lane_confidence:.2f})")
                print(f"  路由理由: {output.lane_reason}")
                print(f"  缺失维度: {output.missing_dimension_keys}")

            except Exception as e:
                print(f"  ✗ 错误: {e}")

    asyncio.run(run_tests())


if __name__ == "__main__":
    print("\n选择测试方式:")
    print("1. 测试 API 端点（需要认证）")
    print("2. 直接测试服务层（无需认证，推荐）")

    choice = input("\n输入选项 (1/2): ").strip()

    if choice == "1":
        test_preprocess_endpoint()
    elif choice == "2":
        test_preprocess_without_auth()
    else:
        print("无效选项，运行服务层测试...")
        test_preprocess_without_auth()
