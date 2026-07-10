"""
慢车道测试脚本

测试内容：
1. LLM 决策循环
2. 三个工具的调用
3. 信息聚合
4. 超时控制

运行: cd backend && uv run tests/test_core/retrieval/test_slow_lane.py
"""
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.db.session import SessionLocal
from app.core.retrieval.slow_lane import SlowLane


async def test_slow_lane_basic():
    """测试慢车道基本流程"""
    print("=" * 60)
    print("测试1: 慢车道基本流程")
    print("=" * 60)

    db = SessionLocal()
    try:
        slow_lane = SlowLane(db=db)

        # 测试查询：跨标准对比（应该触发多步推理）
        query = "异步发电机与变流器型光伏的功率因数要求有无区别？"

        print(f"\n查询: {query}")
        print("\n执行慢车道流程...")

        result = await slow_lane.execute(
            query=query,
            user_context={'user_id': 1},
            strategy_params={}
        )

        print(f"\n状态: {result.status}")
        print(f"执行步数: {result.steps_taken}")
        print(f"召回数量: {result.recall_count}")
        print(f"检索耗时: {result.retrieval_time}ms")

        print("\n推理步骤:")
        for record in result.reasoning_steps:
            print(f"  步骤 {record.step}: {record.tool}")
            print(f"    参数: {record.params}")
            print(f"    耗时: {record.elapsed_ms}ms")
            print(f"    结果数: {record.result_count}")
            print(f"    超时: {record.timeout}")

        if result.retrieved_chunks:
            print(f"\n召回的文档块（前3条）:")
            for i, chunk in enumerate(result.retrieved_chunks[:3], 1):
                print(f"  {i}. [{chunk.standard_no}] {chunk.clause or '无条款'}")
                print(f"     评分: {chunk.score:.4f}")
                print(f"     内容: {chunk.content[:100]}...")

        print("\n✓ 慢车道基本流程测试完成")

    finally:
        db.close()


async def test_slow_lane_list_standards():
    """测试 list_related_standards 工具"""
    print("\n" + "=" * 60)
    print("测试2: list_related_standards 工具")
    print("=" * 60)

    db = SessionLocal()
    try:
        slow_lane = SlowLane(db=db)

        # 直接测试工具
        result = await slow_lane._list_related_standards(
            keyword="功率因数",
            category=None
        )

        print(f"\n查询关键词: 功率因数")
        print(f"找到标准数: {len(result['metadata']['standards'])}")

        print("\n相关标准清单:")
        for std in result['metadata']['standards'][:5]:
            print(f"  - {std['standard_no']}: {std['title']}")
            print(f"    文档数: {std['doc_count']}, 分类: {std.get('category', '未知')}")

        print("\n✓ list_related_standards 工具测试完成")

    finally:
        db.close()


async def test_slow_lane_retrieve_clause():
    """测试 retrieve_clause 工具"""
    print("\n" + "=" * 60)
    print("测试3: retrieve_clause 工具")
    print("=" * 60)

    db = SessionLocal()
    try:
        slow_lane = SlowLane(db=db)

        # 直接测试工具
        result = await slow_lane._retrieve_clause(
            standard_id="GB/T 33593-2017",
            clause_number="5.1"
        )

        print(f"\n查询条款: GB/T 33593-2017 第 5.1 条")
        print(f"找到结果: {len(result['chunks'])} 条")

        if result['chunks']:
            chunk = result['chunks'][0]
            print(f"\n条款内容:")
            print(f"  标准: {chunk.standard_no}")
            print(f"  条款: {chunk.clause}")
            print(f"  评分: {chunk.score}")
            print(f"  内容: {chunk.content[:200]}...")
        else:
            print("\n未找到该条款（可能数据库中不存在）")

        print("\n✓ retrieve_clause 工具测试完成")

    finally:
        db.close()


async def test_slow_lane_retrieve_standard():
    """测试 retrieve_standard 工具"""
    print("\n" + "=" * 60)
    print("测试4: retrieve_standard 工具")
    print("=" * 60)

    db = SessionLocal()
    try:
        slow_lane = SlowLane(db=db)

        # 直接测试工具
        result = await slow_lane._retrieve_standard(
            query="功率因数要求",
            standard_ids=["GB/T 33593-2017"]
        )

        print(f"\n查询: 功率因数要求")
        print(f"限定标准: GB/T 33593-2017")
        print(f"召回数量: {len(result['chunks'])}")

        if result['chunks']:
            print("\n召回结果（前3条）:")
            for i, chunk in enumerate(result['chunks'][:3], 1):
                print(f"  {i}. [{chunk.standard_no}] {chunk.clause or '无条款'}")
                print(f"     评分: {chunk.score:.4f}")
                print(f"     内容: {chunk.content[:80]}...")

        print("\n✓ retrieve_standard 工具测试完成")

    finally:
        db.close()


async def test_slow_lane_timeout():
    """测试超时控制"""
    print("\n" + "=" * 60)
    print("测试5: 超时控制")
    print("=" * 60)

    db = SessionLocal()
    try:
        slow_lane = SlowLane(db=db)

        # 设置很短的超时时间
        query = "35kV 变电站哪些条款同时涉及短路电流和接地？"

        print(f"\n查询: {query}")
        print("设置总超时: 3000ms（很短，可能触发超时）")

        result = await slow_lane.execute(
            query=query,
            user_context={'user_id': 1},
            strategy_params={'total_timeout': 3000}
        )

        print(f"\n执行步数: {result.steps_taken}")
        print(f"检索耗时: {result.retrieval_time}ms")

        # 检查是否有步骤超时
        timeout_steps = [r for r in result.reasoning_steps if r.timeout]
        if timeout_steps:
            print(f"\n超时步骤数: {len(timeout_steps)}")
            for record in timeout_steps:
                print(f"  步骤 {record.step}: {record.tool} (超时)")
        else:
            print("\n未触发超时（可能查询很快完成）")

        print("\n✓ 超时控制测试完成")

    finally:
        db.close()


async def main():
    """主测试函数"""
    print("慢车道测试")
    print("=" * 60)

    try:
        # 基本流程测试
        await test_slow_lane_basic()

        # 工具测试
        await test_slow_lane_list_standards()
        await test_slow_lane_retrieve_clause()
        await test_slow_lane_retrieve_standard()

        # 超时测试
        await test_slow_lane_timeout()

        print("\n" + "=" * 60)
        print("所有测试完成 ✓")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
