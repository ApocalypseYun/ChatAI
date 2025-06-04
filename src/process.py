import logging
import time
import re
from typing import Dict, List, Any, Optional
from pydantic import BaseModel

# 导入配置和其他模块
from src.config import get_config
# 假设这些函数在其他模块中定义
from src.workflow_check import identify_intent, identify_stage
from src.reply import get_unauthenticated_reply, build_reply_with_prompt
from src.util import MessageRequest, MessageResponse, call_openapi_model  # 异步方法
from src.telegram import send_to_telegram
from src.request_internal import query_recharge_status

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
            type="",
            transfer_human=request.transfer_human
        )
    else:  # 已登录
        message_type = request.type
        
        # 如果type为None，进行意图识别
        if message_type is None:
            # 调用外部意图识别函数
            message_type = await identify_intent(
                request.messages, 
                request.history or [], 
                request.language
            )
            logger.info(f"识别到的意图类型: {message_type}")

        response_text = ""
        response_image = []
        response_stage = "working"
        transfer_human = 0

        if message_type == "human_service":
            response_text = "您需要人工客服的帮助，请稍等。"
            response_stage = "working"
            transfer_human = 1
            
        else:
            # 识别流程步骤
            stage_number = await identify_stage(
                message_type,
                request.messages,
                request.history or []
            )
            logger.info(f"识别到的流程步骤: {stage_number}")
            
            # 这里应该根据意图类型和流程步骤获取回复内容
            business_types = config.get("business_types", {})
            workflow = business_types.get(message_type, {}).get("workflow", {})
            step_info = workflow.get(str(stage_number), {})
            # S001的1、2阶段调用AI生成自然回复
            if message_type == "S001":
                if str(stage_number) in ["1", "2", "4"]:
                    # 获取推荐回复内容
                    stage_response = step_info.get("response", {})
                    stage_text = stage_response.get("text") or step_info.get("step", "")
                    prompt = build_reply_with_prompt(request.history or [], request.messages, stage_text, request.language)
                    response_text = await call_openapi_model(prompt=prompt)
                    stage_image = stage_response.get("image", "")
                    if stage_image:
                        response_image = [stage_image]
                    response_stage = "working"
                elif str(stage_number) == "3":
                    # 检查是否上传图片
                    if request.images and len(request.images) > 0:
                        bot_token = config.get("telegram_bot_token", "")
                        chat_id = config.get("telegram_chat_id", "")
                        if bot_token and chat_id:
                            await send_to_telegram(request.images, bot_token, chat_id, username=request.user_id)
                        response_text = "您上传了图片，已为您转接人工客服。"
                        transfer_human = 1
                        response_stage = "finish"
                    else:
                        order_no = extract_order_no(request.messages, request.history)
                        if order_no:
                            api_result = await query_recharge_status(request.session_id, order_no)
                            status = api_result.get("status", "未知")
                            msg = api_result.get("msg", "")
                            response_text = f"订单号{order_no}的充值状态为：{status} {msg}"
                            prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                            response_text = await call_openapi_model(prompt=prompt)
                            response_stage = "finish"
                        else:
                            response_text = "未能识别到您的订单号，已为您转接人工客服。"
                            transfer_human = 1
                            response_stage = "working"
            
        # 构建响应
        response = MessageResponse(
            session_id=request.session_id,
            status="success",
            response=response_text,
            stage=response_stage,
            images=response_image,
            metadata={
                "intent": message_type,
                "api_results": api_results,
                "timestamp": time.time()
            },
            site=request.site,
            type=message_type,
            transfer_human=transfer_human
        )
    
    logger.info(f"会话 {request.session_id} 处理完成")
    return response

def extract_order_no(messages, history):
    """
    从消息和历史中提取订单号（假设为10位及以上数字）
    """
    order_no_pattern = r"\\b\\d{10,}\\b"
    all_text = ""
    if isinstance(messages, list):
        all_text += " ".join([str(m) for m in messages])
    else:
        all_text += str(messages)
    if history:
        for turn in history:
            all_text += " " + str(turn.get("content", ""))
    match = re.search(order_no_pattern, all_text)
    if match:
        return match.group(0)
    return None
