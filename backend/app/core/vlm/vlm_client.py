"""
VLM API Client for image description generation
支持豆包多模态 API / 通义千问 VL API
"""
import base64
import logging
from typing import Dict, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class VLMAPIClient:
    """VLM API 客户端（支持豆包/通义千问）"""

    def __init__(self):
        self.provider = settings.VLM_PROVIDER
        self.enabled = settings.ENABLE_VLM_DESCRIPTION

        if self.provider == "doubao":
            self.api_key = settings.DOUBAO_API_KEY
            self.endpoint = settings.DOUBAO_API_ENDPOINT
            self.model = settings.DOUBAO_MODEL
        elif self.provider == "qwen":
            self.api_key = settings.QWEN_API_KEY
            self.model = settings.QWEN_MODEL
        else:
            self.api_key = None
            self.endpoint = None
            self.model = None

        logger.info(f"VLM客户端初始化: provider={self.provider}, enabled={self.enabled}")

    async def generate_description(self, image_path: str, prompt: Optional[str] = None) -> Dict:
        """
        生成图片描述

        Args:
            image_path: 图片路径
            prompt: 自定义提示词（可选）

        Returns:
            {
                'description': '图片描述文本',
                'confidence': 0.95,
                'model': 'doubao-vision-pro'
            }
        """
        if not self.enabled:
            logger.warning("VLM描述生成未启用")
            return {'description': None, 'confidence': 0.0, 'error': 'VLM disabled'}

        if not self.api_key:
            logger.error(f"VLM API密钥未配置: provider={self.provider}")
            return {'description': None, 'confidence': 0.0, 'error': 'API key not configured'}

        try:
            if self.provider == "doubao":
                return await self._call_doubao_api(image_path, prompt)
            elif self.provider == "qwen":
                return await self._call_qwen_api(image_path, prompt)
            else:
                return {'description': None, 'confidence': 0.0, 'error': f'Unknown provider: {self.provider}'}
        except Exception as e:
            logger.error(f"VLM API调用失败: {e}", exc_info=True)
            return {'description': None, 'confidence': 0.0, 'error': str(e)}

    async def _call_doubao_api(self, image_path: str, custom_prompt: Optional[str] = None) -> Dict:
        """调用豆包多模态API"""

        # 1. 读取图片并转为 base64
        try:
            with open(image_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            return {'description': None, 'confidence': 0.0, 'error': f'Failed to read image: {e}'}

        # 2. 构造默认提示词
        default_prompt = """请详细描述这张工程图纸，包括：
1. 图纸类型（剖面图/平面图/示意图/流程图）
2. 主要组成部分和关键设备
3. 结构布局和空间关系
4. 图中的重要标注和尺寸

要求：用一段话概括，不超过100字，专注于技术细节。"""

        prompt_text = custom_prompt or default_prompt

        # 3. 构造请求
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt_text
                        }
                    ]
                }
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 4. 发送请求
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.endpoint,
                    json=payload,
                    headers=headers
                )

                if response.status_code != 200:
                    error_msg = f"API调用失败: status={response.status_code}, body={response.text}"
                    logger.error(error_msg)
                    return {
                        'description': None,
                        'confidence': 0.0,
                        'error': error_msg
                    }

                # 5. 解析响应
                result = response.json()
                description = result['choices'][0]['message']['content']

                logger.info(f"豆包API调用成功: {description[:50]}...")

                return {
                    'description': description,
                    'confidence': 0.9,
                    'model': self.model
                }

        except httpx.TimeoutException:
            return {'description': None, 'confidence': 0.0, 'error': 'API request timeout'}
        except Exception as e:
            return {'description': None, 'confidence': 0.0, 'error': f'API request failed: {e}'}

    async def _call_qwen_api(self, image_path: str, custom_prompt: Optional[str] = None) -> Dict:
        """调用通义千问VL API"""

        # 通义千问VL API实现（格式类似，略有不同）
        try:
            with open(image_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            return {'description': None, 'confidence': 0.0, 'error': f'Failed to read image: {e}'}

        default_prompt = "请详细描述这张工程图纸的内容，包括图纸类型、主要构成、结构关系和关键标注，不超过100字。"
        prompt_text = custom_prompt or default_prompt

        # 通义千问API格式
        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"image": f"data:image/png;base64,{image_base64}"},
                            {"text": prompt_text}
                        ]
                    }
                ]
            },
            "parameters": {
                "max_tokens": 200
            }
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
                    json=payload,
                    headers=headers
                )

                if response.status_code != 200:
                    error_msg = f"API调用失败: status={response.status_code}, body={response.text}"
                    logger.error(error_msg)
                    return {
                        'description': None,
                        'confidence': 0.0,
                        'error': error_msg
                    }

                result = response.json()
                description = result['output']['choices'][0]['message']['content'][0]['text']

                logger.info(f"通义千问API调用成功: {description[:50]}...")

                return {
                    'description': description,
                    'confidence': 0.9,
                    'model': self.model
                }

        except httpx.TimeoutException:
            return {'description': None, 'confidence': 0.0, 'error': 'API request timeout'}
        except Exception as e:
            return {'description': None, 'confidence': 0.0, 'error': f'API request failed: {e}'}


# 全局实例
vlm_client = VLMAPIClient()
