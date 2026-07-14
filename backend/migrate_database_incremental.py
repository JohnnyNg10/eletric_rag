"""
增量更新数据库表结构 - 添加扫描件PDF支持（不删除数据）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import engine
from sqlalchemy import text

print("=" * 60)
print("增量更新数据库表结构")
print("=" * 60)

print("\n注意: 这是增量更新，不会删除现有数据")

with engine.connect() as conn:
    # 1. 扩展 documents 表
    print("\n1. 扩展 documents 表...")

    alter_sqls = [
        "ALTER TABLE documents ADD COLUMN is_scanned BOOLEAN DEFAULT FALSE COMMENT '是否为扫描件'",
        "ALTER TABLE documents ADD COLUMN ocr_engine VARCHAR(50) COMMENT 'OCR引擎'",
        "ALTER TABLE documents ADD COLUMN ocr_confidence FLOAT COMMENT 'OCR平均置信度'",
        "ALTER TABLE documents ADD COLUMN ocr_version VARCHAR(50) COMMENT 'OCR引擎版本'",
        "ALTER TABLE documents ADD COLUMN markdown_path VARCHAR(500) COMMENT 'Markdown文件路径'",
        "ALTER TABLE documents ADD COLUMN images_prefix VARCHAR(500) COMMENT '图片文件前缀'",
        "ALTER TABLE documents ADD COLUMN tables_prefix VARCHAR(500) COMMENT '表格文件前缀'",
        "ALTER TABLE documents ADD COLUMN image_count INT DEFAULT 0 COMMENT '图片数量'",
        "ALTER TABLE documents ADD COLUMN table_count INT DEFAULT 0 COMMENT '表格数量'",
    ]

    for sql in alter_sqls:
        try:
            conn.execute(text(sql))
            conn.commit()
            print(f"   [OK] {sql.split('ADD COLUMN')[1].split()[0] if 'ADD COLUMN' in sql else 'executed'}")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print(f"   [SKIP] 字段已存在")
            else:
                print(f"   [ERROR] {e}")

    # 2. 扩展 chunks 表
    print("\n2. 扩展 chunks 表...")

    alter_sqls = [
        "ALTER TABLE chunks ADD COLUMN content_type ENUM('text','image_description','table_summary') NOT NULL DEFAULT 'text' COMMENT '内容类型'",
        "ALTER TABLE chunks ADD COLUMN related_resource_id BIGINT COMMENT '关联资源ID'",
        "ALTER TABLE chunks ADD COLUMN related_resource_type VARCHAR(20) COMMENT '关联资源类型'",
    ]

    for sql in alter_sqls:
        try:
            conn.execute(text(sql))
            conn.commit()
            print(f"   [OK] {sql.split('ADD COLUMN')[1].split()[0] if 'ADD COLUMN' in sql else 'executed'}")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print(f"   [SKIP] 字段已存在")
            else:
                print(f"   [ERROR] {e}")

    # 添加复合唯一索引
    try:
        conn.execute(text("ALTER TABLE chunks ADD UNIQUE INDEX uk_doc_content_hash (document_id, content_hash)"))
        conn.commit()
        print("   [OK] uk_doc_content_hash")
    except Exception as e:
        if "Duplicate key name" in str(e):
            print("   [SKIP] 索引已存在")
        else:
            print(f"   [ERROR] {e}")

    # 添加 content_type 索引
    try:
        conn.execute(text("ALTER TABLE chunks ADD INDEX idx_content_type (content_type)"))
        conn.commit()
        print("   [OK] idx_content_type")
    except Exception as e:
        if "Duplicate key name" in str(e):
            print("   [SKIP] 索引已存在")
        else:
            print(f"   [ERROR] {e}")

    # 3. 创建 images 表
    print("\n3. 创建 images 表...")

    create_images_sql = """
    CREATE TABLE IF NOT EXISTS images (
        id BIGINT NOT NULL COMMENT '图片ID' AUTO_INCREMENT,
        document_id BIGINT NOT NULL COMMENT '所属文档ID',
        chunk_id BIGINT COMMENT '关联的VLM描述Chunk ID',
        image_type ENUM('figure','diagram','photo','chart') NOT NULL DEFAULT 'figure' COMMENT '图片类型',
        minio_path VARCHAR(500) NOT NULL COMMENT 'MinIO文件路径',
        file_size INTEGER COMMENT '文件大小（字节）',
        width INTEGER COMMENT '宽度（像素）',
        height INTEGER COMMENT '高度（像素）',
        page_number INTEGER NOT NULL COMMENT '所在页码',
        image_index INTEGER NOT NULL COMMENT '页内图片序号',
        bbox JSON COMMENT '边界框坐标',
        caption TEXT COMMENT '图注/标题',
        figure_number VARCHAR(50) COMMENT '图号',
        ocr_text TEXT COMMENT '图内文字',
        vlm_description TEXT COMMENT 'VLM生成的图片语义描述',
        vlm_model VARCHAR(50) COMMENT '使用的VLM模型',
        vlm_confidence FLOAT COMMENT 'VLM描述置信度',
        metadata JSON COMMENT '扩展元数据',
        created_at TIMESTAMP NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uk_images_doc_page_index (document_id, page_number, image_index),
        KEY idx_images_document_id (document_id),
        KEY idx_images_chunk_id (chunk_id),
        KEY idx_images_page_number (page_number),
        KEY idx_images_figure_number (figure_number),
        FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE,
        FOREIGN KEY(chunk_id) REFERENCES chunks (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='图片表'
    """

    try:
        conn.execute(text(create_images_sql))
        conn.commit()
        print("   [OK] images 表已创建")
    except Exception as e:
        if "already exists" in str(e):
            print("   [SKIP] 表已存在")
        else:
            print(f"   [ERROR] {e}")

    # 4. 创建 tables 表
    print("\n4. 创建 tables 表...")

    create_tables_sql = """
    CREATE TABLE IF NOT EXISTS `tables` (
        id BIGINT NOT NULL COMMENT '表格ID' AUTO_INCREMENT,
        document_id BIGINT NOT NULL COMMENT '所属文档ID',
        chunk_id BIGINT COMMENT '关联的表格摘要Chunk ID',
        table_number VARCHAR(50) COMMENT '表号',
        title TEXT COMMENT '表格标题',
        page_number INTEGER NOT NULL COMMENT '所在页码',
        table_index INTEGER NOT NULL COMMENT '页内表格序号',
        bbox JSON COMMENT '边界框坐标',
        row_count INTEGER COMMENT '行数',
        col_count INTEGER COMMENT '列数',
        headers JSON COMMENT '表头信息',
        minio_path VARCHAR(500) NOT NULL COMMENT 'MinIO存储路径',
        markdown_content TEXT COMMENT '表格Markdown文本',
        metadata JSON COMMENT '扩展元数据',
        created_at TIMESTAMP NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uk_tables_doc_page_index (document_id, page_number, table_index),
        KEY idx_tables_document_id (document_id),
        KEY idx_tables_chunk_id (chunk_id),
        KEY idx_tables_page_number (page_number),
        KEY idx_tables_table_number (table_number),
        FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE,
        FOREIGN KEY(chunk_id) REFERENCES chunks (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='表格表'
    """

    try:
        conn.execute(text(create_tables_sql))
        conn.commit()
        print("   [OK] tables 表已创建")
    except Exception as e:
        if "already exists" in str(e):
            print("   [SKIP] 表已存在")
        else:
            print(f"   [ERROR] {e}")

print("\n" + "=" * 60)
print("[SUCCESS] 数据库表结构更新完成")
print("=" * 60)
print("\n变更摘要:")
print("  - documents 表: 新增 9 个扫描件相关字段")
print("  - chunks 表: 新增 content_type, related_resource_id, related_resource_type")
print("  - 新增 images 表")
print("  - 新增 tables 表")
