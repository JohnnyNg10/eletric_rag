"""
Model Loader - 模型加载与下载管理
"""
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 动态导入下载库（优先使用 ModelScope，国内访问更快）
try:
    from modelscope import snapshot_download
    DOWNLOAD_SOURCE = "modelscope"
    logger.info("Using ModelScope for model download (国内镜像)")
except ImportError:
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import HfHubHTTPError
    DOWNLOAD_SOURCE = "huggingface"
    logger.info("Using HuggingFace for model download")

# ModelScope 模型ID映射（HuggingFace → ModelScope）
MODELSCOPE_MODEL_MAP = {
    "BAAI/bge-large-zh-v1.5": "AI-ModelScope/bge-large-zh-v1.5",
    "BAAI/bge-reranker-large": "AI-ModelScope/bge-reranker-large",
    "BAAI/bge-reranker-base": "AI-ModelScope/bge-reranker-base",
    "efficient-splade/efficient-splade-VI-BT-large-doc": "AI-ModelScope/efficient-splade-VI-BT-large-doc",
}


class ModelDownloadManager:
    """模型下载管理器"""

    def __init__(self, models_dir: str = "models"):
        """
        初始化模型下载管理器

        Args:
            models_dir: 模型存储根目录
        """
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Model storage directory: {self.models_dir.absolute()}")

    def check_model_exists(self, model_name: str) -> bool:
        """
        检查模型是否已下载

        Args:
            model_name: HuggingFace模型名称（如 BAAI/bge-large-zh-v1.5）

        Returns:
            bool: 模型是否存在
        """
        model_path = self.models_dir / model_name.replace("/", "--")

        # 检查关键文件是否存在
        required_files = ["config.json", "pytorch_model.bin"]

        # 有些模型使用 safetensors 格式
        if not (model_path / "pytorch_model.bin").exists():
            required_files = ["config.json", "model.safetensors"]

        exists = all((model_path / file).exists() for file in required_files)

        if exists:
            logger.info(f"✓ Model found: {model_name} at {model_path}")
        else:
            logger.info(f"✗ Model not found: {model_name}")

        return exists

    def download_model(
        self,
        model_name: str,
        force: bool = False,
        proxy: Optional[str] = None
    ) -> Path:
        """
        下载模型（支持 HuggingFace 和 ModelScope）

        Args:
            model_name: 模型名称（HuggingFace格式，如 BAAI/bge-large-zh-v1.5）
            force: 是否强制重新下载
            proxy: HTTP代理（仅 HuggingFace 有效）

        Returns:
            Path: 模型本地路径
        """
        model_local_name = model_name.replace("/", "--")
        model_path = self.models_dir / model_local_name

        # 检查是否已存在
        if not force and self.check_model_exists(model_name):
            logger.info(f"Model {model_name} already exists, skipping download")
            return model_path

        logger.info(f"Downloading model: {model_name}")
        logger.info(f"Destination: {model_path.absolute()}")

        # 根据下载源选择模型ID
        if DOWNLOAD_SOURCE == "modelscope":
            # 使用 ModelScope 映射
            model_id = MODELSCOPE_MODEL_MAP.get(model_name, model_name)
            logger.info(f"Using ModelScope: {model_id}")

            try:
                downloaded_path = snapshot_download(
                    model_id=model_id,
                    cache_dir=str(model_path),
                )
                logger.info(f"✓ Model downloaded successfully: {model_name}")
                logger.info(f"  Path: {downloaded_path}")
                return Path(downloaded_path)

            except Exception as e:
                logger.error(f"✗ Failed to download model {model_name} from ModelScope: {e}")
                logger.error("Please check:")
                logger.error("  1. Network connection")
                logger.error("  2. Model ID is correct in ModelScope")
                logger.error("  3. Install modelscope: pip install modelscope")
                raise

        else:
            # 使用 HuggingFace
            logger.info(f"Using HuggingFace: {model_name}")

            # 设置代理环境变量（如果提供）
            env_backup = {}
            if proxy:
                logger.info(f"Using proxy: {proxy}")
                env_backup = {
                    "HTTP_PROXY": os.environ.get("HTTP_PROXY"),
                    "HTTPS_PROXY": os.environ.get("HTTPS_PROXY"),
                }
                os.environ["HTTP_PROXY"] = proxy
                os.environ["HTTPS_PROXY"] = proxy

            try:
                downloaded_path = snapshot_download(
                    repo_id=model_name,
                    cache_dir=str(self.models_dir),
                    local_dir=str(model_path),
                    local_dir_use_symlinks=False,
                    resume_download=True,
                )

                logger.info(f"✓ Model downloaded successfully: {model_name}")
                logger.info(f"  Path: {downloaded_path}")
                return Path(downloaded_path)

            except HfHubHTTPError as e:
                logger.error(f"✗ Failed to download model {model_name}: {e}")
                logger.error("Please check:")
                logger.error("  1. Network connection (VPN/proxy)")
                logger.error("  2. Model name is correct")
                logger.error("  3. HuggingFace access token (if model is private)")
                raise

            except Exception as e:
                logger.error(f"✗ Unexpected error downloading {model_name}: {e}")
                raise

            finally:
                # 恢复环境变量
                if proxy:
                    for key, value in env_backup.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value

    def download_all_models(
        self,
        models: Dict[str, str],
        proxy: Optional[str] = None
    ) -> Dict[str, Path]:
        """
        批量下载多个模型

        Args:
            models: 模型字典 {模型用途: HuggingFace模型名称}
            proxy: HTTP代理

        Returns:
            Dict[str, Path]: {模型用途: 本地路径}
        """
        results = {}
        failed = []

        logger.info(f"Checking {len(models)} models...")

        for purpose, model_name in models.items():
            try:
                logger.info(f"\n[{purpose}] {model_name}")
                model_path = self.download_model(model_name, proxy=proxy)
                results[purpose] = model_path
            except Exception as e:
                logger.error(f"Failed to download {purpose} model: {e}")
                failed.append((purpose, model_name))

        # 汇总结果
        logger.info("\n" + "="*60)
        logger.info("Model Download Summary:")
        logger.info(f"  Total: {len(models)}")
        logger.info(f"  Success: {len(results)}")
        logger.info(f"  Failed: {len(failed)}")

        if failed:
            logger.warning("\nFailed models:")
            for purpose, model_name in failed:
                logger.warning(f"  - [{purpose}] {model_name}")
            logger.warning("\nThe application may not work properly without these models.")
        else:
            logger.info("\n✓ All models are ready!")

        logger.info("="*60 + "\n")

        return results


