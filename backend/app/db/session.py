"""
Database session management and connection
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Generator
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# 创建数据库引擎
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,  # 禁用 SQL 语句日志输出
    pool_pre_ping=True,  # 自动重连
    pool_size=10,  # 连接池大小
    max_overflow=20,  # 最大溢出连接数
    pool_recycle=3600,  # 连接回收时间（1小时）
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话（依赖注入）

    Usage:
        from fastapi import Depends

        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    初始化数据库
    - 创建所有表
    - 插入初始数据
    """
    from app.db.models import Base, User, TermDictionary
    from passlib.context import CryptContext

    logger.info("Initializing database...")

    # 创建所有表
    Base.metadata.create_all(bind=engine)
    logger.info("All tables created successfully")

    # 插入初始数据
    db = SessionLocal()
    try:
        # 检查是否已有管理员用户
        admin_exists = db.query(User).filter(User.username == "admin").first()
        if not admin_exists:
            # 使用 bcrypt 直接加密（避免 passlib 兼容性问题）
            import bcrypt
            password = "admin123".encode('utf-8')
            hashed = bcrypt.hashpw(password, bcrypt.gensalt())

            admin = User(
                username="admin",
                email="admin@electric-rag.com",
                password_hash=hashed.decode('utf-8'),
                full_name="系统管理员",
                role="admin"
            )
            db.add(admin)
            logger.info("Created default admin user")

        # 检查是否已有术语
        term_count = db.query(TermDictionary).count()
        if term_count == 0:
            terms = [
                TermDictionary(
                    standard_term="电压互感器",
                    aliases='["PT", "电压互感器"]',
                    category="设备",
                    source="manual"
                ),
                TermDictionary(
                    standard_term="电流互感器",
                    aliases='["CT", "电流互感器"]',
                    category="设备",
                    source="manual"
                ),
                TermDictionary(
                    standard_term="隔离开关",
                    aliases='["刀闸", "隔离开关"]',
                    category="设备",
                    source="manual"
                ),
                TermDictionary(
                    standard_term="断路器",
                    aliases='["开关", "断路器"]',
                    category="设备",
                    source="manual"
                ),
                TermDictionary(
                    standard_term="10kV",
                    aliases='["10千伏", "10kV", "10KV"]',
                    category="电压等级",
                    source="manual"
                ),
                TermDictionary(
                    standard_term="35kV",
                    aliases='["35千伏", "35kV", "35KV"]',
                    category="电压等级",
                    source="manual"
                ),
                TermDictionary(
                    standard_term="110kV",
                    aliases='["110千伏", "110kV", "110KV"]',
                    category="电压等级",
                    source="manual"
                ),
                TermDictionary(
                    standard_term="220kV",
                    aliases='["220千伏", "220kV", "220KV"]',
                    category="电压等级",
                    source="manual"
                ),
            ]
            db.add_all(terms)
            logger.info(f"Created {len(terms)} default terms")

        db.commit()
        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def check_db_connection() -> bool:
    """检查数据库连接是否正常"""
    try:
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
