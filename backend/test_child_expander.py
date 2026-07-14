"""
子块扩展功能测试脚本

测试内容：
1. 数据库连接与父子块数据准备
2. ChildChunkExpander 基础功能
3. 批量查询优化（避免 N+1）
4. 三层向量获取（缓存 → Qdrant → 计算）
5. 相似度过滤
6. FastLane 集成测试
"""
import sys
import asyncio
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import get_db
from app.db.models import Chunk, Document
from app.core.retrieval.child_expander import ChildChunkExpander
from app.schemas.retrieval import ChunkResult
from app.config import settings
from sqlalchemy import func


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def ok(msg: str):
    print(f"  [OK] {msg}")


def fail(msg: str):
    print(f"  [FAIL] {msg}")


def info(msg: str):
    print(f"  {msg}")


# ------------------------------------------------------------------ #
# 测试 1：数据库连接与父子块数据检查
# ------------------------------------------------------------------ #
def test_database_connection():
    section("测试 1：数据库连接与父子块数据检查")

    try:
        db = next(get_db())

        # 检查连接
        from sqlalchemy import text
        result = db.execute(text("SELECT 1")).scalar()
        if result == 1:
            ok("数据库连接正常")

        # 统计父块和子块数量
        parent_count = db.query(Chunk).filter(Chunk.chunk_type == 'parent').count()
        child_count = db.query(Chunk).filter(Chunk.chunk_type == 'child').count()

        info(f"父块数量: {parent_count}")
        info(f"子块数量: {child_count}")

        if parent_count == 0:
            fail("数据库中没有父块数据！请先导入文档数据")
            return None

        if child_count == 0:
            fail("数据库中没有子块数据！父子块检索需要子块数据")
            return None

        # 检查是否有父块-子块关联
        parents_with_children = (db.query(Chunk.id)
                                .filter(Chunk.chunk_type == 'parent')
                                .filter(Chunk.id.in_(
                                    db.query(Chunk.parent_chunk_id)
                                    .filter(Chunk.chunk_type == 'child')
                                    .distinct()
                                ))
                                .count())

        info(f"有子块的父块数量: {parents_with_children}")

        if parents_with_children > 0:
            ok(f"父子块关联正常（{parents_with_children}/{parent_count}）")
        else:
            fail("没有父块拥有子块！")
            return None

        return db

    except Exception as e:
        fail(f"数据库连接失败: {e}")
        return None


# ------------------------------------------------------------------ #
# 测试 2：ChildChunkExpander 初始化
# ------------------------------------------------------------------ #
async def test_expander_initialization(db):
    section("测试 2：ChildChunkExpander 初始化")

    try:
        expander = ChildChunkExpander(db)
        ok("ChildChunkExpander 初始化成功")

        # 检查配置
        info(f"CHILD_EXPANSION_ENABLED: {settings.CHILD_EXPANSION_ENABLED}")
        info(f"CHILD_SIMILARITY_THRESHOLD: {settings.CHILD_SIMILARITY_THRESHOLD}")
        info(f"MAX_CHILDREN_PER_PARENT: {settings.MAX_CHILDREN_PER_PARENT}")

        return expander

    except Exception as e:
        fail(f"初始化失败: {e}")
        return None


