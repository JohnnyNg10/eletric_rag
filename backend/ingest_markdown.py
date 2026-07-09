"""
Markdown文档入库脚本

功能：
- 解析Markdown，识别条款/表格/普通段落
- 按条款粒度分块（父块 + 子块）
- 表格独立成块
- 写入 Qdrant / Elasticsearch / MySQL
"""
import asyncio
import sys
import re
import uuid
import hashlib
import time
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent))

from app.storage.vector_store import vector_store
from app.storage.search_engine import search_engine
from app.core.embedding.embedder import embedder
from app.db.session import SessionLocal
from app.db.models import Document, Chunk
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

MAX_PARENT_TOKENS = 800
MAX_CHILD_TOKENS  = 256


# ─── 数据结构 ──────────────────────────────────────────────

@dataclass
class ChunkBlock:
    chunk_id: str
    chunk_type: str          # "parent" | "child" | "table"
    text: str
    parent_chunk_id: Optional[str] = None
    chapter: str = ""
    clause: str = ""
    standard_no: str = ""
    doc_id: str = ""
    position: int = 0
    metadata: Dict = field(default_factory=dict)


# ─── Token 估算 ────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """粗估token数：中文≈1字=1token，英文≈4字符=1token"""
    chinese = sum(1 for c in text if '一' <= c <= '鿿')
    others = len(text) - chinese
    return chinese + others // 4


# ─── Markdown 解析 ─────────────────────────────────────────

@dataclass
class Section:
    """一个顶级章节（## 标题）"""
    heading: str
    chapter_no: str          # "5" / "6" / "附录A" 等
    clauses: List[Dict] = field(default_factory=list)   # 子条款
    tables: List[Dict] = field(default_factory=list)    # 章内表格
    pre_text: str = ""       # 标题后、第一个条款前的段落


def parse_standard_no(heading: str) -> str:
    """从 heading/正文 提取标准号"""
    m = re.search(r'GB[/T\s]*[\dT]+[-–]\d+', heading)
    return m.group(0).strip() if m else ""


def extract_chapter_no(heading: str) -> str:
    """从标题提取章节号，如 '5 规划' → '5'，'附录A' → '附录A'"""
    m = re.match(r'^#{1,6}\s*(\d+|附录[A-Z])', heading)
    return m.group(1) if m else ""


def parse_markdown(md_text: str) -> Tuple[str, str, List[Section]]:
    """
    解析 Markdown，返回 (doc_title, standard_no, sections)

    规则：
    - ## 一级章 → Section
    - ### 小节 → 归入当前 Section 的 clauses
    - x.y.z 正则条款行 → clause
    - | 开头多行 → table block
    """
    lines = md_text.splitlines()

    doc_title = ""
    standard_no = ""
    sections: List[Section] = []
    current_section: Optional[Section] = None
    current_clause: Optional[Dict] = None
    table_buffer: List[str] = []
    table_title: str = ""
    in_table = False
    position_counter = [0]

    def flush_clause():
        if current_clause and current_clause["text"].strip():
            if current_section:
                current_section.clauses.append(current_clause)

    def flush_table():
        nonlocal in_table, table_buffer, table_title
        if table_buffer:
            table_md = "\n".join(table_buffer)
            target = current_section if current_section else None
            if target is not None:
                target.tables.append({
                    "title": table_title,
                    "markdown": table_md,
                    "position": position_counter[0]
                })
                position_counter[0] += 1
        table_buffer = []
        table_title = ""
        in_table = False

    def add_text_to_current(text: str):
        """把普通文本追加到当前clause或section.pre_text"""
        if current_clause is not None:
            current_clause["text"] += "\n" + text
        elif current_section is not None:
            current_section.pre_text += "\n" + text

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 跳过空行（但先检查是否结束表格）
        if stripped == "":
            if in_table:
                flush_table()
            i += 1
            continue

        # 检测表格起始（| 开头的行，或前一行是"表N 描述"）
        if stripped.startswith("|"):
            if not in_table:
                in_table = True
            table_buffer.append(stripped)
            i += 1
            continue
        else:
            if in_table:
                flush_table()

        # # 标题（文档主标题）
        if re.match(r'^# [^#]', line):
            if not doc_title:
                doc_title = stripped.lstrip("# ").strip()
                sno = parse_standard_no(doc_title)
                if sno:
                    standard_no = sno
            i += 1
            continue

        # ## 章节标题 → 新 Section
        if re.match(r'^## ', line):
            flush_clause()
            current_clause = None
            heading_text = stripped.lstrip("# ").strip()
            chap_no = extract_chapter_no(line)
            current_section = Section(heading=heading_text, chapter_no=chap_no)
            sections.append(current_section)
            i += 1
            continue

        # ### 小节标题 → 归入 section，作为一个 clause 起始
        if re.match(r'^### ', line):
            flush_clause()
            heading_text = stripped.lstrip("# ").strip()
            # 尝试提取小节号（如 "5.2"）
            m = re.match(r'^#{2,6}\s*([\d\.]+|[A-Z]\.\d+)\s+', line)
            clause_no = m.group(1) if m else ""
            current_clause = {
                "clause_no": clause_no,
                "title": heading_text,
                "text": heading_text,
                "position": position_counter[0]
            }
            position_counter[0] += 1
            i += 1
            continue

        # x.y.z 条款行（如 "5.2.1 供电区域..."）
        m = re.match(r'^(\d+\.\d+(?:\.\d+)*)\s+\S', stripped)
        if m:
            # 如果和上一个 clause 的编号差距过大，直接追加到当前 clause
            # 否则作为新条款
            clause_no = m.group(1)
            depth = clause_no.count(".")
            if depth >= 1:  # x.y 以上才作为独立条款
                flush_clause()
                current_clause = {
                    "clause_no": clause_no,
                    "title": stripped,
                    "text": stripped,
                    "position": position_counter[0]
                }
                position_counter[0] += 1
                i += 1
                continue

        # "表N 标题" 行 → 记录表格标题，下一行开始是表格
        m = re.match(r'^表\s*\d+', stripped)
        if m:
            table_title = stripped
            i += 1
            continue

        # 普通文本行
        add_text_to_current(stripped)
        i += 1

    # 收尾
    if in_table:
        flush_table()
    flush_clause()

    return doc_title, standard_no, sections


