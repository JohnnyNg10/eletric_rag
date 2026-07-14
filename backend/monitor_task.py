"""
监控后台任务输出
"""
import sys
import time
from pathlib import Path

if len(sys.argv) < 2:
    print("用法: python monitor_task.py <output_file>")
    sys.exit(1)

output_file = Path(sys.argv[1])
last_size = 0

print(f"监控文件: {output_file}")
print("=" * 60)

try:
    while True:
        if output_file.exists():
            current_size = output_file.stat().st_size

            if current_size > last_size:
                with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_size)
                    new_content = f.read()
                    print(new_content, end='', flush=True)
                    last_size = current_size

        time.sleep(2)

except KeyboardInterrupt:
    print("\n\n监控已停止")
