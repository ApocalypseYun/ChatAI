import logging
import time
from typing import Dict, List, Any, Optional
from pydantic import BaseModel

# 导入配置和其他模块
from src.config import get_config
# 假设这些函数在其他模块中定义
from src.workflow_check import identify_intent, identify_stage
from src.reply import get_unauthenticated_reply, build_reply_with_prompt, call_openapi_model, OPENAI_API_KEY
from src.util import MessageRequest, MessageResponse

logger = logging.getLogger("chatai-api")

def handle_api_calls(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理API调用请求
    """
    result = {}
    if not metadata or not metadata.get("is_call"):
        return result
        
    calls = metadata.get("calls", [])
    for call in calls:
        code = call.get("code")
        args = call.get("args", {})
        
        try:
            # 这里应该实现实际的API调用逻辑
            logger.info(f"调用API: {code}, 参数: {args}")
            # result[code] = call_external_api(code, args)
            result[code] = {"status": "success", "data": f"模拟API {code} 的返回结果"}
        except Exception as e:
            logger.error(f"API调用失败: {code}, 错误: {str(e)}")
            result[code] = {"status": "error", "error": str(e)}
            
    return result

async def process_message(request: MessageRequest) -> MessageResponse:
    """
    处理用户消息并生成响应
    
    Args:
        request: 包含用户消息和上下文的请求对象

    Returns:
        MessageResponse: 包含AI回复和元数据的响应对象
    """
    logger.info(f"处理会话 {request.session_id} 的消息")
    
    # 验证必要字段
    if not request.session_id or not request.messages:
        raise ValueError("缺少必要字段: session_id, messages")
    
    # 获取配置
    config = get_config()
    
    # 处理API调用结果
    api_results = {}
    if request.metadata and request.metadata.get("is_call"):
        api_results = handle_api_calls(request.metadata)
    
    # 判断用户是否登录
    if request.status == 0:  # 未登录
        # 调用reply.py中的函数获取未登录回复
        response_text = get_unauthenticated_reply(request.language)
        
        # 构建未登录响应
        response = MessageResponse(
            session_id=request.session_id,
            status="success",
            response=response_text,
            stage="unauthenticated",
            metadata={
                "api_results": api_results,
                "timestamp": time.time()
            },
            site=request.site,
            type="unauthenticated",
            transfer_human=request.transfer_human
        )
    else:  # 已登录
        message_type = request.type
        
        # 如果type为None，进行意图识别
        if message_type is None:
            # 调用外部意图识别函数
            message_type = identify_intent(
                request.messages, 
                request.history or [], 
                request.language
            )
            logger.info(f"识别到的意图类型: {message_type}")
        
        # 识别流程步骤
        stage_number = identify_stage(
            message_type,
            request.messages,
            request.history or []
        )
        logger.info(f"识别到的流程步骤: {stage_number}")
        
        # 这里应该根据意图类型和流程步骤获取回复内容
        response_text = ""
        business_types = config.get("business_types", {})
        workflow = business_types.get(message_type, {}).get("workflow", {})
        step_info = workflow.get(str(stage_number), {})
        # S001的1、2阶段调用AI生成自然回复
        if message_type == "S001" and str(stage_number) in ["1", "2"]:
            # 获取推荐回复内容
            stage_response = step_info.get("response", {})
            stage_text = stage_response.get("text") or step_info.get("step", "")
            prompt = build_reply_with_prompt(request.history or [], request.messages, stage_text, request.language)
            response_text = await call_openapi_model(prompt=prompt, api_key=OPENAI_API_KEY)
        elif step_info and step_info.get("step"):
            response_text = step_info["step"]
        else:
            response_text = "未找到对应的流程步骤，请联系人工客服。"
        
        # 构建响应
        response = MessageResponse(
            session_id=request.session_id,
            status="success",
            response=response_text,
            stage=str(stage_number),
            metadata={
                "intent": message_type,
                "api_results": api_results,
                "timestamp": time.time()
            },
            site=request.site,
            type=message_type,
            transfer_human=request.transfer_human
        )
    
    logger.info(f"会话 {request.session_id} 处理完成")
    return response
