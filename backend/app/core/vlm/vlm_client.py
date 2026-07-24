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

        # 2. 构造电力标准专用提示词
        default_prompt = """请详细描述这张电力工程技术图纸，重点关注以下信息：

**1. 图纸类型识别**（必选其一）
- 电路图/接线图（单线图、双线图、原理图）
- 流程图/步骤图（工艺流程、检查流程、操作流程）
- 示意图/布置图（设备布置、平面布局、剖面图）
- 参数表图（技术参数、对照表、数据表格）
- 设备结构图（零部件、组装图、爆炸图）

**2. 关键数值和标注**（优先识别）
- 电压等级（如 10kV、35kV、110kV、220kV、380V 等）
- 设备型号和规格（如断路器型号、变压器容量）
- 尺寸和距离（如安全距离、设备间距、高度）
- 其他标注文字和图注说明

**3. 主要设备和符号**（列出识别到的）
- 电气设备：断路器、隔离开关、变压器、电容器、避雷器、接地装置、母线、电缆
- 保护设备：继电器、熔断器、互感器（电流/电压）
- 测量仪表：电流表、电压表、功率表
- 控制元件：接触器、按钮、指示灯

**4. 连接关系和流程方向**（如适用）
- 设备之间的连接关系（串联/并联/分支）
- 流程的起点、关键节点、终点
- 判断分支和循环（if/else、是/否分支）
- 信号流向或能量流向

**输出要求**：
- 使用结构化描述，分点列出
- 优先列出电压等级、设备名称等关键信息
- 如果是流程图，说明主要步骤和逻辑
- 如果是参数表，提取表头和关键数值
- 控制在150字以内，聚焦技术要素"""

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
            "max_tokens": 800
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

        default_prompt = """请详细描述这张电力工程技术图纸，重点关注以下信息：

**1. 图纸类型识别**（必选其一）
- 电路图/接线图（单线图、双线图、原理图）
- 流程图/步骤图（工艺流程、检查流程、操作流程）
- 示意图/布置图（设备布置、平面布局、剖面图）
- 参数表图（技术参数、对照表、数据表格）
- 设备结构图（零部件、组装图、爆炸图）

**2. 关键数值和标注**（优先识别）
- 电压等级（如 10kV、35kV、110kV、220kV、380V 等）
- 设备型号和规格（如断路器型号、变压器容量）
- 尺寸和距离（如安全距离、设备间距、高度）
- 其他标注文字和图注说明

**3. 主要设备和符号**（列出识别到的）
- 电气设备：断路器、隔离开关、变压器、电容器、避雷器、接地装置、母线、电缆
- 保护设备：继电器、熔断器、互感器（电流/电压）
- 测量仪表：电流表、电压表、功率表
- 控制元件：接触器、按钮、指示灯

**4. 连接关系和流程方向**（如适用）
- 设备之间的连接关系（串联/并联/分支）
- 流程的起点、关键节点、终点
- 判断分支和循环（if/else、是/否分支）
- 信号流向或能量流向

**输出要求**：
- 使用结构化描述，分点列出
- 优先列出电压等级、设备名称等关键信息
- 如果是流程图，说明主要步骤和逻辑
- 如果是参数表，提取表头和关键数值
- 控制在150字以内，聚焦技术要素"""
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
                "max_tokens": 800
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
