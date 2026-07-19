"""
MinerU FastAPI 包装服务
为 electric-rag 项目提供 PDF 解析 API
"""
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="MinerU API", version="1.0.0")


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "mineru"}


@app.post("/parse/pdf")
async def parse_pdf(
    file: UploadFile = File(...),
    mode: str = "auto",  # auto, ocr, txt
    output_format: str = "markdown"  # markdown, json
):
    """
    解析 PDF 文件

    Args:
        file: PDF 文件
        mode: 解析模式 (auto/ocr/txt)
        output_format: 输出格式 (markdown/json)

    Returns:
        解析结果
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        pdf_path = temp_path / file.filename

        # 保存上传的文件
        content = await file.read()
        with open(pdf_path, 'wb') as f:
            f.write(content)

        try:
            # 调用 MinerU 进行解析
            # TODO: 根据实际 MinerU API 调整
            from magic_pdf.pipe.UNIPipe import UNIPipe
            from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

            # 初始化
            reader_writer = DiskReaderWriter(str(temp_path))
            pipe = UNIPipe(str(pdf_path), reader_writer)

            # 执行解析
            pipe.pipe_classify()

            if mode == "ocr" or (mode == "auto" and pipe.classify_result == "ocr"):
                pipe.pipe_ocr()

            pipe.pipe_parse()

            # 获取结果
            result = pipe.pipe_mk_markdown()

            return JSONResponse({
                "success": True,
                "filename": file.filename,
                "mode": mode,
                "content": result,
                "page_count": pipe.pdf_docs[0].page_count if pipe.pdf_docs else 0
            })

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse PDF: {str(e)}"
            )


@app.post("/parse/image")
async def parse_image(
    file: UploadFile = File(...),
):
    """
    解析图片文件 (OCR)

    Args:
        file: 图片文件

    Returns:
        OCR 识别结果
    """
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {allowed_extensions}"
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        image_path = temp_path / file.filename

        content = await file.read()
        with open(image_path, 'wb') as f:
            f.write(content)

        try:
            # TODO: 实现图片 OCR
            # 这里需要根据你的 MinerU 版本调整
            from magic_pdf.libs.ocr_content_type import ocr

            result = ocr(str(image_path))

            return JSONResponse({
                "success": True,
                "filename": file.filename,
                "text": result
            })

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse image: {str(e)}"
            )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
