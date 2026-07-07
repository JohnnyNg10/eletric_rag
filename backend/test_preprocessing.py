"""
预处理层测试脚本

测试内容：
1. 术语标准化
2. 笼统度评估
3. 完整预处理流程
4. 查询改写（快车道组件）
5. 元数据提取（快车道组件）

注意：
- QueryRewriter 和 MetadataExtractor 已移至快车道
- 它们由 FastLane 调用，不再从 preprocessing 模块导出
- 但仍可从文件直接导入进行单元测试
"""
import asyncio
import sys
import io
sys.path.append('D:/dl/backend')

# 强制UTF-8输出，避免Windows GBK编码错误
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.preprocessing import (
    Preprocessor,
    PreprocessingInput,
    TermNormalizer,
    QueryOptimizer,
)
# 直接从文件导入（用于单元测试）
from app.core.preprocessing.query_rewriter import QueryRewriter
from app.core.preprocessing.metadata_extractor import MetadataExtractor


async def test_term_normalizer():
    """测试术语标准化"""
    print("=" * 60)
    print("测试1: 术语标准化")
    print("=" * 60)

    normalizer = TermNormalizer()

    test_cases = [
        "10千伏配电房的刀闸要求",
        "PT和CT的安装距离",
        "35千伏变压器室的避雷针设置",
        "配电房接地电阻要求"
    ]

    for query in test_cases:
        normalized = normalizer.normalize(query)
        print(f"原始: {query}")
        print(f"标准化: {normalized}")
        print()


async def test_query_optimizer():
    """测试查询优化器"""
    print("=" * 60)
    print("测试2: 查询优化器（笼统度评估）")
    print("=" * 60)

    optimizer = QueryOptimizer()

    test_cases = [
        ("接地", "非常笼统"),
        ("接地要求", "笼统"),
        ("10kV配电室接地电阻要求", "清晰"),
        ("GB 50057-2010第3.2.1条", "非常清晰"),
    ]

    for query, expected in test_cases:
        result = await optimizer.optimize(query)
        print(f"查询: {query}")
        print(f"预期: {expected}")
        print(f"笼统度: {result.vagueness_score:.2f}")
        print(f"策略: {result.strategy}")
        print(f"选项数: {len(result.options)}")
        print()


async def test_query_rewriter():
    """测试查询改写"""
    print("=" * 60)
    print("测试3: 查询改写")
    print("=" * 60)

    rewriter = QueryRewriter()

    test_cases = [
        "10kV配电室安全距离要求",
        "接地电阻检测标准",
        "变压器安装要求"
    ]

    for query in test_cases:
        expanded = await rewriter.rewrite(query, max_expansions=3)
        print(f"原始查询: {query}")
        print(f"扩展查询:")
        for i, eq in enumerate(expanded, 1):
            print(f"  {i}. {eq}")
        print()


async def test_metadata_extractor():
    """测试元数据提取"""
    print("=" * 60)
    print("测试4: 元数据提取")
    print("=" * 60)

    extractor = MetadataExtractor()

    test_cases = [
        "10kV配电室安全距离要求",
        "GB 50057-2010第3.2.1条内容",
        "35kV变电站接地电阻要求",
        "配电室防雷装置设置",
        "DL/T 621-1997中关于继电保护的规定"
    ]

    for query in test_cases:
        filters = extractor.extract(query)
        metadata = extractor.extract_all_metadata(query)
        print(f"查询: {query}")
        print(f"过滤条件: {filters}")
        print(f"完整元数据: {metadata}")
        print()


async def test_full_pipeline():
    """测试完整预处理流程"""
    print("=" * 60)
    print("测试5: 完整预处理流程")
    print("=" * 60)

    preprocessor = Preprocessor()

    # 测试用例1: 清晰查询
    print("--- 用例1: 清晰查询 ---")
    inp1 = PreprocessingInput(
        query="10千伏配电房的刀闸安全距离要求",
        user_context={'user_id': 1},
        enable_optimization=True
    )
    out1 = await preprocessor.preprocess(inp1)
    print(f"状态: {out1.status}")
    print(f"优化后: {out1.optimized_query}")
    print(f"笼统度: {out1.vagueness_score:.2f}")
    print()

    # 测试用例2: 笼统查询
    print("--- 用例2: 笼统查询 ---")
    inp2 = PreprocessingInput(
        query="接地要求",
        user_context={'user_id': 1},
        enable_optimization=True
    )
    out2 = await preprocessor.preprocess(inp2)
    print(f"状态: {out2.status}")
    print(f"笼统度: {out2.vagueness_score:.2f}")
    if out2.clarification_options:
        print(f"澄清选项数: {len(out2.clarification_options)}")
        for opt in out2.clarification_options:
            print(f"  - {opt['label']}")
    print()

    # 测试用例3: 带标准号的查询
    print("--- 用例3: 带标准号的查询 ---")
    inp3 = PreprocessingInput(
        query="GB 50057-2010关于35kV变电站的防雷要求",
        user_context={'user_id': 1},
        enable_optimization=True
    )
    out3 = await preprocessor.preprocess(inp3)
    print(f"状态: {out3.status}")
    print(f"优化后: {out3.optimized_query}")
    print()

    print("注意：查询改写和元数据提取已移至快车道（FastLane）")
    print("      在完整流程中，它们由 QueryService → Router → FastLane 调用")
    print()


async def test_edge_cases():
    """测试边界情况"""
    print("=" * 60)
    print("测试6: 边界情况")
    print("=" * 60)

    preprocessor = Preprocessor()

    edge_cases = [
        ("", "空查询（应抛出异常）", True),
        ("   ", "空白查询（应抛出异常）", True),
        ("a", "极短查询", False),
        ("这是一个非常非常非常非常长的查询，包含了很多信息，比如10kV、35kV、110kV等多个电压等级，还有GB 50057-2010、DL/T 621等多个标准号，以及配电室、变电站、接地、防雷等多个专业术语", "极长查询", False),
    ]

    for query, desc, should_fail in edge_cases:
        print(f"--- {desc} ---")
        try:
            inp = PreprocessingInput(
                query=query,
                user_context={'user_id': 1}
            )
            out = await preprocessor.preprocess(inp)
            print(f"状态: {out.status}")
            print(f"优化后: {out.optimized_query[:50]}")
            if should_fail:
                print("[FAIL] 预期抛出异常但没有")
            else:
                print("[OK] 处理成功")
        except ValueError as e:
            if should_fail:
                print(f"[OK] 正确抛出异常: {e}")
            else:
                print(f"[FAIL] 不应抛出异常: {e}")
        except Exception as e:
            print(f"[ERROR] 未预期错误: {e}")
        print()


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("预处理层完整测试")
    print("=" * 60 + "\n")

    await test_term_normalizer()
    await test_query_optimizer()
    await test_query_rewriter()
    await test_metadata_extractor()
    await test_full_pipeline()
    await test_edge_cases()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
