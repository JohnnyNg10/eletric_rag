"""
PDF 解析器

支持：
- 文字版 PDF：MinerU API 解析（优先）/ VLM 精确识别（保留布局+表格）+ 图片提取单独处理
- 扫描版 PDF：PaddleOCR 识别
- 表格提取：VLM Markdown 输出
- 图片提取：PyMuPDF 嵌入图片 → VLM 描述 → MinIO 存储
"""
import fitz  # PyMuPDF
import pdfplumber
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging
import re
import asyncio
import tempfile
import os

logger = logging.getLogger(__name__)


class PDFParser:
    """PDF 文档解析器"""

    def __init__(self):
        self.ocr_engine = None  # 延迟加载 PaddleOCR
        self.vlm_client = None  # 延迟加载 VLM client
        self.mineru_client = None  # 延迟加载 MinerU client
        self._mineru_available = None  # MinerU 服务可用性缓存

    def parse_pdf(self, pdf_path: str, use_vlm: bool = False, use_mineru: bool = True) -> Dict:
        """
        解析 PDF 文档

        Args:
            pdf_path: PDF 文件路径
            use_mineru: 使用 MinerU 解析文字版 PDF（默认 True，优先级高于 use_vlm）
            use_vlm: 使用 VLM 解析文字版 PDF（use_mineru=False 时生效）

        Returns:
            解析结果字典:
            {
                "title": "文档标题",
                "content": "Markdown 格式内容",
                "pages": 总页数,
                "images": [{"page": 1, "index": 0, "bytes": b"...", "ext": "png", "description": "..."}],
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
                if use_mineru:
                    logger.info("Detected text-based PDF, using MinerU for extraction")
                    page_count = len(doc)
                    doc.close()
                    return self._parse_text_pdf_with_mineru(pdf_path, page_count)
                elif use_vlm:
                    logger.info("Detected text-based PDF, using VLM for precise extraction")
                    result = asyncio.run(self._parse_text_pdf_with_vlm(doc, pdf_path))
                else:
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

    async def _parse_text_pdf_with_vlm(self, doc: fitz.Document, pdf_path: Path) -> Dict:
        """
        使用 VLM 精确解析文字版 PDF

        流程：
        1. 逐页转图送 VLM 识别（获取完整 Markdown 内容，包含表格）
        2. 单独提取页面嵌入图片 → VLM 描述 → 保存图片字节
        3. 返回 Markdown 内容 + 图片列表（供后续 ingestion_pipeline 处理）
        """
        # 延迟加载 VLM client
        if self.vlm_client is None:
            from app.core.vlm.vlm_client import vlm_client
            from app.config import settings
            if not settings.ENABLE_VLM_DESCRIPTION:
                logger.warning("VLM 未启用，回退到 PyMuPDF 解析")
                return self._parse_text_pdf(doc, pdf_path)
            self.vlm_client = vlm_client

        metadata = self._extract_metadata_from_filename(pdf_path.name)
        title = doc.metadata.get("title", pdf_path.stem)

        logger.info(f"VLM 解析开始: {len(doc)} 页")

        # 并行处理所有页面
        tasks = []
        for page_num in range(len(doc)):
            tasks.append(self._process_page_with_vlm(doc, page_num))

        page_results = await asyncio.gather(*tasks)

        # 合并 Markdown 内容
        markdown_parts = []
        all_images = []

        for page_result in page_results:
            page_num = page_result['page_num']
            markdown_parts.append(f"\n\n---\n## 第 {page_num + 1} 页\n\n")
            markdown_parts.append(page_result['content'])
            all_images.extend(page_result['images'])

        full_content = ''.join(markdown_parts)

        logger.info(f"VLM 解析完成: {len(doc)} 页, {len(all_images)} 图片")

        return {
            "title": title,
            "content": full_content,
            "pages": len(doc),
            "images": all_images,
            "metadata": metadata,
            "is_ocr": False,
            "parsed_by": "vlm"
        }

    async def _process_page_with_vlm(self, doc: fitz.Document, page_num: int) -> Dict:
        """
        VLM 处理单页

        Returns:
            {
                'page_num': 1,
                'content': 'VLM 识别的 Markdown 内容',
                'images': [{'page': 1, 'index': 0, 'bytes': b'...', 'ext': 'png', 'description': '...'}]
            }
        """
        page = doc[page_num]

        # 1. 提取页面嵌入的图片
        page_images = []
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                img_ext = base_image["ext"]

                # 保存临时文件用于 VLM 识别
                with tempfile.NamedTemporaryFile(suffix=f".{img_ext}", delete=False) as tmp:
                    tmp.write(img_bytes)
                    tmp_path = tmp.name

                # VLM 生成图片描述
                img_prompt = """请描述这张图片的技术内容。

