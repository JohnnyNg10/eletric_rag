"""
向量化嵌入器

支持：
- 稠密向量：bge-large-zh-v1.5 (1024D)
- 稀疏向量：SPLADE
"""
from typing import List, Dict, Union
import numpy as np
import logging

logger = logging.getLogger(__name__)


class Embedder:
    """向量化嵌入器"""

    def __init__(self):
        self.dense_model = None
        self.sparse_model = None
        self._load_models()

    def _get_model_path(self, model_name: str) -> str:
        """
        获取本地模型路径

        路径规则：MODELS_DIR / model_name.replace("/", "--")
        例如：models/BAAI--bge-large-zh-v1.5
        """
        from app.config import settings
        from pathlib import Path

        local_path = Path(settings.MODELS_DIR) / model_name.replace("/", "--")
        if local_path.exists():
            return str(local_path)
        # 回退到 HuggingFace 模型名（在线下载）
        logger.warning(f"Local model not found at {local_path}, using HF name: {model_name}")
        return model_name

    def _load_models(self):
        """延迟加载模型"""
        from app.config import settings

        try:
            from sentence_transformers import SentenceTransformer

            # 加载稠密向量模型（bge-large-zh-v1.5）
            dense_path = self._get_model_path(settings.EMBEDDING_MODEL)
            logger.info(f"Loading dense embedding model from: {dense_path}")
            self.dense_model = SentenceTransformer(dense_path, device='cpu')
            logger.info(f"Dense model loaded: {settings.EMBEDDING_MODEL}")

        except Exception as e:
            logger.error(f"Failed to load dense model: {e}")
            raise

        try:
            # 加载稀疏向量模型（SPLADE）
            from transformers import AutoModelForMaskedLM, AutoTokenizer

            sparse_path = self._get_model_path(settings.SPARSE_MODEL)
            logger.info(f"Loading sparse embedding model from: {sparse_path}")
            self.sparse_tokenizer = AutoTokenizer.from_pretrained(sparse_path)
            self.sparse_model = AutoModelForMaskedLM.from_pretrained(sparse_path)
            self.sparse_model.eval()
            logger.info(f"Sparse model loaded: {settings.SPARSE_MODEL}")

        except Exception as e:
            logger.warning(f"Failed to load sparse model: {e}")
            self.sparse_model = None

    def encode(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        生成稠密向量

        Args:
            text: 单个文本或文本列表

        Returns:
            向量数组 (D,) 或 (N, D)
        """
        if self.dense_model is None:
            raise RuntimeError("Dense model not loaded")

        embeddings = self.dense_model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        return embeddings

    def encode_sparse(self, text: str) -> Dict[str, List]:
        """
        生成稀疏向量（SPLADE）

        Args:
            text: 文本

        Returns:
            稀疏向量 {"indices": [...], "values": [...]}（Qdrant 格式）
        """
        if self.sparse_model is None:
            logger.warning("Sparse model not loaded, returning empty sparse vector")
            return {"indices": [], "values": []}

        try:
            import torch

            # Tokenize
            inputs = self.sparse_tokenizer(
                text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512
            )

            # Forward pass
            with torch.no_grad():
                outputs = self.sparse_model(**inputs)
                logits = outputs.logits

            # SPLADE: max pooling over tokens
            sparse_vec = torch.max(
                torch.log1p(torch.relu(logits)),
                dim=1
            )[0].squeeze()

            # 转换为 Qdrant 稀疏向量格式（indices + values）
            indices = []
            values = []
            for idx, weight in enumerate(sparse_vec.tolist()):
                if weight > 0:
                    indices.append(idx)
                    values.append(float(weight))

            return {"indices": indices, "values": values}

        except Exception as e:
            logger.error(f"Sparse encoding failed: {e}")
            return {"indices": [], "values": []}

    def encode_batch(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        批量生成稠密向量

        Args:
            texts: 文本列表
            batch_size: 批处理大小

        Returns:
            向量数组 (N, D)
        """
        if self.dense_model is None:
            raise RuntimeError("Dense model not loaded")

        embeddings = self.dense_model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=True
        )

        return embeddings


# 全局实例（单例模式）
_embedder_instance = None


def get_embedder() -> Embedder:
    """获取 embedder 单例"""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = Embedder()
    return _embedder_instance


# 导出实例
embedder = get_embedder()
