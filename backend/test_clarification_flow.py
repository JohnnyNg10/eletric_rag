"""
测试澄清功能与路由层集成

测试流程：
1. 首次查询 → 触发澄清 → 返回澄清选项
2. 用户选择澄清选项后重新查询 → 跳过笼统度评估 → 进入路由层
3. 验证日志记录
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.preprocessing import Preprocessor, PreprocessingInput
from app.core.retrieval import Router
from app.services.query_service import QueryService
from app.db.session import SessionLocal
from app.db.models import QueryLog, ClarificationLog


async def test_clarification_flow():
    """测试完整的澄清流程"""

    print("=" * 80)
    print("测试澄清功能与路由层集成")
    print("=" * 80)

    # 测试用例1: 笼统查询
    vague_query = "隔离开关要求"

    # ==================== 阶段1: 首次查询 ====================
    print("\n[阶段1] 首次查询 - 触发澄清")
    print(f"原始查询: {vague_query}")

    preprocessor = Preprocessor()
    preprocessing_input = PreprocessingInput(
        query=vague_query,
        user_context={'user_id': 1},
        enable_optimization=True
    )

    result = await preprocessor.preprocess(preprocessing_input)

    print(f"预处理结果: status={result.status}")
    print(f"笼统度评分: {result.vagueness_score:.2f}")

    if result.status == 'need_clarification':
        print(f"澄清选项数量: {len(result.clarification_options or [])}")
        if result.clarification_options:
            print("\n生成的澄清选项:")
            for i, opt in enumerate(result.clarification_options, 1):
                print(f"  {i}. {opt['label']}")
                print(f"     精炼查询: {opt['refined_query']}")
                print(f"     相关标准: {opt.get('standard_preview', 'N/A')}")
                print(f"     文档数量: {opt.get('doc_count', 0)}")

        # ==================== 阶段2: 用户选择澄清选项 ====================
        print("\n[阶段2] 用户选择澄清选项后重新查询")

        # 模拟用户选择第1个选项
        selected_option = result.clarification_options[0]
        refined_query = selected_option['refined_query']
        selected_option_id = selected_option['id']

        print(f"用户选择: 选项 {selected_option_id}")
        print(f"精炼查询: {refined_query}")

        # 创建澄清上下文
        clarification_context = {
            'vagueness_score': result.vagueness_score,
            'strategy': 'clarify',
            'options': result.clarification_options,
            'missing_dimensions': ['电压等级', '应用场景']
        }

        # 使用 QueryService 处理澄清后的查询
        print("\n[阶段3] QueryService 处理澄清后的查询")

        db = SessionLocal()
        try:
            query_service = QueryService(db=db)

            final_result = await query_service.execute_query(
                query=vague_query,  # 原始查询（用于日志）
                user_id=1,
                conversation_id=None,
                filters=None,
                refined_query=refined_query,  # 精炼后的查询
                selected_option_id=selected_option_id,
                clarification_context=clarification_context
            )

            print(f"查询状态: {final_result['status']}")
            print(f"路由结果: {final_result['lane']} - {final_result['route_reason']}")
            print(f"检索耗时: {final_result['retrieval_time']}ms")
            print(f"总耗时: {final_result['total_time']}ms")
            print(f"查询日志ID: {final_result['query_log_id']}")

            # ==================== 阶段4: 验证日志记录 ====================
            print("\n[阶段4] 验证日志记录")

            query_log_id = final_result['query_log_id']
            if query_log_id > 0:
                # 查询日志
                query_log = db.query(QueryLog).filter(QueryLog.id == query_log_id).first()
                if query_log:
                    print(f"[OK] 查询日志已记录")
                    print(f"  - 原始查询: {query_log.query}")
                    print(f"  - 标准化查询: {query_log.normalized_query}")
                    print(f"  - 路由车道: {query_log.lane}")
                    print(f"  - 是否澄清: {query_log.clarified}")
                    print(f"  - 总耗时: {query_log.total_time}ms")

                # 澄清日志
                clarification_log = db.query(ClarificationLog).filter(
                    ClarificationLog.query_log_id == query_log_id
                ).first()

                if clarification_log:
                    print(f"[OK] 澄清日志已记录")
                    print(f"  - 原始查询: {clarification_log.original_query}")
                    print(f"  - 精炼查询: {clarification_log.refined_query}")
                    print(f"  - 用户选择: {clarification_log.user_choice}")
                    print(f"  - 笼统度评分: {clarification_log.vagueness_score:.2f}")
                    print(f"  - 澄清策略: {clarification_log.strategy}")
                    print(f"  - 选项数量: {len(clarification_log.options_generated or [])}")
                else:
                    print("[ERROR] 澄清日志未找到")
            else:
                print("[ERROR] 查询日志ID为0，未记录到数据库")

        finally:
            db.close()

    else:
        print("查询未触发澄清，测试流程结束")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


async def test_clear_query():
    """测试明确查询（不触发澄清）"""

    print("\n" + "=" * 80)
    print("测试明确查询（不触发澄清）")
    print("=" * 80)

    clear_query = "GB 50057-2010第3.2.1条关于接地电阻的规定"
    print(f"原始查询: {clear_query}")

    db = SessionLocal()
    try:
        query_service = QueryService(db=db)

        result = await query_service.execute_query(
            query=clear_query,
            user_id=1,
            conversation_id=None,
            filters=None
        )

        print(f"查询状态: {result['status']}")
        print(f"路由结果: {result['lane']} - {result['route_reason']}")
        print(f"总耗时: {result['total_time']}ms")
        print(f"查询日志ID: {result['query_log_id']}")

        # 验证日志
        query_log_id = result['query_log_id']
        if query_log_id > 0:
            query_log = db.query(QueryLog).filter(QueryLog.id == query_log_id).first()
            if query_log:
                print(f"[OK] 查询日志已记录")
                print(f"  - 是否澄清: {query_log.clarified}")
                print(f"  - 笼统度评分: {query_log.vagueness_score}")

    finally:
        db.close()

    print("=" * 80)


async def main():
    """主函数"""
    try:
        # 测试1: 笼统查询 → 澄清流程
        await test_clarification_flow()

        print("\n" + "=" * 80 + "\n")

        # 测试2: 明确查询 → 不触发澄清
        await test_clear_query()

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