class ModelLoader:
    """模型加载器 - 加载嵌入模型和重排模型到内存"""

    def __init__(self, models_dir: str = "models"):
        self.models_dir = Path(models_dir)
        self._embedding_model = None
        self._reranker_large = None
        self._reranker_base = None
        self._sparse_model = None

    def load_embedding_model(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        """
        加载嵌入模型（延迟加载，实际使用时再实现）

        Args:
            model_name: 模型名称

        Note:
            实际加载需要使用 sentence-transformers 或 transformers
            当前只做路径检查
        """
        model_path = self.models_dir / model_name.replace("/", "--")

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        logger.info(f"Embedding model path verified: {model_path}")
        # TODO: 实际加载模型到GPU
        # from sentence_transformers import SentenceTransformer
        # self._embedding_model = SentenceTransformer(str(model_path))

        return model_path

    def load_reranker_model(self, model_name: str = "BAAI/bge-reranker-large"):
        """
        加载重排模型（延迟加载）

        Args:
            model_name: 模型名称
        """
        model_path = self.models_dir / model_name.replace("/", "--")

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        logger.info(f"Reranker model path verified: {model_path}")
        # TODO: 实际加载模型

        return model_path


# 全局单例
_download_manager: Optional[ModelDownloadManager] = None


def get_download_manager(models_dir: str = "models") -> ModelDownloadManager:
    """获取全局模型下载管理器单例"""
    global _download_manager
    if _download_manager is None:
        _download_manager = ModelDownloadManager(models_dir)
    return _download_manager
