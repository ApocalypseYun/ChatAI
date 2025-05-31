# 定义请求模型
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import httpx

class MessageRequest(BaseModel):
    session_id: str
    user_id: str
    platform: str
    language: str = "en"
    status: int = 1  # 0：未登录，1：已登录
    type: Optional[str] = None
    messages: str
    history: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    site: int = 1
    transfer_human: int = 0

class MessageResponse(BaseModel):
    session_id: str
    status: str
    response: str
    stage: str = "working"
    metadata: Dict[str, Any] = {}
    images: Optional[List[str]] = None
    site: int = 1
    type: Optional[str] = None
    transfer_human: int = 0


# 通用调用其他后端服务接口的方法
async def call_backend_service(
    url: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    发送HTTP请求到其他后端服务
    :param url: 请求的完整URL
    :param method: 请求方法，比如 GET, POST, PUT 等
    :param params: URL 查询参数
    :param json_data: 请求体，json格式
    :param headers: 请求头
    :param timeout: 超时时间
    :return: 返回响应的json数据
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method=method,
            url=url,
            params=params,
            json=json_data,
            headers=headers,
        )
        response.raise_for_status()  # 请求失败会抛异常
        return response.json()

# 调用 OpenAPI 大模型接口的方法示例（基于OpenAI通用API，需根据实际API调整）
async def call_openapi_model(
    prompt: str,
    api_key: str,
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    api_url: str = "https://api.openai.com/v1/chat/completions",
) -> str:
    """
    发送请求给OpenAI大模型API，获取回复
    :param prompt: 用户输入的提示文本
    :param api_key: OpenAI API Key
    :param model: 模型名称，如gpt-4
    :param temperature: 采样温度
    :param max_tokens: 最大回复tokens数
    :param api_url: API请求地址
    :return: 模型回复文本
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(api_url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        # 解析回复文本（根据OpenAI API结构）
        return data["choices"][0]["message"]["content"]