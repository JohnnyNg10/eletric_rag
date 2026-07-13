"""
阶段B功能测试脚本

测试内容：
1. QueryOptimizer 一体化输出（笼统度 + 路由建议）
2. PreprocessingOutput 包含路由字段
3. 数据库字段：predicted_lane, lane_confidence, user_lane
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.preprocessing import Preprocessor, PreprocessingInput
from app.core.preprocessing.query_optimizer import QueryOptimizer, POWER_CLARIFICATION_DIMS
from app.db.session import SessionLocal
from sqlalchemy import text


async def test_optimizer():
    """测试 QueryOptimizer 一体化输出"""
    print("=" * 60)
    print("测试 1: QueryOptimizer 一体化输出")
    print("=" * 60)

    optimizer = QueryOptimizer()

    # 测试查询1：明确查询（含标准号）
    query1 = "GB 50057-2010 第 5.2.1 条的接地要求"
    print(f"\n查询: {query1}")
    result1 = await optimizer.optimize(query1)
    print(f"  笼统度: {result1.vagueness_score:.2f}")
    print(f"  策略: {result1.strategy}")
    print(f"  路由建议: {result1.lane_suggestion} (置信度: {result1.lane_confidence:.2f})")
    print(f"  路由理由: {result1.lane_reason}")
    print(f"  缺失维度: {result1.missing_dimension_keys}")

    # 测试查询2：笼统查询（无电压等级、无设备类型）
    query2 = "隔离开关的技术参数要求"
    print(f"\n查询: {query2}")
    result2 = await optimizer.optimize(query2)
    print(f"  笼统度: {result2.vagueness_score:.2f}")
    print(f"  策略: {result2.strategy}")
    print(f"  路由建议: {result2.lane_suggestion} (置信度: {result2.lane_confidence:.2f})")
    print(f"  路由理由: {result2.lane_reason}")
    print(f"  缺失维度: {result2.missing_dimension_keys}")
    print(f"  澄清选项数量: {len(result2.options)}")
    if result2.options:
        for opt in result2.options:
            print(f"    - [{opt.id}] {opt.label} → {opt.refined_query}")


async def test_preprocessor():
    """测试 Preprocessor 传递路由字段"""
    print("\n" + "=" * 60)
    print("测试 2: Preprocessor 传递路由字段")
    print("=" * 60)

    preprocessor = Preprocessor()

    query = "10kV配电装置的安全距离和35kV配电装置的安全距离对比"
    print(f"\n查询: {query}")

    input_data = PreprocessingInput(
        query=query,
        user_context={'user_id': 1},
        enable_optimization=True
    )

    output = await preprocessor.preprocess(input_data)
    print(f"  状态: {output.status}")
    print(f"  标准化查询: {output.optimized_query}")
    print(f"  笼统度: {output.vagueness_score:.2f}")
    print(f"  策略: {output.strategy}")
    print(f"  路由建议: {output.lane_suggestion} (置信度: {output.lane_confidence:.2f})")
    print(f"  路由理由: {output.lane_reason}")
    print(f"  缺失维度: {output.missing_dimension_keys}")


def test_database_schema():
    """测试数据库新字段"""
    print("\n" + "=" * 60)
    print("测试 3: 数据库新字段")
    print("=" * 60)

    db = SessionLocal()
    try:
        # 检查 query_logs 表结构
        result = db.execute(text("DESCRIBE query_logs"))
        columns = result.fetchall()

        print("\n检查 query_logs 表新增字段:")
        target_fields = ['lane', 'predicted_lane', 'lane_confidence', 'user_lane']
        for col in columns:
            col_name = col[0]
            if col_name in target_fields:
                print(f"  ✓ {col_name}: {col[1]} {col[2]} {col[3]}")

        # 测试插入数据
        print("\n测试插入带有阶段B字段的记录:")
        insert_sql = text("""
            INSERT INTO query_logs
            (query, normalized_query, lane, predicted_lane, lane_confidence, user_lane,
             vagueness_score, clarified)
            VALUES
            (:query, :normalized_query, :lane, :predicted_lane, :lane_confidence, :user_lane,
             :vagueness_score, :clarified)
        """)

        db.execute(insert_sql, {
            'query': '测试查询',
            'normalized_query': '测试查询（标准化）',
            'lane': 'slow',
            'predicted_lane': 'fast',
            'lane_confidence': 0.75,
            'user_lane': 'slow',
            'vagueness_score': 0.6,
            'clarified': False
        })
        db.commit()
        print("  ✓ 插入成功")

        # 查询刚插入的记录
        query_result = db.execute(text(
            "SELECT lane, predicted_lane, lane_confidence, user_lane FROM query_logs ORDER BY id DESC LIMIT 1"
        ))
        row = query_result.fetchone()
        print(f"  lane={row[0]}, predicted_lane={row[1]}, lane_confidence={row[2]}, user_lane={row[3]}")

        # 清理测试数据
        db.execute(text("DELETE FROM query_logs WHERE query = '测试查询'"))
        db.commit()
        print("  ✓ 清理测试数据完成")

    except Exception as e:
        db.rollback()
        print(f"  ✗ 错误: {e}")
    finally:
        db.close()


def test_dimension_enum():
    """测试预定义维度表"""
    print("\n" + "=" * 60)
    print("测试 4: 预定义维度表")
    print("=" * 60)

    print(f"\n电力专业澄清维度（共 {len(POWER_CLARIFICATION_DIMS)} 个）:")
    for key, value in POWER_CLARIFICATION_DIMS.items():
        print(f"  - {key:20s} : {value}")


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("阶段B功能测试")
    print("=" * 60)

    # 测试1: QueryOptimizer
    await test_optimizer()

    # 测试2: Preprocessor
    await test_preprocessor()

    # 测试3: 数据库字段
    test_database_schema()

    # 测试4: 维度枚举
    test_dimension_enum()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
