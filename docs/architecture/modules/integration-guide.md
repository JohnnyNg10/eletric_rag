# MinerU 主业务项目对接指南

本文档面向需要在主业务项目中集成 MinerU 文档解析服务的开发者。

---

## 快速开始

### 前置条件

- MinerU API 已部署并运行在 `http://127.0.0.1:8001`
- 主业务项目与 MinerU 部署在同一台服务器
- Python 3.10+（示例代码基于 Python，其他语言类似）

### 5 分钟集成示例

```python
import requests

# 同步解析 PDF
def parse_pdf(file_path):
    with open(file_path, "rb") as f:
        resp = requests.post(
            "http://127.0.0.1:8001/file_parse",
            files={"files": f},
            data={
                "backend": "pipeline",      # 纯 CPU 后端
                "return_md": "true",        # 返回 Markdown
            },
            timeout=120,
        )
    
    if resp.status_code == 200:
        result = resp.json()
        # 获取文件名（不含扩展名）
        file_name = result["file_names"][0]
        # 提取 Markdown 内容
        md_content = result["results"][file_name]["md_content"]
        return md_content
    else:
        raise Exception(f"解析失败: {resp.text}")

# 使用示例
markdown = parse_pdf("document.pdf")
print(markdown)
```

---

## 接口选择

MinerU 提供两种调用模式：

| 模式 | 接口 | 适用场景 | 超时设置 |
|------|------|----------|---------|
| **同步** | `POST /file_parse` | 小文件（<10MB）、实时处理 | 建议 60-120 秒 |
| **异步** | `POST /tasks` + 轮询 | 大文件、批量处理、后台任务 | 无需设置 |

---

## 同步模式详解

### 基本调用

```python
import requests

MINERU_API = "http://127.0.0.1:8001"

def sync_parse(file_path, backend="pipeline"):
    """
    同步解析文件，等待完成后返回结果
    
    Args:
        file_path: 文件路径
        backend: 解析后端，pipeline（纯CPU）或 hybrid-engine（需GPU）
    
    Returns:
        dict: {"file_name": "内容的Markdown字符串", ...}
    """
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{MINERU_API}/file_parse",
            files={"files": f},
            data={
                "backend": backend,
                "return_md": "true",
            },
            timeout=120,
        )
    
    resp.raise_for_status()
    result = resp.json()
    
    # 构造返回格式：{文件名: Markdown内容}
    outputs = {}
    for file_name in result["file_names"]:
        outputs[file_name] = result["results"][file_name]["md_content"]
    
    return outputs
```

### 多文件批量解析

```python
def batch_sync_parse(file_paths):
    """批量同步解析多个文件"""
    files = [("files", open(path, "rb")) for path in file_paths]
    
    try:
        resp = requests.post(
            f"{MINERU_API}/file_parse",
            files=files,
            data={"backend": "pipeline", "return_md": "true"},
            timeout=300,
        )
        resp.raise_for_status()
        result = resp.json()
        
        # 返回 {文件名: Markdown内容} 字典
        outputs = {}
        for file_name in result["file_names"]:
            outputs[file_name] = result["results"][file_name]["md_content"]
        return outputs
    finally:
        # 关闭文件句柄
        for _, file_obj in files:
            file_obj.close()
```

---

## 异步模式详解

### 提交任务并轮询

```python
import time

def async_parse(file_path, backend="pipeline", poll_interval=3):
    """
    异步解析文件，轮询直到完成
    
    Args:
        file_path: 文件路径
        backend: 解析后端
        poll_interval: 轮询间隔（秒）
    
    Returns:
        dict: {"file_name": "Markdown内容"}
    """
    # 1. 提交任务
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{MINERU_API}/tasks",
            files={"files": f},
            data={"backend": backend, "return_md": "true"},
        )
    
    resp.raise_for_status()
    task_info = resp.json()
    task_id = task_info["task_id"]
    
    print(f"任务已提交，ID: {task_id}")
    
    # 2. 轮询状态
    while True:
        status_resp = requests.get(f"{MINERU_API}/tasks/{task_id}")
        status_resp.raise_for_status()
        status_data = status_resp.json()
        
        status = status_data["status"]
        print(f"任务状态: {status}")
        
        if status == "completed":
            break
        elif status == "failed":
            raise Exception(f"任务失败: {status_data.get('error')}")
        
        time.sleep(poll_interval)
    
    # 3. 获取结果
    result_resp = requests.get(f"{MINERU_API}/tasks/{task_id}/result")
    result_resp.raise_for_status()
    result = result_resp.json()
    
    # 返回结果
    outputs = {}
    for file_name in result["file_names"]:
        outputs[file_name] = result["results"][file_name]["md_content"]
    
    return outputs
```

### 异步批量处理

