"""
测试 MinerU 解析文字版 PDF
用法: uv run python test_mineru.py <pdf路径>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.document_processor.parser import pdf_parser


def main():
    if len(sys.argv) < 2:
        print("用法: uv run python test_mineru.py <pdf路径>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    print("=" * 60)
    print(f"文件: {Path(pdf_path).name}")
    print(f"解析方式: MinerU (use_mineru=True, use_vlm=False)")
    print("=" * 60)
    print()

    result = pdf_parser.parse_pdf(pdf_path, use_mineru=True, use_vlm=False)

    content = result["content"]
    print(f"解析完成")
    print(f"  解析器   : {result.get('parsed_by', 'unknown')}")
    print(f"  总页数   : {result['pages']}")
    print(f"  总字符数 : {len(content)}")
    print(f"  图片数   : {len(result.get('images', []))}")
    print()

    # 保存输出
    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{Path(pdf_path).stem}_mineru.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"输出路径: {out_path.resolve()}")
    print()

    # 预览前 800 字符
    print("--- 内容预览（前 800 字符）---")
    print(content[:800])
    print("...")


if __name__ == "__main__":
    main()
