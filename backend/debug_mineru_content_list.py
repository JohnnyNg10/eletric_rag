"""
调试脚本：检查 MinerU content_list 的实际内容
"""
import sys
sys.path.insert(0, '.')

from pathlib import Path
from app.core.document_processor.mineru_client import mineru_client
from app.config import settings
import json

# 使用已存在的 Markdown 文件对应的 PDF
pdf_path = Path('/tmp/rag_import/af3c9584cac3416b9e7328f9a28ada7d_GB+5226.6-2014.pdf')

# 如果 PDF 不存在，使用任意一个
if not pdf_path.exists():
    import os
    for f in os.listdir('电力国标PDF'):
        if f.endswith('.pdf'):
            pdf_path = Path('电力国标PDF') / f
            break

if not pdf_path.exists():
    print(f'找不到测试PDF文件')
    sys.exit(1)

print(f'测试PDF: {pdf_path.name}')
print('=' * 60)

# 调用 MinerU API
print('调用 MinerU API (同步模式)...')
result = mineru_client.parse_sync(
    str(pdf_path),
    backend=settings.MINERU_BACKEND,
    return_content_list=True,
    timeout=60
)

print(f'\n返回结果:')
print(f'  - md_content长度: {len(result.get("md_content", ""))} 字符')

content_list = result.get('content_list', [])
print(f'  - content_list 原始类型: {type(content_list)}')

# 如果是字符串，解析 JSON
if isinstance(content_list, str):
    try:
        content_list = json.loads(content_list)
        print(f'  - 解析后类型: {type(content_list)}')
    except Exception as e:
        print(f'  - JSON 解析失败: {e}')
        sys.exit(1)

print(f'  - content_list 长度: {len(content_list)}')

# 统计类型
types_count = {}
for item in content_list:
    if isinstance(item, dict):
        t = item.get('type', 'unknown')
        types_count[t] = types_count.get(t, 0) + 1

print(f'\n类型统计:')
for t, count in sorted(types_count.items()):
    print(f'  {t}: {count}')

# 显示前 3 个 image 类型的详细信息
print(f'\n前3个图片项详细信息:')
image_items = [item for item in content_list if isinstance(item, dict) and item.get('type') == 'image'][:3]

for i, item in enumerate(image_items):
    print(f'\n[图片 {i+1}]')
    print(f'  所有字段: {list(item.keys())}')
    print(f'  img_path: {item.get("img_path")}')
    print(f'  content (描述): {item.get("content", "")[:100]}')
    if 'page_number' in item:
        print(f'  page_number: {item.get("page_number")}')
    if 'bbox' in item:
        print(f'  bbox: {item.get("bbox")}')
