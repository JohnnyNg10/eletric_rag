"""
Pytest 配置文件

提供：
1. 统一的路径配置
2. 数据库 session fixture
3. UTF-8 编码配置
4. 通用测试工具
"""
import sys
import io
from pathlib import Path

import pytest

# 强制 UTF-8 输出，避免 Windows GBK 编码错误
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


@pytest.fixture
def db_session():
    """提供数据库 session fixture"""
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def async_db_session():
    """提供异步数据库 session fixture（如果需要）"""
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
