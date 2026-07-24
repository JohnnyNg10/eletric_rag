"""
查找 MinerU 生成的图片文件位置
"""
import os
import sys
from pathlib import Path

# 从 Markdown 中提取的图片文件名
target_image = "e9c5752034733b41f26df35d0f1e66fdc7e53c718e53c67b651fa6e7861c4be8.jpg"

print(f"查找图片: {target_image}")
print("=" * 60)

# 搜索可能的目录
search_roots = [
    Path("D:/dl"),
    Path.home(),
    Path("/tmp"),
    Path("C:/tmp"),
    Path("C:/Users/39948/AppData/Local/Temp"),
]

found_paths = []

for root in search_roots:
    if not root.exists():
        continue

    print(f"搜索: {root}")

    try:
        # 使用 os.walk 递归搜索（限制深度避免太慢）
        for dirpath, dirnames, filenames in os.walk(str(root)):
            # 限制搜索深度
            depth = dirpath.count(os.sep) - str(root).count(os.sep)
            if depth > 5:
                dirnames.clear()  # 不再递归子目录
                continue

            if target_image in filenames:
                full_path = Path(dirpath) / target_image
                found_paths.append(full_path)
                print(f"  ✓ 找到: {full_path}")

    except Exception as e:
        print(f"  × 搜索失败: {e}")

print("\n" + "=" * 60)
if found_paths:
    print(f"共找到 {len(found_paths)} 个匹配文件:")
    for p in found_paths:
        print(f"  - {p}")
        print(f"    父目录: {p.parent}")
        print(f"    大小: {p.stat().st_size} bytes")
else:
    print("未找到图片文件")
    print("\n可能的原因:")
    print("1. MinerU 没有保存图片文件，只保存了 Markdown 引用")
    print("2. 图片在 MinerU 服务端，需要通过 API 下载")
    print("3. 图片已被清理")
