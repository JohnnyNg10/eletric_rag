"""
批量修复测试文件的导入路径
移除硬编码的 sys.path 和编码设置（已在 conftest.py 中统一处理）
"""
import sys
import io
import re
from pathlib import Path

# 强制 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def fix_test_file(filepath: Path):
    """修复单个测试文件的导入"""
    content = filepath.read_text(encoding='utf-8')
    original = content

    # 移除硬编码的 sys.path.append
    content = re.sub(r"sys\.path\.append\(['\"]D:/dl/backend['\"]\)", "", content)
    content = re.sub(r"sys\.path\.insert\(0, str\(Path\(__file__\)\.parent\)\)", "", content)

    # 移除重复的 UTF-8 编码设置（conftest.py 已处理）
    content = re.sub(r"sys\.stdout = io\.TextIOWrapper\(sys\.stdout\.buffer, encoding=['\"]utf-8['\"]\)", "", content)
    content = re.sub(r"sys\.stderr = io\.TextIOWrapper\(sys\.stderr\.buffer, encoding=['\"]utf-8['\"]\)", "", content)
    content = re.sub(r"sys\.stdout\.reconfigure\(encoding=['\"]utf-8['\"]\)", "", content)
    content = re.sub(r"sys\.stderr\.reconfigure\(encoding=['\"]utf-8['\"]\)", "", content)

    # 移除不必要的 import io（如果没有其他用途）
    if 'io.' not in content.replace('import io', ''):
        content = re.sub(r"^import io\n", "", content, flags=re.MULTILINE)

    # 清理多余的空行
    content = re.sub(r"\n{3,}", "\n\n", content)

    if content != original:
        filepath.write_text(content, encoding='utf-8')
        print(f"✓ 修复: {filepath.relative_to(Path(__file__).parent.parent)}")
        return True
    return False


def main():
    tests_dir = Path(__file__).parent
    test_files = list(tests_dir.rglob("test_*.py"))

    print(f"找到 {len(test_files)} 个测试文件\n")

    fixed_count = 0
    for test_file in sorted(test_files):
        if fix_test_file(test_file):
            fixed_count += 1

    print(f"\n共修复 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