# ─── 分块 ──────────────────────────────────────────────────

def chunk_section(section: Section, doc_id: str, standard_no: str) -> List[ChunkBlock]:
    """将一个 Section 拆成若干父块 + 子块 + 表格块"""
    blocks: List[ChunkBlock] = []

    # 1. 表格独立成块（chunk_type="parent"，table元数据）
    for tbl in section.tables:
        block = ChunkBlock(
            chunk_id=str(uuid.uuid4()),
            chunk_type="parent",
            text=f"{tbl['title']}\n\n{tbl['markdown']}" if tbl['title'] else tbl['markdown'],
            chapter=section.chapter_no,
            clause="",
            standard_no=standard_no,
            doc_id=doc_id,
            position=tbl['position'],
            metadata={
                "is_table": True,
                "table_title": tbl['title'],
                "chapter": section.chapter_no,
                "chapter_heading": section.heading,
            }
        )
        blocks.append(block)

    # 2. 条款分块（父块 + 子块）
    clauses = section.clauses
    if not clauses:
        # 章节没有条款，把 pre_text 作为一个父块
        text = section.heading
        if section.pre_text.strip():
            text += "\n\n" + section.pre_text.strip()
        if text.strip():
            blocks.append(ChunkBlock(
                chunk_id=str(uuid.uuid4()),
                chunk_type="parent",
                text=text,
                chapter=section.chapter_no,
                standard_no=standard_no,
                doc_id=doc_id,
                position=0,
                metadata={"chapter": section.chapter_no, "chapter_heading": section.heading}
            ))
        return blocks

    # 将条款按 token 限制分组
    groups: List[List[Dict]] = []
    current_group: List[Dict] = []
    current_tokens = 0

    for clause in clauses:
        t = estimate_tokens(clause["text"])
        if current_group and current_tokens + t > MAX_PARENT_TOKENS:
            groups.append(current_group)
            current_group = []
            current_tokens = 0
        current_group.append(clause)
        current_tokens += t
    if current_group:
        groups.append(current_group)

    # 每组生成一个父块 + N个子块
    for g_idx, group in enumerate(groups):
        parent_text = f"{section.heading}\n\n" + "\n\n".join(c["text"] for c in group)
        parent_id = str(uuid.uuid4())
        parent = ChunkBlock(
            chunk_id=parent_id,
            chunk_type="parent",
            text=parent_text,
            chapter=section.chapter_no,
            clause=group[0]["clause_no"] if group else "",
            standard_no=standard_no,
            doc_id=doc_id,
            position=group[0]["position"] if group else 0,
            metadata={
                "chapter": section.chapter_no,
                "chapter_heading": section.heading,
                "part_index": g_idx + 1,
            }
        )
        blocks.append(parent)

        for clause in group:
            child_text = clause["text"]
            # 子块超限时截断（极少发生）
            if estimate_tokens(child_text) > MAX_CHILD_TOKENS * 2:
                child_text = child_text[:MAX_CHILD_TOKENS * 4]

            child = ChunkBlock(
                chunk_id=str(uuid.uuid4()),
                chunk_type="child",
                text=child_text,
                parent_chunk_id=parent_id,
                chapter=section.chapter_no,
                clause=clause["clause_no"],
                standard_no=standard_no,
                doc_id=doc_id,
                position=clause["position"],
                metadata={
                    "chapter": section.chapter_no,
                    "clause": clause["clause_no"],
                    "clause_title": clause["title"][:100],
                }
            )
            blocks.append(child)

    return blocks


