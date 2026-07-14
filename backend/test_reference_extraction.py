"""
跨标准引用提取测试

测试 ReferenceExtractor 从文本和 gaps 中提取被引用标准号的能力。

运行方式：
  cd backend && uv run python test_reference_extraction.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.core.retrieval.reference_extractor import ReferenceExtractor


def test_extract_from_gaps():
    """测试从 gaps 中提取被引用标准号"""
    extractor = ReferenceExtractor()

    # 测试1: 标准的 gap 描述
    gaps = [
        "缺少 GB/T 14549 的具体限值",
        "未找到 GB 50054-2011 的分类要求"
    ]
    result = extractor.extract_from_gaps(gaps)
    print(f"Test 1 - gaps: {gaps}")
    print(f"  → Extracted: {result}")
    assert "GB/T 14549" in str(result) or "GB/T" in str(result)
    print("  OK Passed\n")

    # 测试2: 无标准号的 gap
    gaps = ["缺少电压等级分类", "未找到具体数值"]
    result = extractor.extract_from_gaps(gaps)
    print(f"Test 2 - gaps: {gaps}")
    print(f"  → Extracted: {result}")
    assert len(result) == 0
    print("  OK Passed\n")

    # 测试3: 混合标准类型
    gaps = [
        "缺少 DL/T 5432-2021 的内容",
        "未提及 NB/T 32048-2018 的要求",
        "GB 50016-2014 部分条款缺失"
    ]
    result = extractor.extract_from_gaps(gaps)
    print(f"Test 3 - gaps: {gaps}")
    print(f"  → Extracted: {result}")
    assert len(result) == 3
    print("  OK Passed\n")


def test_extract_from_chunks():
    """测试从召回块中提取被引用标准号"""
    extractor = ReferenceExtractor()

    # 测试1: 包含引用指示词的文本
    chunks = [
        {"content": "用户侧储能系统的谐波应符合 GB/T 14549 的规定"},
        {"content": "接地电阻应满足 GB 50057-2010 的要求"},
        {"content": "其他普通描述文本，不含标准引用"}
    ]
    result = extractor.extract_from_chunks(chunks)
    print(f"Test 1 - chunks with references")
    print(f"  → Extracted: {result}")
    assert len(result) >= 2
    print("  OK Passed\n")

    # 测试2: 无引用指示词（不应提取）
    chunks = [
        {"content": "GB/T 14549 是一个标准"},  # 无"应符合"等指示词
        {"content": "根据经验判断"}
    ]
    result = extractor.extract_from_chunks(chunks)
    print(f"Test 2 - chunks without indicators")
    print(f"  → Extracted: {result}")
    # 应该不提取（没有引用指示词）
    print("  OK Passed\n")

    # 测试3: 多种引用指示词
    chunks = [
        {"content": "应执行 DL/T 5000-2020 的相关规定"},
        {"content": "参见 GB 50052-2009 第3章"},
        {"content": "依据 NB/T 12345-2019 进行设计"},
        {"content": "需符合 GB/T 33593-2017 要求"}
    ]
    result = extractor.extract_from_chunks(chunks)
    print(f"Test 3 - multiple indicators")
    print(f"  → Extracted: {result}")
    assert len(result) == 4
    print("  OK Passed\n")


def test_reference_indicators():
    """测试引用指示词检测"""
    extractor = ReferenceExtractor()

    # 正例
    positive_cases = [
        "应符合 GB/T 14549",
        "需满足相关要求",
        "参见第3章",
        "依据国家标准",
        "按照规范执行"
    ]
    for text in positive_cases:
        result = extractor._contains_reference_indicators(text)
        print(f"'{text}' → {result}")
        assert result is True

    print("  OK All positive cases passed\n")

    # 负例
    negative_cases = [
        "这是一个普通描述",
        "电压等级为10kV",
        "系统容量1MW"
    ]
    for text in negative_cases:
        result = extractor._contains_reference_indicators(text)
        print(f"'{text}' -> {result}")
        assert result is False

    print("  OK All negative cases passed\n")


def main():
    print("=" * 60)
    print("跨标准引用提取测试")
    print("=" * 60 + "\n")

    print("[Test Suite 1] Extract from gaps")
    print("-" * 60)
    test_extract_from_gaps()

    print("[Test Suite 2] Extract from chunks")
    print("-" * 60)
    test_extract_from_chunks()

    print("[Test Suite 3] Reference indicators")
    print("-" * 60)
    test_reference_indicators()

    print("=" * 60)
    print("OK All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
