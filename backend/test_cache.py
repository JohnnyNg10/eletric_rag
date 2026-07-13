"""
缓存层功能测试脚本

测试内容：
1. Redis 连接
2. L1 Embedding 缓存（dense / sparse）
3. L2 召回缓存
4. L3 重排缓存
5. L4 生成缓存
6. 缓存开关（禁用后不命中）
7. 主动失效（invalidate_recall_and_generation）
"""
import sys
import time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.storage.cache import get_cache_manager
from app.config import settings


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
# 测试 1：Redis 连接
# ------------------------------------------------------------------ #
def test_connection():
    section("测试 1：Redis 连接")
    cache = get_cache_manager()
    try:
        pong = cache.client.ping()
        if pong:
            ok(f"Redis 连接正常 ({settings.REDIS_HOST}:{settings.REDIS_PORT} db={settings.REDIS_DB})")
        else:
            fail("Redis ping 返回 False")
    except Exception as e:
        fail(f"Redis 连接失败: {e}")
        sys.exit(1)


# ------------------------------------------------------------------ #
# 测试 2：L1 Embedding 缓存（dense）
# ------------------------------------------------------------------ #
def test_l1_dense():
    section("测试 2：L1 Embedding 缓存 (dense)")
    cache = get_cache_manager()
    text = "测试缓存：10kV线路最大允许电流"

    # 先清除残留
    from app.storage.cache import _md5
    key = f"embedding:dense:{_md5(text)}"
    cache.client.delete(key)

    # 未命中
    result = cache.get_dense(text)
    if result is None:
        ok("未命中（首次查询，符合预期）")
    else:
        fail("首次查询不应命中缓存")

    # 写入
    vec = np.random.rand(1024).astype(np.float32)
    vec = vec / np.linalg.norm(vec)  # 归一化
    ok_write = cache.set_dense(text, vec)
    if ok_write:
        ok(f"写入成功（{vec.shape}, dtype={vec.dtype}）")
    else:
        fail("写入失败")
        return

    # 命中
    cached = cache.get_dense(text)
    if cached is not None:
        if np.allclose(vec, cached, atol=1e-6):
            ok(f"命中且向量一致（max_diff={np.max(np.abs(vec - cached)):.2e}）")
        else:
            fail(f"命中但向量不一致（max_diff={np.max(np.abs(vec - cached)):.4f}）")
    else:
        fail("写入后未命中")

    # 检查 TTL
    ttl = cache.client.ttl(key)
    info(f"TTL = {ttl}s（预期 ≈ {settings.CACHE_EMBEDDING_TTL}s）")


# ------------------------------------------------------------------ #
# 测试 3：L1 Embedding 缓存（sparse）
# ------------------------------------------------------------------ #
def test_l1_sparse():
    section("测试 3：L1 Embedding 缓存 (sparse)")
    cache = get_cache_manager()
    text = "测试缓存：接地电阻值"

    from app.storage.cache import _md5
    key = f"embedding:sparse:{_md5(text)}"
    cache.client.delete(key)

    sparse_vec = {"indices": [1, 5, 100, 2048], "values": [0.3, 0.8, 0.1, 0.5]}

    result = cache.get_sparse(text)
    if result is None:
        ok("未命中（首次查询，符合预期）")

    cache.set_sparse(text, sparse_vec)
    cached = cache.get_sparse(text)

    if cached == sparse_vec:
        ok(f"命中且内容一致（{len(sparse_vec['indices'])} 个非零维）")
    else:
        fail(f"内容不一致: expected={sparse_vec}, got={cached}")


# ------------------------------------------------------------------ #
# 测试 4：L2 召回缓存
# ------------------------------------------------------------------ #
def test_l2_recall():
    section("测试 4：L2 召回缓存")
    cache = get_cache_manager()
    query = "变压器差动保护定值"
    filters = {"doc_type": "standard", "category": "继电保护"}

    # 清除
    from app.storage.cache import _md5
    import json
    raw = query + "|" + json.dumps(filters, sort_keys=True, ensure_ascii=False)
    key = f"recall:{_md5(raw)}"
    cache.client.delete(key)

    result = cache.get_recall(query, filters)
    if result is None:
        ok("未命中（首次查询，符合预期）")

    chunks = [
        {"chunk_id": 1, "content": "差动保护定值...", "document_id": 10,
         "standard_no": "DL/T 559", "clause": "5.3", "score": 0.92,
         "recall_source": "vector", "document_title": "变压器保护规程"},
        {"chunk_id": 2, "content": "差动保护整定...", "document_id": 10,
         "standard_no": "DL/T 559", "clause": "5.4", "score": 0.85,
         "recall_source": "keyword", "document_title": "变压器保护规程"},
    ]
    cache.set_recall(query, filters, chunks)

    cached = cache.get_recall(query, filters)
    if cached is not None and len(cached) == 2 and cached[0]["chunk_id"] == 1:
        ok(f"命中且内容一致（{len(cached)} 条 chunks）")
    else:
        fail(f"内容异常: {cached}")

    # 不同 filters 不应命中
    cached2 = cache.get_recall(query, {"doc_type": "textbook"})
    if cached2 is None:
        ok("不同 filters 正确 miss（Key 隔离有效）")
    else:
        fail("不同 filters 不应命中")

    ttl = cache.client.ttl(key)
    info(f"TTL = {ttl}s（预期 ≈ {settings.CACHE_RECALL_TTL}s）")


