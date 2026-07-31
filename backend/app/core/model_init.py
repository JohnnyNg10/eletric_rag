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


def _check_colpali_model_exists() -> bool:
    """
    检查 ColPali 模型是否已下载

    Returns:
        bool: 模型是否存在
    """
    from pathlib import Path

    model_path = Path(settings.COLPALI_MODEL_CACHE_DIR)
    # 检查关键文件（transformers 模型至少需要 config.json）
    config_file = model_path / "config.json"
    exists = config_file.exists()

    if exists:
        logger.info(f"✓ ColPali model found at {model_path}")
    else:
        logger.info(f"✗ ColPali model not found at {model_path}")

    return exists


def download_colpali_model() -> bool:
    """
    下载 ColPali 模型（~8GB，需要通过代理）

    Returns:
        bool: 下载是否成功
    """
    from pathlib import Path

    model_name = settings.COLPALI_MODEL_NAME
    cache_dir = Path(settings.COLPALI_MODEL_CACHE_DIR)
    proxy = get_proxy_from_env()

    logger.info(f"Downloading ColPali model: {model_name}")
    logger.info(f"Destination: {cache_dir.absolute()}")
    logger.info("Note: ColPali model is ~8GB, this will take a while...")

    if proxy:
        logger.info(f"Using proxy: {proxy}")
    else:
        logger.warning(
            "No proxy detected. ColPali model is on HuggingFace — "
            "set HTTP_PROXY if download fails"
        )

    try:
        from huggingface_hub import snapshot_download

        cache_dir.mkdir(parents=True, exist_ok=True)

        env_backup = {}
        if proxy:
            import os
            env_backup = {
                "HTTP_PROXY": os.environ.get("HTTP_PROXY"),
                "HTTPS_PROXY": os.environ.get("HTTPS_PROXY"),
            }
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy

        try:
            snapshot_download(
                repo_id=model_name,
                local_dir=str(cache_dir),
                local_dir_use_symlinks=False,
                resume_download=True,
            )
            logger.info(f"✓ ColPali model downloaded successfully to {cache_dir}")
            return True

        finally:
            if proxy:
                import os
                for key, value in env_backup.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    except Exception as e:
        logger.error(f"✗ Failed to download ColPali model: {e}")
        logger.error("Troubleshooting tips:")
        logger.error(f"  1. Manually download {model_name} to {cache_dir}")
        logger.error("  2. Set HTTP_PROXY for HuggingFace access")
        logger.error("  3. Disable ColPali: set ENABLE_VISUAL_RECALL=False")
        return False


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

    # 单独检查 ColPali（路径不同，且可选）
    colpali_missing = settings.ENABLE_VISUAL_RECALL and not _check_colpali_model_exists()

    # 如果所有模型都存在
    if not missing_models and not colpali_missing:
        logger.info("✓ All models are already downloaded and ready")
        logger.info("="*60 + "\n")
        return True

    # 如果有缺失模型
    if missing_models:
        logger.warning(f"Found {len(missing_models)} missing model(s):")
        for purpose, model_name in missing_models.items():
            logger.warning(f"  - [{purpose}] {model_name}")

    if colpali_missing:
        logger.warning(f"  - [colpali] {settings.COLPALI_MODEL_NAME} (~8GB)")

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

    success = True

    # 下载常规模型
    if missing_models:
        try:
            results = download_manager.download_all_models(missing_models, proxy=proxy)

            if len(results) == len(missing_models):
                logger.info("✓ All missing base models downloaded successfully")
            else:
                logger.error("✗ Some base models failed to download")
                success = False

        except Exception as e:
            logger.error(f"✗ Model initialization failed: {e}")
            logger.error("\nTroubleshooting tips:")
            logger.error("  1. Check network connection")
            logger.error("  2. Set proxy: export HTTP_PROXY=http://127.0.0.1:7897")
            logger.error("  3. Check HuggingFace service status")
            logger.error("  4. Manually download models if needed")
            success = False

    # 下载 ColPali 模型（失败仅警告，不阻塞启动）
    if colpali_missing:
        colpali_ok = download_colpali_model()
        if not colpali_ok:
            logger.warning(
                "ColPali model download failed — visual recall will be disabled. "
                "Set ENABLE_VISUAL_RECALL=False to suppress this warning."
            )
            # ColPali 失败不影响整体返回值（降级处理）

    logger.info("="*60 + "\n")
    return success


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

    if settings.ENABLE_VISUAL_RECALL and not _check_colpali_model_exists():
        logger.warning(f"Model not ready: [colpali] {settings.COLPALI_MODEL_NAME}")
        # ColPali 不阻塞就绪状态检查

    return all_ready
