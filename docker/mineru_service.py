"""
MinerU FastAPI 服务封装
提供与 MinerU 官方 API 兼容的接口
"""
import os
import uuid
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="MinerU API Service", version="0.7.0")

# 全局任务存储（生产环境应使用 Redis）
tasks_store = {}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "0.7.0",
        "backend_available": ["pipeline", "hybrid-engine"]
    }


@app.post("/file_parse")
async def file_parse_sync(
    files: List[UploadFile] = File(...),
    backend: str = Form("pipeline"),
    return_md: str = Form("true"),
    formula_enable: str = Form("true"),
    table_enable: str = Form("true"),
):
    """
    同步解析接口
    """
    task_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat() + "+00:00"

    try:
        from magic_pdf.pipe.UNIPipe import UNIPipe
        from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter
        import json

        results = {}
        file_names = []

        for file in files:
            # 创建临时目录
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_dir = Path(tmp_dir)

                # 保存上传的文件
                pdf_path = tmp_dir / file.filename
                with open(pdf_path, "wb") as f:
                    content = await file.read()
                    f.write(content)

                # 初始化 MinerU
                pdf_bytes = open(pdf_path, "rb").read()

                # 使用 UNIPipe 解析
                pipe = UNIPipe(pdf_bytes, {
                    "parse_method": backend,
                })
                pipe.pipe_classify()
                pipe.pipe_parse()

                # 获取 Markdown 内容
                md_content = pipe.pipe_mk_markdown(
                    tmp_dir / "output",
                    drop_mode="none",
                )

                # 文件名（不含扩展名）
                file_name = Path(file.filename).stem
                file_names.append(file_name)

                results[file_name] = {
                    "md_content": md_content
                }

        completed_at = datetime.utcnow().isoformat() + "+00:00"

        return JSONResponse({
            "task_id": task_id,
            "status": "completed",
            "backend": backend,
            "file_names": file_names,
            "created_at": created_at,
            "started_at": created_at,
            "completed_at": completed_at,
            "results": results
        })

    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/tasks")
async def submit_task(
    files: List[UploadFile] = File(...),
    backend: str = Form("pipeline"),
    return_md: str = Form("true"),
):
    """
    异步任务提交接口
    """
    task_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat() + "+00:00"

    # 保存任务信息
    tasks_store[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "backend": backend,
        "file_names": [Path(f.filename).stem for f in files],
        "created_at": created_at,
    }

    # 实际应该放到后台队列处理，这里简化为立即处理
    try:
        result = await file_parse_sync(files, backend, return_md)
        result_data = result.body.decode()
        import json
        parsed = json.loads(result_data)

        tasks_store[task_id].update({
            "status": "completed",
            "completed_at": parsed["completed_at"],
            "results": parsed["results"]
        })
    except Exception as e:
        tasks_store[task_id].update({
            "status": "failed",
            "error": str(e)
        })

    return JSONResponse({
        "task_id": task_id,
        "status": "pending",
        "backend": backend,
        "file_names": tasks_store[task_id]["file_names"],
        "created_at": created_at,
        "status_url": f"http://localhost:8001/tasks/{task_id}",
        "result_url": f"http://localhost:8001/tasks/{task_id}/result",
        "message": "Task submitted successfully"
    }, status_code=202)


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """查询任务状态"""
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks_store[task_id]
    return JSONResponse({
        "task_id": task_id,
        "status": task["status"],
        "backend": task["backend"],
        "file_names": task["file_names"],
        "created_at": task["created_at"],
        "error": task.get("error")
    })


@app.get("/tasks/{task_id}/result")
async def get_task_result(task_id: str):
    """获取任务结果"""
    if task_id not in tasks_store:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks_store[task_id]

    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task not completed yet")

    return JSONResponse({
        "task_id": task_id,
        "status": "completed",
        "file_names": task["file_names"],
        "results": task["results"]
    })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
