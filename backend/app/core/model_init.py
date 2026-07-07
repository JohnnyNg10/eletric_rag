"""
Model Initialization - 应用启动时初始化模型
"""
import os
import logging
from pathlib import Path
from typing import Optional

from app.config import settings
from app.core.embedding.model_loader import get_download_manager

logger = logging.getLogger(__name__)


def get_proxy_from_env() -> Optional[str]:
    """
    从环境变量获取代理配置

    检查顺序：
    1. HTTP_PROXY / HTTPS_PROXY
    2. http_proxy / https_proxy
    3. 默认 7897 端口（如果配置了）

    Returns:
        Optional[str]: 代理URL，如 http://127.0.0.1:7897
    """
    proxy = (
        os.environ.get("HTTPS_PROXY") or
        os.environ.get("HTTP_PROXY") or
        os.environ.get("https_proxy") or
        os.environ.get("http_proxy")
    )

    if proxy:
        logger.info(f"Using proxy from environment: {proxy}")

    return proxy


def init_models() -> bool:
    """
    初始化所有AI模型

    功能：
    1. 检查模型是否存在
    2. 如果配置了自动下载且模型缺失，则下载
    3. 返回初始化结果

    Returns:
        bool: 是否所有模型都准备就绪
    """
    logger.info("="*60)
    logger.info("Initializing AI Models...")
    logger.info("="*60)

    # 模型配置
    models = {
        "embedding": settings.EMBEDDING_MODEL,
        "reranker_large": settings.RERANKER_MODEL_LARGE,
        "reranker_base": settings.RERANKER_MODEL_BASE,
        "sparse": settings.SPARSE_MODEL,
    }

    # 获取下载管理器
    download_manager = get_download_manager(settings.MODELS_DIR)

    # 检查哪些模型缺失
    missing_models = {}
    for purpose, model_name in models.items():
        if not download_manager.check_model_exists(model_name):
            missing_models[purpose] = model_name

    # 如果所有模型都存在
    if not missing_models:
        logger.info("✓ All models are already downloaded and ready")
        logger.info("="*60 + "\n")
        return True

    # 如果有缺失模型
    logger.warning(f"Found {len(missing_models)} missing model(s):")
    for purpose, model_name in missing_models.items():
        logger.warning(f"  - [{purpose}] {model_name}")

    # 检查是否自动下载
    if not settings.AUTO_DOWNLOAD_MODELS:
        logger.error("\nAUTO_DOWNLOAD_MODELS is disabled in config")
        logger.error("Please either:")
        logger.error("  1. Set AUTO_DOWNLOAD_MODELS=True in .env")
        logger.error("  2. Manually download models to the models/ directory")
        logger.error("="*60 + "\n")
        return False

    # 自动下载缺失的模型
    logger.info("\nAUTO_DOWNLOAD_MODELS is enabled, starting download...")

    # 获取代理配置
    proxy = get_proxy_from_env()

    if proxy:
        logger.info(f"Proxy detected: {proxy}")
    else:
        logger.info("No proxy detected. If download fails, set HTTP_PROXY environment variable")
        logger.info("Example: export HTTP_PROXY=http://127.0.0.1:7897")

    # 下载模型
    try:
        results = download_manager.download_all_models(missing_models, proxy=proxy)

        # 检查是否全部成功
        if len(results) == len(missing_models):
            logger.info("✓ All missing models downloaded successfully")
            return True
        else:
            logger.error("✗ Some models failed to download")
            return False

    except Exception as e:
        logger.error(f"✗ Model initialization failed: {e}")
        logger.error("\nTroubleshooting tips:")
        logger.error("  1. Check network connection")
        logger.error("  2. Set proxy: export HTTP_PROXY=http://127.0.0.1:7897")
        logger.error("  3. Check HuggingFace service status")
        logger.error("  4. Manually download models if needed")
        return False


def check_models_ready() -> bool:
    """
    检查所有模型是否准备就绪（仅检查，不下载）

    Returns:
        bool: 所有模型是否都存在
    """
    models = {
        "embedding": settings.EMBEDDING_MODEL,
        "reranker_large": settings.RERANKER_MODEL_LARGE,
        "reranker_base": settings.RERANKER_MODEL_BASE,
        "sparse": settings.SPARSE_MODEL,
    }

    download_manager = get_download_manager(settings.MODELS_DIR)

    all_ready = True
    for purpose, model_name in models.items():
        if not download_manager.check_model_exists(model_name):
            logger.warning(f"Model not ready: [{purpose}] {model_name}")
            all_ready = False

    return all_ready
