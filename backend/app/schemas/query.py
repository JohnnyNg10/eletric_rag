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

    # [阶段B] 路由覆盖字段
    user_lane: Optional[str] = Field(default=None, description="用户选择的车道（覆盖系统建议）")

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("查询内容不能为空")
        return v

    @field_validator('refined_query')
    @classmethod
    def validate_refined_query(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v

    @field_validator('user_lane')
    @classmethod
    def validate_user_lane(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ('fast', 'slow'):
            raise ValueError("user_lane 必须是 'fast' 或 'slow'")
        return v


class Citation(BaseModel):
    """引用来源"""
    index: int = Field(..., description="引用编号")
    chunk_id: int = Field(default=0, description="块ID")
    standard_no: Optional[str] = Field(default=None, description="标准号")
    clause: Optional[str] = Field(default=None, description="条款号")
    content_snippet: str = Field(default="", description="引用内容片段")
    document_title: Optional[str] = Field(default=None, description="文档标题")


class OptimizationOption(BaseModel):
    """优化选项"""
    id: int = Field(..., description="选项ID")
    label: str = Field(..., description="选项标签")
    refined_query: str = Field(..., description="优化后的查询")
    standard_preview: Optional[str] = Field(default=None, description="相关标准预览")
    doc_count: int = Field(default=0, description="相关文档数量")
    kb_verified: bool = Field(default=False, description="True 表示 standard_preview/doc_count 来自 ES 真实聚合")


class QueryResponse(BaseModel):
    """执行查询响应（统一结构，status 字段区分状态）"""
    status: str = Field(default="success", description="状态：success / need_clarification")

    # 成功时填充
    answer: Optional[str] = Field(default=None, description="生成的答案")
    citations: List[Citation] = Field(default_factory=list, description="引用来源列表")
    lane: Optional[str] = Field(default=None, description="路由车道：fast/slow")
    retrieval_time: Optional[int] = Field(default=None, description="检索耗时（ms）")
    generation_time: Optional[int] = Field(default=None, description="生成耗时（ms）")
    expanded_queries: List[str] = Field(default_factory=list, description="扩展的查询")
    query_log_id: Optional[int] = Field(default=None, description="查询日志ID")

    # need_clarification 时填充
    vagueness_score: Optional[float] = Field(default=None, description="笼统度评分（0-1）")
    clarification_options: Optional[List[OptimizationOption]] = Field(default=None, description="澄清选项列表")

    # [阶段B] 路由建议字段（后确认模式：系统建议，用户可替换）
    lane_suggestion: Optional[str] = Field(default=None, description="系统建议的车道（fast/slow）")
    lane_confidence: Optional[float] = Field(default=None, description="路由置信度（0-1）")
    lane_reason: Optional[str] = Field(default=None, description="路由理由（给用户看）")


class OptimizeQueryRequest(BaseModel):
    """提问优化请求"""
    query: str = Field(..., min_length=1, max_length=500, description="查询内容")


class OptimizeQueryResponse(BaseModel):
    """提问优化响应"""
    strategy: str = Field(..., description="策略：none/suggest/clarify_optional/clarify_required")
    vagueness_score: float = Field(..., ge=0, le=1, description="笼统度评分（0-1）")
    options: List[OptimizationOption] = Field(default_factory=list, description="澄清/补全选项")

    # [阶段B] 路由建议字段（与 QueryResponse 保持一致）
    lane_suggestion: str = Field(default="fast", description="系统建议的车道（fast/slow）")
    lane_confidence: float = Field(default=0.7, ge=0, le=1, description="路由置信度（0-1）")
    lane_reason: str = Field(default="", description="路由理由（给用户看）")
    missing_dimension_keys: List[str] = Field(default_factory=list, description="缺失维度的枚举键列表")


class FeedbackRequest(BaseModel):
    """用户反馈请求"""
    feedback_score: int = Field(..., ge=1, le=5, description="评分 1-5")
    feedback_text: Optional[str] = Field(default=None, max_length=1000, description="反馈文本")


class FeedbackResponse(BaseModel):
    """用户反馈响应"""
    query_log_id: int
    feedback_score: int
    message: str = "反馈已记录"


class QueryHistoryItem(BaseModel):
    """查询历史条目"""
    query_log_id: int
    query: str
    answer: Optional[str] = None
    lane: str
    total_time: Optional[int] = None
    feedback_score: Optional[int] = None
    created_at: str


class QueryHistoryResponse(BaseModel):
    """查询历史响应"""
    items: List[QueryHistoryItem]
    total: int
    page: int
    page_size: int
    has_more: bool
