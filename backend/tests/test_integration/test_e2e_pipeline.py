"""
端到端 RAG 管道测试

按照架构文档覆盖完整功能：
  16-业务流程图.md         —— 7 层架构、快/慢车道详细流程
  08-RAG功能层次与状态机.md —— 14 个查询状态

测试用例（5个）：
  TC1  快车道 + 标准号精确查询  → 三路召回 + 重排 + 充分性
  TC2  快车道 + N-1 语义查询    → 向量/关键词主导召回
  TC3  笼统查询                 → NEED_CLARIFICATION 状态
  TC4  慢车道（含"对比"）        → REASONING 状态
  TC5  快车道 + 表格内容查询     → 验证 is_table 块被召回

运行: cd backend && python test_e2e_pipeline.py
"""
import asyncio
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from pathlib import Path

import logging
logging.basicConfig(level=logging.WARNING)

from app.db.session import SessionLocal
from app.services.query_service import QueryService

# 14 个状态（08-RAG功能层次与状态机.md 第四章）
ALL_STATES = [
    "PENDING", "PREPROCESSING", "NEED_CLARIFICATION", "ROUTING",
    "RECALLING", "RERANKING", "SUFFICIENCY_CHECK", "RETRY_RECALL",
    "REASONING", "GENERATING", "CITING", "VALIDATING", "COMPLETED", "ERROR",
]

@dataclass
class TestCase:
    id: str
    name: str
    query: str
    expected_lane: str   # "fast" / "slow" / "clarify"
    expected_states: list
    notes: str = ""

@dataclass
class TestResult:
    case_id: str
    passed: bool
    actual_lane: str
    actual_states: list
    retrieval_ms: int
    total_ms: int
    recall_count: int
    retry_triggered: bool
    top_chunks: list
    answer_preview: str
    errors: list = field(default_factory=list)

# ──────────────────────────────────────────────────────────────
# 测试用例（基于已入库的 GB/T 45418-2025，298 个块）
# ──────────────────────────────────────────────────────────────

TEST_CASES = [
    TestCase(
        id="TC1",
        name="快车道 - 标准号精确查询",
        query="GB/T 45418-2025 的适用范围是什么",
        expected_lane="fast",
        expected_states=["PREPROCESSING", "ROUTING", "RECALLING",
                         "RERANKING", "SUFFICIENCY_CHECK", "GENERATING", "COMPLETED"],
        notes="含标准号 → 快车道；结构化召回应命中"
    ),
    TestCase(
        id="TC2",
        name="快车道 - N-1 语义查询",
        query="N-1准则对电力系统稳定性的具体要求",
        expected_lane="fast",
        expected_states=["PREPROCESSING", "ROUTING", "RECALLING",
                         "RERANKING", "SUFFICIENCY_CHECK", "GENERATING", "COMPLETED"],
        notes="无标准号 → 默认快车道；向量+关键词召回主导"
    ),
    TestCase(
        id="TC3",
        name="笼统查询 - 触发澄清",
        query="电力",
        expected_lane="clarify",
        expected_states=["PREPROCESSING", "NEED_CLARIFICATION"],
        notes="高笼统度 → NEED_CLARIFICATION；不进入检索层"
    ),
    TestCase(
        id="TC4",
        name="慢车道 - 对比查询（多跳推理）",
        query="N-1准则与短路电流额定值之间有什么区别和对比",
        expected_lane="slow",
        expected_states=["PREPROCESSING", "ROUTING", "REASONING",
                         "GENERATING", "COMPLETED"],
        notes='含"区别"+"对比" → 路由到慢车道'
    ),
    TestCase(
        id="TC5",
        name="快车道 - 表格内容查询",
        query="GB/T 45418-2025 短路电流额定值的表格规定",
        expected_lane="fast",
        expected_states=["PREPROCESSING", "ROUTING", "RECALLING",
                         "RERANKING", "SUFFICIENCY_CHECK", "GENERATING", "COMPLETED"],
        notes="应召回 is_table=True 的表格块（表2/表3）"
    ),
]