def build_all_chunks(doc_title: str, standard_no: str, sections: List[Section]) -> List[ChunkBlock]:
    doc_id = standard_no.replace(" ", "_").replace("/", "_") or doc_title[:20]
    all_blocks: List[ChunkBlock] = []
    for section in sections:
        all_blocks.extend(chunk_section(section, doc_id, standard_no))
    # 全局排序编号
    for i, b in enumerate(all_blocks):
        b.position = i
    return all_blocks, doc_id


# ─── 写入存储 ──────────────────────────────────────────────

def write_to_mysql(doc_title: str, standard_no: str, doc_id: str,
                   blocks: List[ChunkBlock]) -> int:
    """写入 MySQL，返回 document.id"""
    db = SessionLocal()
    try:
        doc = Document(
            title=doc_title,
            doc_type='standard',
            standard_no=standard_no,
            status='valid',
            file_path=f"standards/{doc_id}.md",
            category="配电网",
            file_hash=hashlib.md5(doc_title.encode()).hexdigest(),
            chunk_count=len(blocks),
            process_status='processing',
        )
        db.add(doc)
        db.flush()  # 获取 doc.id
        document_id = doc.id

        # 先插入所有父块，记录 chunk_id → db_id 的映射
        parent_db_id: Dict[str, int] = {}
        chunk_objs: List[Chunk] = []

        for block in blocks:
            content_hash = hashlib.sha256(block.text.encode()).hexdigest()
            chunk_type_val = 'parent' if block.chunk_type in ('parent',) else 'child'
            c = Chunk(
                document_id=document_id,
                content=block.text,
                content_hash=content_hash,
                chunk_type=chunk_type_val,
                vector_id=block.chunk_id,
                chapter=block.chapter,
                clause=block.clause,
                position_in_doc=block.position,
                token_count=estimate_tokens(block.text),
                char_count=len(block.text),
                meta_data=block.metadata,
            )
            chunk_objs.append((block, c))

        # 两次遍历：先插父块，再插子块（需要父块的 db id）
        child_pending = []
        for block, c in chunk_objs:
            if block.chunk_type == "parent":
                db.add(c)
                db.flush()
                parent_db_id[block.chunk_id] = c.id
            else:
                child_pending.append((block, c))

        for block, c in child_pending:
            if block.parent_chunk_id and block.parent_chunk_id in parent_db_id:
                c.parent_chunk_id = parent_db_id[block.parent_chunk_id]
            db.add(c)

        doc.process_status = 'completed'
        db.commit()
        print(f"  ✓ MySQL：文档ID={document_id}，{len(blocks)} 个chunk")
        return document_id

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def write_to_qdrant(blocks: List[ChunkBlock], document_title: str = "") -> int:
    """向量化并写入 Qdrant，返回写入数量"""
    points = []
    for block in blocks:
        try:
            dense_vec = embedder.encode(block.text).tolist()
        except Exception as e:
            print(f"  ! 向量化失败 chunk {block.chunk_id[:8]}: {e}")
            continue

        points.append({
            "id": block.chunk_id,
            "dense_vector": dense_vec,
            "sparse_vector": {"indices": [], "values": []},
            "payload": {
                "doc_id": block.doc_id,
                "chunk_id": block.chunk_id,
                "chunk_type": block.chunk_type,
                "text": block.text,
                "standard_no": block.standard_no,
                "document_title": document_title,
                "chapter": block.chapter,
                "clause": block.clause,
                "is_table": block.metadata.get("is_table", False),
                "table_title": block.metadata.get("table_title", ""),
                "position": block.position,
            }
        })

    if points:
        vector_store.upsert_points(points)
    print(f"  ✓ Qdrant：{len(points)} 个向量点")
    return len(points)