要求：
1. 如果是工程图、示意图、流程图，描述其结构和关键元素
2. 如果是照片，描述场景和重点对象
3. 保持简洁专业，100字以内

直接输出描述，无需前缀。"""

                vlm_result = await self.vlm_client.generate_description(tmp_path, img_prompt)
                description = (vlm_result.get('description') or '') if vlm_result else ''

                # 清理临时文件
                os.unlink(tmp_path)

                page_images.append({
                    'page': page_num + 1,
                    'index': img_index,
                    'bytes': img_bytes,
                    'ext': img_ext,
                    'description': description,
                    'vlm_model': vlm_result.get('model', '') if vlm_result else '',
                    'vlm_confidence': vlm_result.get('confidence', 0.0) if vlm_result else 0.0
                })

                logger.info(f"页 {page_num + 1} 图片 {img_index} 提取完成")

            except Exception as e:
                logger.warning(f"页 {page_num + 1} 图片 {img_index} 提取失败: {e}")

        # 2. 整页转图送 VLM 识别获取 Markdown 内容
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 300 DPI
        page_img_bytes = pix.tobytes("png")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(page_img_bytes)
            tmp_path = tmp.name

        page_prompt = f"""识别这一页的全部内容，输出为 Markdown 格式。

要求：
1. 保留章节标题、条款编号（如 3.2.1）
2. 表格转为 Markdown 表格格式
3. 图片位置标记为 [图片占位符]，不要尝试描述图片内容
4. 保持原文排版顺序（双栏从左到右）
5. 公式尽量还原为文本或 LaTeX

