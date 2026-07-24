"""
检索相关的数据模型
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ImageRef(BaseModel):
    """单张图片引用，用于 text/table Chunk 中的图号反查结果"""
    image_id: int = Field(..., description="图片ID")
    image_url: str = Field(..., description="预签名访问URL")
    figure_number: Optional[str] = Field(None, description="图号，如 '图1'")
    caption: Optional[str] = Field(None, description="图注")
    page_number: int = Field(..., description="所在页码")


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

    # 内容类型（关键字段）
    content_type: Optional[str] = Field(None, description="内容类型：text/table/image_description")

    # 召回来源
    recall_source: Optional[str] = Field(None, description="召回来源：vector/keyword/structured/pull_along")
    recall_sources: List[str] = Field(default_factory=list, description="多个召回来源")

    # 图片信息（场景 A：content_type == 'image_description' 时填充）
    image_id: Optional[int] = Field(None, description="图片ID（仅image_description类型）")
    image_url: Optional[str] = Field(None, description="图片访问URL（仅image_description类型）")
    image_page: Optional[int] = Field(None, description="图片所在页码")
    image_figure_number: Optional[str] = Field(None, description="图号")
    image_caption: Optional[str] = Field(None, description="图注")

    # 图片引用（场景 B：text/table Chunk 中的图号引用解析结果）
    referenced_images: List[ImageRef] = Field(default_factory=list, description="正文中引用的图片列表")

    # 关联 Chunk ID 列表（入库时预计算的语义关联）
    related_chunk_ids: List[int] = Field(default_factory=list, description="关联的 Chunk ID 列表")

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


class ExpandedChunkResult(BaseModel):
    """扩展后的检索结果（父块 + 高相关子块）"""
    parent: ChunkResult = Field(..., description="父块")
    relevant_children: List[ChunkResult] = Field(default_factory=list, description="高相关子块，按相似度降序")
    expansion_stats: Optional[Dict[str, Any]] = Field(None, description="扩展统计信息")

    class Config:
        from_attributes = True
