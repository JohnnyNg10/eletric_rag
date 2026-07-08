"""
SQLAlchemy ORM Models
所有数据库表的ORM映射
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, BigInteger, String, Text, Enum, Date, Integer,
    Boolean, Float, JSON, TIMESTAMP, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Document(Base):
    """文档表"""
    __tablename__ = "documents"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="文档ID")
    title = Column(String(500), nullable=False, comment="文档标题")
    doc_type = Column(
        Enum('standard', 'textbook', 'manual', 'regulation', name='doc_type_enum'),
        nullable=False,
        comment="文档类型"
    )

    # 标准类文档特有字段
    standard_no = Column(String(100), comment="标准号")
    version = Column(String(50), comment="版本号")
    publish_org = Column(String(200), comment="发布机构")
    publish_date = Column(Date, comment="发布日期")
    implement_date = Column(Date, comment="实施日期")
    status = Column(
        Enum('valid', 'expired', 'draft', name='doc_status_enum'),
        default='valid',
        comment="有效性状态"
    )
    replaced_by = Column(String(100), comment="被哪个标准替代")
    replaces = Column(String(100), comment="替代哪个标准")

    # 分类字段
    category = Column(String(50), comment="专业分类")
    voltage_level = Column(String(50), comment="电压等级")
    keywords = Column(Text, comment="关键词（JSON）")
    abstract = Column(Text, comment="摘要")

    # 文件信息
    file_path = Column(String(500), nullable=False, comment="MinIO文件路径")
    file_size = Column(BigInteger, comment="文件大小")
    file_hash = Column(String(64), unique=True, comment="文件哈希")
    page_count = Column(Integer, comment="页数")

    # 处理状态
    process_status = Column(
        Enum('pending', 'processing', 'completed', 'failed', name='process_status_enum'),
        default='pending',
        comment="处理状态"
    )
    process_error = Column(Text, comment="处理错误")

    # 统计信息
    chunk_count = Column(Integer, default=0, comment="分块数量")
    view_count = Column(Integer, default=0, comment="查看次数")
    reference_count = Column(Integer, default=0, comment="被引用次数")

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    processed_at = Column(TIMESTAMP, nullable=True, comment="处理完成时间")

    # 关系
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    # 索引
    __table_args__ = (
        Index('idx_standard_no', 'standard_no'),
        Index('idx_doc_type', 'doc_type'),
        Index('idx_category', 'category'),
        Index('idx_voltage_level', 'voltage_level'),
        Index('idx_status', 'status'),
        Index('idx_process_status', 'process_status'),
        Index('idx_created_at', 'created_at'),
        {'comment': '文档表'}
    )


class Chunk(Base):
    """文档块表"""
    __tablename__ = "chunks"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="块ID")
    document_id = Column(BigInteger, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, comment="文档ID")
    parent_chunk_id = Column(BigInteger, ForeignKey('chunks.id', ondelete='CASCADE'), nullable=True, comment="父块ID")

    # 内容
    content = Column(Text, nullable=False, comment="文本内容")
    content_hash = Column(String(64), nullable=False, unique=True, comment="内容哈希")
    chunk_type = Column(
        Enum('parent', 'child', name='chunk_type_enum'),
        nullable=False,
        default='parent',
        comment="块类型"
    )

    # 向量信息
    vector_id = Column(String(100), comment="Qdrant向量ID")
    has_dense_vector = Column(Boolean, default=False, comment="是否有稠密向量")
    has_sparse_vector = Column(Boolean, default=False, comment="是否有稀疏向量")

    # 位置信息
    page_start = Column(Integer, comment="起始页码")
    page_end = Column(Integer, comment="结束页码")
    chapter = Column(String(200), comment="章节号")
    section = Column(String(200), comment="节号")
    clause = Column(String(200), comment="条款号")
    position_in_doc = Column(Integer, comment="在文档中的位置序号")

    # 元数据
    meta_data = Column(JSON, comment="扩展元数据", name="metadata")
    related_chunk_ids = Column(JSON, comment="关联块IDs")

    # 统计信息
    token_count = Column(Integer, comment="Token数量")
    char_count = Column(Integer, comment="字符数")

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系
    document = relationship("Document", back_populates="chunks")
    parent_chunk = relationship("Chunk", remote_side=[id], backref="child_chunks")

    # 索引
    __table_args__ = (
        Index('idx_document_id', 'document_id'),
        Index('idx_parent_chunk_id', 'parent_chunk_id'),
        Index('idx_vector_id', 'vector_id'),
        Index('idx_chunk_type', 'chunk_type'),
        Index('idx_clause', 'clause'),
        {'comment': '文档块表'}
    )


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="用户ID")
    username = Column(String(50), nullable=False, unique=True, comment="用户名")
    email = Column(String(100), nullable=False, unique=True, comment="邮箱")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    full_name = Column(String(100), comment="真实姓名")

    # 角色权限
    role = Column(
        Enum('admin', 'user', 'readonly', name='user_role_enum'),
        default='user',
        comment="角色"
    )
    is_active = Column(Boolean, default=True, comment="是否激活")

    # 统计信息
    query_count = Column(Integer, default=0, comment="查询次数")
    last_login_at = Column(TIMESTAMP, nullable=True, comment="最后登录时间")

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关系
    query_logs = relationship("QueryLog", back_populates="user")

    # 索引
    __table_args__ = (
        Index('idx_role', 'role'),
        Index('idx_is_active', 'is_active'),
        {'comment': '用户表'}
    )


class QueryLog(Base):
    """查询日志表"""
    __tablename__ = "query_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment="用户ID")

    # 查询内容
    query = Column(Text, nullable=False, comment="原始查询")
    normalized_query = Column(Text, comment="标准化后的查询")

    # 路由信息
    lane = Column(
        Enum('fast', 'slow', name='lane_enum'),
        nullable=False,
        comment="路由车道"
    )
    complexity_score = Column(Float, comment="复杂度评分")

    # 召回信息
    recall_success = Column(Boolean, comment="是否召回成功")
    recall_count = Column(Integer, comment="召回文档数")
    retry_count = Column(Integer, default=0, comment="二次检索次数")
    retrieved_chunk_ids = Column(JSON, comment="召回的chunk IDs")

    # 重排信息
    rerank_scores = Column(JSON, nullable=True, comment="精排结果：[{chunk_id, score}]，Top5或Top8")
    sufficiency_result = Column(JSON, nullable=True, comment="充分性判断结果：{sufficient, source, confidence, gaps}")

    # 提问优化信息
    vagueness_score = Column(Float, comment="笼统度评分")
    strategy = Column(String(30), comment="提问优化策略")
    clarified = Column(Boolean, default=False, comment="是否触发澄清")

    # 性能指标
    preprocessing_time = Column(Integer, comment="预处理耗时（ms）")
    retrieval_time = Column(Integer, comment="检索耗时（ms）")
    generation_time = Column(Integer, comment="生成耗时（ms）")
    total_time = Column(Integer, comment="总耗时（ms）")

    # 生成结果
    answer = Column(Text, comment="生成的答案")
    answer_hash = Column(String(64), comment="答案哈希")
    citations = Column(JSON, comment="引用来源")
    has_citations = Column(Boolean, default=True, comment="是否有引用")

    # 用户反馈
    feedback_score = Column(Integer, comment="用户评分1-5")
    feedback_text = Column(Text, comment="用户反馈文本")

    # 元数据
    filters_applied = Column(JSON, comment="应用的元数据过滤条件")
    expanded_queries = Column(JSON, comment="扩展的查询")

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="创建时间")

    # 关系
    user = relationship("User", back_populates="query_logs")
    clarification_log = relationship("ClarificationLog", back_populates="query_log", uselist=False)
    badcase = relationship("BadcaseTracking", back_populates="query_log", uselist=False)

    # 索引
    __table_args__ = (
        Index('idx_user_id', 'user_id'),
        Index('idx_lane', 'lane'),
        Index('idx_recall_success', 'recall_success'),
        Index('idx_strategy', 'strategy'),
        Index('idx_created_at', 'created_at'),
        Index('idx_feedback_score', 'feedback_score'),
        Index('idx_answer_hash', 'answer_hash'),
        {'comment': '查询日志表'}
    )


class ClarificationLog(Base):
    """澄清对话日志表"""
    __tablename__ = "clarification_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    query_log_id = Column(BigInteger, ForeignKey('query_logs.id', ondelete='CASCADE'), comment="关联查询日志ID")

    # 澄清信息
    original_query = Column(Text, nullable=False, comment="原始查询")
    strategy = Column(String(30), nullable=False, comment="澄清策略")
    vagueness_score = Column(Float, comment="笼统度评分")
    missing_dimensions = Column(JSON, comment="缺失的维度")

    # 澄清选项
    options_generated = Column(JSON, comment="生成的澄清选项")

    # 用户行为
    user_choice = Column(String(100), comment="用户选择")
    user_input = Column(Text, comment="用户自定义输入")
    refined_query = Column(Text, comment="澄清后的查询")

    # 效果评估
    final_recall_success = Column(Boolean, comment="澄清后是否成功")
    recall_improvement = Column(Float, comment="召回率提升")

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="创建时间")

    # 关系
    query_log = relationship("QueryLog", back_populates="clarification_log")

    # 索引
    __table_args__ = (
        Index('idx_query_log_id', 'query_log_id'),
        Index('idx_strategy', 'strategy'),
        Index('idx_user_choice', 'user_choice'),
        Index('idx_created_at', 'created_at'),
        {'comment': '澄清对话日志表'}
    )


class BadcaseTracking(Base):
    """难例追踪表"""
    __tablename__ = "badcase_tracking"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    query_log_id = Column(BigInteger, ForeignKey('query_logs.id', ondelete='SET NULL'), comment="关联查询日志ID")

    # 难例信息
    query = Column(Text, nullable=False, comment="查询")
    expected_doc = Column(String(200), comment="期望命中的文档")
    expected_chunk_id = Column(BigInteger, ForeignKey('chunks.id', ondelete='SET NULL'), comment="期望块ID")
    retrieved_docs = Column(JSON, comment="实际召回的文档")

    # 根因分析
    root_cause = Column(
        Enum('chunking', 'embedding', 'reranking', 'missing_doc', name='root_cause_enum'),
        comment="根因类型"
    )
    root_cause_detail = Column(Text, comment="根因详细说明")

    # 处理状态
    status = Column(
        Enum('pending', 'analyzing', 'fixed', 'ignored', name='badcase_status_enum'),
        default='pending',
        comment="处理状态"
    )
    fix_method = Column(String(100), comment="修复方法")
    fix_description = Column(Text, comment="修复说明")

    # 优先级
    priority = Column(
        Enum('low', 'medium', 'high', name='priority_enum'),
        default='medium',
        comment="优先级"
    )
    frequency = Column(Integer, default=1, comment="出现频率")

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="创建时间")
    fixed_at = Column(TIMESTAMP, nullable=True, comment="修复时间")

    # 关系
    query_log = relationship("QueryLog", back_populates="badcase")

    # 索引
    __table_args__ = (
        Index('idx_query_log_id', 'query_log_id'),
        Index('idx_root_cause', 'root_cause'),
        Index('idx_status', 'status'),
        Index('idx_priority', 'priority'),
        Index('idx_created_at', 'created_at'),
        {'comment': '难例追踪表'}
    )


class TermDictionary(Base):
    """术语词典表"""
    __tablename__ = "term_dictionary"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")

    # 术语信息
    standard_term = Column(String(200), nullable=False, comment="标准术语")
    aliases = Column(JSON, nullable=False, comment="别名列表")
    category = Column(String(50), comment="术语分类")
    definition = Column(Text, comment="术语定义")

    # 来源信息
    source = Column(
        Enum('manual', 'auto', 'loop_engineering', name='term_source_enum'),
        default='manual',
        comment="来源"
    )
    confidence = Column(Float, comment="置信度")
    frequency = Column(Integer, default=0, comment="使用频率")

    # 状态
    is_active = Column(Boolean, default=True, comment="是否激活")

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 索引
    __table_args__ = (
        Index('idx_standard_term', 'standard_term'),
        Index('idx_category', 'category'),
        Index('idx_source', 'source'),
        Index('idx_is_active', 'is_active'),
        {'comment': '术语词典表'}
    )


class TestCase(Base):
    """测试用例表"""
    __tablename__ = "test_cases"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")

    # 测试用例信息
    query = Column(Text, nullable=False, comment="测试查询")
    expected_chunks = Column(JSON, nullable=False, comment="期望召回的chunk IDs")
    expected_answer = Column(Text, comment="期望答案")

    # 分类信息
    category = Column(String(50), comment="测试用例分类")
    difficulty = Column(
        Enum('easy', 'medium', 'hard', name='difficulty_enum'),
        default='medium',
        comment="难度"
    )
    source = Column(
        Enum('manual', 'badcase', 'user_feedback', name='test_source_enum'),
        default='manual',
        comment="来源"
    )
    tags = Column(JSON, comment="标签")

    # 状态
    is_active = Column(Boolean, default=True, comment="是否激活")

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 索引
    __table_args__ = (
        Index('idx_category', 'category'),
        Index('idx_difficulty', 'difficulty'),
        Index('idx_source', 'source'),
        Index('idx_is_active', 'is_active'),
        {'comment': '测试用例表'}
    )


class ClauseReference(Base):
    """条款引用关系表"""
    __tablename__ = "clause_references"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")

    # 引用关系
    source_chunk_id = Column(BigInteger, ForeignKey('chunks.id', ondelete='CASCADE'), nullable=False, comment="源条款块ID")
    target_standard_no = Column(String(100), comment="目标标准号")
    target_clause = Column(String(200), comment="目标条款号")
    target_chunk_id = Column(BigInteger, ForeignKey('chunks.id', ondelete='SET NULL'), comment="目标块ID")

    # 引用类型
    reference_type = Column(
        Enum('direct', 'related', 'superseded', name='reference_type_enum'),
        default='direct',
        comment="引用类型"
    )

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="创建时间")

    # 索引
    __table_args__ = (
        Index('idx_source_chunk', 'source_chunk_id'),
        Index('idx_target_standard', 'target_standard_no', 'target_clause'),
        {'comment': '条款引用关系表'}
    )


class ABExperiment(Base):
    """A/B测试实验表"""
    __tablename__ = "ab_experiments"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="实验ID")

    # 实验信息
    name = Column(String(100), nullable=False, unique=True, comment="实验名称")
    description = Column(Text, comment="实验描述")
    experiment_type = Column(String(50), comment="实验类型")

    # 变体配置
    control_config = Column(JSON, comment="对照组配置")
    treatment_config = Column(JSON, comment="实验组配置")

    # 流量分配
    traffic_percent = Column(Integer, default=10, comment="实验组流量百分比")

    # 状态
    status = Column(
        Enum('draft', 'running', 'completed', 'rolled_back', name='experiment_status_enum'),
        default='draft',
        comment="实验状态"
    )

    # 指标
    control_metrics = Column(JSON, comment="对照组指标")
    treatment_metrics = Column(JSON, comment="实验组指标")

    # 决策
    decision = Column(
        Enum('pending', 'rollout', 'rollback', 'manual', name='decision_enum'),
        comment="决策结果"
    )
    decision_reason = Column(Text, comment="决策理由")
    decided_at = Column(TIMESTAMP, nullable=True, comment="决策时间")

    # 时间
    start_at = Column(TIMESTAMP, comment="开始时间")
    end_at = Column(TIMESTAMP, comment="结束时间")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 索引
    __table_args__ = (
        Index('idx_status', 'status'),
        Index('idx_start_at', 'start_at'),
        Index('idx_end_at', 'end_at'),
        {'comment': 'A/B测试实验表'}
    )
