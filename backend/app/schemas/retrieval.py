"""
检索相关的数据模型
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ChunkResult(BaseModel):
    """召回的文档块结果"""
    chunk_id: int = Field(..., description="块ID")
    document_id: int = Field(..., description="文档ID")
    content: str = Field(..., description="文本内容")
    score: float = Field(..., description="相关性分数")

    # 文档信息
    document_title: Optional[str] = Field(None, description="文档标题")
    standard_no: Optional[str] = Field(None, description="标准号")
    doc_type: Optional[str] = Field(None, description="文档类型")
    category: Optional[str] = Field(None, description="专业分类")
    voltage_level: Optional[str] = Field(None, description="电压等级")

    # 位置信息
    clause: Optional[str] = Field(None, description="条款号")
    chapter: Optional[str] = Field(None, description="章节号")
    section: Optional[str] = Field(None, description="节号")
    page_start: Optional[int] = Field(None, description="起始页码")
    page_end: Optional[int] = Field(None, description="结束页码")

    # 召回来源
    recall_source: Optional[str] = Field(None, description="召回来源：vector/keyword/structured")
    recall_sources: List[str] = Field(default_factory=list, description="多个召回来源")

    class Config:
        from_attributes = True


class RecallRequest(BaseModel):
    """召回请求"""
    query: str = Field(..., description="查询文本")
    filters: Dict[str, Any] = Field(default_factory=dict, description="过滤条件")
    top_k: int = Field(50, description="召回数量", ge=1, le=100)
    expanded_queries: Optional[List[str]] = Field(None, description="扩展查询列表")


class RecallResponse(BaseModel):
    """召回响应"""
    chunks: List[ChunkResult] = Field(..., description="召回的文档块")
    total: int = Field(..., description="总数")
    latency_ms: int = Field(..., description="召回耗时（毫秒）")
    sources_stats: Dict[str, int] = Field(default_factory=dict, description="各召回源统计")