直接输出 Markdown，无需额外说明。这是第 {page_num + 1} 页。"""

        vlm_result = await self.vlm_client.generate_description(tmp_path, page_prompt)
        page_content = (vlm_result.get('description') or '') if vlm_result else ''

        os.unlink(tmp_path)

        logger.info(f"页 {page_num + 1} 内容识别完成，长度 {len(page_content)} 字符")

        return {
            'page_num': page_num,
            'content': page_content,
            'images': page_images
        }

    def _check_mineru_availability(self) -> bool:
        """检查 MinerU 服务可用性（带缓存）"""
        from app.config import settings

        if not settings.MINERU_ENABLED:
            logger.info("MinerU 已在配置中禁用")
            return False

        # 使用缓存结果（避免每次调用都健康检查）
        if self._mineru_available is not None:
            return self._mineru_available

        # 延迟加载 MinerU 客户端
        if self.mineru_client is None:
            from app.core.document_processor.mineru_client import mineru_client
            self.mineru_client = mineru_client

        # 健康检查
        self._mineru_available = self.mineru_client.health_check()
        return self._mineru_available

    def _parse_text_pdf_with_mineru(self, pdf_path: Path, page_count: int) -> Dict:
        """使用 MinerU API 解析文字版 PDF（HTTP 调用同机部署的服务）"""
        from app.config import settings

        # 检查服务可用性
        if not self._check_mineru_availability():
            logger.warning("MinerU 服务不可用，回退到 PyMuPDF 解析")
            import fitz as _fitz
            _doc = _fitz.open(str(pdf_path))
            result = self._parse_text_pdf(_doc, pdf_path)
            _doc.close()
            return result

        logger.info(f"MinerU API 解析开始: {pdf_path.name} (backend={settings.MINERU_BACKEND})")

        try:
            # 始终使用异步模式，避免同步超时导致回退到 PyMuPDF 产生乱码
            # 异步模式无客户端超时限制，只需等待 MinerU 处理完成
            result = self.mineru_client.parse_with_retry(
                str(pdf_path),
                mode="async",
                backend=settings.MINERU_BACKEND,
                poll_interval=settings.MINERU_ASYNC_POLL_INTERVAL,
                max_poll_time=settings.MINERU_ASYNC_MAX_POLL_TIME,
                max_retries=2,
                return_content_list=True,
            )

            md_content = result["md_content"]
            content_list = result.get("content_list", [])

            logger.info(f"MinerU 返回类型检查: md_content类型={type(md_content).__name__}, content_list类型={type(content_list).__name__}, content_list长度={len(content_list) if isinstance(content_list, (list, str)) else 'N/A'}")

            # 从 Markdown 文件中提取图片引用（MinerU 的 content_list 可能不包含图片二进制数据）
            images = self._extract_images_from_markdown(md_content, pdf_path)

            # 如果提取失败，尝试从 content_list 提取（兼容旧版）
            if not images:
                images = self._extract_images_from_content_list(content_list, pdf_path)

            # pipeline 模式下 MinerU 不做 VLM 分析，调用 VLM API 补充图片语义描述
            if images and settings.ENABLE_VLM_DESCRIPTION:
                logger.info(f"MinerU pipeline 模式：调用 VLM API 为 {len(images)} 张图片生成语义描述")
                images = asyncio.run(self._enrich_images_with_vlm(images))

            logger.info(
                f"MinerU API 解析完成: {pdf_path.name}, "
                f"内容长度={len(md_content)} 字符, "
                f"提取图片={len(images)} 张"
            )

            return {
                "title": pdf_path.stem,
                "content": md_content,
                "pages": page_count,
                "images": images,
                "metadata": self._extract_metadata_from_filename(pdf_path.name),
                "is_ocr": False,
                "parsed_by": "mineru_api",
            }

        except Exception as e:
            logger.error(f"MinerU API 解析失败: {e}，回退到 PyMuPDF")
            # 回退到 PyMuPDF
            import fitz as _fitz
            _doc = _fitz.open(str(pdf_path))
            result = self._parse_text_pdf(_doc, pdf_path)
            _doc.close()
            return result

    def _extract_images_from_content_list(self, content_list: list, pdf_path: Path) -> list:
        """
        从 MinerU 的 content_list 中提取图片信息

        Args:
            content_list: MinerU 返回的结构化内容列表
            pdf_path: PDF 文件路径

        Returns:
            图片列表 [{"page": 1, "index": 0, "bytes": b"...", "ext": "png", "description": "..."}]
        """
        images = []

        if not content_list:
            return images

        # 如果 content_list 是 JSON 字符串，先解析
        if isinstance(content_list, str):
            try:
                import json
                content_list = json.loads(content_list)
            except Exception as e:
                logger.warning(f"content_list JSON 解析失败: {e}")
                return images

        # MinerU 的 content_list 结构：
        # [{"type": "image", "img_path": "images/xxx.jpg", "content": "AI描述", ...}, ...]
        for idx, item in enumerate(content_list):
            # 跳过非字典类型的元素
            if not isinstance(item, dict):
                continue
            if item.get("type") != "image":
                continue

            try:
                img_path_str = item.get("img_path", "")
                if not img_path_str:
                    continue

                # MinerU 生成的图片通常在 PDF 所在目录的输出子目录中
                # 实际路径需要根据 MinerU 的输出配置确定
                # 这里简化处理：如果是相对路径，从 PDF 目录查找
                img_path = Path(img_path_str)
                if not img_path.is_absolute():
                    # 尝试从 PDF 同目录下的可能输出目录查找
                    possible_dirs = [
                        pdf_path.parent / "output" / "images",
                        pdf_path.parent / "images",
                        pdf_path.parent,
                    ]
                    for base_dir in possible_dirs:
                        full_path = base_dir / img_path.name
                        if full_path.exists():
                            img_path = full_path
                            break

                if not img_path.exists():
                    logger.warning(f"图片文件不存在: {img_path}")
                    continue

                # 读取图片字节
                with open(img_path, "rb") as f:
                    img_bytes = f.read()

                ext = img_path.suffix.lstrip(".")
                description = item.get("content", "")  # MinerU VLM 生成的描述

                images.append({
                    "page": item.get("page_number", 0),  # MinerU 可能提供页码
                    "index": idx,
                    "bytes": img_bytes,
                    "ext": ext or "png",
                    "description": description,
                    "vlm_model": "mineru",
                    "vlm_confidence": 1.0 if description else 0.0,
                    "_source_path": str(img_path),  # 供后续 VLM 增强直接读文件，处理完后去除
                })

                logger.debug(f"提取图片: {img_path.name}, 描述长度={len(description)}")

            except Exception as e:
                logger.warning(f"提取图片失败 (index={idx}): {e}")

        return images

    def _extract_images_from_markdown(self, md_content: str, pdf_path: Path) -> list:
        """
        从 Markdown 内容中提取图片引用，并尝试读取图片文件

        Args:
            md_content: Markdown 文本内容
            pdf_path: PDF 文件路径

        Returns:
            图片列表 [{"page": 0, "index": 0, "bytes": b"...", "ext": "png", ...}]
        """
        import re
        images = []

        # 匹配 Markdown 图片语法: ![可选描述](图片路径)
        # 示例: ![](images/e9c5752034733b41f26df35d0f1e66fdc7e53c718e53c67b651fa6e7861c4be8.jpg)
        img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
        matches = img_pattern.findall(md_content)

        if not matches:
            logger.debug("Markdown 中未找到图片引用")
            return images

        logger.info(f"从 Markdown 中找到 {len(matches)} 个图片引用")

        # MinerU 服务的输出目录（包含任务ID子目录）
        mineru_output = Path("D:/dl/MinerU/output")

        # 可能的图片搜索目录
        search_dirs = [
            pdf_path.parent / "images",  # 与PDF同级
            pdf_path.parent / "output" / "images",
            pdf_path.parent,
            Path("debug_markdown") / "images",  # 调试目录
            Path.cwd() / "images",
        ]

        for idx, (caption, img_rel_path) in enumerate(matches):
            try:
                img_path = Path(img_rel_path)
                img_filename = img_path.name

                found_path = None

                # 优先在 MinerU output 中递归搜索（因为包含任务ID子目录）
                if mineru_output.exists():
                    for img_file in mineru_output.rglob(img_filename):
                        if img_file.is_file():
                            found_path = img_file
                            logger.debug(f"在 MinerU output 中找到图片: {img_file}")
                            break

                # 如果没找到，尝试在其他目录中查找
                if not found_path:
                    for search_dir in search_dirs:
                        candidate = search_dir / img_filename
                        if candidate.exists():
                            found_path = candidate
                            logger.debug(f"找到图片: {candidate}")
                            break

                if not found_path:
                    logger.warning(f"图片文件不存在: {img_filename} (搜索了 {len(search_dirs)} 个目录)")
                    continue

                # 读取图片字节
                with open(found_path, "rb") as f:
                    img_bytes = f.read()

                ext = found_path.suffix.lstrip(".") or "jpg"

                images.append({
                    "page": 0,  # 页码从 Markdown 不易提取，后续可优化
                    "index": idx,
                    "bytes": img_bytes,
                    "ext": ext,
                    "description": "",  # Markdown 模式下无 VLM 描述，需后续补充
                    "caption": caption,  # 图注
                    "vlm_model": None,
                    "vlm_confidence": 0.0,
                    "_source_path": str(found_path),
                })

                logger.debug(f"成功提取图片 [{idx}]: {found_path.name}, 大小={len(img_bytes)} bytes")

            except Exception as e:
                logger.warning(f"提取图片失败 [{idx}]: {e}")

        logger.info(f"成功提取 {len(images)} 张图片")
        return images

    def _extract_images_from_content_list(self, content_list: list, pdf_path: Path) -> list:
        """
        从 MinerU 的 content_list 中提取图片信息

        Args:
            content_list: MinerU 返回的结构化内容列表
            pdf_path: PDF 文件路径

        Returns:
            图片列表 [{"page": 1, "index": 0, "bytes": b"...", "ext": "png", "description": "..."}]
        """
        images = []

        if not content_list:
            return images

        # 如果 content_list 是 JSON 字符串，先解析
        if isinstance(content_list, str):
            try:
                import json
                content_list = json.loads(content_list)
            except Exception as e:
                logger.warning(f"content_list JSON 解析失败: {e}")
                return images

        # MinerU 的 content_list 结构：
        # [{"type": "image", "img_path": "images/xxx.jpg", "content": "AI描述", ...}, ...]
        for idx, item in enumerate(content_list):
            # 跳过非字典类型的元素
            if not isinstance(item, dict):
                continue
            if item.get("type") != "image":
                continue

            try:
                img_path_str = item.get("img_path", "")
                if not img_path_str:
                    continue

                # MinerU 生成的图片通常在 PDF 所在目录的输出子目录中
                # 实际路径需要根据 MinerU 的输出配置确定
                # 这里简化处理：如果是相对路径，从 PDF 目录查找
                img_path = Path(img_path_str)
                if not img_path.is_absolute():
                    # 尝试从 PDF 同目录下的可能输出目录查找
                    possible_dirs = [
                        pdf_path.parent / "output" / "images",
                        pdf_path.parent / "images",
                        pdf_path.parent,
                    ]
                    for base_dir in possible_dirs:
                        full_path = base_dir / img_path.name
                        if full_path.exists():
                            img_path = full_path
                            break

                if not img_path.exists():
                    logger.warning(f"图片文件不存在: {img_path}")
                    continue

                # 读取图片字节
                with open(img_path, "rb") as f:
                    img_bytes = f.read()

                ext = img_path.suffix.lstrip(".")
                description = item.get("content", "")  # MinerU VLM 生成的描述

                images.append({
                    "page": item.get("page_number", 0),  # MinerU 可能提供页码
                    "index": idx,
                    "bytes": img_bytes,
                    "ext": ext or "png",
                    "description": description,
                    "vlm_model": "mineru",
                    "vlm_confidence": 1.0 if description else 0.0,
                    "_source_path": str(img_path),  # 供后续 VLM 增强直接读文件，处理完后去除
                })

                logger.debug(f"提取图片: {img_path.name}, 描述长度={len(description)}")

            except Exception as e:
                logger.warning(f"提取图片失败 (index={idx}): {e}")

        return images

    async def _enrich_images_with_vlm(self, images: list) -> list:
        """对 MinerU 提取的图片并行调用 VLM API，补充语义描述"""
        if self.vlm_client is None:
            from app.core.vlm.vlm_client import vlm_client as _vlm
            self.vlm_client = _vlm

        prompt = """请描述这张工程图片的技术内容。
