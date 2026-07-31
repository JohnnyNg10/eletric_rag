"""
嵌入向量模块
"""
from app.core.embedding.embedder import embedder, Embedder, get_embedder
from app.core.embedding.colpali_embedder import ColPaliEmbedder, get_colpali_embedder

__all__ = [
    "embedder",
    "Embedder",
    "get_embedder",
    "ColPaliEmbedder",
    "get_colpali_embedder",
]
