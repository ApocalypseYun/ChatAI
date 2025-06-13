import time
import re
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel
from enum import Enum

# 导入配置和其他模块
from src.config import get_config, get_message_by_language
# 假设这些函数在其他模块中定义
from src.workflow_check import identify_intent, identify_stage
from src.reply import get_unauthenticated_reply, build_reply_with_prompt, build_guidance_prompt
from src.util import MessageRequest, MessageResponse, call_openapi_model  # 异步方法
from src.telegram import send_to_telegram
from src.request_internal import (
    query_recharge_status, query_withdrawal_status, query_activity_list, query_user_eligibility,
    extract_recharge_status, extract_withdrawal_status, extract_activity_list, extract_user_eligibility
)
from src.logging_config import get_logger, log_api_call

logger = get_logger("chatai-api")

# 常量定义
class Constants:
    MAX_CONVERSATION_ROUNDS = 7
    ORDER_NUMBER_LENGTH = 18
    GUIDANCE_THRESHOLD_ROUNDS = 5
    ACTIVITY_GUIDANCE_THRESHOLD = 2

class BusinessType(Enum):
    RECHARGE_QUERY = "S001"
    WITHDRAWAL_QUERY = "S002"
    ACTIVITY_QUERY = "S003"
    HUMAN_SERVICE = "human_service"

class ResponseStage(Enum):
    WORKING = "working"
    FINISH = "finish"
    UNAUTHENTICATED = "unauthenticated"

class ProcessingResult:
    """处理结果的数据类"""
    def __init__(self, text: str = "", image: str = "", stage: str = ResponseStage.WORKING.value, 
                 transfer_human: int = 0, message_type: str = None):
        self.text = text
        self.image = image
        self.stage = stage
        self.transfer_human = transfer_human
        self.message_type = message_type


async def process_message(request: MessageRequest) -> MessageResponse:
    """
    处理用户消息并生成响应
    
    Args:
        request: 包含用户消息和上下文的请求对象

    Returns:
        MessageResponse: 包含AI回复和元数据的响应对象
    """
    start_time = time.time()
    
    logger.info(f"开始处理会话 {request.session_id} 的消息", extra={
        'session_id': request.session_id,
        'user_id': getattr(request, 'user_id', 'unknown'),
        'message_length': len(str(request.messages)),
        'has_images': bool(request.images and len(request.images) > 0),
        'language': request.language,
        'platform': request.platform
    })
    
    try:
        # 验证请求
        _validate_request(request)
        
        # 未登录用户处理
        if request.status == 0:
            return _handle_unauthenticated_user(request)
        
        # 已登录用户处理
        result = await _process_authenticated_user(request)
        
        # 构建响应
        response = _build_response(request, result, start_time)
        
        logger.info(f"会话处理完成", extra={
            'session_id': request.session_id,
            'final_status': 'success',
            'business_type': result.message_type,
            'transfer_human': result.transfer_human,
            'stage': result.stage,
            'processing_time': round(time.time() - start_time, 3)
        })
        
        return response
        
    except Exception as e:
        logger.error(f"消息处理失败", extra={
            'session_id': request.session_id,
            'error': str(e)
        }, exc_info=True)
        raise


def _validate_request(request: MessageRequest) -> None:
    """验证请求参数"""
    if not request.session_id or not request.messages:
        logger.error(f"请求验证失败：缺少必要字段", extra={
            'session_id': request.session_id,
            'has_session_id': bool(request.session_id),
            'has_messages': bool(request.messages)
        })
        raise ValueError("缺少必要字段: session_id, messages")
    
    # 已登录用户需要验证token
    if request.status == 1:
        token_valid, token_error = request.validate_token()
        if not token_valid:
            logger.error(f"Token验证失败", extra={
                'session_id': request.session_id,
                'user_id': request.user_id,
                'token_error': token_error,
                'has_token': bool(request.token)
            })
            raise ValueError(f"Token验证失败: {token_error}")


def _handle_unauthenticated_user(request: MessageRequest) -> MessageResponse:
    """处理未登录用户"""
    logger.info(f"用户未登录，返回登录提示", extra={
        'session_id': request.session_id,
        'language': request.language
    })
    
    response_text = get_unauthenticated_reply(request.language)
    
    return MessageResponse(
        session_id=request.session_id,
        status="success",
        response=response_text,
        stage=ResponseStage.UNAUTHENTICATED.value,
        metadata={"timestamp": time.time()},
        site=request.site,
        type="",
        transfer_human=0
    )