```python
def async_batch_parse(file_paths, max_concurrent=5):
    """
    异步批量提交多个任务，并发轮询
    
    Args:
        file_paths: 文件路径列表
        max_concurrent: 最大并发任务数
    
    Returns:
        dict: {文件路径: Markdown内容}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    results = {}
    
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        # 提交所有任务
        future_to_path = {
            executor.submit(async_parse, path): path 
            for path in file_paths
        }
        
        # 收集结果
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                result = future.result()
                results[path] = result
            except Exception as e:
                print(f"解析失败 {path}: {e}")
                results[path] = None
    
    return results
```

---

## 参数配置

### 核心参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `backend` | string | `hybrid-engine` | `pipeline`（纯CPU）/ `hybrid-engine`（需GPU） |
| `return_md` | bool | `true` | 是否返回 Markdown 格式内容 |
| `return_content_list` | bool | `false` | 是否返回结构化 JSON（含类型、位置等） |
| `return_images` | bool | `false` | 是否返回提取的图片（base64 编码） |

### 解析选项

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `effort` | string | `medium` | 仅 hybrid 后端：`medium`（快）/ `high`（精度高） |
| `formula_enable` | bool | `true` | 启用公式解析（LaTeX 格式） |
| `table_enable` | bool | `true` | 启用表格解析（HTML 格式） |
| `image_analysis` | bool | `true` | 启用图片内容分析（需 `effort=high`） |
| `start_page_id` | int | `0` | PDF 起始页（从 0 开始） |
| `end_page_id` | int | `99999` | PDF 结束页 |

### 推荐配置

```python
# 场景 1：快速提取文字（无 GPU）
data = {
    "backend": "pipeline",
    "return_md": "true",
    "formula_enable": "true",
    "table_enable": "true",
}

# 场景 2：高精度解析（有 GPU）
data = {
    "backend": "hybrid-engine",
    "effort": "high",
    "return_md": "true",
    "image_analysis": "true",  # 提取图片描述
    "return_content_list": "true",  # 获取结构化数据
}

# 场景 3：仅解析前 10 页
data = {
    "backend": "pipeline",
    "start_page_id": "0",
    "end_page_id": "9",
    "return_md": "true",
}
```

---

## 响应格式

### 同步响应（`/file_parse`）

```json
{
  "task_id": "abc123",
  "status": "completed",
  "backend": "pipeline",
  "file_names": ["document"],
  "created_at": "2026-07-18T10:00:00+00:00",
  "started_at": "2026-07-18T10:00:01+00:00",
  "completed_at": "2026-07-18T10:01:30+00:00",
  "results": {
    "document": {
      "md_content": "# 标题\n\n正文内容..."
    }
  }
}
```

### 异步提交响应（`/tasks`）

```json
{
  "task_id": "abc123",
  "status": "pending",
  "backend": "pipeline",
  "file_names": ["document"],
  "created_at": "2026-07-18T10:00:00+00:00",
  "status_url": "http://127.0.0.1:8001/tasks/abc123",
  "result_url": "http://127.0.0.1:8001/tasks/abc123/result",
  "message": "Task submitted successfully"
}
```

### 关键字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 任务唯一标识 |
| `status` | string | `pending` / `processing` / `completed` / `failed` |
| `file_names` | array | 文件名列表（不含扩展名） |
| `results[文件名].md_content` | string | Markdown 格式内容 |
| `results[文件名].content_list` | array | 结构化内容块（需开启 `return_content_list`） |

---

## 获取图片和结构化数据

### 提取图片描述

当需要 AI 生成的图片内容描述时：

```python
resp = requests.post(
    f"{MINERU_API}/file_parse",
    files={"files": open("document.pdf", "rb")},
    data={
        "backend": "hybrid-engine",
        "effort": "high",  # 必须是 high
        "image_analysis": "true",
        "return_content_list": "true",  # 必须开启
    },
    timeout=180,
)

result = resp.json()
content_list = result["results"]["document"]["content_list"]

# 提取图片块
for item in content_list:
    if item["type"] == "image":
        print(f"图片路径: {item['img_path']}")
        print(f"AI 描述: {item['content']}")  # VLM 生成的描述
```

### content_list 数据结构

```json
[
  {
    "type": "text",
    "text": "段落内容"
  },
  {
    "type": "image",
    "img_path": "images/xxx.jpg",
    "content": "VLM 生成的图片描述文字",
    "image_caption": ["图1 示意图"],
    "image_footnote": []
  },
  {
    "type": "table",
    "text": "<table>...</table>"
  }
]
```

---

## 错误处理

### 常见错误码

