# 定义请求模型
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any, Optional
import httpx
import time
from .config import get_config
from .logging_config import get_logger, log_api_call
from .auth import verify_token

class MessageRequest(BaseModel):
    session_id: str
    user_id: str
    platform: str
    language: str = "en"
    status: int = Field(default=1, description="用户登录状态：0=未登录，1=已登录")
    type: Optional[str] = None
    messages: str
    history: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    site: int = 1
    token: Optional[str] = Field(default=None, description="用户认证token")
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v not in [0, 1]:
            raise ValueError("status必须是0（未登录）或1（已登录）")
        return v
    
    def validate_token(self) -> tuple[bool, Optional[str]]:
        """
        验证token的有效性
        
        Returns:
            tuple[bool, Optional[str]]: (是否有效, 错误信息)
        """
        if not self.token:
            return False, "缺少认证token"
        
        is_valid, token_user_id, error_msg = verify_token(self.token)
        
        if not is_valid:
            return False, error_msg
        
        # 验证token中的user_id与请求中的user_id是否一致
        if token_user_id != self.user_id:
            return False, f"Token中的用户ID({token_user_id})与请求中的用户ID({self.user_id})不匹配"
        
        return True, None

class MessageResponse(BaseModel):
    session_id: str
    status: str
    response: str
    stage: str = "working"
    metadata: Dict[str, Any] = {}
    images: str = None
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
    logger = get_logger("chatai-api")
    start_time = time.time()
    
    logger.debug(f"准备调用后端服务", extra={
        'url': url,
        'method': method,
        'has_params': bool(params),
        'has_json_data': bool(json_data),
        'timeout': timeout
    })
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers,
            )
            
            call_time = time.time() - start_time
            
            response.raise_for_status()  # 请求失败会抛异常
            response_data = response.json()
            
            logger.info(f"后端服务调用成功", extra={
                'url': url,
                'method': method,
                'status_code': response.status_code,
                'response_time': round(call_time, 3),
                'response_size': len(str(response_data))
            })
            
            return response_data
            
    except httpx.HTTPStatusError as e:
        call_time = time.time() - start_time
        logger.error(f"后端服务HTTP错误", extra={
            'url': url,
            'method': method,
            'status_code': e.response.status_code,
            'error': str(e),
            'response_time': round(call_time, 3)
        }, exc_info=True)
        raise
        
    except Exception as e:
        call_time = time.time() - start_time
        logger.error(f"后端服务调用异常", extra={
            'url': url,
            'method': method,
            'error': str(e),
            'error_type': type(e).__name__,
            'response_time': round(call_time, 3)
        }, exc_info=True)
        raise

# 调用 OpenAPI 大模型接口的方法示例（基于OpenAI通用API，需根据实际API调整）
async def call_openapi_model(
    prompt: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    api_url: Optional[str] = None,
) -> str:
    """
    发送请求给OpenAI大模型API，获取回复
    :param prompt: 用户输入的提示文本
    :param api_key: OpenAI API Key，如果为None则从配置文件读取
    :param model: 模型名称，如果为None则从配置文件读取默认值
    :param temperature: 采样温度，如果为None则从配置文件读取默认值
    :param max_tokens: 最大回复tokens数，如果为None则从配置文件读取默认值
    :param api_url: API请求地址，如果为None则从配置文件读取
    :return: 模型回复文本
    """
    logger = get_logger("chatai-api")
    start_time = time.time()
    
    # 从配置文件读取默认值
    config = get_config()
    
    logger.debug(f"开始调用OpenAI模型", extra={
        'prompt_length': len(prompt),
        'prompt_preview': prompt[:200] + '...' if len(prompt) > 200 else prompt,
        'has_custom_api_key': api_key is not None,
        'custom_model': model,
        'custom_temperature': temperature,
        'custom_max_tokens': max_tokens
    })
    
    # 如果参数为None，则从配置文件中获取
    if api_key is None:
        api_key = config.get("api_key", "")
    
    openai_config = config.get("openai_api", {})
    if api_url is None:
        api_url = openai_config.get("api_url", "https://api.openai.com/v1/chat/completions")
    if model is None:
        model = openai_config.get("default_model", "gpt-4")
    if temperature is None:
        temperature = openai_config.get("default_temperature", 0.7)
    if max_tokens is None:
        max_tokens = openai_config.get("default_max_tokens", 1024)
    
    logger.debug(f"使用配置参数", extra={
        'final_api_url': api_url,
        'final_model': model,
        'final_temperature': temperature,
        'final_max_tokens': max_tokens,
        'api_key_length': len(api_key) if api_key else 0
    })
    
    # 检查是否是测试模式（API密钥包含'test'）
    if "test" in api_key.lower():
        call_time = time.time() - start_time
        
        logger.info(f"使用测试模式响应", extra={
            'test_mode': True,
            'prompt_keywords': [word for word in ['订单', '充值', '提现', '帮助', '谢谢'] if word in prompt],
            'response_time': round(call_time, 3)
        })
        
        # 返回模拟响应
        if "订单" in prompt:
            return "我已经收到您的请求，正在为您查询订单状态。请稍等片刻。"
        elif "充值" in prompt:
            return "感谢您选择我们的充值服务，我将帮助您解决充值相关问题。"
        elif "提现" in prompt:
            return "我理解您对提现的关注，让我为您查询相关信息。"
        elif "帮助" in prompt or "谢谢" in prompt:
            return "很高兴能够帮助您！如果您还有其他问题，请随时告诉我。"
        else:
            return "我已经收到您的消息，正在为您处理相关请求。"
    
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
    
    log_api_call("openai_chat_completion", "system", model=model, prompt_length=len(prompt))
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(api_url, headers=headers, json=payload)
            
            call_time = time.time() - start_time
            
            resp.raise_for_status()
            data = resp.json()
            
            # 解析回复文本（根据OpenAI API结构）
            response_content = data["choices"][0]["message"]["content"]
            
            logger.info(f"OpenAI模型调用成功", extra={
                'model': model,
                'prompt_length': len(prompt),
                'response_length': len(response_content),
                'response_time': round(call_time, 3),
                'usage_tokens': data.get('usage', {}).get('total_tokens', 0),
                'status_code': resp.status_code
            })
            
            return response_content
            
    except httpx.HTTPStatusError as e:
        call_time = time.time() - start_time
        logger.error(f"OpenAI模型HTTP错误", extra={
            'model': model,
            'status_code': e.response.status_code,
            'error': str(e),
            'response_time': round(call_time, 3),
            'api_url': api_url
        }, exc_info=True)
        
        # 对于特定错误返回友好的回复
        if e.response.status_code == 401:
            return "抱歉，AI服务暂时不可用，请稍后再试。"
        elif e.response.status_code == 429:
            return "当前请求过多，请稍后再试。"
        else:
            return "抱歉，遇到了一些技术问题，请稍后再试。"
            
    except Exception as e:
        call_time = time.time() - start_time
        logger.error(f"OpenAI模型调用异常", extra={
            'model': model,
            'error': str(e),
            'error_type': type(e).__name__,
            'response_time': round(call_time, 3),
            'api_url': api_url
        }, exc_info=True)
        
        return "抱歉，AI服务暂时不可用，请稍后再试。"