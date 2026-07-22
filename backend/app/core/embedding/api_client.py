"""
Embedding API 客户端

支持通过远程 API 获取向量嵌入（作为本地模型的替代方案）
"""
import httpx
import logging
from typing import List, Union, Dict
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingAPIClient:
    """Embedding API 客户端"""

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        model: str = None,
        timeout: int = 30,
    ):
        """
        初始化 API 客户端

        Args:
            base_url: API 基础URL
            api_key: API 密钥
            model: 模型名称
            timeout: 请求超时（秒）
        """
        self.base_url = base_url or settings.EMBEDDING_API_BASE_URL
        self.api_key = api_key or settings.EMBEDDING_API_KEY
        self.model = model or settings.EMBEDDING_API_MODEL
        self.timeout = timeout

        if not self.api_key:
            logger.warning("[EmbeddingAPIClient] API key not configured")

    async def encode(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        生成稠密向量

        Args:
            text: 单个文本或文本列表

        Returns:
            向量数组 (D,) 或 (N, D)
        """
        is_single = isinstance(text, str)
        texts = [text] if is_single else text

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "input": texts,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # 解析 OpenAI 格式响应
                embeddings = [item["embedding"] for item in data["data"]]
                result = np.array(embeddings, dtype=np.float32)

                # L2 归一化
                norms = np.linalg.norm(result, axis=1, keepdims=True)
                result = result / (norms + 1e-9)

                return result[0] if is_single else result

        except httpx.HTTPStatusError as e:
            logger.error(f"[EmbeddingAPIClient] HTTP error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"Embedding API request failed: {e}")
        except Exception as e:
            logger.error(f"[EmbeddingAPIClient] Error: {e}")
            raise RuntimeError(f"Embedding API error: {e}")

    async def encode_batch(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        批量生成稠密向量

        Args:
            texts: 文本列表
            batch_size: 批处理大小（部分 API 有限制）

        Returns:
            向量数组 (N, D)
        """
        if len(texts) <= batch_size:
            return await self.encode(texts)

        # 分批请求
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = await self.encode(batch)
            all_embeddings.append(embeddings)

        return np.vstack(all_embeddings)

    def encode_sparse(self, text: str) -> Dict[str, List]:
        """
        生成稀疏向量（API 模式暂不支持）

        Args:
            text: 文本

        Returns:
            空稀疏向量（占位）
        """
        logger.warning("[EmbeddingAPIClient] Sparse encoding not supported in API mode")
        return {"indices": [], "values": []}
