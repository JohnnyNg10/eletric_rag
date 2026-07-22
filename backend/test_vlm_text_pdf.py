"""
测试文字版 PDF 的 VLM 解析效果
用法: uv run python test_vlm_text_pdf.py <pdf路径> [--pages N]
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings
from app.core.document_processor.parser import PDFParser


async def test_vlm_parse(pdf_path: str, max_pages: int | None = None):
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"文件不存在: {pdf_path}")
        sys.exit(1)

    print("=" * 60)
    print(f"文件  : {pdf_file.name}")
    print(f"大小  : {pdf_file.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"最多处理: {'全部' if max_pages is None else max_pages} 页")
    print(f"VLM   : {settings.VLM_PROVIDER} / {settings.DOUBAO_MODEL}")
    print("=" * 60)

    if not settings.ENABLE_VLM_DESCRIPTION:
        print("ENABLE_VLM_DESCRIPTION=False，退出")
        return

    import fitz

    doc = fitz.open(str(pdf_file))
    total_pages = len(doc)
    n = total_pages if max_pages is None else min(max_pages, total_pages)
    print(f"\nPDF 总页数: {total_pages}，本次解析 {n} 页\n")

    parser = PDFParser()

    # 加载 VLM client（延迟加载）
    from app.core.vlm.vlm_client import vlm_client
    parser.vlm_client = vlm_client

    tasks = [
        parser._process_page_with_vlm(doc, page_num)
        for page_num in range(n)
    ]

    print("开始并行 VLM 解析...")
    page_results = await asyncio.gather(*tasks)
    doc.close()

    # 汇总
    markdown_parts = []
    total_chars = 0
    total_images = 0

    for pr in page_results:
        page_num = pr["page_num"]
        content = pr["content"]
        images = pr["images"]

        total_chars += len(content)
        total_images += len(images)

        markdown_parts.append(f"\n\n---\n## 第 {page_num + 1} 页\n\n")
        markdown_parts.append(content)

        if images:
            markdown_parts.append(f"\n\n*[本页包含 {len(images)} 张嵌入图片]*\n")
            for img in images:
                if img.get("description"):
                    markdown_parts.append(
                        f"- 图{img['index'] + 1}：{img['description']}\n"
                    )

        print(f"  第 {page_num + 1} 页：{len(content)} 字符，{len(images)} 图片")

    full_md = "".join(markdown_parts)

    # 保存 Markdown 到本地
    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{pdf_file.stem}_vlm.md"
    out_path.write_text(full_md, encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"解析完成")
    print(f"  总字符数 : {total_chars}")
    print(f"  总图片数 : {total_images}")
    print(f"  输出路径 : {out_path.resolve()}")
    print("=" * 60)

    # 打印前 500 字符预览
    print("\n--- Markdown 预览（前 500 字符）---\n")
    print(full_md[:500])
    print("\n...")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("用法: uv run python test_vlm_text_pdf.py <pdf路径> [--pages N]")
        sys.exit(1)

    pdf = args[0]
    pages = None
    if "--pages" in args:
        idx = args.index("--pages")
        pages = int(args[idx + 1])

    asyncio.run(test_vlm_parse(pdf, pages))