def write_to_es(blocks: List[ChunkBlock]) -> int:
    """写入 Elasticsearch，返回写入数量"""
    docs = []
    for block in blocks:
        docs.append({
            "chunk_id": block.chunk_id,
            "doc_id": block.doc_id,
            "text": block.text,
            "standard_no": block.standard_no,
            "category": "配电网",
            "chapter": block.chapter,
            "clause": block.clause,
            "chunk_type": block.chunk_type,
            "is_table": block.metadata.get("is_table", False),
            "importance_score": 0.9 if block.chunk_type == "parent" else 0.7,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    if docs:
        search_engine.bulk_index(docs)
    print(f"  ✓ Elasticsearch：{len(docs)} 个文档")
    return len(docs)


# ─── 主流程 ────────────────────────────────────────────────

async def ingest(md_path: str):
    print(f"\n{'='*60}")
    print(f"开始入库：{Path(md_path).name}")
    print(f"{'='*60}")

    # 1. 读取文件
    text = Path(md_path).read_text(encoding='utf-8')
    print(f"\n1. 解析文档...")
    doc_title, standard_no, sections = parse_markdown(text)
    print(f"  标题：{doc_title}")
    print(f"  标准号：{standard_no}")
    print(f"  章节数：{len(sections)}")

    # 2. 分块
    print(f"\n2. 分块...")
    blocks, doc_id = build_all_chunks(doc_title, standard_no, sections)

    parents  = [b for b in blocks if b.chunk_type == "parent" and not b.metadata.get("is_table")]
    children = [b for b in blocks if b.chunk_type == "child"]
    tables   = [b for b in blocks if b.metadata.get("is_table")]

    print(f"  父块：{len(parents)} 个")
    print(f"  子块：{len(children)} 个")
    print(f"  表格块：{len(tables)} 个")
    print(f"  合计：{len(blocks)} 个")

    # 打印表格块预览
    if tables:
        print(f"\n  发现的表格：")
        for t in tables:
            first_line = t.text.split('\n')[0]
            print(f"    - {first_line[:60]}")

    # 打印前几个子块预览
    print(f"\n  前3个子块预览：")
    for b in children[:3]:
        preview = b.text[:80].replace('\n', ' ')
        print(f"    [{b.clause}] {preview}...")

    # 3. 写入 MySQL
    print(f"\n3. 写入 MySQL...")
    write_to_mysql(doc_title, standard_no, doc_id, blocks)

    # 4. 向量化 + 写入 Qdrant
    print(f"\n4. 向量化并写入 Qdrant...")
    t0 = time.time()
    write_to_qdrant(blocks, document_title=doc_title)
    print(f"  耗时：{time.time()-t0:.1f}s")

    # 5. 写入 Elasticsearch
    print(f"\n5. 写入 Elasticsearch...")
    write_to_es(blocks)

    # 6. 验证
    print(f"\n6. 验证...")
    await asyncio.sleep(1)
    qdrant_info = vector_store.get_collection_info()
    es_stats = search_engine.get_index_stats()
    print(f"  Qdrant 点数：{qdrant_info.get('points_count', 0)}")
    print(f"  Elasticsearch 文档数：{es_stats.get('docs_count', 0)}")

    # 7. 抽样检索验证
    print(f"\n7. 抽样检索验证...")

    test_queries = ["配电网供电区域划分", "短路电流限定值", "N-1停运要求"]
    for q in test_queries:
        vec = embedder.encode(q).tolist()
        results = vector_store.hybrid_search(dense_vector=vec, limit=1)
        if results:
            score = results[0]['score']
            text_preview = results[0]['payload'].get('text', '')[:60].replace('\n', ' ')
            print(f"  查询「{q}」→ [{score:.3f}] {text_preview}...")
        else:
            print(f"  查询「{q}」→ 无结果")

    print(f"\n{'='*60}")
    print(f"✅ 入库完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    md_file = r"D:\dl\测试数据\md\GBT+45418-2025.md"
    asyncio.run(ingest(md_file))