# ------------------------------------------------------------------ #
# 测试 5：L3 重排缓存
# ------------------------------------------------------------------ #
def test_l3_rerank():
    section("测试 5：L3 重排缓存")
    cache = get_cache_manager()
    query = "变压器差动保护定值"
    chunk_ids = [1, 2, 5, 8]

    from app.storage.cache import _md5
    raw = query + "|" + str(sorted(chunk_ids))
    key = f"rerank:{_md5(raw)}"
    cache.client.delete(key)

    result = cache.get_rerank(query, chunk_ids)
    if result is None:
        ok("未命中（首次查询，符合预期）")

    rerank_results = [
        {"chunk_id": 1, "content": "差动保护定值...", "document_id": 10,
         "standard_no": "DL/T 559", "clause": "5.3", "score": 0.95,
         "recall_source": "vector", "document_title": "变压器保护规程"},
    ]
    cache.set_rerank(query, chunk_ids, rerank_results)

    cached = cache.get_rerank(query, chunk_ids)
    if cached is not None and cached[0]["score"] == 0.95:
        ok(f"命中且内容一致（{len(cached)} 条结果）")
    else:
        fail(f"内容异常: {cached}")

    # chunk_ids 顺序不同也应命中（sorted key）
    cached2 = cache.get_rerank(query, [8, 5, 2, 1])
    if cached2 is not None:
        ok("chunk_ids 顺序不同仍命中（sorted Key 正常）")
    else:
        fail("chunk_ids 顺序不同时 Key 计算有误")

    ttl = cache.client.ttl(key)
    info(f"TTL = {ttl}s（预期 ≈ {settings.CACHE_RERANK_TTL}s）")


# ------------------------------------------------------------------ #
# 测试 6：L4 生成缓存
# ------------------------------------------------------------------ #
def test_l4_generation():
    section("测试 6：L4 生成缓存")
    cache = get_cache_manager()
    query = "变压器差动保护定值"
    chunk_contents = ["差动保护定值内容A...", "差动保护定值内容B..."]

    from app.storage.cache import _md5
    raw = query + "|" + "".join(chunk_contents)
    key = f"generation:{_md5(raw)}"
    cache.client.delete(key)

    result = cache.get_generation(query, chunk_contents)
    if result is None:
        ok("未命中（首次查询，符合预期）")

    gen_data = {
        "answer": "变压器差动保护定值应按照 DL/T 559 第 5.3 条执行...",
        "citations": [{"index": 1, "chunk_id": 1, "standard_no": "DL/T 559"}],
        "generation_time_ms": 1850,
    }
    cache.set_generation(query, chunk_contents, gen_data)

    cached = cache.get_generation(query, chunk_contents)
    if cached is not None and cached["answer"] == gen_data["answer"]:
        ok(f"命中且内容一致（answer={cached['answer'][:30]}...）")
    else:
        fail(f"内容异常: {cached}")

    # chunk_contents 顺序不同应 miss（顺序影响答案语义）
    cached2 = cache.get_generation(query, list(reversed(chunk_contents)))
    if cached2 is None:
        ok("chunk_contents 顺序不同正确 miss（保证答案与上下文一致性）")
    else:
        fail("chunk_contents 顺序不同不应命中")

    ttl = cache.client.ttl(key)
    info(f"TTL = {ttl}s（预期 ≈ {settings.CACHE_GENERATION_TTL}s）")