| HTTP 状态码 | 说明 | 处理方式 |
|------------|------|----------|
| `200` | 成功 | - |
| `202` | 任务已提交（异步） | 轮询状态 |
| `400` | 参数错误 | 检查请求参数 |
| `409` | 任务失败 | 查看 `error` 字段 |
| `422` | 验证错误 | 检查文件格式 |
| `500` | 服务内部错误 | 重试或联系管理员 |

### 错误处理示例

```python
def safe_parse(file_path, max_retries=3):
    """带重试的安全解析"""
    for attempt in range(max_retries):
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"{MINERU_API}/file_parse",
                    files={"files": f},
                    data={"backend": "pipeline", "return_md": "true"},
                    timeout=120,
                )
            
            if resp.status_code == 200:
                result = resp.json()
                file_name = result["file_names"][0]
                return result["results"][file_name]["md_content"]
            
            elif resp.status_code == 500 and attempt < max_retries - 1:
                # 服务器错误，重试
                print(f"服务器错误，重试 {attempt + 1}/{max_retries}")
                time.sleep(2 ** attempt)  # 指数退避
                continue
            
            else:
                # 其他错误，不重试
                error_msg = resp.json().get("detail", resp.text)
                raise Exception(f"解析失败 ({resp.status_code}): {error_msg}")
        
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                print(f"超时，重试 {attempt + 1}/{max_retries}")
                continue
            raise Exception("解析超时")
        
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"错误: {e}，重试 {attempt + 1}/{max_retries}")
            time.sleep(1)
    
    raise Exception("达到最大重试次数")
```

---

## 生产环境最佳实践

### 1. 超时配置

```python
# 根据文件大小动态设置超时
def get_timeout(file_size_mb):
    """根据文件大小估算超时时间（秒）"""
    if file_size_mb < 5:
        return 60
    elif file_size_mb < 20:
        return 120
    else:
        return 300

import os
file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
timeout = get_timeout(file_size_mb)
```

### 2. 连接池复用

```python
# 使用 Session 复用连接
session = requests.Session()
session.mount('http://', requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=20,
    max_retries=3,
))

# 所有请求使用同一个 session
resp = session.post(f"{MINERU_API}/file_parse", ...)
```

### 3. 异步队列集成

以 Celery 为例：

```python
from celery import Celery

app = Celery('tasks', broker='redis://localhost:6379/0')

@app.task(bind=True, max_retries=3)
def parse_document_task(self, file_path):
    """Celery 任务：解析文档"""
    try:
        # 提交异步任务
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{MINERU_API}/tasks",
                files={"files": f},
                data={"backend": "pipeline", "return_md": "true"},
            )
        
        resp.raise_for_status()
        task_info = resp.json()
        task_id = task_info["task_id"]
        
        # 轮询结果
        while True:
            status_resp = requests.get(f"{MINERU_API}/tasks/{task_id}")
            status = status_resp.json()["status"]
            
            if status == "completed":
                result_resp = requests.get(f"{MINERU_API}/tasks/{task_id}/result")
                result = result_resp.json()
                file_name = result["file_names"][0]
                return result["results"][file_name]["md_content"]
            
            elif status == "failed":
                raise Exception("MinerU 解析失败")
            
            time.sleep(3)
    
    except Exception as exc:
        # Celery 重试
        raise self.retry(exc=exc, countdown=60)

# 调用
result = parse_document_task.delay("/path/to/file.pdf")
```

### 4. 日志记录

```python
import logging

logger = logging.getLogger(__name__)

def parse_with_logging(file_path):
    logger.info(f"开始解析: {file_path}")
    start_time = time.time()
    
    try:
        result = sync_parse(file_path)
        elapsed = time.time() - start_time
        logger.info(f"解析成功: {file_path}, 耗时 {elapsed:.2f}s")
        return result
    except Exception as e:
        logger.error(f"解析失败: {file_path}, 错误: {e}")
        raise
```

---

## 性能参考

基于实际测试（CPU: Intel i7-13700, GPU: RTX 4070）：

| 文件类型 | 大小 | Backend | 耗时 |
|---------|------|---------|------|
| PDF（纯文字） | 5 页 | pipeline | ~10s |
| PDF（图文混合） | 10 页 | pipeline | ~30s |
| PDF（复杂表格） | 20 页 | hybrid-engine (medium) | ~45s |
| PDF（复杂表格） | 20 页 | hybrid-engine (high) | ~80s |

**优化建议：**
- 文件 <10 页：同步模式
- 文件 >10 页：异步模式
- 纯文字提取：`pipeline` 足够
- 需要高精度/图片分析：`hybrid-engine` + `effort=high`

---

## 健康检查

在主业务启动时检查 MinerU 可用性：

