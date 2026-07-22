#!/usr/bin/env python3
"""
测试 MinerU 隔离环境是否正常工作

用法:
    cd backend
    uv run python test_mineru_isolation.py <pdf路径>
"""
import sys
from pathlib import Path

# 添加 app 到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.document_processor.parser import PDFParser


def main():
    if len(sys.argv) < 2:
        print("用法: uv run python test_mineru_isolation.py <pdf路径>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    print(f"=== 测试 MinerU 隔离环境 ===")
    print(f"PDF: {pdf_path}")
    print()

    # 验证主环境的 transformers 版本
    import transformers
    print(f"主环境 transformers 版本: {transformers.__version__}")
    assert transformers.__version__ >= "5.0.0", "主环境应该是 transformers 5.x"
    print("✓ 主环境版本正确\n")

    # 测试 MinerU 解析
    print("开始 MinerU 解析（subprocess 隔离模式）...")
    parser = PDFParser()

    try:
        result = parser.parse_pdf(pdf_path, use_mineru=True, use_vlm=False)

        print(f"\n=== 解析结果 ===")
        print(f"标题: {result['title']}")
        print(f"页数: {result['pages']}")
        print(f"内容长度: {len(result['content'])} 字符")
        print(f"解析方式: {result.get('parsed_by', 'unknown')}")
        print(f"\n内容预览（前 500 字符）:")
        print(result['content'][:500])

        # 保存结果
        out_dir = Path(__file__).parent / "test_output"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{Path(pdf_path).stem}_mineru_isolated.md"
        out_path.write_text(result['content'], encoding="utf-8")
        print(f"\n完整内容已保存到: {out_path}")

        print("\n✓ 测试通过！MinerU 隔离环境工作正常")

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