要求：
1. 如果是结构图/示意图/流程图，描述其组成和关键元素
2. 如果是照片，描述场景和重点对象
3. 保持简洁专业，100字以内
直接输出描述，无需前缀。"""

        async def _enrich_one(img: dict) -> dict:
            source_path = img.pop("_source_path", None)
            tmp_path = None
            try:
                if source_path and Path(source_path).exists():
                    call_path = source_path
                else:
                    # 没有原始文件路径，写临时文件
                    ext = img.get("ext", "png")
                    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                        tmp.write(img["bytes"])
                        tmp_path = call_path = tmp.name

                vlm_result = await self.vlm_client.generate_description(call_path, prompt)
                if vlm_result and vlm_result.get("description"):
                    img["description"] = vlm_result["description"]
                    img["vlm_model"] = vlm_result.get("model", "vlm_api")
                    img["vlm_confidence"] = vlm_result.get("confidence", 0.0)
                    logger.debug(f"VLM 描述生成成功: 页{img['page']} 图{img['index']}")
                else:
                    logger.warning(f"VLM 描述生成失败: 页{img['page']} 图{img['index']} — {vlm_result.get('error')}")
            except Exception as e:
                logger.warning(f"VLM 增强异常: 页{img.get('page')} 图{img.get('index')}: {e}")
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            return img

        return list(await asyncio.gather(*[_enrich_one(img) for img in images]))

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