async def _process_authenticated_user(request: MessageRequest) -> ProcessingResult:
    """处理已登录用户"""
    logger.debug(f"用户已登录，开始业务处理", extra={'session_id': request.session_id})
    
    # 检查对话轮次
    conversation_rounds = len(request.history or []) // 2
    if conversation_rounds >= Constants.MAX_CONVERSATION_ROUNDS:
        return _handle_max_rounds_exceeded(request)
    
    # 获取或识别业务类型
    message_type = await _get_or_identify_business_type(request)
    
    # 检查是否需要转人工
    if _should_transfer_to_human(message_type):
        return await _handle_human_service_request(request, message_type)
    
    # 处理具体业务
    return await _handle_business_process(request, message_type)


def _handle_max_rounds_exceeded(request: MessageRequest) -> ProcessingResult:
    """处理超过最大对话轮次的情况"""
    logger.warning(f"对话轮次超过限制，转人工处理", extra={
        'session_id': request.session_id,
        'rounds': len(request.history or []) // 2,
        'max_rounds': Constants.MAX_CONVERSATION_ROUNDS,
        'transfer_reason': 'conversation_rounds_exceeded'
    })
    
    response_text = get_message_by_language({
        "zh": "很抱歉，我们已经聊了很多轮，为了更好地帮助您，让我为您转接人工客服。",
        "en": "I'm sorry, we've been chatting for a while. To better assist you, let me transfer you to a human agent."
    }, request.language)
    
    return ProcessingResult(
        text=response_text,
        stage=ResponseStage.FINISH.value,
        transfer_human=1,
        message_type=request.type
    )


async def _get_or_identify_business_type(request: MessageRequest) -> str:
    """获取或识别业务类型"""
    if request.type is not None:
        logger.debug(f"使用预设业务类型: {request.type}", extra={
            'session_id': request.session_id,
            'preset_type': request.type
        })
        return request.type
    
    # 进行意图识别
    logger.debug(f"未指定业务类型，开始意图识别", extra={
        'session_id': request.session_id,
        'message': str(request.messages)[:100] + '...' if len(str(request.messages)) > 100 else str(request.messages)
    })
    
    message_type = await identify_intent(
        request.messages, 
        request.history or [], 
        request.language
    )
    
    logger.info(f"意图识别完成: {message_type}", extra={
        'session_id': request.session_id,
        'identified_intent': message_type,
        'language': request.language,
        'has_history': bool(request.history)
    })
    
    return message_type


def _should_transfer_to_human(message_type: str) -> bool:
    """判断是否应该转人工"""
    return (message_type == BusinessType.HUMAN_SERVICE.value or 
            message_type not in [BusinessType.RECHARGE_QUERY.value, 
                               BusinessType.WITHDRAWAL_QUERY.value, 
                               BusinessType.ACTIVITY_QUERY.value])


async def _handle_human_service_request(request: MessageRequest, message_type: str) -> ProcessingResult:
    """处理人工客服请求"""
    if message_type == BusinessType.HUMAN_SERVICE.value:
        transfer_reason = 'user_request_or_ai_fallback'
        logger.info(f"意图识别为人工客服", extra={
            'session_id': request.session_id,
            'transfer_reason': transfer_reason
        })
        response_text = "您需要人工客服的帮助，请稍等。"
    else:
        transfer_reason = 'unrecognized_intent'
        logger.warning(f"未识别到有效业务类型，转人工处理", extra={
            'session_id': request.session_id,
            'unrecognized_type': message_type,
            'transfer_reason': transfer_reason
        })
        response_text = "抱歉，我无法理解您的问题，已为您转接人工客服。"
    
    prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
    response_text = await call_openapi_model(prompt=prompt)
    
    return ProcessingResult(
        text=response_text,
        stage=ResponseStage.WORKING.value,
        transfer_human=1,
        message_type=message_type
    )