# ------------------------------------------------------------------ #
# 测试 3：批量获取子块（避免 N+1）
# ------------------------------------------------------------------ #
def test_batch_get_children(db, expander):
    section("测试 3：批量获取子块（避免 N+1 查询）")

    try:
        # 获取前 5 个有子块的父块
        parent_ids = (db.query(Chunk.id)
                     .filter(Chunk.chunk_type == 'parent')
                     .filter(Chunk.id.in_(
                         db.query(Chunk.parent_chunk_id)
                         .filter(Chunk.chunk_type == 'child')
                         .distinct()
                     ))
                     .limit(5)
                     .all())

        parent_ids = [p[0] for p in parent_ids]

        if not parent_ids:
            fail("没有可测试的父块")
            return False

        info(f"测试父块 IDs: {parent_ids}")

        # 批量获取
        children_map = expander._get_children_batch(parent_ids)

        total_children = sum(len(children) for children in children_map.values())

        ok(f"批量获取成功：{len(children_map)} 个父块，共 {total_children} 个子块")

        for parent_id, children in children_map.items():
            info(f"  父块 {parent_id}: {len(children)} 个子块")

        return True

    except Exception as e:
        fail(f"批量获取子块失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# ------------------------------------------------------------------ #
# 测试 4：子块扩展功能（端到端）
# ------------------------------------------------------------------ #
async def test_expand_functionality(db, expander):
    section("测试 4：子块扩展功能（端到端）")

    try:
        # 获取测试用的父块
        parent_chunks_db = (db.query(Chunk)
                           .filter(Chunk.chunk_type == 'parent')
                           .filter(Chunk.id.in_(
                               db.query(Chunk.parent_chunk_id)
                               .filter(Chunk.chunk_type == 'child')
                               .distinct()
                           ))
                           .limit(3)
                           .all())

        if not parent_chunks_db:
            fail("没有可测试的父块")
            return False

        # 转换为 ChunkResult
        parent_chunks = []
        for chunk in parent_chunks_db:
            parent_chunks.append(ChunkResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                score=0.85,
                document_title=chunk.document.title if chunk.document else "测试文档",
                standard_no=chunk.document.standard_no if chunk.document else None,
                doc_type=chunk.document.doc_type if chunk.document else None,
                category=chunk.document.category if chunk.document else None,
                voltage_level=chunk.document.voltage_level if chunk.document else None,
                clause=chunk.clause,
                recall_source="test"
            ))

        info(f"测试 {len(parent_chunks)} 个父块")

        # 执行扩展
        query = "变压器差动保护定值"
        expanded_results = await expander.expand(
            parent_chunks=parent_chunks,
            query=query,
            similarity_threshold=0.7,
            max_children_per_parent=5
        )

        ok(f"扩展完成：{len(expanded_results)} 个结果")

        # 统计信息
        total_relevant_children = sum(len(r.relevant_children) for r in expanded_results)
        parents_with_children = sum(1 for r in expanded_results if len(r.relevant_children) > 0)

        info(f"总共过滤出 {total_relevant_children} 个高相关子块")
        info(f"{parents_with_children}/{len(expanded_results)} 个父块有高相关子块")

        # 显示详细结果
        for i, result in enumerate(expanded_results):
            print(f"\n  父块 {i+1} (ID={result.parent.chunk_id}):")
            print(f"    内容: {result.parent.content[:50]}...")
            print(f"    相关子块数: {len(result.relevant_children)}")

            if result.expansion_stats:
                stats = result.expansion_stats
                print(f"    统计: total={stats.get('total_children', 0)}, "
                      f"filtered={stats.get('filtered_children', 0)}, "
                      f"avg_score={stats.get('avg_score', 0):.3f}")

            for j, child in enumerate(result.relevant_children[:2]):  # 只显示前2个
                print(f"      子块 {j+1} (score={child.score:.3f}): {child.content[:40]}...")

        return True

    except Exception as e:
        fail(f"扩展功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# ------------------------------------------------------------------ #
# 测试 5：缓存命中率测试
# ------------------------------------------------------------------ #
async def test_cache_hit_rate(db, expander):
    section("测试 5：缓存命中率测试")

    try:
        # 获取测试父块
        parent_chunks_db = (db.query(Chunk)
                           .filter(Chunk.chunk_type == 'parent')
                           .filter(Chunk.id.in_(
                               db.query(Chunk.parent_chunk_id)
                               .filter(Chunk.chunk_type == 'child')
                               .distinct()
                           ))
                           .limit(2)
                           .all())

        parent_chunks = []
        for chunk in parent_chunks_db:
            parent_chunks.append(ChunkResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                score=0.85,
                document_title=chunk.document.title if chunk.document else "测试文档",
                standard_no=chunk.document.standard_no if chunk.document else None,
                doc_type=chunk.document.doc_type if chunk.document else None,
                category=chunk.document.category if chunk.document else None,
                voltage_level=chunk.document.voltage_level if chunk.document else None,
                clause=chunk.clause,
                recall_source="test"
            ))

        query = "接地电阻值要求"

        # 第一次调用（缓存 miss）
        info("第一次调用（预期：缓存 miss）...")
        result1 = await expander.expand(parent_chunks, query)

        # 第二次调用（缓存 hit）
        info("第二次调用（预期：缓存 hit）...")
        result2 = await expander.expand(parent_chunks, query)

        ok("缓存测试完成（查看日志中的 cache_hit_rate）")

        return True

    except Exception as e:
        fail(f"缓存测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# ------------------------------------------------------------------ #
# 测试 6：FastLane 集成测试
# ------------------------------------------------------------------ #
async def test_fastlane_integration(db):
    section("测试 6：FastLane 集成测试")

    try:
        from app.core.retrieval.fast_lane import FastLane

        fast_lane = FastLane(db)

        # 执行查询
        query = "10kV线路接地电阻要求"
        user_context = {}
        strategy_params = {
            "enable_retry": False,
            "enable_hyde": False
        }

        info(f"执行查询: {query}")
        result = await fast_lane.execute(
            query=query,
            user_context=user_context,
            strategy_params=strategy_params
        )

        ok(f"FastLane 执行成功")
        info(f"检索耗时: {result.retrieval_time}ms")
        info(f"召回数量: {result.recall_count}")
        info(f"扩展结果数量: {len(result.expanded_results)}")

        # 检查扩展结果
        if hasattr(result, 'expanded_results'):
            total_children = sum(len(r.relevant_children) for r in result.expanded_results)
            info(f"总共扩展出 {total_children} 个高相关子块")

            ok("FastLane 已正确集成子块扩展功能")
        else:
            fail("FastLane 结果中没有 expanded_results 字段")

        return True

    except Exception as e:
        fail(f"FastLane 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# ------------------------------------------------------------------ #
# 测试 7：相似度阈值调整测试
# ------------------------------------------------------------------ #
async def test_similarity_threshold(db, expander):
    section("测试 7：相似度阈值调整测试")

    try:
        # 获取测试父块
        parent_chunks_db = (db.query(Chunk)
                           .filter(Chunk.chunk_type == 'parent')
                           .filter(Chunk.id.in_(
                               db.query(Chunk.parent_chunk_id)
                               .filter(Chunk.chunk_type == 'child')
                               .distinct()
                           ))
                           .limit(2)
                           .all())

        parent_chunks = []
        for chunk in parent_chunks_db:
            parent_chunks.append(ChunkResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                score=0.85,
                document_title=chunk.document.title if chunk.document else "测试文档",
                standard_no=chunk.document.standard_no if chunk.document else None,
                doc_type=chunk.document.doc_type if chunk.document else None,
                category=chunk.document.category if chunk.document else None,
                voltage_level=chunk.document.voltage_level if chunk.document else None,
                clause=chunk.clause,
                recall_source="test"
            ))

        query = "变压器保护"

        # 测试不同阈值
        thresholds = [0.5, 0.7, 0.9]
        for threshold in thresholds:
            result = await expander.expand(
                parent_chunks=parent_chunks,
                query=query,
                similarity_threshold=threshold
            )

            total_children = sum(len(r.relevant_children) for r in result)
            info(f"阈值 {threshold}: 过滤出 {total_children} 个子块")

        ok("相似度阈值调整测试完成")
        return True

    except Exception as e:
        fail(f"阈值测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# ------------------------------------------------------------------ #
# 主流程
# ------------------------------------------------------------------ #
async def main():
    print("\n子块扩展功能测试")
    print(f"配置: threshold={settings.CHILD_SIMILARITY_THRESHOLD}, "
          f"max_children={settings.MAX_CHILDREN_PER_PARENT}")

    # 测试 1: 数据库连接
    db = test_database_connection()
    if db is None:
        print("\n数据库连接失败，终止测试")
        return

    # 测试 2: 初始化
    expander = await test_expander_initialization(db)
    if expander is None:
        print("\n初始化失败，终止测试")
        return

    # 测试 3: 批量获取子块
    if not test_batch_get_children(db, expander):
        print("\n批量获取测试失败")

    # 测试 4: 子块扩展功能
    if not await test_expand_functionality(db, expander):
        print("\n扩展功能测试失败")

    # 测试 5: 缓存命中率
    if not await test_cache_hit_rate(db, expander):
        print("\n缓存测试失败")

    # 测试 6: FastLane 集成
    if not await test_fastlane_integration(db):
        print("\n FastLane 集成测试失败")

    # 测试 7: 相似度阈值
    if not await test_similarity_threshold(db, expander):
        print("\n阈值测试失败")

    print("\n" + "=" * 60)
    print("  全部测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
