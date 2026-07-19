"""
MinerU API 客户端

通过 HTTP API 调用同机部署的 MinerU 服务进行文档解析
"""
import requests
import time
import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class MinerUClient:
    """MinerU API 客户端"""

    def __init__(self, base_url: str = "http://127.0.0.1:8001"):
        """
        初始化客户端

        Args:
            base_url: MinerU API 地址
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.session.mount(
            'http://',
            requests.adapters.HTTPAdapter(
                pool_connections=10,
                pool_maxsize=20,
                max_retries=3,
            )
        )

    def health_check(self) -> bool:
        """
        健康检查

        Returns:
            bool: 服务是否可用
        """
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "healthy":
                    logger.info(f"MinerU 服务正常 (版本 {data.get('version', 'unknown')})")
                    return True
            return False
        except Exception as e:
            logger.warning(f"MinerU 服务不可用: {e}")
            return False

    def parse_sync(
        self,
        file_path: str,
        backend: str = "pipeline",
        formula_enable: bool = True,
        table_enable: bool = True,
        return_content_list: bool = False,
        timeout: int = 120,
        **kwargs
    ) -> Dict:
        """
        同步解析文档

        Args:
            file_path: 文件路径
            backend: 解析后端 (pipeline=纯CPU / hybrid-engine=需GPU)
            formula_enable: 启用公式解析
            table_enable: 启用表格解析
            return_content_list: 返回结构化内容（包含图片信息）
            timeout: 超时时间（秒），根据文件大小动态设置
            **kwargs: 其他参数（effort, image_analysis, start_page_id, end_page_id 等）

        Returns:
            Dict: {
                "md_content": "Markdown内容",
                "content_list": [...] (如果 return_content_list=True)
            }

        Raises:
            FileNotFoundError: 文件不存在
            RuntimeError: 解析失败
            requests.exceptions.Timeout: 请求超时
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        logger.info(f"MinerU 同步解析: {file_path.name} (backend={backend}, timeout={timeout}s)")

        # 构造请求参数
        data = {
            "backend": backend,
            "return_md": "true",
            "return_content_list": str(return_content_list).lower(),
            "formula_enable": str(formula_enable).lower(),
            "table_enable": str(table_enable).lower(),
            **{k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in kwargs.items()}
        }

        try:
            with open(file_path, "rb") as f:
                resp = self.session.post(
                    f"{self.base_url}/file_parse",
                    files={"files": (file_path.name, f)},
                    data=data,
                    timeout=timeout,
                )

            if resp.status_code == 200:
                result = resp.json()
                if "file_names" in result:
                    file_name = result["file_names"][0]
                elif result.get("results"):
                    file_name = next(iter(result["results"]))
                else:
                    raise RuntimeError(f"MinerU 结果格式异常: {str(result)[:300]}")
                file_result = result["results"][file_name]

                md_content = file_result.get("md_content", "")
                content_list = file_result.get("content_list", [])

                logger.info(
                    f"MinerU 解析完成: {file_path.name}, "
                    f"状态={result.get('status')}, "
                    f"内容长度={len(md_content)} 字符, "
                    f"结构化块={len(content_list)} 个"
                )

                return {
                    "md_content": md_content,
                    "content_list": content_list
                }

            else:
                error_msg = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                raise RuntimeError(f"MinerU 解析失败 ({resp.status_code}): {error_msg}")

        except requests.exceptions.Timeout:
            logger.error(f"MinerU 解析超时 (>{timeout}s): {file_path.name}")
            raise RuntimeError(f"MinerU 解析超时 (>{timeout}s)")
        except requests.exceptions.RequestException as e:
            logger.error(f"MinerU 请求失败: {e}")
            raise RuntimeError(f"MinerU 请求失败: {e}")

    def parse_async(
        self,
        file_path: str,
        backend: str = "pipeline",
        poll_interval: int = 3,
        max_poll_time: int = 600,
        **kwargs
    ) -> Dict:
        """
        异步解析文档（提交任务后轮询）

        Args:
            file_path: 文件路径
            backend: 解析后端
            poll_interval: 轮询间隔（秒）
            max_poll_time: 最大轮询时间（秒）
            **kwargs: 其他参数

        Returns:
            str: Markdown 格式内容

        Raises:
            FileNotFoundError: 文件不存在
            RuntimeError: 解析失败或超时
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        logger.info(f"MinerU 异步解析: {file_path.name} (backend={backend})")

        # 1. 提交任务
        data = {
            "backend": backend,
            "return_md": "true",
            **{k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in kwargs.items()}
        }

        try:
            with open(file_path, "rb") as f:
                resp = self.session.post(
                    f"{self.base_url}/tasks",
                    files={"files": (file_path.name, f)},
                    data=data,
                )

            resp.raise_for_status()
            task_info = resp.json()
            task_id = task_info["task_id"]
            logger.info(f"任务已提交: {task_id}")

            # 2. 轮询状态
            start_time = time.time()
            while True:
                if time.time() - start_time > max_poll_time:
                    raise RuntimeError(f"轮询超时 (>{max_poll_time}s)")

                status_resp = self.session.get(f"{self.base_url}/tasks/{task_id}")
                status_resp.raise_for_status()
                status_data = status_resp.json()

                status = status_data["status"]
                logger.debug(f"任务状态: {status} (task_id={task_id})")

                if status == "completed":
                    break
                elif status == "failed":
                    error = status_data.get("error", "未知错误")
                    raise RuntimeError(f"任务失败: {error}")

                time.sleep(poll_interval)

            # 3. 获取结果
            result_resp = self.session.get(f"{self.base_url}/tasks/{task_id}/result")
            result_resp.raise_for_status()
            result = result_resp.json()

            logger.info(f"MinerU 结果响应 keys: {list(result.keys())}")

            if "file_names" in result:
                file_name = result["file_names"][0]
            elif result.get("results"):
                file_name = next(iter(result["results"]))
            else:
                raise RuntimeError(
                    f"MinerU 结果格式异常，缺少 results 字段。"
                    f"实际响应: {str(result)[:500]}"
                )

            file_result = result["results"][file_name]

            md_content = file_result.get("md_content", "")
            content_list = file_result.get("content_list", [])

            logger.info(
                f"MinerU 异步解析完成: {file_path.name}, "
                f"内容长度={len(md_content)} 字符, "
                f"结构化块={len(content_list)} 个"
            )

            return {
                "md_content": md_content,
                "content_list": content_list
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"MinerU 异步请求失败: {e}")
            raise RuntimeError(f"MinerU 异步请求失败: {e}")

    def parse_with_retry(
        self,
        file_path: str,
        max_retries: int = 3,
        mode: str = "sync",
        **kwargs
    ) -> Dict:
        """
        带重试的解析（生产环境推荐）

        Args:
            file_path: 文件路径
            max_retries: 最大重试次数
            mode: 解析模式 (sync / async)
            **kwargs: 传递给 parse_sync 或 parse_async 的参数

        Returns:
            Dict: 解析结果

        Raises:
            RuntimeError: 达到最大重试次数仍失败
        """
        file_path = Path(file_path)

        for attempt in range(max_retries):
            try:
                if mode == "sync":
                    return self.parse_sync(str(file_path), **kwargs)
                elif mode == "async":
                    return self.parse_async(str(file_path), **kwargs)
                else:
                    raise ValueError(f"不支持的模式: {mode}")

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    logger.warning(f"超时，重试 {attempt + 1}/{max_retries}")
                    time.sleep(2 ** attempt)  # 指数退避
                    continue
                raise RuntimeError("达到最大重试次数，解析超时")

            except RuntimeError as e:
                error_msg = str(e)
                # 服务器内部错误才重试，其他错误直接抛出
                if "500" in error_msg and attempt < max_retries - 1:
                    logger.warning(f"服务器错误，重试 {attempt + 1}/{max_retries}: {error_msg}")
                    time.sleep(2 ** attempt)
                    continue
                raise

            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"解析失败: {e}")
                logger.warning(f"错误: {e}，重试 {attempt + 1}/{max_retries}")
                time.sleep(1)

        raise RuntimeError("达到最大重试次数")

    def get_timeout_by_filesize(self, file_path: str) -> int:
        """
        根据文件大小估算超时时间

        Args:
            file_path: 文件路径

        Returns:
            int: 建议的超时时间（秒）
        """
        import os
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

        if file_size_mb < 5:
            return 180  # 3分钟
        elif file_size_mb < 20:
            return 300  # 5分钟
        else:
            return 600  # 10分钟


# 全局客户端实例
mineru_client = MinerUClient()
