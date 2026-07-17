"""
测试路由器增强 - 验证正则匹配改进
"""
import sys
import importlib.util

# 直接加载 router.py，避免触发 retrieval/__init__.py 中对 FastLane 的导入
spec = importlib.util.spec_from_file_location(
    "router", "D:/dl/backend/app/core/retrieval/router.py"
)
_router_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_router_module)
Router = _router_module.Router


def main():
    router = Router()

    print("=" * 60)
    print("测试路由器增强：正则匹配改进")
    print("=" * 60)

    test_cases = [
        # 原有能正确识别的对比查询
        ("10kV配电和35kV配电在接地方式上有何对比", "对比查询", "slow"),
        ("GB 50054和DL/T 5352在接地要求上的差异", "多标准对比", "slow"),

        # 问题8提到的漏掉的表达
        ("GB 50053 和 GB 50054 有什么不同", "不同表达（之前漏掉）", "slow"),
        ("哪些标准涉及继电保护配置", "涉及哪些（语序）", "slow"),
        ("10kV和35kV的接地方式相同吗", "相同判断", "slow"),

        # 新增的表达覆盖
        ("GB 50057 与 DL/T 621 的异同点", "异同表达", "slow"),
        ("变压器需要同时满足温升和噪声要求", "同时满足", "slow"),
        ("什么标准参考了GB 50054", "参考（新词）", "slow"),
        ("继电保护既要选择性又要速动性", "既...又", "slow"),
        ("哪些标准依据GB 50052", "依据（新词）", "slow"),

        # 应该走快车道的查询（确保不误判）
        ("10kV配电室的接地要求", "简单查询", "fast"),
        ("GB 50054 安全距离规定", "单标准查询", "fast"),
        ("变压器保护配置要求", "普通查询", "fast"),
    ]

    all_ok = True
    for query, description, expected_lane in test_cases:
        decision = router.route(query)

        lane_match = decision.lane == expected_lane
        status = "[OK]" if lane_match else "[FAIL]"

        if not lane_match:
            all_ok = False

        print(f"  {status} {description}")
        print(f"      Query: {query}")
        print(f"      路由: {decision.lane} (期望: {expected_lane})")
        print(f"      理由: {decision.reason}")
        print()

    print("=" * 60)
    if all_ok:
        print("[PASS] 所有测试通过")
    else:
        print("[FAIL] 部分测试失败")
    print("=" * 60)


if __name__ == "__main__":
    main()
