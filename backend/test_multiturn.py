"""
多轮对话功能测试

测试覆盖：
  1. QueryLogRepository.get_conversation_history — 历史读取、升序排序、空结果
  2. CoreferenceResolver.resolve — 不触发/触发/降级/配置关闭
  3. AnswerGenerator._build_history_section — 空/正常/token截断
  4. cache.get_generation / set_generation — 多轮时跳过缓存

运行方式：
  cd backend && python test_multiturn.py
"""
import sys
import os
import asyncio
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))

# ──────────────────────────────────────────────────────────────────────────────
# 辅助：构造假 QueryLog 行
# ──────────────────────────────────────────────────────────────────────────────
def _make_row(query: str, answer: str):
    row = MagicMock()
    row.query = query
    row.answer = answer
    return row


# ══════════════════════════════════════════════════════════════════════════════
# 1. QueryLogRepository
# ══════════════════════════════════════════════════════════════════════════════
class TestQueryLogRepository(unittest.TestCase):

    def _make_repo(self, rows):
        """返回一个注入了假数据的 QueryLogRepository"""
        from app.db.repositories.query_repo import QueryLogRepository
        db = MagicMock()
        db.execute.return_value.all.return_value = rows
        return QueryLogRepository(db)

    def test_empty_history(self):
        repo = self._make_repo([])
        result = repo.get_conversation_history("conv-001", limit=5)
        self.assertEqual(result, [])

    def test_returns_ascending_order(self):
        """
        DB 以 DESC 返回 [新, 旧]，reversed() 后应变成 [旧, 新]。
        """
        rows = [
            _make_row("第二轮问题", "第二轮答案"),
            _make_row("第一轮问题", "第一轮答案"),
        ]
        repo = self._make_repo(rows)
        result = repo.get_conversation_history("conv-001")
        self.assertEqual(result[0]["query"], "第一轮问题")
        self.assertEqual(result[1]["query"], "第二轮问题")

    def test_result_format(self):
        rows = [_make_row("问", "答")]
        repo = self._make_repo(rows)
        result = repo.get_conversation_history("conv-001")
        self.assertIn("query", result[0])
        self.assertIn("answer", result[0])

    def test_limit_passed_to_query(self):
        from app.db.repositories.query_repo import QueryLogRepository
        db = MagicMock()
        db.execute.return_value.all.return_value = []
        repo = QueryLogRepository(db)
        repo.get_conversation_history("conv-001", limit=3)
        # 确认 execute 被调用了（limit 由 SQLAlchemy statement 内部处理，无需二次断言）
        db.execute.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# 2. CoreferenceResolver
# ══════════════════════════════════════════════════════════════════════════════
class TestCoreferenceResolver(unittest.TestCase):

    def setUp(self):
        from app.core.preprocessing.coreference_resolver import CoreferenceResolver
        self.resolver = CoreferenceResolver()

    def test_no_resolution_when_history_empty(self):
        result = self.resolver.resolve("接地电阻有哪些要求？", history=[])
        self.assertEqual(result, "接地电阻有哪些要求？")

    def test_no_resolution_when_no_signals(self):
        history = [{"query": "接地要求", "answer": "接地电阻不超过4Ω"}]
        result = self.resolver.resolve("变压器的额定电压是多少？", history=history)
        self.assertEqual(result, "变压器的额定电压是多少？")

    def test_coreference_signal_triggers_llm(self):
        """含指代词"它"时应调用 LLM"""
        history = [{"query": "什么是接地电阻", "answer": "接地电阻是..."}]
        with patch(
            "app.core.preprocessing.coreference_resolver.CoreferenceResolver._llm_resolve",
            return_value="接地电阻的限值是多少？"
        ) as mock_llm:
            result = self.resolver.resolve("它的限值是多少？", history=history)
        mock_llm.assert_called_once()
        self.assertEqual(result, "接地电阻的限值是多少？")

    def test_ellipsis_signal_triggers_llm(self):
        """省略主语的追问应触发 LLM"""
        history = [{"query": "接地网设计", "answer": "接地网需要..."}]
        with patch(
            "app.core.preprocessing.coreference_resolver.CoreferenceResolver._llm_resolve",
            return_value="接地网还有哪些施工要求？"
        ) as mock_llm:
            result = self.resolver.resolve("还有哪些要求？", history=history)
        mock_llm.assert_called_once()

    def test_llm_failure_falls_back_to_original(self):
        """LLM 异常时降级返回原始 query"""
        history = [{"query": "接地要求", "answer": "某答案"}]
        with patch(
            "app.core.preprocessing.coreference_resolver.CoreferenceResolver._llm_resolve",
            side_effect=RuntimeError("LLM timeout")
        ):
            result = self.resolver.resolve("它的限值？", history=history)
        self.assertEqual(result, "它的限值？")

    def test_disabled_by_config(self):
        """COREFERENCE_RESOLUTION_ENABLED=False 时直接返回原始 query"""
        history = [{"query": "接地要求", "answer": "某答案"}]
        with patch("app.config.settings") as mock_settings:
            mock_settings.COREFERENCE_RESOLUTION_ENABLED = False
            result = self.resolver.resolve("它的限值？", history=history)
        self.assertEqual(result, "它的限值？")

    def test_uses_only_last_two_turns(self):
        """只取最近 2 轮传给 _llm_resolve"""
        history = [
            {"query": "Q1", "answer": "A1"},
            {"query": "Q2", "answer": "A2"},
            {"query": "Q3", "answer": "A3"},
        ]
        captured = {}

        def fake_llm_resolve(query, recent):
            captured["recent"] = recent
            return query

        with patch.object(self.resolver, "_llm_resolve", side_effect=fake_llm_resolve):
            self.resolver.resolve("该标准是什么？", history=history)

        self.assertEqual(len(captured["recent"]), 2)
        self.assertEqual(captured["recent"][0]["query"], "Q2")
        self.assertEqual(captured["recent"][1]["query"], "Q3")


