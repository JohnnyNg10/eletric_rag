-- =====================================================
-- 电力专业知识库RAG系统 - 数据库初始化脚本
-- 版本: v2.0
-- 创建日期: 2026-07-06
-- 说明: 包含10张核心表，支持完整的RAG业务流程和Loop Engineering
-- =====================================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS electric_rag
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE electric_rag;

-- 设置时区
SET time_zone = '+08:00';

-- =====================================================
-- 1. 文档表 (documents)
-- 存储文档的基本信息和元数据
-- =====================================================
CREATE TABLE documents (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '文档ID',
    title VARCHAR(500) NOT NULL COMMENT '文档标题',
    doc_type ENUM('standard', 'textbook', 'manual', 'regulation') NOT NULL COMMENT '文档类型',

    -- 标准类文档特有字段
    standard_no VARCHAR(100) COMMENT '标准号，如：GB 50057-2010',
    version VARCHAR(50) COMMENT '版本号',
    publish_org VARCHAR(200) COMMENT '发布机构',
    publish_date DATE COMMENT '发布日期',
    implement_date DATE COMMENT '实施日期',
    status ENUM('valid', 'expired', 'draft') DEFAULT 'valid' COMMENT '有效性状态',
    replaced_by VARCHAR(100) COMMENT '被哪个标准替代',
    replaces VARCHAR(100) COMMENT '替代哪个标准',

    -- 分类字段
    category VARCHAR(50) COMMENT '专业分类：配电/变电/继保/高压/输电',
    voltage_level VARCHAR(50) COMMENT '电压等级：10kV/35kV/110kV等',
    keywords TEXT COMMENT '关键词（JSON数组）',
    abstract TEXT COMMENT '摘要',

    -- 文件信息
    file_path VARCHAR(500) NOT NULL COMMENT 'MinIO中的文件路径',
    file_size BIGINT COMMENT '文件大小（字节）',
    file_hash VARCHAR(64) COMMENT '文件SHA256哈希（去重）',
    page_count INT COMMENT '页数',

    -- 处理状态
    process_status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending' COMMENT '处理状态',
    process_error TEXT COMMENT '处理错误信息',

    -- 统计信息
    chunk_count INT DEFAULT 0 COMMENT '分块数量',
    view_count INT DEFAULT 0 COMMENT '查看次数',
    reference_count INT DEFAULT 0 COMMENT '被引用次数',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    processed_at TIMESTAMP NULL COMMENT '处理完成时间',

    -- 索引
    INDEX idx_standard_no (standard_no),
    INDEX idx_doc_type (doc_type),
    INDEX idx_category (category),
    INDEX idx_voltage_level (voltage_level),
    INDEX idx_status (status),
    INDEX idx_process_status (process_status),
    INDEX idx_created_at (created_at),
    UNIQUE KEY uk_file_hash (file_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档表';

-- =====================================================
-- 2. 文档块表 (chunks)
-- 存储文档分块信息，支持父子块结构
-- =====================================================
CREATE TABLE chunks (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '块ID',
    document_id BIGINT UNSIGNED NOT NULL COMMENT '文档ID',
    parent_chunk_id BIGINT UNSIGNED COMMENT '父块ID（子块时有值）',

    -- 内容
    content TEXT NOT NULL COMMENT '文本内容',
    content_hash VARCHAR(64) NOT NULL COMMENT '内容哈希（去重）',
    chunk_type ENUM('parent', 'child') NOT NULL DEFAULT 'parent' COMMENT '块类型',

    -- 向量信息
    vector_id VARCHAR(100) COMMENT 'Qdrant中的向量ID',
    has_dense_vector BOOLEAN DEFAULT FALSE COMMENT '是否有稠密向量',
    has_sparse_vector BOOLEAN DEFAULT FALSE COMMENT '是否有稀疏向量',

    -- 位置信息
    page_start INT COMMENT '起始页码',
    page_end INT COMMENT '结束页码',
    chapter VARCHAR(200) COMMENT '章节号',
    section VARCHAR(200) COMMENT '节号',
    clause VARCHAR(200) COMMENT '条款号',
    position_in_doc INT COMMENT '在文档中的位置序号',

    -- 元数据
    metadata JSON COMMENT '扩展元数据',
    related_chunk_ids JSON COMMENT '关联块IDs（引用的其他条款）',

    -- 统计信息
    token_count INT COMMENT 'Token数量',
    char_count INT COMMENT '字符数',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 外键
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_chunk_id) REFERENCES chunks(id) ON DELETE CASCADE,

    -- 索引
    INDEX idx_document_id (document_id),
    INDEX idx_parent_chunk_id (parent_chunk_id),
    INDEX idx_vector_id (vector_id),
    INDEX idx_chunk_type (chunk_type),
    INDEX idx_clause (clause),
    UNIQUE KEY uk_content_hash (content_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档块表';

-- =====================================================
-- 3. 用户表 (users)
-- =====================================================
CREATE TABLE users (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
    email VARCHAR(100) NOT NULL UNIQUE COMMENT '邮箱',
    password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
    full_name VARCHAR(100) COMMENT '真实姓名',

    -- 角色权限
    role ENUM('admin', 'user', 'readonly') DEFAULT 'user' COMMENT '角色',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',

    -- 统计信息
    query_count INT DEFAULT 0 COMMENT '查询次数',
    last_login_at TIMESTAMP NULL COMMENT '最后登录时间',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 索引
    INDEX idx_role (role),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- =====================================================
-- 4. 查询日志表 (query_logs)
-- 记录所有查询请求，支持Loop Engineering分析
-- =====================================================
CREATE TABLE query_logs (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '日志ID',
    user_id BIGINT UNSIGNED COMMENT '用户ID',

    -- 查询内容
    query TEXT NOT NULL COMMENT '原始查询',
    normalized_query TEXT COMMENT '标准化后的查询',

    -- 路由信息
    lane ENUM('fast', 'slow') NOT NULL COMMENT '路由车道',
    complexity_score FLOAT COMMENT '复杂度评分',

    -- 召回信息
    recall_success BOOLEAN COMMENT '是否召回成功',
    recall_count INT COMMENT '召回文档数',
    retry_count INT DEFAULT 0 COMMENT '二次检索次数',
    retrieved_chunk_ids JSON COMMENT '召回的chunk IDs',

    -- 提问优化信息
    vagueness_score FLOAT COMMENT '笼统度评分 0-1',
    strategy VARCHAR(30) COMMENT '提问优化策略',
    clarified BOOLEAN DEFAULT FALSE COMMENT '是否触发了澄清',

    -- 性能指标（毫秒）
    preprocessing_time INT COMMENT '预处理耗时（ms）',
    retrieval_time INT COMMENT '检索耗时（ms）',
    generation_time INT COMMENT '生成耗时（ms）',
    total_time INT COMMENT '总耗时（ms）',

    -- 生成结果
    answer TEXT COMMENT '生成的答案',
    answer_hash VARCHAR(64) COMMENT '答案哈希（去重检测）',
    citations JSON COMMENT '引用来源列表',
    has_citations BOOLEAN DEFAULT TRUE COMMENT '是否有引用',

    -- 用户反馈
    feedback_score INT COMMENT '用户评分 1-5',
    feedback_text TEXT COMMENT '用户反馈文本',

    -- 元数据
    filters_applied JSON COMMENT '应用的元数据过滤条件',
    expanded_queries JSON COMMENT '扩展的查询（HyDE/多Query）',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    -- 外键
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,

    -- 索引
    INDEX idx_user_id (user_id),
    INDEX idx_lane (lane),
    INDEX idx_recall_success (recall_success),
    INDEX idx_strategy (strategy),
    INDEX idx_created_at (created_at),
    INDEX idx_feedback_score (feedback_score),
    INDEX idx_answer_hash (answer_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='查询日志表';

-- =====================================================
-- 5. 澄清对话日志表 (clarification_logs)
-- 记录提问优化的澄清对话，支持Loop Engineering闭环1、2
-- =====================================================
CREATE TABLE clarification_logs (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '日志ID',
    query_log_id BIGINT UNSIGNED COMMENT '关联的查询日志ID',

    -- 澄清信息
    original_query TEXT NOT NULL COMMENT '原始查询',
    strategy VARCHAR(30) NOT NULL COMMENT '澄清策略',
    vagueness_score FLOAT COMMENT '笼统度评分',
    missing_dimensions JSON COMMENT '缺失的维度',

    -- 澄清选项
    options_generated JSON COMMENT '生成的澄清选项',

    -- 用户行为
    user_choice VARCHAR(100) COMMENT '用户选择：选项ID/skip/custom_input',
    user_input TEXT COMMENT '用户自定义输入',
    refined_query TEXT COMMENT '澄清后的查询',

    -- 效果评估
    final_recall_success BOOLEAN COMMENT '澄清后是否召回成功',
    recall_improvement FLOAT COMMENT '召回率提升',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    -- 外键
    FOREIGN KEY (query_log_id) REFERENCES query_logs(id) ON DELETE CASCADE,

    -- 索引
    INDEX idx_query_log_id (query_log_id),
    INDEX idx_strategy (strategy),
    INDEX idx_user_choice (user_choice),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='澄清对话日志表';

-- =====================================================
-- 6. 难例追踪表 (badcase_tracking)
-- 记录召回失败的case，支持Loop Engineering闭环3、4
-- =====================================================
CREATE TABLE badcase_tracking (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT 'ID',
    query_log_id BIGINT UNSIGNED COMMENT '关联的查询日志ID',

    -- 难例信息
    query TEXT NOT NULL COMMENT '查询',
    expected_doc VARCHAR(200) COMMENT '期望命中的文档',
    expected_chunk_id BIGINT UNSIGNED COMMENT '期望命中的块ID',
    retrieved_docs JSON COMMENT '实际召回的文档列表',

    -- 根因分析
    root_cause ENUM('chunking', 'embedding', 'reranking', 'missing_doc') COMMENT '根因类型',
    root_cause_detail TEXT COMMENT '根因详细说明',

    -- 处理状态
    status ENUM('pending', 'analyzing', 'fixed', 'ignored') DEFAULT 'pending' COMMENT '处理状态',
    fix_method VARCHAR(100) COMMENT '修复方法',
    fix_description TEXT COMMENT '修复说明',

    -- 优先级
    priority ENUM('low', 'medium', 'high') DEFAULT 'medium' COMMENT '优先级',
    frequency INT DEFAULT 1 COMMENT '出现频率',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    fixed_at TIMESTAMP NULL COMMENT '修复时间',

    -- 外键
    FOREIGN KEY (query_log_id) REFERENCES query_logs(id) ON DELETE SET NULL,
    FOREIGN KEY (expected_chunk_id) REFERENCES chunks(id) ON DELETE SET NULL,

    -- 索引
    INDEX idx_query_log_id (query_log_id),
    INDEX idx_root_cause (root_cause),
    INDEX idx_status (status),
    INDEX idx_priority (priority),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='难例追踪表';

-- =====================================================
-- 7. 术语词典表 (term_dictionary)
-- 存储电力专业术语映射关系
-- =====================================================
CREATE TABLE term_dictionary (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT 'ID',

    -- 术语信息
    standard_term VARCHAR(200) NOT NULL COMMENT '标准术语',
    aliases JSON NOT NULL COMMENT '别名列表（俗称、缩写等）',
    category VARCHAR(50) COMMENT '术语分类',
    definition TEXT COMMENT '术语定义',

    -- 来源信息
    source ENUM('manual', 'auto', 'loop_engineering') DEFAULT 'manual' COMMENT '来源',
    confidence FLOAT COMMENT '置信度（自动挖掘时）',
    frequency INT DEFAULT 0 COMMENT '使用频率',

    -- 状态
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 索引
    INDEX idx_standard_term (standard_term),
    INDEX idx_category (category),
    INDEX idx_source (source),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='术语词典表';

-- =====================================================
-- 8. 测试用例表 (test_cases)
-- 存储测试集，支持Loop Engineering闭环4和评测任务
-- =====================================================
CREATE TABLE test_cases (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT 'ID',

    -- 测试用例信息
    query TEXT NOT NULL COMMENT '测试查询',
    expected_chunks JSON NOT NULL COMMENT '期望召回的chunk IDs',
    expected_answer TEXT COMMENT '期望答案（可选）',

    -- 分类信息
    category VARCHAR(50) COMMENT '测试用例分类',
    difficulty ENUM('easy', 'medium', 'hard') DEFAULT 'medium' COMMENT '难度',
    source ENUM('manual', 'badcase', 'user_feedback') DEFAULT 'manual' COMMENT '来源',
    tags JSON COMMENT '标签（JSON数组）',

    -- 状态
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 索引
    INDEX idx_category (category),
    INDEX idx_difficulty (difficulty),
    INDEX idx_source (source),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='测试用例表';

-- =====================================================
-- 9. 条款引用关系表 (clause_references)
-- 存储标准条款间的引用关系，支持自动展开关联条款
-- =====================================================
CREATE TABLE clause_references (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT 'ID',

    -- 引用关系
    source_chunk_id BIGINT UNSIGNED NOT NULL COMMENT '源条款块ID',
    target_standard_no VARCHAR(100) COMMENT '目标标准号',
    target_clause VARCHAR(200) COMMENT '目标条款号',
    target_chunk_id BIGINT UNSIGNED COMMENT '目标块ID（如已入库）',

    -- 引用类型
    reference_type ENUM('direct', 'related', 'superseded') DEFAULT 'direct' COMMENT '引用类型',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    -- 外键
    FOREIGN KEY (source_chunk_id) REFERENCES chunks(id) ON DELETE CASCADE,
    FOREIGN KEY (target_chunk_id) REFERENCES chunks(id) ON DELETE SET NULL,

    -- 索引
    INDEX idx_source_chunk (source_chunk_id),
    INDEX idx_target_standard (target_standard_no, target_clause)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='条款引用关系表';

-- =====================================================
-- 10. A/B测试实验表 (ab_experiments)
-- 记录A/B测试实验，支持Loop Engineering闭环5
-- =====================================================
CREATE TABLE ab_experiments (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '实验ID',

    -- 实验信息
    name VARCHAR(100) NOT NULL UNIQUE COMMENT '实验名称',
    description TEXT COMMENT '实验描述',
    experiment_type VARCHAR(50) COMMENT '实验类型：prompt/retrieval/rerank等',

    -- 变体配置
    control_config JSON COMMENT '对照组配置',
    treatment_config JSON COMMENT '实验组配置',

    -- 流量分配
    traffic_percent INT DEFAULT 10 COMMENT '实验组流量百分比',

    -- 状态
    status ENUM('draft', 'running', 'completed', 'rolled_back') DEFAULT 'draft' COMMENT '实验状态',

    -- 指标
    control_metrics JSON COMMENT '对照组指标',
    treatment_metrics JSON COMMENT '实验组指标',

    -- 决策
    decision ENUM('pending', 'rollout', 'rollback', 'manual') COMMENT '决策结果',
    decision_reason TEXT COMMENT '决策理由',
    decided_at TIMESTAMP NULL COMMENT '决策时间',

    -- 时间
    start_at TIMESTAMP COMMENT '开始时间',
    end_at TIMESTAMP COMMENT '结束时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 索引
    INDEX idx_status (status),
    INDEX idx_start_at (start_at),
    INDEX idx_end_at (end_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='A/B测试实验表';

-- =====================================================
-- 初始化数据
-- =====================================================

-- 插入默认管理员用户（密码: admin123，需要在应用层修改）
INSERT INTO users (username, email, password_hash, full_name, role) VALUES
('admin', 'admin@electric-rag.com', '$2b$12$placeholder_hash', '系统管理员', 'admin');

-- 插入常用电力术语
INSERT INTO term_dictionary (standard_term, aliases, category, source) VALUES
('电压互感器', '["PT", "电压互感器"]', '设备', 'manual'),
('电流互感器', '["CT", "电流互感器"]', '设备', 'manual'),
('隔离开关', '["刀闸", "隔离开关"]', '设备', 'manual'),
('断路器', '["开关", "断路器"]', '设备', 'manual'),
('10kV', '["10千伏", "10kV", "10KV"]', '电压等级', 'manual'),
('35kV', '["35千伏", "35kV", "35KV"]', '电压等级', 'manual'),
('110kV', '["110千伏", "110kV", "110KV"]', '电压等级', 'manual'),
('220kV', '["220千伏", "220kV", "220KV"]', '电压等级', 'manual');

-- =====================================================
-- 完成
-- =====================================================
SELECT 'Database initialization completed successfully!' AS message;
SELECT COUNT(*) AS table_count FROM information_schema.tables
WHERE table_schema = 'electric_rag' AND table_type = 'BASE TABLE';
