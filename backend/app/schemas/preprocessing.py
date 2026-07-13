"""
预处理层响应模型

[阶段B] 新增：POST /api/v1/query/preprocess 专用响应模型
"""
from typing import List, Optional
from pydantic import BaseModel, Field

from app.schemas.query import OptimizationOption


class PreprocessResponse(BaseModel):
    """
    预处理响应（阶段B：返回预处理结果但不执行检索）

    包含：
    - 标准化后的查询
    - 笼统度评分
    - 澄清选项
    - 路由建议（lane_suggestion/lane_confidence/lane_reason）
    """
    normalized_query: str = Field(..., description="标准化后的查询")
    vagueness_score: float = Field(..., ge=0, le=1, description="笼统度评分（0-1）")
    strategy: str = Field(..., description="策略：none/suggest/clarify_optional/clarify_required")

    # 澄清选项
    options: List[OptimizationOption] = Field(default_factory=list, description="澄清选项")
    missing_dimension_keys: List[str] = Field(default_factory=list, description="缺失维度的枚举键列表")

    # 路由建议（阶段B核心：LLM一体化输出）
    lane_suggestion: str = Field(default="fast", description="系统建议的车道（fast/slow）")
    lane_confidence: float = Field(default=0.7, ge=0, le=1, description="路由置信度（0-1）")
    lane_reason: str = Field(default="", description="路由理由（给用户看）")

    # 元信息
    preprocessing_time: int = Field(default=0, description="预处理耗时（ms）")
