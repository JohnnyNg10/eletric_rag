"""
Convert all PDFs in D:\dl\测试数据\ to Markdown, output to D:\dl\测试数据\md\
Skips files that already have a corresponding .md file.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from pdf_to_md import convert_pdf_to_md

PDF_DIR = r"D:\dl\测试数据"
MD_DIR  = r"D:\dl\测试数据\md"

os.makedirs(MD_DIR, exist_ok=True)

pdf_files = sorted(f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf"))
print(f"Found {len(pdf_files)} PDF(s) in {PDF_DIR}\n")

completed = failed = skipped = 0

for pdf_file in pdf_files:
    md_name = os.path.splitext(pdf_file)[0] + ".md"
    md_path = os.path.join(MD_DIR, md_name)

    if os.path.exists(md_path):
        print(f"  SKIP  {pdf_file}  (already converted)")
        skipped += 1
        continue

    pdf_path = os.path.join(PDF_DIR, pdf_file)
    print(f"  CONV  {pdf_file} ...", end=" ", flush=True)
    try:
        convert_pdf_to_md(pdf_path, MD_DIR)
        print("OK")
        completed += 1
    except Exception as e:
        print(f"FAIL  {e}")
        failed += 1

print(f"\nDone — converted: {completed}, skipped: {skipped}, failed: {failed}")