# ──────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────

SEP  = "─" * 68
SEP2 = "=" * 68

def infer_state_trace(result: dict) -> list:
    """根据 execute_query() 返回值推断实际状态转换路径"""
    states = ["PENDING", "PREPROCESSING"]

    if result.get("status") == "need_clarification":
        states.append("NEED_CLARIFICATION")
        return states

    states.append("ROUTING")

    lane = result.get("lane", "fast")
    if lane == "slow":
        states.append("REASONING")
    else:
        states.extend(["RECALLING", "RERANKING", "SUFFICIENCY_CHECK"])
        if result.get("retry_triggered"):
            states.append("RETRY_RECALL")

    states.extend(["GENERATING", "CITING", "VALIDATING", "COMPLETED"])
    return states

def fmt_state_arrow(states: list) -> str:
    return " → ".join(states)

def check_states(expected: list, actual: list) -> bool:
    """验证 expected 中的关键状态是否都出现在 actual 中（保持相对顺序）"""
    it = iter(actual)
    return all(s in it for s in expected)

def perf_verdict(total_ms: int, lane: str) -> str:
    """对照性能目标给出判断（08-RAG功能层次 6.1 节）"""
    if lane == "fast":
        if total_ms <= 2500:
            return f"✅ {total_ms}ms  ≤ 2500ms P50目标"
        elif total_ms <= 4000:
            return f"⚠️  {total_ms}ms  2500ms < t ≤ 4000ms P99目标"
        else:
            return f"❌ {total_ms}ms  > 4000ms P99上限"
    elif lane == "slow":
        if total_ms <= 5000:
            return f"✅ {total_ms}ms  ≤ 5000ms P50目标"
        elif total_ms <= 8000:
            return f"⚠️  {total_ms}ms  5000ms < t ≤ 8000ms P99目标"
        else:
            return f"❌ {total_ms}ms  > 8000ms P99上限"
    return f"{total_ms}ms"

# ──────────────────────────────────────────────────────────────
# 单个测试用例执行
# ──────────────────────────────────────────────────────────────