async def _handle_business_process(request: MessageRequest, message_type: str) -> ProcessingResult:
    """处理具体业务流程"""
    # 识别流程步骤
    stage_number = await identify_stage(
        message_type,
        request.messages,
        request.history or []
    )
    
    logger.info(f"流程步骤识别完成: stage={stage_number}", extra={
        'session_id': request.session_id,
        'business_type': message_type,
        'stage_number': stage_number,
        'history_length': len(request.history or [])
    })
    
    # 获取业务配置
    config = get_config()
    business_types = config.get("business_types", {})
    workflow = business_types.get(message_type, {}).get("workflow", {})
    status_messages = business_types.get(message_type, {}).get("status_messages", {})
    
    # 处理0阶段（非相关业务询问）
    if str(stage_number) == "0":
        return await _handle_stage_zero(request, message_type, status_messages)
    
    # 处理具体业务阶段
    if message_type == BusinessType.RECHARGE_QUERY.value:
        return await _handle_s001_process(request, stage_number, workflow, status_messages, config)
    elif message_type == BusinessType.WITHDRAWAL_QUERY.value:
        return await _handle_s002_process(request, stage_number, workflow, status_messages, config)
    elif message_type == BusinessType.ACTIVITY_QUERY.value:
        return await _handle_s003_process(request, stage_number, status_messages, config)
    
    # 默认情况
    return ProcessingResult(
        text="抱歉，无法处理您的请求。",
        transfer_human=1,
        stage=ResponseStage.FINISH.value,
        message_type=message_type
    )


async def _handle_stage_zero(request: MessageRequest, message_type: str, status_messages: Dict) -> ProcessingResult:
    """处理阶段0（非相关业务询问）"""
    if request.type is not None:
        # 有预设业务类型，尝试引导用户回到正常流程
        conversation_rounds = len(request.history or []) // 2
        logger.info(f"识别为0阶段但有预设业务类型，尝试引导用户", extra={
            'session_id': request.session_id,
            'business_type': message_type,
            'stage': 0,
            'conversation_rounds': conversation_rounds,
            'guidance_mode': True
        })
        
        guidance_prompt = build_guidance_prompt(
            message_type, 
            conversation_rounds, 
            str(request.messages), 
            request.history or [], 
            request.language
        )
        
        response_text = await call_openapi_model(prompt=guidance_prompt)
        
        return ProcessingResult(
            text=response_text,
            stage=ResponseStage.WORKING.value,
            transfer_human=0,
            message_type=message_type
        )
    else:
        # 没有预设业务类型，转人工
        logger.warning(f"识别为0阶段，非{message_type}相关询问，转人工处理", extra={
            'session_id': request.session_id,
            'business_type': message_type,
            'stage': 0,
            'transfer_reason': 'non_business_inquiry'
        })
        
        response_text = get_message_by_language(
            status_messages.get("non_business_inquiry", {}), 
            request.language
        )
        
        return ProcessingResult(
            text=response_text,
            transfer_human=1,
            stage=ResponseStage.FINISH.value,
            message_type=message_type
        )


def _build_response(request: MessageRequest, result: ProcessingResult, start_time: float) -> MessageResponse:
    """构建最终响应"""
    conversation_rounds = len(request.history or []) // 2
    
    logger.debug(f"构建最终响应", extra={
        'session_id': request.session_id,
        'response_stage': result.stage,
        'transfer_human': result.transfer_human,
        'has_images': bool(result.image),
        'response_length': len(result.text),
        'conversation_rounds': conversation_rounds
    })
    
    return MessageResponse(
        session_id=request.session_id,
        status="success",
        response=result.text,
        stage=result.stage,
        images=result.image,
        metadata={
            "intent": result.message_type,
            "timestamp": time.time(),
            "conversation_rounds": conversation_rounds,
            "max_rounds": Constants.MAX_CONVERSATION_ROUNDS,
            "has_preset_type": request.type is not None,
            "processing_time": round(time.time() - start_time, 3)
        },
        site=request.site,
        type=result.message_type,
        transfer_human=result.transfer_human
    )


