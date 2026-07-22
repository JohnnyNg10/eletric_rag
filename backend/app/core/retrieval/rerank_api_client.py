"""
Reranker API 客户端

支持通过远程 API 进行重排序（作为本地模型的替代方案）
"""
import httpx
import logging
from typing import List, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


class RerankerAPIClient:
    """Reranker API 客户端"""

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
        self.base_url = base_url or settings.RERANKER_API_BASE_URL
        self.api_key = api_key or settings.RERANKER_API_KEY
        self.model = model or settings.RERANKER_API_MODEL
        self.timeout = timeout

        if not self.api_key:
            logger.warning("[RerankerAPIClient] API key not configured")

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = None,
    ) -> List[Tuple[int, float]]:
        """
        重排序文档

        Args:
            query: 查询文本
            documents: 文档列表
            top_k: 返回前K个结果（None表示全部）

        Returns:
            List[(index, score)]: 原始索引和重排分数
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/rerank",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": documents,
                        "top_n": top_k,
                        "return_documents": False,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # 解析响应 (假设返回格式: {"results": [{"index": int, "relevance_score": float}]})
                results = []
                for item in data.get("results", []):
                    index = item["index"]
                    score = item["relevance_score"]
                    results.append((index, score))

                return results

        except httpx.HTTPStatusError as e:
            logger.error(f"[RerankerAPIClient] HTTP error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"Reranker API request failed: {e}")
        except Exception as e:
            logger.error(f"[RerankerAPIClient] Error: {e}")
            raise RuntimeError(f"Reranker API error: {e}")