async def run_test_case(tc: TestCase, service: QueryService) -> TestResult:
    print(f"\n{SEP2}")
    print(f"  {tc.id}  {tc.name}")
    print(f"  查询: 「{tc.query}」")
    if tc.notes:
        print(f"  说明: {tc.notes}")
    print(SEP2)

    errors: list = []
    t0 = time.time()

    try:
        result = await service.execute_query(
            query=tc.query,
            user_id=1,
            conversation_id=f"test_{tc.id}"
        )
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        print(f"  ❌ execute_query 异常: {e}")
        return TestResult(
            case_id=tc.id, passed=False, actual_lane="error",
            actual_states=["PENDING", "ERROR"], retrieval_ms=elapsed,
            total_ms=elapsed, recall_count=0, retry_triggered=False,
            top_chunks=[], answer_preview="", errors=[str(e)]
        )

    # ── 状态机追踪 ──────────────────────────────────────────────
    actual_states = infer_state_trace(result)
    print(f"\n【状态机】")
    print(f"  预期: {fmt_state_arrow(tc.expected_states)}")
    print(f"  实际: {fmt_state_arrow(actual_states)}")

    states_ok = check_states(tc.expected_states, actual_states)
    if states_ok:
        print(f"  ✅ 状态路径匹配")
    else:
        missing = [s for s in tc.expected_states if s not in actual_states]
        print(f"  ❌ 缺少状态: {missing}")
        errors.append(f"missing states: {missing}")

    # ── 澄清分支（TC3）──────────────────────────────────────────
    if result.get("status") == "need_clarification":
        print(f"\n【预处理层】")
        print(f"  笼统度: {result.get('vagueness_score', 'N/A')}")
        opts = result.get("clarification_options") or []
        print(f"  澄清选项数: {len(opts)}")
        for opt in opts[:3]:
            print(f"    · [{opt.get('id')}] {opt.get('label', '')}")
        lane_ok = (tc.expected_lane == "clarify")
        print(f"\n  {'✅' if lane_ok else '❌'} 正确触发澄清流程")
        if not lane_ok:
            errors.append(f"expected lane=clarify, got need_clarification")
        return TestResult(
            case_id=tc.id, passed=(states_ok and lane_ok),
            actual_lane="clarify", actual_states=actual_states,
            retrieval_ms=0, total_ms=result.get("total_time", 0),
            recall_count=0, retry_triggered=False,
            top_chunks=[], answer_preview="", errors=errors
        )

    # ── 路由层 ──────────────────────────────────────────────────
    actual_lane = result.get("lane", "unknown")
    print(f"\n【路由层】")
    print(f"  决策: {actual_lane.upper()}  原因: {result.get('route_reason', 'N/A')}")
    lane_ok = actual_lane == tc.expected_lane
    print(f"  {'✅' if lane_ok else '❌'} 路由决策（期望={tc.expected_lane}，实际={actual_lane}）")
    if not lane_ok:
        errors.append(f"lane mismatch: expected={tc.expected_lane}, got={actual_lane}")

    # ── 召回层 + 重排层（快车道）────────────────────────────────
    top_chunks: list = []
    if actual_lane == "fast":
        print(f"\n【召回层 + 重排层】")
        exp_queries = result.get("expanded_queries") or []
        print(f"  扩展查询数: {len(exp_queries)}")
        for q in exp_queries[:3]:
            print(f"    · {q}")
        filters = result.get("filters") or {}
        print(f"  元数据过滤: {filters if filters else '（无）'}")
        rc = result.get("recall_count", 0)
        retry = result.get("retry_triggered", False)
        print(f"  重排后块数: {rc}  二次检索: {'是' if retry else '否'}")
        suf = result.get("sufficiency_result")
        if suf:
            ok_   = suf.sufficient if hasattr(suf, 'sufficient') else suf.get('sufficient')
            src_  = suf.source if hasattr(suf, 'source') else suf.get('source', '?')
            conf_ = (suf.confidence if hasattr(suf, 'confidence') else suf.get('confidence')) or 0
            print(f"  充分性判断: {'充分' if ok_ else '不充分'}  来源={src_}  置信={conf_:.2f}")
        rerank_results = result.get("rerank_results") or []
        if rerank_results:
            print(f"\n  Top-{len(rerank_results)} 重排结果：")
            for i, r in enumerate(rerank_results, 1):
                cid     = r.chunk_id if hasattr(r, 'chunk_id') else r.get('chunk_id')
                score   = r.score if hasattr(r, 'score') else r.get('score', 0)
                src     = r.recall_source if hasattr(r, 'recall_source') else r.get('recall_source', '?')
                std     = r.standard_no if hasattr(r, 'standard_no') else r.get('standard_no', '')
                clause  = r.clause if hasattr(r, 'clause') else r.get('clause', '')
                content = (r.content if hasattr(r, 'content') else r.get('content', '')) or ''
                preview = content[:80].replace('\n', ' ')
                print(f"  [{i}] chunk_id={cid}  score={score:.4f}  src={src}")
                print(f"       {std}  {clause}")
                print(f"       {preview}...")
                top_chunks.append({'chunk_id': cid, 'score': score, 'source': src})

    # ── 慢车道 ──────────────────────────────────────────────────
    elif actual_lane == "slow":
        print(f"\n【慢车道 - 多跳推理】")
        steps = result.get("steps_taken", 0)
        reasoning = result.get("reasoning_steps") or []
        print(f"  推理步数: {steps}")
        for i, step in enumerate(reasoning[:3], 1):
            print(f"  步骤{i}: {str(step)[:120]}")

    # ── 生成层 ──────────────────────────────────────────────────
    print(f"\n【生成层】")
    answer = result.get("answer", "") or ""
    gen_ms = result.get("generation_time", 0)
    citations = result.get("citations") or []
    answer_preview = answer[:160].replace('\n', ' ')
    print(f"  生成耗时: {gen_ms}ms")
    print(f"  答案（前160字）: {answer_preview}")
    print(f"  引用数: {len(citations)}")
    for c in citations[:3]:
        std_  = c.get('standard_no', '')
        cl_   = c.get('clause', '')
        snip_ = (c.get('content_snippet') or '')[:50]
        print(f"    [{c.get('index')}] {std_} {cl_}  「{snip_}」")

    # ── 性能 ──────────────────────────────────────────────────
    total_ms = result.get("total_time", 0)
    retr_ms  = result.get("retrieval_time", 0)
    print(f"\n【性能】")
    print(f"  检索层: {retr_ms}ms  |  生成层: {gen_ms}ms  |  端到端: {total_ms}ms")
    print(f"  {perf_verdict(total_ms, actual_lane)}")

    passed = states_ok and lane_ok
    print(f"\n  {'✅ PASS' if passed else '❌ FAIL'}  {tc.id}")
    if errors:
        for e in errors:
            print(f"    · {e}")

    return TestResult(
        case_id=tc.id, passed=passed,
        actual_lane=actual_lane, actual_states=actual_states,
        retrieval_ms=retr_ms, total_ms=total_ms,
        recall_count=result.get("recall_count", 0),
        retry_triggered=result.get("retry_triggered", False),
        top_chunks=top_chunks, answer_preview=answer_preview,
        errors=errors
    )

