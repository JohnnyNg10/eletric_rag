"""
Application configuration
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""

    # Application
    APP_NAME: str = "Electric RAG System"
    DEBUG: bool = False
    ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "your_password"
    MYSQL_DB: str = "electric_rag"

    @property
    def DATABASE_URL(self) -> str:
        """构建数据库连接URL"""
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    @property
    def REDIS_URL(self) -> str:
        """构建Redis连接URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "documents"

    # Elasticsearch
    ES_HOSTS: str = "http://localhost:9200"
    ES_INDEX: str = "documents"
    # Elasticsearch
    ELASTICSEARCH_HOST: str = "localhost"
    ELASTICSEARCH_PORT: int = 9200
    ES_USER: Optional[str] = None
    ES_PASSWORD: Optional[str] = None

    # MinIO
    MINIO_HOST: str = "localhost"
    MINIO_PORT: int = 9000
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "electric-rag"
    MINIO_SECURE: bool = False

    # LLM API (Volcengine Ark)
    ARK_API_KEY: str = "your_api_key"
    LLM_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    LLM_MODEL: str = "ep-20260709155619-6cv8s"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.7

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Business Config
    MAX_RECALL_COUNT: int = 20
    TOP_K_RESULTS: int = 5
    CACHE_TTL: int = 3600  # 保留兼容，实际各级由下方配置控制
    QUERY_EXPAND_MAX: int = 3
    SLOW_LANE_MAX_STEPS: int = 3
    SLOW_LANE_TIMEOUT: int = 8000

    # Cache Control（四级缓存开关与TTL）
    CACHE_EMBEDDING_ENABLED: bool = True   # L1: Embedding 向量缓存
    CACHE_RECALL_ENABLED: bool = True      # L2: 三路召回结果缓存
    CACHE_RERANK_ENABLED: bool = True      # L3: 重排结果缓存
    CACHE_GENERATION_ENABLED: bool = True  # L4: LLM 生成结果缓存
    CACHE_EMBEDDING_TTL: int = 86400       # L1 TTL，默认 24h
    CACHE_RECALL_TTL: int = 21600          # L2 TTL，默认 6h
    CACHE_RERANK_TTL: int = 14400          # L3 TTL，默认 4h
    CACHE_GENERATION_TTL: int = 7200       # L4 TTL，默认 2h

    # Semantic Cache（语义缓存，基于向量相似度）
    SEMANTIC_CACHE_ENABLED: bool = True    # 是否启用语义缓存
    SEMANTIC_CACHE_SIMILARITY_THRESHOLD: float = 0.95  # 相似度阈值（0.9-0.99）
    SEMANTIC_CACHE_TTL_HOURS: int = 6      # 语义缓存 TTL（小时）

    # Multi-turn Conversation（多轮对话）
    MAX_HISTORY_TURNS: int = 5               # 历史注入轮数上限
    MAX_HISTORY_TOKENS: int = 2000           # 历史 token 预算（按字符数 /1.5 粗估）
    COREFERENCE_RESOLUTION_ENABLED: bool = True  # 是否启用指代消解

    # Child Chunk Expansion（父子块检索扩展）
    CHILD_EXPANSION_ENABLED: bool = True        # 是否启用子块扩展
    CHILD_SIMILARITY_THRESHOLD: float = 0.7     # 子块相似度阈值
    MAX_CHILDREN_PER_PARENT: int = 5            # 每个父块最多保留的子块数

    # Security
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Logging
    LOG_LEVEL: str = "INFO"

    # Model Configuration
    MODELS_DIR: str = "models"  # 模型存储目录
    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    RERANKER_MODEL_LARGE: str = "BAAI/bge-reranker-large"
    RERANKER_MODEL_BASE: str = "BAAI/bge-reranker-base"
    SPARSE_MODEL: str = "naver/efficient-splade-VI-BT-large-query"  # 稀疏向量模型
    AUTO_DOWNLOAD_MODELS: bool = True  # 启动时自动下载缺失的模型

    # Scanned PDF Processing (扫描件PDF处理)
    ENABLE_SCANNED_PDF: bool = False  # 是否启用扫描件处理
    ENABLE_IMAGE_SEARCH: bool = False  # 是否启用图片检索
    ENABLE_VLM_DESCRIPTION: bool = False  # 是否启用VLM描述生成

    # VLM API Configuration
    VLM_PROVIDER: str = "doubao"  # doubao / qwen / local
    DOUBAO_API_KEY: str = ""
    DOUBAO_API_ENDPOINT: str = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    DOUBAO_MODEL: str = "doubao-vision-pro"
    QWEN_API_KEY: str = ""
    QWEN_MODEL: str = "qwen-vl-plus"

    # OCR Configuration
    OCR_USE_GPU: bool = True
    OCR_CONFIDENCE_THRESHOLD: float = 0.85  # OCR置信度阈值

    class Config:
        env_file = ".env"
        case_sensitive = True


# 创建全局配置实例
settings = Settings()
