"""
FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import logging.handlers
import os

from app.config import settings
from app.db.session import init_db, check_db_connection

# 确保临时上传目录存在
import os
os.makedirs("/tmp/rag_import", exist_ok=True)

# 配置日志
_log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
_log_level = getattr(logging, settings.LOG_LEVEL)

logging.basicConfig(level=_log_level, format=_log_format)

if settings.LOG_FILE_ENABLED:
    os.makedirs(os.path.dirname(settings.LOG_FILE_PATH), exist_ok=True)
    _file_handler = logging.handlers.RotatingFileHandler(
        settings.LOG_FILE_PATH,
        maxBytes=settings.LOG_FILE_MAX_BYTES,
        backupCount=settings.LOG_FILE_BACKUP_COUNT,
        encoding='utf-8',
    )
    _file_handler.setLevel(_log_level)
    _file_handler.setFormatter(logging.Formatter(_log_format))
    logging.getLogger().addHandler(_file_handler)

logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="工业级电力专业知识库RAG系统",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需要配置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logger.info("Starting application...")

    # 1. 初始化AI模型（检查并下载）
    logger.info("Step 1/3: Initializing AI models...")
    from app.core.model_init import init_models

    try:
        models_ready = init_models()
        if not models_ready:
            logger.warning("Some models are not ready. The application may have limited functionality.")
            logger.warning("You can continue, but some features may not work properly.")
    except Exception as e:
        logger.error(f"Model initialization failed: {e}")
        logger.warning("Continuing startup without models. Please check model configuration.")

    # 2. 检查数据库连接
    logger.info("Step 2/3: Checking database connection...")
    if not check_db_connection():
        logger.error("Database connection failed! Please check your MySQL configuration.")
        logger.error(f"Connection string: {settings.DATABASE_URL.replace(settings.MYSQL_PASSWORD, '***')}")
        raise Exception("Database connection failed")

    logger.info("Database connection successful")

    # 初始化数据库（创建表 + 初始数据）
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # 3. 预加载重排模型（避免首次请求承担模型加载延迟）
    logger.info("Step 3/3: Warming up reranker models...")
    try:
        from app.core.retrieval.rerank import get_reranker
        get_reranker()
        logger.info("Reranker models loaded successfully")
    except Exception as e:
        logger.warning(f"Reranker warmup failed (non-fatal): {e}")

    # 4. 检查 MinerU API 可用性（非致命，服务不可用时回退 PyMuPDF）
    if settings.MINERU_ENABLED:
        try:
            from app.core.document_processor.mineru_client import mineru_client
            if mineru_client.health_check():
                logger.info(f"MinerU API 就绪: {settings.MINERU_API_URL}")
            else:
                logger.warning(
                    f"MinerU API 未就绪 ({settings.MINERU_API_URL})，"
                    "文档解析将回退到 PyMuPDF。"
                    "启动 MinerU 后重启应用或重新上传文档。"
                )
        except Exception as e:
            logger.warning(f"MinerU 检查失败 (non-fatal): {e}")

    logger.info("Application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    logger.info("Shutting down application...")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Electric RAG System API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    db_status = check_db_connection()
    return {
        "status": "healthy" if db_status else "unhealthy",
        "database": "connected" if db_status else "disconnected",
        "version": "1.0.0"
    }


# 导入路由
from app.api.v1.router import api_router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