class StageHandler:
    """阶段处理器基类"""
    
    @staticmethod
    async def handle_image_upload(request: MessageRequest, status_messages: Dict) -> ProcessingResult:
        """处理图片上传情况"""
        logger.warning(f"检测到图片上传，转人工处理", extra={
            'session_id': request.session_id,
            'image_count': len(request.images),
            'transfer_reason': 'image_upload'
        })
        
        response_text = get_message_by_language(
            status_messages.get("image_uploaded", {}), 
            request.language
        )
        
        return ProcessingResult(
            text=response_text,
            transfer_human=1,
            stage=ResponseStage.FINISH.value
        )
    
    @staticmethod
    async def handle_standard_stage(request: MessageRequest, stage_number: str, workflow: Dict) -> ProcessingResult:
        """处理标准阶段（1、2、4）"""
        step_info = workflow.get(stage_number, {})
        stage_response = step_info.get("response", {})
        stage_text = stage_response.get("text") or step_info.get("step", "")
        
        prompt = build_reply_with_prompt(request.history or [], request.messages, stage_text, request.language)
        response_text = await call_openapi_model(prompt=prompt)
        
        stage_image = stage_response.get("image", "")
        response_stage = ResponseStage.WORKING.value if stage_number in ["1", "2"] else ResponseStage.FINISH.value
        
        return ProcessingResult(
            text=response_text,
            image=stage_image,
            stage=response_stage
        )
    
    @staticmethod
    def handle_order_not_found(request: MessageRequest, status_messages: Dict, business_type: str) -> ProcessingResult:
        """处理订单号未找到的情况"""
        conversation_rounds = len(request.history or []) // 2
        
        if conversation_rounds >= Constants.GUIDANCE_THRESHOLD_ROUNDS and request.type is not None:
            # 使用引导策略
            return ProcessingResult(
                text="",  # 将在调用者中使用guidance_prompt填充
                stage=ResponseStage.WORKING.value,
                message_type=business_type
            )
        else:
            response_text = get_message_by_language(
                status_messages.get("order_not_found", {}), 
                request.language
            )
            return ProcessingResult(
                text=response_text,
                stage=ResponseStage.WORKING.value
            )


async def _handle_s001_process(request: MessageRequest, stage_number: int, workflow: Dict, 
                             status_messages: Dict, config: Dict) -> ProcessingResult:
    """处理S001充值查询流程"""
    # 检查图片上传
    if request.images and len(request.images) > 0:
        return await StageHandler.handle_image_upload(request, status_messages)
    
    # 标准阶段处理
    if str(stage_number) in ["1", "2", "4"]:
        return await StageHandler.handle_standard_stage(request, str(stage_number), workflow)
    
    # 阶段3：订单号查询处理
    elif str(stage_number) == "3":
        return await _handle_order_query_s001(request, status_messages, workflow)
    
    return ProcessingResult(text="未知阶段", transfer_human=1, stage=ResponseStage.FINISH.value)


async def _handle_order_query_s001(request: MessageRequest, status_messages: Dict, workflow: Dict) -> ProcessingResult:
    """处理S001的订单查询"""
    order_no = extract_order_no(request.messages, request.history)
    
    if not order_no:
        result = StageHandler.handle_order_not_found(request, status_messages, BusinessType.RECHARGE_QUERY.value)
        if not result.text:  # 需要使用guidance
            guidance_prompt = build_guidance_prompt(
                BusinessType.RECHARGE_QUERY.value, 
                len(request.history or []) // 2, 
                str(request.messages), 
                request.history or [], 
                request.language
            )
            result.text = await call_openapi_model(prompt=guidance_prompt)
        return result
    
    # 调用API查询
    log_api_call("A001_query_recharge_status", request.session_id, order_no=order_no)
    
    try:
        api_result = await query_recharge_status(request.session_id, order_no, request.site)
    except Exception as e:
        logger.error(f"A001接口调用异常", extra={
            'session_id': request.session_id,
            'order_no': order_no,
            'error': str(e)
        }, exc_info=True)
        api_result = None
    
    # 验证API结果
    is_valid, error_message = validate_session_and_handle_errors(api_result, status_messages, request.language)
    if not is_valid:
        return ProcessingResult(
            text=error_message,
            transfer_human=1,
            stage=ResponseStage.FINISH.value
        )
    
    # 处理查询结果
    extracted_data = extract_recharge_status(api_result)
    if not extracted_data["is_success"]:
        response_text = get_message_by_language(
            status_messages.get("query_failed", {}), 
            request.language
        )
        return ProcessingResult(
            text=response_text,
            transfer_human=1,
            stage=ResponseStage.FINISH.value
        )
    
    # 根据状态处理
    return await _process_recharge_status(extracted_data["status"], status_messages, workflow, request)


