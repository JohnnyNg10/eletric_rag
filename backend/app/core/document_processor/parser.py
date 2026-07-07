"""
PDF 解析器

支持：
- 文字版 PDF：PyMuPDF 提取原生文本
- 扫描版 PDF：PaddleOCR 识别
- 表格提取：pdfplumber
- 公式识别：LaTeX 格式
"""
import fitz  # PyMuPDF
import pdfplumber
from typing import Dict, List, Optional
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)


class PDFParser:
    """PDF 文档解析器"""

    def __init__(self):
        self.ocr_engine = None  # 延迟加载 PaddleOCR

    def parse_pdf(self, pdf_path: str) -> Dict:
        """
        解析 PDF 文档

        Args:
            pdf_path: PDF 文件路径

        Returns:
            解析结果字典:
            {
                "title": "文档标题",
                "content": "Markdown 格式内容",
                "pages": 总页数,
                "metadata": {
                    "standard_no": "GB 1002-2024",
                    "version": "2024版",
                    ...
                }
            }
        """
        try:
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            logger.info(f"Parsing PDF: {pdf_path.name}")

            # 尝试提取文字版 PDF
            doc = fitz.open(str(pdf_path))
            is_text_pdf = self._is_text_pdf(doc)

            if is_text_pdf:
                logger.info("Detected text-based PDF, using PyMuPDF")
                result = self._parse_text_pdf(doc, pdf_path)
            else:
                logger.info("Detected scanned PDF, using OCR")
                result = self._parse_scanned_pdf(doc, pdf_path)

            doc.close()

            return result

        except Exception as e:
            logger.error(f"Failed to parse PDF: {e}")
            raise

    def _is_text_pdf(self, doc: fitz.Document) -> bool:
        """判断是否为文字版 PDF"""
        # 检查前3页，如果有文本则认为是文字版
        for page_num in range(min(3, len(doc))):
            page = doc[page_num]
            text = page.get_text().strip()
            if len(text) > 100:  # 至少100字符
                return True
        return False

    def _parse_text_pdf(self, doc: fitz.Document, pdf_path: Path) -> Dict:
        """解析文字版 PDF"""
        markdown_content = []
        metadata = {}

        # 提取元数据
        title = doc.metadata.get("title", pdf_path.stem)
        metadata = self._extract_metadata_from_filename(pdf_path.name)

        # 逐页提取文本
        for page_num in range(len(doc)):
            page = doc[page_num]

            # 提取文本（使用 text 方法，保留布局）
            text = page.get_text("text")

            if text.strip():
                # 按行分割并过滤
                lines = text.split("\n")
                page_lines = []

                for line in lines:
                    line = line.strip()
                    if line and len(line) > 1:  # 过滤太短的行
                        # 检测标题
                        if self._is_heading(line):
                            level = self._detect_heading_level(line)
                            page_lines.append(f"{'#' * level} {line}")
                        else:
                            page_lines.append(line)

                if page_lines:
                    markdown_content.append("\n".join(page_lines))

        # 提取表格（使用 pdfplumber）
        tables = self._extract_tables(str(pdf_path))

        # 合并内容
        full_content = "\n\n".join(markdown_content)

        # 添加表格
        if tables:
            full_content += "\n\n" + "\n\n".join(tables)

        return {
            "title": title,
            "content": full_content,
            "pages": len(doc),
            "metadata": metadata,
            "is_ocr": False
        }

    def _parse_scanned_pdf(self, doc: fitz.Document, pdf_path: Path) -> Dict:
        """解析扫描版 PDF（使用 OCR）"""
        if self.ocr_engine is None:
            try:
                from paddleocr import PaddleOCR
                self.ocr_engine = PaddleOCR(
                    use_angle_cls=True,
                    lang="ch",
                    show_log=False
                )
            except ImportError:
                logger.warning("PaddleOCR not installed, falling back to basic text extraction")
                return self._parse_text_pdf(doc, pdf_path)

        markdown_content = []
        metadata = self._extract_metadata_from_filename(pdf_path.name)

        # OCR 识别每一页
        for page_num in range(len(doc)):
            page = doc[page_num]

            # 将页面转为图片
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x 放大提高识别率
            img_data = pix.tobytes("png")

            # OCR 识别
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(img_data))
            result = self.ocr_engine.ocr(img, cls=True)

            # 提取文本
            page_text = []
            if result and result[0]:
                for line in result[0]:
                    text = line[1][0]  # 文本内容
                    confidence = line[1][1]  # 置信度
                    if confidence > 0.8:  # 过滤低置信度
                        page_text.append(text)

            markdown_content.append("\n".join(page_text))

        full_content = "\n\n".join(markdown_content)

        return {
            "title": pdf_path.stem,
            "content": full_content,
            "pages": len(doc),
            "metadata": metadata,
            "is_ocr": True
        }

    def _extract_tables(self, pdf_path: str) -> List[str]:
        """提取表格（Markdown 格式）"""
        tables_md = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        if table:
                            md_table = self._table_to_markdown(table)
                            tables_md.append(md_table)
        except Exception as e:
            logger.warning(f"Table extraction failed: {e}")

        return tables_md

    def _table_to_markdown(self, table: List[List[str]]) -> str:
        """将表格转换为 Markdown 格式"""
        if not table:
            return ""

        md_lines = []

        # 表头
        header = table[0]
        md_lines.append("| " + " | ".join(str(cell or "") for cell in header) + " |")
        md_lines.append("| " + " | ".join("---" for _ in header) + " |")

        # 表体
        for row in table[1:]:
            md_lines.append("| " + " | ".join(str(cell or "") for cell in row) + " |")

        return "\n".join(md_lines)

    def _extract_metadata_from_filename(self, filename: str) -> Dict:
        """从文件名提取元数据（如 GB_1002-2024.pdf）"""
        metadata = {}

        # 提取标准号
        standard_pattern = r"(GB|DL|NB)[\s_]+(\d+(?:\.\d+)?)-?(\d{4})"
        match = re.search(standard_pattern, filename, re.IGNORECASE)
        if match:
            prefix = match.group(1).upper()
            number = match.group(2)
            year = match.group(3)
            metadata["standard_no"] = f"{prefix} {number}-{year}"
            metadata["version"] = f"{year}版"
            metadata["publish_date"] = f"{year}-01-01"  # 简化

        return metadata

    def _is_heading(self, text: str) -> bool:
        """判断是否为标题"""
        # 简单规则：以数字编号开头，如 "5.2.1"、"第 5 章"
        patterns = [
            r"^\d+\.\d+",  # 5.2.1
            r"^第\s*\d+\s*章",  # 第 5 章
            r"^第\s*\d+\s*节",  # 第 5 节
        ]
        for pattern in patterns:
            if re.match(pattern, text):
                return True
        return False

    def _detect_heading_level(self, text: str) -> int:
        """检测标题级别"""
        if "章" in text:
            return 1
        elif "节" in text:
            return 2
        elif re.match(r"^\d+\.\d+\.\d+", text):
            return 4
        elif re.match(r"^\d+\.\d+", text):
            return 3
        else:
            return 2


# 全局实例
pdf_parser = PDFParser()