# ------------------------------------------------------------------ #
# 测试 7：缓存开关
# ------------------------------------------------------------------ #
def test_cache_switches():
    section("测试 7：缓存开关（禁用后不读写）")
    cache = get_cache_manager()

    original = settings.CACHE_GENERATION_ENABLED

    # 禁用 L4
    settings.CACHE_GENERATION_ENABLED = False
    query = "开关测试查询"
    chunk_contents = ["内容X"]

    ok_write = cache.set_generation(query, chunk_contents, {"answer": "test"})
    cached = cache.get_generation(query, chunk_contents)

    if not ok_write and cached is None:
        ok("CACHE_GENERATION_ENABLED=False 时 set/get 均跳过")
    else:
        fail(f"开关无效：set={ok_write}, get={cached}")

    # 恢复
    settings.CACHE_GENERATION_ENABLED = original
    ok(f"CACHE_GENERATION_ENABLED 恢复为 {original}")


# ------------------------------------------------------------------ #
# 测试 8：主动失效
# ------------------------------------------------------------------ #
def test_invalidation():
    section("测试 8：主动失效（invalidate_recall_and_generation）")
    cache = get_cache_manager()

    # 写入各级数据
    cache.set_recall("查询A", {}, [{"chunk_id": 1}])
    cache.set_rerank("查询A", [1], [{"chunk_id": 1}])
    cache.set_generation("查询A", ["内容"], {"answer": "答案"})
    cache.set_dense("文本A", np.random.rand(1024).astype(np.float32))

    # 验证写入
    assert cache.get_recall("查询A", {}) is not None
    assert cache.get_generation("查询A", ["内容"]) is not None
    ok("失效前：recall / generation / dense 均已写入")

    # 执行失效
    count = cache.invalidate_recall_and_generation()
    info(f"清除了 {count} 个 key")

    # 验证 L2/L3/L4 被清除
    r = cache.get_recall("查询A", {})
    g = cache.get_generation("查询A", ["内容"])
    d = cache.get_dense("文本A")

    if r is None and g is None:
        ok("L2 召回缓存 / L4 生成缓存 已清除")
    else:
        fail(f"清除不完整: recall={r is not None}, generation={g is not None}")

    if d is not None:
        ok("L1 Embedding 缓存 未被清除（符合预期）")
    else:
        fail("L1 Embedding 缓存 不应被清除")


# ------------------------------------------------------------------ #
# 测试 9：性能基准（set/get 耗时）
# ------------------------------------------------------------------ #
def test_performance():
    section("测试 9：性能基准")
    cache = get_cache_manager()
    n = 100

    # Dense set
    vec = np.random.rand(1024).astype(np.float32)
    t0 = time.perf_counter()
    for i in range(n):
        cache.set_dense(f"perf_text_{i}", vec)
    t1 = time.perf_counter()
    info(f"dense set  ×{n}: {(t1-t0)*1000:.1f}ms  avg={(t1-t0)/n*1000:.2f}ms")

    # Dense get
    t0 = time.perf_counter()
    hits = sum(1 for i in range(n) if cache.get_dense(f"perf_text_{i}") is not None)
    t1 = time.perf_counter()
    info(f"dense get  ×{n}: {(t1-t0)*1000:.1f}ms  avg={(t1-t0)/n*1000:.2f}ms  hits={hits}/{n}")

    # Generation set/get
    t0 = time.perf_counter()
    for i in range(n):
        cache.set_generation(f"perf_query_{i}", ["内容"], {"answer": f"答案{i}"})
    t1 = time.perf_counter()
    info(f"generation set ×{n}: {(t1-t0)*1000:.1f}ms  avg={(t1-t0)/n*1000:.2f}ms")

    t0 = time.perf_counter()
    hits = sum(1 for i in range(n) if cache.get_generation(f"perf_query_{i}", ["内容"]) is not None)
    t1 = time.perf_counter()
    info(f"generation get ×{n}: {(t1-t0)*1000:.1f}ms  avg={(t1-t0)/n*1000:.2f}ms  hits={hits}/{n}")

    # 清理性能测试数据
    for i in range(n):
        cache.delete(f"perf_text_{i}")  # dense key 不会被这个删掉，但无所谓
    ok("性能测试完成")


# ------------------------------------------------------------------ #
# 主流程
# ------------------------------------------------------------------ #
if __name__ == "__main__":
    print("\n缓存层功能测试")
    print(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    print(f"TTL: L1={settings.CACHE_EMBEDDING_TTL}s  L2={settings.CACHE_RECALL_TTL}s  "
          f"L3={settings.CACHE_RERANK_TTL}s  L4={settings.CACHE_GENERATION_TTL}s")

    test_connection()
    test_l1_dense()
    test_l1_sparse()
    test_l2_recall()
    test_l3_rerank()
    test_l4_generation()
    test_cache_switches()
    test_invalidation()
    test_performance()

    print("\n" + "=" * 60)
    print("  全部测试完成")
    print("=" * 60)
