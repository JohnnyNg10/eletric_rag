"""
预处理层 (Preprocessing Layer)

职责：
- 术语标准化
- 查询笼统度评估（提问优化）

对外接口：
- Preprocessor: 预处理协调器（主入口）
- PreprocessingInput: 输入数据模型
- PreprocessingOutput: 输出数据模型

注意：
- QueryRewriter 和 MetadataExtractor 保留在此目录（代码位置）
- 但它们逻辑上属于快车道，由 retrieval/fast_lane.py 调用
- 不再从 preprocessing 模块导出
"""
from .preprocessor import (
    Preprocessor,
    PreprocessingInput,
    PreprocessingOutput
)
from .term_normalizer import TermNormalizer
from .query_optimizer import QueryOptimizer, OptimizationResult

__all__ = [
    'Preprocessor',
    'PreprocessingInput',
    'PreprocessingOutput',
    'TermNormalizer',
    'QueryOptimizer',
    'OptimizationResult',
]
