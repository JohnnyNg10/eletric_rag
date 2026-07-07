"""
预处理层 (Preprocessing Layer)

职责：
- 术语标准化
- 查询优化（笼统度评估）
- 查询改写与扩展
- 元数据提取

对外接口：
- Preprocessor: 预处理协调器（主入口）
- PreprocessingInput: 输入数据模型
- PreprocessingOutput: 输出数据模型
"""
from .preprocessor import (
    Preprocessor,
    PreprocessingInput,
    PreprocessingOutput
)
from .term_normalizer import TermNormalizer
from .query_optimizer import QueryOptimizer, OptimizationResult
from .query_rewriter import QueryRewriter
from .metadata_extractor import MetadataExtractor

__all__ = [
    'Preprocessor',
    'PreprocessingInput',
    'PreprocessingOutput',
    'TermNormalizer',
    'QueryOptimizer',
    'OptimizationResult',
    'QueryRewriter',
    'MetadataExtractor',
]