async def _process_recharge_status(status: str, status_messages: Dict, workflow: Dict, 
                                 request: MessageRequest) -> ProcessingResult:
    """处理充值状态"""
    status_mapping = {
        "Recharge successful": ("recharge_successful", ResponseStage.FINISH.value, 0),
        "canceled": ("payment_canceled", ResponseStage.FINISH.value, 0),
        "pending": ("payment_issue", ResponseStage.FINISH.value, 1),
        "rejected": ("payment_issue", ResponseStage.FINISH.value, 1),
        "Recharge failed": ("payment_issue", ResponseStage.FINISH.value, 1),
    }
    
    message_key, stage, transfer_human = status_mapping.get(
        status, ("status_unclear", ResponseStage.FINISH.value, 1)
    )
    
    response_text = get_message_by_language(
        status_messages.get(message_key, {}), 
        request.language
    )
    
    # 添加成功状态的图片
    response_image = ""
    if status == "Recharge successful":
        stage_4_info = workflow.get("4", {})
        response_image = stage_4_info.get("response", {}).get("image", "")
    
    # 生成最终回复
    prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
    final_text = await call_openapi_model(prompt=prompt)
    
    return ProcessingResult(
        text=final_text,
        image=response_image,
        stage=stage,
        transfer_human=transfer_human
    )


async def _handle_s002_process(request: MessageRequest, stage_number: int, workflow: Dict, 
                             status_messages: Dict, config: Dict) -> ProcessingResult:
    """处理S002提现查询流程"""
    # 检查图片上传
    if request.images and len(request.images) > 0:
        return await StageHandler.handle_image_upload(request, status_messages)
    
    # 标准阶段处理
    if str(stage_number) in ["1", "2", "4"]:
        return await StageHandler.handle_standard_stage(request, str(stage_number), workflow)
    
    # 阶段3：订单号查询处理
    elif str(stage_number) == "3":
        return await _handle_order_query_s002(request, status_messages, workflow, config)
    
    return ProcessingResult(text="未知阶段", transfer_human=1, stage=ResponseStage.FINISH.value)


async def _handle_order_query_s002(request: MessageRequest, status_messages: Dict, 
                                 workflow: Dict, config: Dict) -> ProcessingResult:
    """处理S002的订单查询"""
    order_no = extract_order_no(request.messages, request.history)
    
    if not order_no:
        result = StageHandler.handle_order_not_found(request, status_messages, BusinessType.WITHDRAWAL_QUERY.value)
        if not result.text:  # 需要使用guidance
            guidance_prompt = build_guidance_prompt(
                BusinessType.WITHDRAWAL_QUERY.value, 
                len(request.history or []) // 2, 
                str(request.messages), 
                request.history or [], 
                request.language
            )
            result.text = await call_openapi_model(prompt=guidance_prompt)
        return result
    
    # 调用API查询
    log_api_call("A002_query_withdrawal_status", request.session_id, order_no=order_no)
    
    try:
        api_result = await query_withdrawal_status(request.session_id, order_no, request.site)
    except Exception as e:
        logger.error(f"A002接口调用异常", extra={
            'session_id': request.session_id,
            'order_no': order_no,
            'error': str(e)
        }, exc_info=True)
        api_result = None
    
    # 验证API结果
    is_valid, error_message = validate_session_and_handle_errors(api_result, status_messages, request.language)
    if not is_valid:
        return ProcessingResult(
            text=error_message,
            transfer_human=1,
            stage=ResponseStage.FINISH.value
        )
    
    # 处理查询结果
    extracted_data = extract_withdrawal_status(api_result)
    if not extracted_data["is_success"]:
        response_text = get_message_by_language(
            status_messages.get("query_failed", {}), 
            request.language
        )
        return ProcessingResult(
            text=response_text,
            transfer_human=1,
            stage=ResponseStage.FINISH.value
        )
    
    # 根据状态处理
    return await _process_withdrawal_status(extracted_data["status"], status_messages, workflow, request, config)


