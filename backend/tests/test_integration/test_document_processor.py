"""
测试文档处理流程
"""
import sys
sys.path.append('.')

from app.core.document_processor.parser import pdf_parser
from app.core.document_processor.chunker import document_chunker
from app.core.document_processor.metadata_extractor import metadata_extractor
from app.core.document_processor.classifier import document_classifier
from pathlib import Path

# 设置 UTF-8 输出

def test_document_processing():
    """测试文档处理流程"""
    print("Testing document processing pipeline...")

    # 查找一个测试 PDF
    pdf_dir = Path("../电力国标PDF")
    if not pdf_dir.exists():
        print(f"PDF directory not found: {pdf_dir}")
        return

    # 选择第一个 PDF 文件
    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print("No PDF files found")
        return

    test_pdf = pdf_files[0]
    print(f"\nTesting with: {test_pdf.name}")

    # 1. 测试 PDF 解析
    print("\n=== Step 1: PDF Parsing ===")
    try:
        parsed = pdf_parser.parse_pdf(str(test_pdf))
        print(f"Title: {parsed['title']}")
        print(f"Pages: {parsed['pages']}")
        print(f"Is OCR: {parsed['is_ocr']}")
        print(f"Metadata: {parsed['metadata']}")
        print(f"Content length: {len(parsed['content'])} chars")
        print(f"Content preview:\n{parsed['content'][:500]}")

        # 保存完整内容到文件用于调试
        with open("parsed_content.txt", "w", encoding="utf-8") as f:
            f.write(parsed['content'])
        print("\n[DEBUG] Full content saved to parsed_content.txt")

    except Exception as e:
        print(f"PDF parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 2. 测试元数据提取
    print("\n=== Step 2: Metadata Extraction ===")
    try:
        metadata = metadata_extractor.extract_from_document(
            content=parsed['content'],
            filename=test_pdf.name,
            parsed_metadata=parsed['metadata']
        )
        print(f"Extracted metadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")

        keywords = metadata_extractor.extract_keywords(parsed['content'], top_k=5)
        print(f"Keywords: {keywords}")
    except Exception as e:
        print(f"Metadata extraction failed: {e}")
        import traceback
        traceback.print_exc()

    # 3. 测试文档分类
    print("\n=== Step 3: Document Classification ===")
    try:
        classification = document_classifier.classify(
            content=parsed['content'],
            metadata=metadata,
            use_llm=False  # 使用规则分类
        )
        print(f"Classification result:")
        for key, value in classification.items():
            print(f"  {key}: {value}")
    except Exception as e:
        print(f"Classification failed: {e}")
        import traceback
        traceback.print_exc()

    # 4. 测试文档分块
    print("\n=== Step 4: Document Chunking ===")
    try:
        chunks = document_chunker.chunk_document(
            content=parsed['content'],
            doc_metadata=metadata,
            document_id=1,  # 假设文档 ID
            doc_type="standard"
        )
        print(f"Total chunks: {len(chunks)}")

        # 统计父子块
        parent_chunks = [c for c in chunks if c.chunk_type == "parent"]
        child_chunks = [c for c in chunks if c.chunk_type == "child"]
        print(f"Parent chunks: {len(parent_chunks)}")
        print(f"Child chunks: {len(child_chunks)}")

        # 显示前3个块
        print("\nFirst 3 chunks:")
        for i, chunk in enumerate(chunks[:3]):
            print(f"\n[Chunk {i+1}]")
            print(f"  Type: {chunk.chunk_type}")
            print(f"  Chapter: {chunk.chapter}")
            print(f"  Clause: {chunk.clause}")
            print(f"  Chars: {chunk.char_count}")
            print(f"  Tokens: {chunk.token_count}")
            print(f"  Content preview: {chunk.content[:200]}")

    except Exception as e:
        print(f"Chunking failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n[PASS] Document processing test completed!")

if __name__ == "__main__":
    test_document_processing()
