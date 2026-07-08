"""
查询相关的 Pydantic 模型
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    """执行查询请求"""
    query: str = Field(..., min_length=1, max_length=500, description="查询内容")
    stream: bool = Field(default=False, description="是否流式输出")
    conversation_id: Optional[str] = Field(default=None, description="会话ID（多轮对话）")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="手动指定过滤条件")

    # 澄清功能字段
    refined_query: Optional[str] = Field(default=None, description="用户选择澄清选项后的精炼查询")
    selected_option_id: Optional[int] = Field(default=None, description="用户选择的澄清选项ID")
    clarification_context: Optional[Dict[str, Any]] = Field(default=None, description="澄清上下文（包含原始query、vagueness_score等）")

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        """验证查询内容"""
        v = v.strip()
        if not v:
            raise ValueError("查询内容不能为空")
        return v

    @field_validator('refined_query')
    @classmethod
    def validate_refined_query(cls, v: Optional[str]) -> Optional[str]:
        """验证精炼查询内容"""
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v


class Citation(BaseModel):
    """引用来源"""
    index: int = Field(..., description="引用编号")
    standard_no: str = Field(..., description="标准号")
    clause_no: Optional[str] = Field(default=None, description="条款号")
    title: str = Field(..., description="标题")
    content: str = Field(..., description="引用内容片段")
    page: Optional[int] = Field(default=None, description="页码")


class QueryResponse(BaseModel):
    """执行查询响应"""
    answer: str = Field(..., description="生成的答案")
    citations: List[Citation] = Field(default_factory=list, description="引用来源列表")
    lane: str = Field(..., description="路由车道：fast/slow")
    retrieval_time: int = Field(..., description="检索耗时（ms）")
    generation_time: int = Field(..., description="生成耗时（ms）")
    expanded_queries: List[str] = Field(default_factory=list, description="扩展的查询")
    query_log_id: int = Field(..., description="查询日志ID")


class OptimizeQueryRequest(BaseModel):
    """提问优化请求"""
    query: str = Field(..., min_length=1, max_length=500, description="查询内容")


class OptimizationOption(BaseModel):
    """优化选项"""
    id: int = Field(..., description="选项ID")
    label: str = Field(..., description="选项标签")
    refined_query: str = Field(..., description="优化后的查询")
    standard_preview: Optional[str] = Field(default=None, description="相关标准预览")
    doc_count: int = Field(default=0, description="相关文档数量")


class OptimizeQueryResponse(BaseModel):
    """提问优化响应"""
    strategy: str = Field(..., description="策略：none/suggest/clarify_optional/clarify_required")
    vagueness_score: float = Field(..., ge=0, le=1, description="笼统度评分（0-1）")
    options: List[OptimizationOption] = Field(default_factory=list, description="澄清/补全选项")