async def _process_withdrawal_status(status: str, status_messages: Dict, workflow: Dict, 
                                   request: MessageRequest, config: Dict) -> ProcessingResult:
    """处理提现状态"""
    # 定义状态映射
    status_mapping = {
        "Withdrawal successful": ("withdrawal_successful", ResponseStage.FINISH.value, 0, False),
        "pending": ("withdrawal_processing", ResponseStage.FINISH.value, 0, False),
        "obligation": ("withdrawal_processing", ResponseStage.FINISH.value, 0, False),
        "canceled": ("withdrawal_canceled", ResponseStage.FINISH.value, 0, False),
        "rejected": ("withdrawal_issue", ResponseStage.FINISH.value, 1, False),
        "prepare": ("withdrawal_issue", ResponseStage.FINISH.value, 1, False),
        "lock": ("withdrawal_issue", ResponseStage.FINISH.value, 1, False),
        "oblock": ("withdrawal_issue", ResponseStage.FINISH.value, 1, False),
        "refused": ("withdrawal_issue", ResponseStage.FINISH.value, 1, False),
        "Withdrawal failed": ("withdrawal_failed", ResponseStage.FINISH.value, 1, True),
        "confiscate": ("withdrawal_failed", ResponseStage.FINISH.value, 1, True),
    }
    
    message_key, stage, transfer_human, needs_telegram = status_mapping.get(
        status, ("withdrawal_issue", ResponseStage.FINISH.value, 1, False)
    )
    
    # 发送TG通知（如果需要）
    if needs_telegram:
        await _send_telegram_notification(config, request, extract_order_no(request.messages, request.history), status)
    
    response_text = get_message_by_language(
        status_messages.get(message_key, {}), 
        request.language
    )
    
    # 添加成功状态的图片
    response_image = ""
    if status == "Withdrawal successful":
        stage_4_info = workflow.get("4", {})
        response_image = stage_4_info.get("response", {}).get("image", "")
    
    # 生成最终回复
    prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
    final_text = await call_openapi_model(prompt=prompt)
    
    return ProcessingResult(
        text=final_text,
        image=response_image,
        stage=stage,
        transfer_human=transfer_human
    )


async def _send_telegram_notification(config: Dict, request: MessageRequest, order_no: str, status: str) -> None:
    """发送Telegram通知"""
    bot_token = config.get("telegram_bot_token", "")
    chat_id = config.get("telegram_chat_id", "")
    
    if bot_token and chat_id:
        tg_message = f"⚠️ 提现异常\n用户ID: {request.user_id}\n订单号: {order_no}\n状态: {status}"
        try:
            await send_to_telegram([], bot_token, chat_id, username=request.user_id, custom_message=tg_message)
        except Exception as e:
            logger.error(f"TG异常通知发送失败", extra={
                'session_id': request.session_id,
                'error': str(e)
            })


async def _handle_s003_process(request: MessageRequest, stage_number: int, 
                             status_messages: Dict, config: Dict) -> ProcessingResult:
    """处理S003活动查询流程"""
    if str(stage_number) in ["1", "2"]:
        return await _handle_activity_query(request, status_messages)
    else:
        # 其他阶段，转人工处理
        response_text = get_message_by_language(
            status_messages.get("query_failed", {}), 
            request.language
        )
        return ProcessingResult(
            text=response_text,
            transfer_human=1,
            stage=ResponseStage.FINISH.value
        )


async def _handle_activity_query(request: MessageRequest, status_messages: Dict) -> ProcessingResult:
    """处理活动查询"""
    # 查询活动列表
    log_api_call("A003_query_activity_list", request.session_id)
    try:
        api_result = await query_activity_list(request.session_id, request.site)
    except Exception as e:
        logger.error(f"A003接口调用异常", extra={
            'session_id': request.session_id,
            'error': str(e)
        }, exc_info=True)
        api_result = None
    
    is_valid, error_message = validate_session_and_handle_errors(api_result, status_messages, request.language)
    if not is_valid:
        prompt = build_reply_with_prompt(request.history or [], request.messages, error_message, request.language)
        final_text = await call_openapi_model(prompt=prompt)
        return ProcessingResult(
            text=final_text,
            transfer_human=1,
            stage=ResponseStage.FINISH.value
        )
    
    extracted_data = extract_activity_list(api_result)
    if not extracted_data["is_success"]:
        response_text = get_message_by_language(
            status_messages.get("query_failed", {}), 
            request.language
        )
        prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
        final_text = await call_openapi_model(prompt=prompt)
        return ProcessingResult(
            text=final_text,
            transfer_human=1,
            stage=ResponseStage.FINISH.value
        )
    
    # 构建活动列表
    all_activities = []
    all_activities.extend(extracted_data["agent_activities"])
    all_activities.extend(extracted_data["deposit_activities"])
    all_activities.extend(extracted_data["rebate_activities"])
    all_activities.extend(extracted_data["lucky_spin_activities"])
    all_activities.extend(extracted_data["all_member_activities"])
    all_activities.extend(extracted_data["sports_activities"])
    
    if not all_activities:
        response_text = get_message_by_language(
            status_messages.get("no_activities", {}), 
            request.language
        )
        prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
        final_text = await call_openapi_model(prompt=prompt)
        return ProcessingResult(
            text=final_text,
            stage=ResponseStage.FINISH.value
        )
    
    # 识别用户想要的活动
    return await _identify_and_query_activity(request, all_activities, status_messages)