# ──────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────

async def main():
    print(f"\n{SEP2}")
    print("  端到端 RAG 管道测试")
    print("  16-业务流程图.md + 08-RAG功能层次与状态机.md")
    print(f"{SEP2}")

    db = SessionLocal()
    service = QueryService(db=db)
    results: list[TestResult] = []

    try:
        for tc in TEST_CASES:
            tr = await run_test_case(tc, service)
            results.append(tr)
    finally:
        db.close()

    # ── 汇总报告 ────────────────────────────────────────────────
    print(f"\n{SEP2}")
    print("  测试汇总")
    print(SEP2)
    passed_n = sum(1 for r in results if r.passed)
    total_n  = len(results)
    print(f"\n  通过: {passed_n}/{total_n}")
    print(f"\n  {'ID':<5}  {'通过':<4}  {'车道':<6}  {'总耗时':>7}  {'状态路径'}")
    print(f"  {SEP}")
    for r in results:
        mark   = "✅" if r.passed else "❌"
        states = " → ".join(r.actual_states)
        print(f"  {r.case_id:<5}  {mark:<4}  {r.actual_lane:<6}  {r.total_ms:>6}ms  {states}")

    # 性能汇总（仅快车道，对照 <2.5s P50 目标）
    fast_results = [r for r in results if r.actual_lane == "fast"]
    if fast_results:
        avg_ms = sum(r.total_ms for r in fast_results) // len(fast_results)
        max_ms = max(r.total_ms for r in fast_results)
        print(f"\n  快车道性能（n={len(fast_results)}）：")
        print(f"    平均端到端: {avg_ms}ms  最大: {max_ms}ms")
        print(f"    {perf_verdict(avg_ms, 'fast')} （均值）")

    # 14 状态覆盖汇总
    covered = set()
    for r in results:
        covered.update(r.actual_states)
    uncovered = [s for s in ALL_STATES if s not in covered]
    print(f"\n  状态机覆盖率: {len(covered)}/{len(ALL_STATES)} 个状态")
    print(f"    已覆盖: {', '.join(sorted(covered))}")
    if uncovered:
        print(f"    未覆盖: {', '.join(uncovered)}")
        print(f"    (RETRY_RECALL 需不充分查询触发；VALIDATING 需LLM校验开启)")

    print(f"\n{SEP2}")
    return 0 if passed_n == total_n else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
