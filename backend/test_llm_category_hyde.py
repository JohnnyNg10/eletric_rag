"""
测试 LLM 类别识别 + HyDE + 类别过滤组合方案

对比三种方案：
1. 基线：不启用任何优化
2. 方案A：LLM 类别识别 + 硬过滤
3. 方案B：LLM 类别识别 + 硬过滤 + HyDE
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.core.preprocessing import Preprocessor, PreprocessingInput
from app.core.retrieval.fast_lane import FastLane


async def test_category_solutions():
    """对比测试不同方案的效果"""

    test_queries = [
        {
            "query": "整定计算原则",
            "expected_category": "继保",
            "description": "隐含类别（无'继电保护'关键词），测试 LLM 识别能力"
        },
        {
            "query": "继电保护配置要求",
            "expected_category": "继保",
            "description": "显式类别（含'继电保护'关键词），测试基线准确率"
        },
        {
            "query": "10kV配电室安全距离",
            "expected_category": "配电",
            "description": "配电类别，测试跨类别误召回"
        }
    ]

    db = SessionLocal()
    preprocessor = Preprocessor()
    fast_lane = FastLane(db=db)

    for test_case in test_queries:
        query = test_case["query"]
        expected_category = test_case["expected_category"]

        print(f"\n{'='*100}")
        print(f"测试查询: {query}")
        print(f"预期类别: {expected_category}")
        print(f"说明: {test_case['description']}")
        print(f"{'='*100}")

        # 预处理：获取 LLM 类别识别结果
        preprocessing_input = PreprocessingInput(
            query=query,
            user_context={},
            enable_optimization=True
        )
        preprocessing_output = await preprocessor.preprocess(preprocessing_input)

        llm_category = preprocessing_output.optimization_result.category if preprocessing_output.optimization_result else None
        llm_confidence = preprocessing_output.optimization_result.category_confidence if preprocessing_output.optimization_result else 0.0

        print(f"\nLLM 类别识别:")
        print(f"  识别类别: {llm_category}")
        print(f"  置信度: {llm_confidence:.2f}")
        is_correct = "[OK]" if llm_category == expected_category else "[WRONG]"
        print(f"  是否正确: {is_correct}")

        # 方案1: 基线（不启用任何优化）
        print(f"\n{'─'*100}")
        print(f"【方案1】基线：无类别过滤 + 无 HyDE")
        print(f"{'─'*100}")
        result_baseline = await fast_lane.execute(
            query=preprocessing_output.optimized_query,
            user_context={},
            strategy_params={"enable_retry": False},
            preprocessing_result=None  # 不传递预处理结果
        )
        analyze_results("基线", result_baseline, expected_category)

        # 方案2: LLM 类别识别 + 硬过滤
        print(f"\n{'─'*100}")
        print(f"【方案2】LLM 类别识别 + 硬过滤（无 HyDE）")
        print(f"{'─'*100}")
        result_filter = await fast_lane.execute(
            query=preprocessing_output.optimized_query,
            user_context={},
            strategy_params={"enable_retry": False, "enable_hyde": False},
            preprocessing_result=preprocessing_output.optimization_result  # 传递预处理结果
        )
        analyze_results("类别过滤", result_filter, expected_category)

        # 方案3: LLM 类别识别 + 硬过滤 + HyDE
        print(f"\n{'─'*100}")
        print(f"【方案3】LLM 类别识别 + 硬过滤 + HyDE")
        print(f"{'─'*100}")
        result_hyde = await fast_lane.execute(
            query=preprocessing_output.optimized_query,
            user_context={},
            strategy_params={"enable_retry": False, "enable_hyde": True},
            preprocessing_result=preprocessing_output.optimization_result  # 传递预处理结果
        )
        if result_hyde.hyde_query:
            print(f"HyDE 假设文档:")
            print(f"  {result_hyde.hyde_query[:200]}...")
        analyze_results("类别过滤 + HyDE", result_hyde, expected_category)

        # 对比总结
        print(f"\n{'─'*100}")
        print(f"【对比总结】")
        print(f"{'─'*100}")
        baseline_acc = calculate_accuracy(result_baseline, expected_category)
        filter_acc = calculate_accuracy(result_filter, expected_category)
        hyde_acc = calculate_accuracy(result_hyde, expected_category)

        print(f"Top 5 正确类别占比:")
        print(f"  基线:              {baseline_acc:.1%}")
        print(f"  类别过滤:          {filter_acc:.1%}  (改善: {(filter_acc - baseline_acc):.1%})")
        print(f"  类别过滤 + HyDE:   {hyde_acc:.1%}  (改善: {(hyde_acc - baseline_acc):.1%})")

    db.close()
    print(f"\n{'='*100}")
    print("测试完成")


def analyze_results(method_name: str, result, expected_category: str):
    """分析召回结果"""
    print(f"召回数量: {len(result.retrieved_chunks)}")
    print(f"过滤条件: {result.filters}")

    if not result.retrieved_chunks:
        print("[WARNING] 无召回结果")
        return

    print(f"\nTop 5 召回结果:")
    category_count = {}
    for i, chunk in enumerate(result.retrieved_chunks[:5]):
        category = chunk.get('category', 'unknown')
        category_count[category] = category_count.get(category, 0) + 1
        is_correct = '[OK]' if category == expected_category else '[X]'
        print(f"  [{i+1}] {is_correct} {chunk.get('standard_no', 'N/A'):20s} | "
              f"类别: {category:6s} | "
              f"评分: {chunk.get('score', 0):.3f}")

    print(f"\n类别分布（Top 5）: {category_count}")
    correct_count = category_count.get(expected_category, 0)
    print(f"正确类别数: {correct_count}/5 ({correct_count/5:.1%})")


def calculate_accuracy(result, expected_category: str) -> float:
    """计算 Top 5 正确类别占比"""
    if not result.retrieved_chunks:
        return 0.0
    correct_count = sum(
        1 for chunk in result.retrieved_chunks[:5]
        if chunk.get('category') == expected_category
    )
    return correct_count / 5


if __name__ == "__main__":
    asyncio.run(test_category_solutions())