async def _identify_and_query_activity(request: MessageRequest, all_activities: List[str], 
                                     status_messages: Dict) -> ProcessingResult:
    """识别并查询活动"""
    # 构建活动列表文本
    activity_list_text = _build_activity_list_text(all_activities, request.language)
    
    # 识别活动
    identified_activity = await _identify_user_activity(request, activity_list_text)
    
    # 处理识别结果
    if identified_activity.strip().lower() == "unclear" or identified_activity.strip() not in all_activities:
        return await _handle_unclear_activity(request, status_messages, activity_list_text)
    
    # 查询用户资格
    return await _query_user_activity_eligibility(request, identified_activity.strip(), status_messages)


def _build_activity_list_text(all_activities: List[str], language: str) -> str:
    """构建活动列表文本"""
    if language == "en":
        activity_list_text = "Available activities:\n"
    else:
        activity_list_text = "可用活动列表：\n"
    
    for i, activity in enumerate(all_activities, 1):
        activity_list_text += f"{i}. {activity}\n"
    
    return activity_list_text


async def _identify_user_activity(request: MessageRequest, activity_list_text: str) -> str:
    """识别用户想要的活动"""
    user_message = request.messages
    
    if request.language == "en":
        activity_prompt = f"""
Based on the user's message and activity list, identify the specific activity the user wants to query.

User message: {user_message}

{activity_list_text}

Please analyze the user's message and find the most matching activity name from the activity list.
If the user's description is not clear enough or cannot match a specific activity, please reply "unclear".
If you find a matching activity, please return the complete activity name directly.
"""
    else:
        activity_prompt = f"""
根据用户的消息和活动列表，识别用户想要查询的具体活动。

用户消息：{user_message}

{activity_list_text}

请分析用户的消息，从活动列表中找出最匹配的活动名称。
如果用户的描述不够明确或无法匹配到具体活动，请回复"unclear"。
如果找到匹配的活动，请直接返回活动的完整名称。
"""
    
    return await call_openapi_model(prompt=activity_prompt)


async def _handle_unclear_activity(request: MessageRequest, status_messages: Dict, 
                                 activity_list_text: str) -> ProcessingResult:
    """处理活动识别不明确的情况"""
    conversation_rounds = len(request.history or []) // 2
    
    if conversation_rounds >= Constants.ACTIVITY_GUIDANCE_THRESHOLD and request.type is not None:
        # 使用引导策略，包含活动列表信息
        enhanced_message = f"{str(request.messages)}\n\n可用活动列表：\n{activity_list_text}"
        guidance_prompt = build_guidance_prompt(
            BusinessType.ACTIVITY_QUERY.value, 
            conversation_rounds, 
            enhanced_message, 
            request.history or [], 
            request.language
        )
        response_text = await call_openapi_model(prompt=guidance_prompt)
    else:
        # 标准处理：提供活动列表和更友好的引导
        base_message = get_message_by_language(
            status_messages.get("unclear_activity", {}), 
            request.language
        )
        response_text = f"{base_message}\n{activity_list_text}"
        prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
        response_text = await call_openapi_model(prompt=prompt)
    
    return ProcessingResult(
        text=response_text,
        stage=ResponseStage.WORKING.value
    )


