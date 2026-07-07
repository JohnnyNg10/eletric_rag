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
    ES_USER: Optional[str] = None
    ES_PASSWORD: Optional[str] = None

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "electric-rag"
    MINIO_SECURE: bool = False

    # LLM API
    LLM_API_KEY: str = "your_api_key"
    LLM_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    LLM_MODEL: str = "doubao-pro-32k"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Business Config
    MAX_RECALL_COUNT: int = 20
    TOP_K_RESULTS: int = 5
    CACHE_TTL: int = 3600
    QUERY_EXPAND_MAX: int = 3
    SLOW_LANE_MAX_STEPS: int = 3
    SLOW_LANE_TIMEOUT: int = 8000

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

    class Config:
        env_file = ".env"
        case_sensitive = True


# 创建全局配置实例
settings = Settings()