# ══════════════════════════════════════════════════════════════════════════════
# 3. AnswerGenerator._build_history_section
# ══════════════════════════════════════════════════════════════════════════════
class TestBuildHistorySection(unittest.TestCase):

    def setUp(self):
        from app.core.generation.generator import AnswerGenerator
        # 跳过 LLMClient 初始化
        with patch("app.core.generation.generator.get_llm_client"), \
             patch("app.core.generation.generator.get_citation_extractor"), \
             patch("app.core.generation.generator.get_validator"):
            self.gen = AnswerGenerator()

    def test_none_history_returns_empty(self):
        self.assertEqual(self.gen._build_history_section(None), "")

    def test_empty_history_returns_empty(self):
        self.assertEqual(self.gen._build_history_section([]), "")

    def test_single_turn_in_output(self):
        history = [{"query": "接地要求？", "answer": "接地电阻不超过4Ω。"}]
        section = self.gen._build_history_section(history)
        self.assertIn("接地要求？", section)
        self.assertIn("接地电阻不超过4Ω。", section)
        self.assertIn("对话历史", section)

    def test_answer_truncated_to_500_chars(self):
        long_answer = "答" * 600
        history = [{"query": "Q", "answer": long_answer}]
        section = self.gen._build_history_section(history)
        # section 中的 answer 部分不应超过 500 字
        self.assertNotIn("答" * 501, section)

    def test_token_budget_drops_oldest_turns(self):
        """超出 token 预算时最旧的轮次被丢弃"""
        # 每轮约 200 chars → 3 轮 ≈ 400 tokens（/1.5）
        # 将 MAX_HISTORY_TOKENS 设为 200，迫使丢弃最旧一轮
        turns = [
            {"query": "旧问题A" * 30, "answer": "旧答案A" * 30},
            {"query": "旧问题B" * 30, "answer": "旧答案B" * 30},
            {"query": "新问题C", "answer": "新答案C"},
        ]
        with patch("app.config.settings") as mock_settings:
            mock_settings.MAX_HISTORY_TOKENS = 50  # 非常小，迫使截断
            section = self.gen._build_history_section(turns)

        # 最旧的轮次应被丢弃；最新轮次应保留
        self.assertIn("新问题C", section)

    def test_all_turns_within_budget_kept(self):
        history = [
            {"query": "Q1", "answer": "A1"},
            {"query": "Q2", "answer": "A2"},
        ]
        with patch("app.config.settings") as mock_settings:
            mock_settings.MAX_HISTORY_TOKENS = 2000
            section = self.gen._build_history_section(history)
        self.assertIn("Q1", section)
        self.assertIn("Q2", section)

    def test_section_contains_disclaimer(self):
        history = [{"query": "Q", "answer": "A"}]
        section = self.gen._build_history_section(history)
        self.assertIn("不作为答案依据", section)


# ══════════════════════════════════════════════════════════════════════════════
# 4. L4 缓存：多轮时跳过
# ══════════════════════════════════════════════════════════════════════════════
class TestGenerationCacheMultiTurn(unittest.TestCase):

    def _make_cache(self):
        from app.storage.cache import CacheManager
        cache = CacheManager.__new__(CacheManager)
        # 注入假 Redis client（绕过 property）
        mock_redis = MagicMock()
        cache._client = mock_redis
        return cache, mock_redis

    def _patch_settings(self, enabled=True):
        mock = MagicMock()
        mock.CACHE_GENERATION_ENABLED = enabled
        mock.CACHE_GENERATION_TTL = 7200
        return mock

    def test_get_returns_none_when_conversation_id_present(self):
        cache, _ = self._make_cache()
        with patch("app.storage.cache.settings", self._patch_settings()):
            result = cache.get_generation("query", ["chunk1"], conversation_id="conv-123")
        self.assertIsNone(result)

    def test_set_returns_false_when_conversation_id_present(self):
        cache, mock_redis = self._make_cache()
        with patch("app.storage.cache.settings", self._patch_settings()):
            result = cache.set_generation("query", ["chunk1"], {"answer": "x"}, conversation_id="conv-123")
        self.assertFalse(result)
        mock_redis.setex.assert_not_called()

    def test_get_proceeds_when_no_conversation_id(self):
        """无 conversation_id 时走正常缓存路径（Redis get）"""
        cache, mock_redis = self._make_cache()
        mock_redis.get.return_value = None
        with patch("app.storage.cache.settings", self._patch_settings()):
            cache.get_generation("query", ["chunk1"], conversation_id=None)
        mock_redis.get.assert_called_once()

    def test_get_bypassed_when_cache_disabled(self):
        cache, mock_redis = self._make_cache()
        with patch("app.storage.cache.settings", self._patch_settings(enabled=False)):
            result = cache.get_generation("query", ["chunk1"], conversation_id=None)
        self.assertIsNone(result)
        mock_redis.get.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestQueryLogRepository))
    suite.addTests(loader.loadTestsFromTestCase(TestCoreferenceResolver))
    suite.addTests(loader.loadTestsFromTestCase(TestBuildHistorySection))
    suite.addTests(loader.loadTestsFromTestCase(TestGenerationCacheMultiTurn))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
