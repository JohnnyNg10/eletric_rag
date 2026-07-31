"""
ColPali Embedder - 视觉文档检索的多向量嵌入器

基于 vidore/colqwen2-base 模型，使用 colpali-engine 库
支持：
- 文本查询编码（multi-vector, 动态长度 × 128 维）
- 图片编码（multi-vector, 动态分辨率）
- Late Interaction MaxSim 打分
"""
import logging
from pathlib import Path
from typing import Optional, Union
import numpy as np

logger = logging.getLogger(__name__)


class ColPaliEmbedder:
    """ColPali 视觉文档嵌入器（基于 colpali-engine）"""

    def __init__(self, model_path: Optional[Union[str, Path]] = None, device: str = "cpu"):
        """
        初始化 ColPali embedder

        Args:
            model_path: 模型路径（本地路径）
            device: 设备（cuda / cpu）
        """
        from app.config import settings

        self.model_path = model_path or settings.COLPALI_MODEL_CACHE_DIR
        self.device = device
        self.model = None
        self.processor = None

        logger.info(f"[ColPaliEmbedder] Initializing with model: {self.model_path}")
        logger.info(f"[ColPaliEmbedder] Device: {self.device}")

        try:
            self._load_model()
            logger.info("[ColPaliEmbedder] Model loaded successfully")
        except Exception as e:
            logger.error(f"[ColPaliEmbedder] Failed to load model: {e}")
            raise

    def _load_model(self):
        """加载 ColPali 模型和处理器（使用 colpali-engine）"""
        try:
            from colpali_engine.models import ColQwen2, ColQwen2Processor
            import torch
            import os

            # 检查模型路径
            model_path = Path(self.model_path)
            if not model_path.exists():
                raise FileNotFoundError(f"Model path does not exist: {model_path}")

            logger.info(f"[ColPaliEmbedder] Loading from: {model_path}")

            # 根据设备选择数据类型
            if self.device == "cuda":
                torch_dtype = torch.float16
            else:
                torch_dtype = torch.float32  # CPU 只支持 float32

            # 加载处理器
            logger.info(f"[ColPaliEmbedder] Loading processor...")
            self.processor = ColQwen2Processor.from_pretrained(
                str(model_path),
                trust_remote_code=True
            )

            # 加载模型
            logger.info(f"[ColPaliEmbedder] Loading model (dtype={torch_dtype})...")
            self.model = ColQwen2.from_pretrained(
                str(model_path),
                torch_dtype=torch_dtype,
                device_map=self.device,
                trust_remote_code=True
            ).eval()

            logger.info(f"[ColPaliEmbedder] Model loaded on device: {self.device}")

        except ImportError as e:
            logger.error(f"[ColPaliEmbedder] Missing dependencies: {e}")
            logger.error("Please install: pip install colpali-engine")
            raise
        except Exception as e:
            logger.error(f"[ColPaliEmbedder] Failed to load model: {e}")
            raise

    def encode_query(self, query: str) -> np.ndarray:
        """
        生成查询的 multi-vector 表示

        Args:
            query: 查询文本

        Returns:
            np.ndarray: multi-vector (Seq_Len, 128), L2-normalized
        """
        if self.model is None or self.processor is None:
            raise RuntimeError("[ColPaliEmbedder] Model not loaded")

        try:
            import torch

            # 使用 process_queries 处理查询
            batch = self.processor.process_queries([query])
            batch = {k: v.to(self.device) for k, v in batch.items()}

            # 前向传播
            with torch.inference_mode():
                embeddings = self.model(**batch)

            # 转换为 numpy 并移除 batch 维度
            result = embeddings.cpu().numpy().squeeze(0)  # (Seq_Len, 128)

            logger.debug(
                f"[ColPaliEmbedder] Query encoded: '{query[:50]}...' "
                f"-> shape {result.shape}"
            )

            return result

        except Exception as e:
            logger.error(f"[ColPaliEmbedder] Query encoding failed: {e}")
            raise

    def encode_image(self, image) -> np.ndarray:
        """
        生成图片的 multi-vector 表示

        Args:
            image: PIL.Image 对象

        Returns:
            np.ndarray: multi-vector (Seq_Len, 128), L2-normalized
        """
        if self.model is None or self.processor is None:
            raise RuntimeError("[ColPaliEmbedder] Model not loaded")

        try:
            import torch
            from PIL import Image

            # 确保是 PIL.Image 对象
            if not isinstance(image, Image.Image):
                raise ValueError(
                    f"[ColPaliEmbedder] Expected PIL.Image, got {type(image)}"
                )

            # 使用 process_images 处理图片
            batch = self.processor.process_images([image])
            batch = {k: v.to(self.device) for k, v in batch.items()}

            # 前向传播
            with torch.inference_mode():
                embeddings = self.model(**batch)

            # 转换为 numpy 并移除 batch 维度
            result = embeddings.cpu().numpy().squeeze(0)  # (Seq_Len, 128)

            logger.debug(
                f"[ColPaliEmbedder] Image encoded: size={image.size} "
                f"-> shape {result.shape}"
            )

            return result

        except Exception as e:
            logger.error(f"[ColPaliEmbedder] Image encoding failed: {e}")
            raise

    def compute_score(
        self,
        query_vectors: np.ndarray,  # (N, 128)
        doc_vectors: np.ndarray     # (M, 128)
    ) -> float:
        """
        Late Interaction MaxSim 打分（使用官方 processor 方法）

        MaxSim = Σ_i max_j (q_i · d_j)
        其中 q_i 是查询的第 i 个 token，d_j 是文档的第 j 个 token

        Args:
            query_vectors: 查询向量 (N, 128)
            doc_vectors: 文档向量 (M, 128)

        Returns:
            float: MaxSim 分数
        """
        try:
            import torch

            # 转换为 torch tensor 列表（processor.score_multi_vector 需要列表格式）
            query_embeddings = [torch.from_numpy(query_vectors)]
            doc_embeddings = [torch.from_numpy(doc_vectors)]

            # 使用官方 processor 的打分方法
            scores = self.processor.score_multi_vector(query_embeddings, doc_embeddings)

            # 返回标量分数
            return float(scores[0, 0].item())

        except Exception as e:
            logger.error(f"[ColPaliEmbedder] Score computation failed: {e}")
            raise

    def encode_batch_queries(self, queries: list[str], batch_size: int = 8) -> list[np.ndarray]:
        """
        批量编码查询（优化性能）

        Args:
            queries: 查询列表
            batch_size: 批处理大小

        Returns:
            list[np.ndarray]: multi-vector 列表
        """
        results = []

        for i in range(0, len(queries), batch_size):
            batch = queries[i:i + batch_size]
            for query in batch:
                results.append(self.encode_query(query))

        logger.info(f"[ColPaliEmbedder] Batch encoded {len(queries)} queries")
        return results

    def encode_batch_images(self, images: list, batch_size: int = 4) -> list[np.ndarray]:
        """
        批量编码图片（优化性能）

        Args:
            images: PIL.Image 列表
            batch_size: 批处理大小

        Returns:
            list[np.ndarray]: multi-vector 列表
        """
        results = []

        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            for image in batch:
                results.append(self.encode_image(image))

        logger.info(f"[ColPaliEmbedder] Batch encoded {len(images)} images")
        return results


# 全局实例（单例模式）
_colpali_embedder_instance: Optional[ColPaliEmbedder] = None


def get_colpali_embedder() -> ColPaliEmbedder:
    """获取 ColPali embedder 单例"""
    global _colpali_embedder_instance

    if _colpali_embedder_instance is None:
        from app.config import settings

        _colpali_embedder_instance = ColPaliEmbedder(
            model_path=settings.COLPALI_MODEL_CACHE_DIR,
            device=settings.COLPALI_DEVICE
        )

    return _colpali_embedder_instance


def reset_colpali_embedder():
    """重置单例（用于测试）"""
    global _colpali_embedder_instance
    _colpali_embedder_instance = None