```python
def check_mineru_health():
    """检查 MinerU 服务健康状态"""
    try:
        resp = requests.get(f"{MINERU_API}/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data["status"] == "healthy":
                print(f"MinerU 服务正常 (版本 {data['version']})")
                return True
        return False
    except Exception as e:
        print(f"MinerU 服务不可用: {e}")
        return False

# 启动时检查
if not check_mineru_health():
    logger.warning("MinerU 服务未就绪，文档解析功能不可用")
```

---

## 完整集成示例

```python
import requests
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class MinerUClient:
    """MinerU API 客户端"""
    
    def __init__(self, base_url="http://127.0.0.1:8001"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def parse_sync(
        self, 
        file_path: str, 
        backend: str = "pipeline",
        **kwargs
    ) -> str:
        """
        同步解析文档
        
        Args:
            file_path: 文件路径
            backend: 解析后端
            **kwargs: 其他参数（formula_enable, table_enable 等）
        
        Returns:
            str: Markdown 内容
        """
        logger.info(f"同步解析: {file_path}")
        
        data = {"backend": backend, "return_md": "true", **kwargs}
        
        with open(file_path, "rb") as f:
            resp = self.session.post(
                f"{self.base_url}/file_parse",
                files={"files": f},
                data=data,
                timeout=120,
            )
        
        resp.raise_for_status()
        result = resp.json()
        file_name = result["file_names"][0]
        
        return result["results"][file_name]["md_content"]
    
    def parse_async(
        self,
        file_path: str,
        backend: str = "pipeline",
        poll_interval: int = 3,
        **kwargs
    ) -> str:
        """
        异步解析文档
        
        Args:
            file_path: 文件路径
            backend: 解析后端
            poll_interval: 轮询间隔（秒）
            **kwargs: 其他参数
        
        Returns:
            str: Markdown 内容
        """
        logger.info(f"异步解析: {file_path}")
        
        # 提交任务
        data = {"backend": backend, "return_md": "true", **kwargs}
        with open(file_path, "rb") as f:
            resp = self.session.post(
                f"{self.base_url}/tasks",
                files={"files": f},
                data=data,
            )
        
        resp.raise_for_status()
        task_id = resp.json()["task_id"]
        logger.info(f"任务已提交: {task_id}")
        
        # 轮询状态
        while True:
            status_resp = self.session.get(f"{self.base_url}/tasks/{task_id}")
            status_resp.raise_for_status()
            status_data = status_resp.json()
            status = status_data["status"]
            
            if status == "completed":
                logger.info(f"任务完成: {task_id}")
                break
            elif status == "failed":
                error = status_data.get("error", "未知错误")
                raise Exception(f"任务失败: {error}")
            
            time.sleep(poll_interval)
        
        # 获取结果
        result_resp = self.session.get(f"{self.base_url}/tasks/{task_id}/result")
        result_resp.raise_for_status()
        result = result_resp.json()
        file_name = result["file_names"][0]
        
        return result["results"][file_name]["md_content"]
    
    def health(self) -> dict:
        """健康检查"""
        resp = self.session.get(f"{self.base_url}/health", timeout=5)
        resp.raise_for_status()
        return resp.json()

# 使用示例
if __name__ == "__main__":
    client = MinerUClient()
    
    # 健康检查
    health = client.health()
    print(f"服务状态: {health['status']}, 版本: {health['version']}")
    
    # 同步解析
    md_content = client.parse_sync("test.pdf")
    print(md_content[:500])
    
    # 异步解析（大文件）
    md_content = client.parse_async("large.pdf", backend="pipeline")
    print(md_content[:500])
```

---

## 常见问题

### Q1: 如何选择 backend？

- **有 GPU**：`hybrid-engine`（精度最高 95.39）
- **无 GPU / 纯 CPU 服务器**：`pipeline`（精度 86.47，兼容性好）
- **需要图片分析**：`hybrid-engine` + `effort=high` + `image_analysis=true`

### Q2: 如何判断文件是否解析成功？

检查响应中的 `status` 字段：
- `completed`：成功
- `failed`：失败，查看 `error` 字段

### Q3: 为什么同步接口超时？

- 文件过大：改用异步接口
- 超时设置过短：根据文件大小调整 `timeout`
- 服务负载高：增加 MinerU 实例或使用异步模式

### Q4: 如何获取原始图片而非路径？

设置 `return_images=true` 和 `response_format_zip=true`，结果会以 ZIP 包返回，包含所有图片。

### Q5: 支持哪些文件格式？

- **文档**：PDF, DOCX, PPTX, XLSX
- **图片**：JPG, PNG, BMP, TIFF
- 单次请求支持多文件上传

---

## 获取帮助

- **API 文档**：`http://127.0.0.1:8001/docs`（Swagger 交互式文档）
- **部署文档**：`docs/deployment-and-api.md`
- **GitHub Issues**：[https://github.com/opendatalab/MinerU/issues](https://github.com/opendatalab/MinerU/issues)