async def _query_user_activity_eligibility(request: MessageRequest, activity_name: str, 
                                         status_messages: Dict) -> ProcessingResult:
    """查询用户活动资格"""
    log_api_call("A004_query_user_eligibility", request.session_id, activity=activity_name)
    
    try:
        api_result = await query_user_eligibility(request.session_id, request.site)
        eligibility_data = extract_user_eligibility(api_result)
        
        if not eligibility_data["is_success"]:
            response_text = get_message_by_language(
                status_messages.get("query_failed", {}), 
                request.language
            )
            return ProcessingResult(
                text=response_text,
                transfer_human=1,
                stage=ResponseStage.FINISH.value
            )
        
        # 处理资格状态
        return await _process_activity_eligibility(eligibility_data, status_messages, request)
        
    except Exception as e:
        logger.error(f"A004接口调用异常", extra={
            'session_id': request.session_id,
            'error': str(e)
        }, exc_info=True)
        
        response_text = get_message_by_language(
            status_messages.get("query_failed", {}), 
            request.language
        )
        return ProcessingResult(
            text=response_text,
            transfer_human=1,
            stage=ResponseStage.FINISH.value
        )


async def _process_activity_eligibility(eligibility_data: Dict, status_messages: Dict, 
                                      request: MessageRequest) -> ProcessingResult:
    """处理活动资格状态"""
    status = eligibility_data["status"]
    message = eligibility_data["message"]
    
    # 状态映射
    status_mapping = {
        "Conditions not met": ("conditions_not_met", ResponseStage.FINISH.value, 0),
        "Paid success": ("paid_success", ResponseStage.FINISH.value, 0),
        "Waiting paid": ("waiting_paid", ResponseStage.FINISH.value, 0),
        "Need paid": ("need_paid", ResponseStage.FINISH.value, 1),
    }
    
    message_key, stage, transfer_human = status_mapping.get(
        status, ("unknown_status", ResponseStage.FINISH.value, 1)
    )
    
    base_message = get_message_by_language(
        status_messages.get(message_key, {}), 
        request.language
    )
    
    # 组合消息
    if message and message_key in ["conditions_not_met", "waiting_paid"]:
        response_text = f"{base_message} {message}".strip()
    else:
        response_text = base_message
    
    # 生成最终回复
    prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
    final_text = await call_openapi_model(prompt=prompt)
    
    return ProcessingResult(
        text=final_text,
        stage=stage,
        transfer_human=transfer_human
    )


def extract_order_no(messages, history):
    """
    从消息和历史中提取订单号（18位纯数字）
    """
    logger.debug(f"开始提取订单号", extra={
        'message_type': type(messages),
        'has_history': bool(history),
        'history_length': len(history) if history else 0
    })
    
    all_text = ""
    if isinstance(messages, list):
        all_text += " ".join([str(m) for m in messages])
    else:
        all_text += str(messages)
    if history:
        for turn in history:
            all_text += " " + str(turn.get("content", ""))
    
    # 找到所有连续的数字序列
    number_sequences = re.findall(r'\d+', all_text)
    
    # 只返回长度恰好为18位的数字序列
    for seq in number_sequences:
        if len(seq) == Constants.ORDER_NUMBER_LENGTH:
            logger.info(f"成功提取18位订单号", extra={
                'order_no': seq,
                'source_text_length': len(all_text)
            })
            return seq
    
    logger.warning(f"未找到18位订单号", extra={
        'found_sequences': len(number_sequences),
        'sequence_lengths': [len(seq) for seq in number_sequences[:10]]
    })
    return None


def validate_session_and_handle_errors(api_result, status_messages, language):
    """
    验证session_id和处理API调用错误
    """
    if not api_result:
        return False, get_message_by_language(
            status_messages.get("query_failed", {}), 
            language
        )
    
    # 检查是否是session_id无效或其他错误
    state = api_result.get("state", -1)
    
    error_mapping = {
        886: "session_invalid",        # Missing required parameters
        887: "invalid_order_number",   # 订单号格式正确但查询不到记录
    }
    
    if state in error_mapping:
        return False, get_message_by_language(
            status_messages.get(error_mapping[state], {}), 
            language
        )
    elif state != 0:  # 其他错误
        return False, get_message_by_language(
            status_messages.get("query_failed", {}), 
            language
        )
    
    return True, "" 