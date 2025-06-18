import time
import re
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel
from enum import Enum

# 导入配置和其他模块
from src.config import get_config, get_message_by_language
# 假设这些函数在其他模块中定义
from src.workflow_check import identify_intent, identify_stage, is_follow_up_satisfaction_check
from src.reply import get_unauthenticated_reply, build_reply_with_prompt, build_guidance_prompt, get_follow_up_message
from src.util import MessageRequest, MessageResponse, call_openapi_model, identify_user_satisfaction  # 异步方法
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
    MAX_CHAT_ROUNDS = 7  # 闲聊最大轮数

class BusinessType(Enum):
    RECHARGE_QUERY = "S001"
    WITHDRAWAL_QUERY = "S002"
    ACTIVITY_QUERY = "S003"
    HUMAN_SERVICE = "human_service"
    CHAT_SERVICE = "chat_service"  # 闲聊服务

class ResponseStage(Enum):
    WORKING = "working"
    FINISH = "finish"
    UNAUTHENTICATED = "unauthenticated"



class ProcessingResult:
    """处理结果的数据类"""
    def __init__(self, text: str = "", images: List[str] = None, stage: str = ResponseStage.WORKING.value, 
                 transfer_human: int = 0, message_type: str = ""):
        self.text = text
        self.images = images or []
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
    
    # 检查是否为后续询问的回复（用户表示满意或没有其他问题）
    if is_follow_up_satisfaction_check(request):
        user_satisfied = await identify_user_satisfaction(str(request.messages), request.language)
        if user_satisfied:
            logger.info(f"用户表示满意，结束对话", extra={
                'session_id': request.session_id,
                'conversation_rounds': conversation_rounds
            })
            return ProcessingResult(
                text=get_message_by_language({
                    "zh": "感谢您的使用，祝您生活愉快！",
                    "en": "Thank you for using our service. Have a great day!",
                    "th": "ขอบคุณที่ใช้บริการของเรา ขอให้มีความสุข!",
                    "tl": "Salamat sa paggamit ng aming serbisyo. Magkaroon ng magandang araw!",
                    "ja": "ご利用ありがとうございました。良い一日をお過ごしください！"
                }, request.language),
                stage=ResponseStage.FINISH.value,
                transfer_human=0,
                message_type=request.type or ""
            )
    
    # 获取或识别业务类型
    message_type = await _get_or_identify_business_type(request)
    
    # 检查是否需要转人工
    if _should_transfer_to_human(message_type):
        return await _handle_human_service_request(request, message_type)
    
    # 处理具体业务
    return await _handle_business_process(request, message_type)


def _add_follow_up_to_result(result: ProcessingResult, language: str) -> ProcessingResult:
    """
    为结果添加后续询问，将finish状态改为working
    """
    if result.stage == ResponseStage.FINISH.value and result.transfer_human == 0:
        follow_up_message = get_follow_up_message(language)
        result.text = f"{result.text}\n{follow_up_message}"
        result.stage = ResponseStage.WORKING.value
    return result


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
    if request.type is not None and request.type != "":
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
        request.language,
        request.category
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
                               BusinessType.ACTIVITY_QUERY.value,
                               BusinessType.CHAT_SERVICE.value])


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
    elif message_type == BusinessType.CHAT_SERVICE.value:
        return await handle_chat_service(request)
    
    # 默认情况
    result = ProcessingResult(
        text="抱歉，无法处理您的请求。",
        transfer_human=1,
        stage=ResponseStage.FINISH.value,
        message_type=message_type
    )
    
    # 为非转人工的结果添加后续询问
    return _add_follow_up_to_result(result, request.language)


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
        # 没有预设业务类型，处理为闲聊
        logger.info(f"识别为0阶段，非{message_type}相关询问，处理为闲聊", extra={
            'session_id': request.session_id,
            'business_type': message_type,
            'stage': 0,
            'chat_mode': True
        })
        
        return await handle_chat_service(request)


def _build_response(request: MessageRequest, result: ProcessingResult, start_time: float) -> MessageResponse:
    """构建最终响应"""
    conversation_rounds = len(request.history or []) // 2
    
    logger.debug(f"构建最终响应", extra={
        'session_id': request.session_id,
        'response_stage': result.stage,
        'transfer_human': result.transfer_human,
        'has_images': bool(result.images),
        'response_length': len(result.text),
        'conversation_rounds': conversation_rounds
    })
    
    return MessageResponse(
        session_id=request.session_id,
        status="success",
        response=result.text,
        stage=result.stage,
        images=result.images,
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
    async def handle_image_upload(request: MessageRequest, status_messages: Dict, message_type: str) -> ProcessingResult:
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
            stage=ResponseStage.FINISH.value,
            message_type=message_type
        )
    
    @staticmethod
    async def handle_standard_stage(request: MessageRequest, stage_number: str, workflow: Dict, message_type: str) -> ProcessingResult:
        """处理标准阶段（1、2、4）"""
        step_info = workflow.get(stage_number, {})
        stage_response = step_info.get("response", {})
        stage_text = stage_response.get("text") or step_info.get("step", "")
        
        prompt = build_reply_with_prompt(request.history or [], request.messages, stage_text, request.language)
        response_text = await call_openapi_model(prompt=prompt)
        
        stage_images = stage_response.get("images", [])
        response_stage = ResponseStage.WORKING.value if stage_number in ["1", "2"] else ResponseStage.FINISH.value
        
        result = ProcessingResult(
            text=response_text,
            images=stage_images,
            stage=response_stage,
            message_type=message_type
        )
        
        # 为非转人工的结果添加后续询问
        return _add_follow_up_to_result(result, request.language)
    
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
                stage=ResponseStage.WORKING.value,
                message_type=business_type
            )


async def _handle_s001_process(request: MessageRequest, stage_number: int, workflow: Dict, 
                             status_messages: Dict, config: Dict) -> ProcessingResult:
    """处理S001充值查询流程"""
    # 检查图片上传
    if request.images and len(request.images) > 0:
        return await StageHandler.handle_image_upload(request, status_messages, BusinessType.RECHARGE_QUERY.value)
    
    # 标准阶段处理
    if str(stage_number) in ["1", "2", "4"]:
        return await StageHandler.handle_standard_stage(request, str(stage_number), workflow, BusinessType.RECHARGE_QUERY.value)
    
    # 阶段3：订单号查询处理
    elif str(stage_number) == "3":
        return await _handle_order_query_s001(request, status_messages, workflow)
    
    return ProcessingResult(
        text="未知阶段", 
        transfer_human=1, 
        stage=ResponseStage.FINISH.value,
        message_type=BusinessType.RECHARGE_QUERY.value
    )


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
    is_valid, error_message, error_type = validate_session_and_handle_errors(api_result, status_messages, request.language)
    if not is_valid:
        if error_type == "user_input":
            # state=886: 订单号不对，不转人工
            response_text = get_message_by_language(
                status_messages.get("invalid_order_number", {}), 
                request.language
            )
            return ProcessingResult(
                text=response_text,
                transfer_human=0,
                stage=ResponseStage.WORKING.value,
                message_type=BusinessType.RECHARGE_QUERY.value
            )
        else:
            # 系统错误，转人工
            return ProcessingResult(
                text=error_message,
                transfer_human=1,
                stage=ResponseStage.FINISH.value
            )
    
    # 处理查询结果
    extracted_data = extract_recharge_status(api_result)
    if not extracted_data["is_success"]:
        # A001接口能调通但查询失败，说明订单号不对，不转人工
        response_text = get_message_by_language(
            status_messages.get("invalid_order_number", {}), 
            request.language
        )
        return ProcessingResult(
            text=response_text,
            transfer_human=0,
            stage=ResponseStage.WORKING.value,
            message_type=BusinessType.RECHARGE_QUERY.value
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
    response_images = []
    if status == "Recharge successful":
        stage_4_info = workflow.get("4", {})
        response_images = stage_4_info.get("response", {}).get("images", [])
    
    # 生成最终回复
    prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
    final_text = await call_openapi_model(prompt=prompt)
    
    result = ProcessingResult(
        text=final_text,
        images=response_images,
        stage=stage,
        transfer_human=transfer_human
    )
    
    # 为非转人工的结果添加后续询问
    return _add_follow_up_to_result(result, request.language)


async def _handle_s002_process(request: MessageRequest, stage_number: int, workflow: Dict, 
                             status_messages: Dict, config: Dict) -> ProcessingResult:
    """处理S002提现查询流程"""
    # 检查图片上传
    if request.images and len(request.images) > 0:
        return await StageHandler.handle_image_upload(request, status_messages, BusinessType.WITHDRAWAL_QUERY.value)
    
    # 标准阶段处理
    if str(stage_number) in ["1", "2", "4"]:
        return await StageHandler.handle_standard_stage(request, str(stage_number), workflow, BusinessType.WITHDRAWAL_QUERY.value)
    
    # 阶段3：订单号查询处理
    elif str(stage_number) == "3":
        return await _handle_order_query_s002(request, status_messages, workflow, config)
    
    return ProcessingResult(
        text="未知阶段", 
        transfer_human=1, 
        stage=ResponseStage.FINISH.value,
        message_type=BusinessType.WITHDRAWAL_QUERY.value
    )


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
    is_valid, error_message, error_type = validate_session_and_handle_errors(api_result, status_messages, request.language)
    if not is_valid:
        if error_type == "user_input":
            # state=886: 订单号不对，不转人工
            response_text = get_message_by_language(
                status_messages.get("invalid_order_number", {}), 
                request.language
            )
            return ProcessingResult(
                text=response_text,
                transfer_human=0,
                stage=ResponseStage.WORKING.value,
                message_type=BusinessType.WITHDRAWAL_QUERY.value
            )
        else:
            # 系统错误，转人工
            return ProcessingResult(
                text=error_message,
                transfer_human=1,
                stage=ResponseStage.FINISH.value
            )
    
    # 处理查询结果
    extracted_data = extract_withdrawal_status(api_result)
    if not extracted_data["is_success"]:
        # A002接口能调通但查询失败，说明订单号不对，不转人工
        response_text = get_message_by_language(
            status_messages.get("invalid_order_number", {}), 
            request.language
        )
        return ProcessingResult(
            text=response_text,
            transfer_human=0,
            stage=ResponseStage.WORKING.value,
            message_type=BusinessType.WITHDRAWAL_QUERY.value
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
    response_images = []
    if status == "Withdrawal successful":
        stage_4_info = workflow.get("4", {})
        response_images = stage_4_info.get("response", {}).get("images", [])
    
    # 生成最终回复
    prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
    final_text = await call_openapi_model(prompt=prompt)
    
    result = ProcessingResult(
        text=final_text,
        images=response_images,
        stage=stage,
        transfer_human=transfer_human
    )
    
    # 为非转人工的结果添加后续询问
    return _add_follow_up_to_result(result, request.language)


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
            stage=ResponseStage.FINISH.value,
            message_type=BusinessType.ACTIVITY_QUERY.value
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
    
    is_valid, error_message, error_type = validate_session_and_handle_errors(api_result, status_messages, request.language)
    if not is_valid:
        if error_type == "user_input":
            # state=886: 活动信息提供不正确，不转人工
            response_text = get_message_by_language(
                status_messages.get("activity_not_found", {}), 
                request.language
            )
        else:
            # 系统错误，转人工
            response_text = error_message
            
        prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
        final_text = await call_openapi_model(prompt=prompt)
        return ProcessingResult(
            text=final_text,
            transfer_human=1 if error_type == "system" else 0,
            stage=ResponseStage.FINISH.value if error_type == "system" else ResponseStage.WORKING.value,
            message_type=BusinessType.ACTIVITY_QUERY.value
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
            stage=ResponseStage.FINISH.value,
            message_type=BusinessType.ACTIVITY_QUERY.value
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
        result = ProcessingResult(
            text=final_text,
            stage=ResponseStage.FINISH.value,
            message_type=BusinessType.ACTIVITY_QUERY.value
        )
        # 为非转人工的结果添加后续询问
        return _add_follow_up_to_result(result, request.language)
    
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
        # 基于category提供更精准的错误处理
        if request.category:
            category_value = list(request.category.values())[0] if request.category else None
            
            # 如果是特殊的不需要活动识别的情况，直接返回错误
            special_cases = [
                "Check agent commission", 
                "Check rebate bonus", 
                "Check spin promotion", 
                "Check VIP salary"
            ]
            
            if category_value in special_cases:
                # 这些情况应该由意图识别阶段处理，不应该到达这里
                response_text = get_message_by_language(
                    status_messages.get("activity_not_found", {}), 
                    request.language
                )
                return ProcessingResult(
                    text=response_text,
                    stage=ResponseStage.WORKING.value,
                    transfer_human=0,
                    message_type=BusinessType.ACTIVITY_QUERY.value
                )
        
        # 检查是否用户提供了具体的活动名称但找不到
        user_message = request.messages.strip()
        if len(user_message) > 10:  # 用户提供了较长的描述，可能是具体活动名称
            # 返回活动找不到的错误，让用户提供正确信息
            response_text = get_message_by_language(
                status_messages.get("activity_not_found", {}), 
                request.language
            )
            return ProcessingResult(
                text=response_text,
                stage=ResponseStage.WORKING.value,
                transfer_human=0,
                message_type=BusinessType.ACTIVITY_QUERY.value
            )
        else:
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
    
    # 构建基础prompt
    if request.language == "en":
        activity_prompt = f"""
Based on the user's message and activity list, identify the specific activity the user wants to query.

User message: {user_message}

{activity_list_text}
"""
        
        # 添加category信息作为活动识别的参考
        if request.category:
            activity_prompt += f"""
User intent category reference: {request.category}

Activity type guidance based on category:
- If category shows "Agent" → Focus on agent-related activities (代理/Agent commission, referral, etc.)
- If category shows "Rebate" → Focus on rebate-related activities (返水/Rebate bonus, cashback, etc.)  
- If category shows "Lucky Spin" → Focus on lucky spin/wheel activities (幸运转盘/Lucky draw, etc.)
- If category shows "All member" → Focus on VIP/member activities (VIP salary, member bonus, etc.)
- If category shows "Deposit" activities → Focus on deposit bonus activities
- If category shows "Sports" → Focus on sports betting activities

Note: Use the category as a reference to narrow down the activity type, but still match based on the actual user message content.
"""
        
        activity_prompt += """
Please analyze the user's message and find the most matching activity name from the activity list.
If the user's description is not clear enough or cannot match a specific activity, please reply "unclear".
If you find a matching activity, please return the complete activity name directly.
"""
    else:
        activity_prompt = f"""
根据用户的消息和活动列表，识别用户想要查询的具体活动。

用户消息：{user_message}

{activity_list_text}
"""
        
        # 添加category信息作为活动识别的参考
        if request.category:
            activity_prompt += f"""
用户意图分类参考：{request.category}

基于category的活动类型指导：
- 如果category显示"Agent" → 重点关注代理相关活动（代理佣金、代理推荐等）
- 如果category显示"Rebate" → 重点关注返水相关活动（返水奖金、现金返还等）
- 如果category显示"Lucky Spin" → 重点关注幸运转盘类活动（幸运抽奖、转盘等）
- 如果category显示"All member" → 重点关注VIP/会员活动（VIP工资、会员奖金等）
- 如果category显示"Deposit"相关 → 重点关注充值奖励活动
- 如果category显示"Sports" → 重点关注体育投注活动

注意：category仅作为参考来缩小活动类型范围，仍需基于用户的实际消息内容进行匹配。
"""
        
        activity_prompt += """
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
        stage=ResponseStage.WORKING.value,
        message_type=BusinessType.ACTIVITY_QUERY.value
    )


async def _query_user_activity_eligibility(request: MessageRequest, activity_name: str, 
                                         status_messages: Dict) -> ProcessingResult:
    """查询用户活动资格"""
    log_api_call("A004_query_user_eligibility", request.session_id, activity=activity_name)
    
    try:
        api_result = await query_user_eligibility(request.session_id, request.site)
        eligibility_data = extract_user_eligibility(api_result)
        
        if not eligibility_data["is_success"]:
            # A004接口能调通但查询失败，说明活动信息不对，不转人工
            response_text = get_message_by_language(
                status_messages.get("activity_not_found", {}), 
                request.language
            )
            return ProcessingResult(
                text=response_text,
                transfer_human=0,
                stage=ResponseStage.WORKING.value,
                message_type=BusinessType.ACTIVITY_QUERY.value
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
            stage=ResponseStage.FINISH.value,
            message_type=BusinessType.ACTIVITY_QUERY.value
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
    
    result = ProcessingResult(
        text=final_text,
        stage=stage,
        transfer_human=transfer_human,
        message_type=BusinessType.ACTIVITY_QUERY.value
    )
    
    # 为非转人工的结果添加后续询问
    return _add_follow_up_to_result(result, request.language)


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
    返回: (是否成功, 错误消息, 错误类型)
    错误类型: "user_input" - 用户输入问题, "system" - 系统问题
    """
    if not api_result:
        return False, get_message_by_language(
            status_messages.get("query_failed", {}), 
            language
        ), "system"
    
    # 检查API调用状态
    state = api_result.get("state", -1)
    
    if state == 886:  # Missing required parameters - 用户输入问题
        return False, "", "user_input"
    elif state != 0:  # 其他错误 - 系统问题
        return False, get_message_by_language(
            status_messages.get("query_failed", {}), 
            language
        ), "system"
    
    return True, "", None


async def identify_message_type(messages: str, language: str) -> str:
    """
    识别消息类型：正常闲聊 vs 不当言论
    
    Args:
        messages: 用户消息
        language: 语言
        
    Returns:
        str: "normal_chat" - 正常闲聊, "inappropriate" - 不当言论
    """
    logger = get_logger("chatai-api")
    
    if language == "en":
        prompt = f"""
You are a message classification assistant. Classify the user's message as either normal chat or inappropriate content.

User message: {messages}

Criteria for classification:
- "normal_chat": Friendly conversation, questions about general topics, greetings, polite inquiries
- "inappropriate": Abusive language, swearing, insults, nonsensical input, spam, harassment

Please respond with only "normal_chat" or "inappropriate".
"""
    elif language == "th":
        prompt = f"""
คุณเป็นผู้ช่วยจำแนกข้อความ จำแนกข้อความของผู้ใช้ว่าเป็นการสนทนาปกติหรือเนื้อหาที่ไม่เหมาะสม

ข้อความของผู้ใช้: {messages}

เกณฑ์การจำแนก:
- "normal_chat": การสนทนาที่เป็นมิตร คำถามเกี่ยวกับหัวข้อทั่วไป การทักทาย การสอบถามอย่างสุภาพ
- "inappropriate": ภาษาที่ดูหมิ่น การด่าทอ การดูถูก การป้อนข้อมูลที่ไร้สาระ สแปม การคุกคาม

กรุณาตอบเพียง "normal_chat" หรือ "inappropriate" เท่านั้น
"""
    elif language == "tl":
        prompt = f"""
Ikaw ay isang message classification assistant. I-classify ang mensahe ng user bilang normal chat o inappropriate content.

Mensahe ng user: {messages}

Criteria para sa classification:
- "normal_chat": Friendly na pag-uusap, mga tanong tungkol sa general topics, pagbati, magalang na pagtatanong
- "inappropriate": Masasamang salita, mura, pang-iinsulto, walang-senseng input, spam, harassment

Mangyaring tumugon lamang ng "normal_chat" o "inappropriate".
"""
    elif language == "ja":
        prompt = f"""
あなたはメッセージ分類アシスタントです。ユーザーのメッセージを通常のチャットか不適切なコンテンツかに分類してください。

ユーザーメッセージ: {messages}

分類基準:
- "normal_chat": 友好的な会話、一般的なトピックに関する質問、挨拶、丁寧な問い合わせ
- "inappropriate": 暴言、罵倒、侮辱、無意味な入力、スパム、嫌がらせ

"normal_chat"または"inappropriate"のみで回答してください。
"""
    else:  # 默认中文
        prompt = f"""
你是消息分类助手。将用户的消息分类为正常闲聊或不当言论。

用户消息：{messages}

分类标准：
- "normal_chat"：友好对话、一般性话题询问、问候、礼貌咨询
- "inappropriate"：辱骂语言、脏话、侮辱、无意义输入、垃圾信息、骚扰

请只回复"normal_chat"或"inappropriate"。
"""
    
    try:
        response = await call_openapi_model(prompt=prompt)
        result = response.strip().lower()
        return "normal_chat" if result == "normal_chat" else "inappropriate"
    except Exception as e:
        logger.error(f"消息类型识别失败", extra={
            'error': str(e),
            'message': messages[:100]
        })
        # 默认返回normal_chat，避免误判
        return "normal_chat"


async def handle_chat_service(request: MessageRequest) -> ProcessingResult:
    """
    处理闲聊服务
    
    Args:
        request: 用户请求
        
    Returns:
        ProcessingResult: 处理结果
    """
    logger = get_logger("chatai-api")
    conversation_rounds = len(request.history or []) // 2
    
    logger.info(f"处理闲聊服务", extra={
        'session_id': request.session_id,
        'conversation_rounds': conversation_rounds,
        'max_chat_rounds': Constants.MAX_CHAT_ROUNDS
    })
    
    # 检查是否超过闲聊轮数限制
    if conversation_rounds >= Constants.MAX_CHAT_ROUNDS:
        logger.info(f"闲聊轮数超过限制，结束对话", extra={
            'session_id': request.session_id,
            'conversation_rounds': conversation_rounds,
            'limit': Constants.MAX_CHAT_ROUNDS
        })
        
        end_message = get_message_by_language({
            "zh": "我们已经聊了很久了，感谢您的陪伴！如果您有任何业务问题需要帮助，欢迎随时联系我们。祝您生活愉快！",
            "en": "We've been chatting for a while, thank you for your company! If you have any business questions that need help, feel free to contact us anytime. Have a great day!",
            "th": "เราคุยกันมานานแล้ว ขอบคุณที่ให้เวลา! หากคุณมีคำถามทางธุรกิจที่ต้องการความช่วยเหลือ สามารถติดต่อเราได้ตลอดเวลา ขอให้มีความสุข!",
            "tl": "Matagal na nating nakakausap, salamat sa inyong oras! Kung may mga tanong kayo tungkol sa business na kailangan ng tulong, makipag-ugnayan sa amin anumang oras. Magkaroon ng magandang araw!",
            "ja": "長い間お話しできて、お時間をいただきありがとうございました！ビジネスに関するご質問がございましたら、いつでもお気軽にお声かけください。良い一日をお過ごしください！"
        }, request.language)
        
        return ProcessingResult(
            text=end_message,
            stage=ResponseStage.FINISH.value,
            transfer_human=0,
            message_type=BusinessType.CHAT_SERVICE.value
        )
    
    # 识别消息类型
    message_type = await identify_message_type(request.messages, request.language)
    
    if message_type == "inappropriate":
        # 处理不当言论
        logger.warning(f"检测到不当言论", extra={
            'session_id': request.session_id,
            'message_preview': request.messages[:50]
        })
        
        response_text = get_message_by_language({
            "zh": "请您理性表达，详细描述您遇到的问题，我很乐意为您提供帮助。有什么问题要帮您的？",
            "en": "Please express yourself rationally and describe your problem in detail. I'm happy to help you. Is there anything I can help you with?",
            "th": "โปรดแสดงออกอย่างมีเหตุผลและอธิบายปัญหาของคุณโดยละเอียด ฉันยินดีที่จะช่วยคุณ มีอะไรที่ฉันช่วยคุณได้ไหม?",
            "tl": "Mangyaring magpahayag nang makatuwiran at ilarawan ang inyong problema nang detalyado. Natutuwa akong tumulong sa inyo. May maitutulong ba ako sa inyo?",
            "ja": "理性的に表現し、問題を詳しく説明してください。喜んでお手伝いいたします。何かお手伝いできることはありますか？"
        }, request.language)
        
        return ProcessingResult(
            text=response_text,
            stage=ResponseStage.WORKING.value,
            transfer_human=0,
            message_type=BusinessType.CHAT_SERVICE.value
        )
    
    # 处理正常闲聊
    logger.info(f"处理正常闲聊", extra={
        'session_id': request.session_id,
        'conversation_rounds': conversation_rounds
    })
    
    # 构建闲聊回复的prompt
    if request.language == "en":
        chat_prompt = f"""
You are a friendly customer service assistant. The user is having a casual conversation with you. Please provide a warm, helpful response to their message and then ask if there's anything you can help them with.

User message: {request.messages}

Please respond naturally to their message first, then end with asking "Is there anything I can help you with?"

Keep your response friendly, concise, and professional.
"""
    elif request.language == "th":
        chat_prompt = f"""
คุณเป็นผู้ช่วยบริการลูกค้าที่เป็นมิตร ผู้ใช้กำลังสนทนาสบายๆ กับคุณ กรุณาให้การตอบกลับที่อบอุ่นและเป็นประโยชน์ต่อข้อความของพวกเขา จากนั้นถามว่ามีอะไรที่คุณสามารถช่วยได้หรือไม่

ข้อความของผู้ใช้: {request.messages}

กรุณาตอบสนองต่อข้อความของพวกเขาอย่างเป็นธรรมชาติก่อน จากนั้นจบด้วยการถาม "มีอะไรที่ฉันช่วยคุณได้ไหม?"

ให้การตอบกลับของคุณเป็นมิตร กระชับ และเป็นมืออาชีพ
"""
    elif request.language == "tl":
        chat_prompt = f"""
Ikaw ay isang friendly na customer service assistant. Ang user ay nakikipag-casual conversation sa iyo. Mangyaring magbigay ng mainit at nakakatulong na tugon sa kanilang mensahe at tanungin kung may maitutulong ka.

Mensahe ng user: {request.messages}

Mangyaring tumugon nang natural sa kanilang mensahe muna, tapos tapusin sa pagtatanong ng "May maitutulong ba ako sa inyo?"

Panatilihin ang inyong tugon na friendly, concise, at professional.
"""
    elif request.language == "ja":
        chat_prompt = f"""
あなたは親しみやすいカスタマーサービスアシスタントです。ユーザーはあなたとカジュアルな会話をしています。彼らのメッセージに温かく有用な回答を提供し、何かお手伝いできることがあるかを尋ねてください。

ユーザーメッセージ: {request.messages}

まず彼らのメッセージに自然に応答し、最後に「何かお手伝いできることはありますか？」と尋ねて終わってください。

回答は親しみやすく、簡潔で、プロフェッショナルに保ってください。
"""
    else:  # 默认中文
        chat_prompt = f"""
你是一个友好的客服助手。用户正在与你进行闲聊对话。请对他们的消息提供温暖、有帮助的回复，然后询问有什么可以帮助他们的。

用户消息：{request.messages}

请首先自然地回应他们的消息，然后以询问"有什么问题要帮您的？"结尾。

保持你的回复友好、简洁、专业。
"""
    
    try:
        response_text = await call_openapi_model(prompt=chat_prompt)
        
        # 确保回复以询问结尾
        help_question = get_message_by_language({
            "zh": "有什么问题要帮您的？",
            "en": "Is there anything I can help you with?",
            "th": "มีอะไรที่ฉันช่วยคุณได้ไหม?",
            "tl": "May maitutulong ba ako sa inyo?",
            "ja": "何かお手伝いできることはありますか？"
        }, request.language)
        
        if not any(keyword in response_text for keyword in ["有什么问题要帮您的", "Is there anything I can help you with", "มีอะไรที่ฉันช่วยคุณได้ไหม", "May maitutulong ba ako sa inyo", "何かお手伝いできることはありますか"]):
            response_text = f"{response_text} {help_question}"
        
        return ProcessingResult(
            text=response_text,
            stage=ResponseStage.WORKING.value,
            transfer_human=0,
            message_type=BusinessType.CHAT_SERVICE.value
        )
        
    except Exception as e:
        logger.error(f"闲聊回复生成失败", extra={
            'session_id': request.session_id,
            'error': str(e)
        })
        
        # 回退到简单回复
        fallback_response = get_message_by_language({
            "zh": "感谢您的消息！有什么问题要帮您的？",
            "en": "Thank you for your message! Is there anything I can help you with?",
            "th": "ขอบคุณสำหรับข้อความของคุณ! มีอะไรที่ฉันช่วยคุณได้ไหม?",
            "tl": "Salamat sa inyong mensahe! May maitutulong ba ako sa inyo?",
            "ja": "メッセージをありがとうございます！何かお手伝いできることはありますか？"
        }, request.language)
        
        return ProcessingResult(
            text=fallback_response,
            stage=ResponseStage.WORKING.value,
            transfer_human=0,
            message_type=BusinessType.CHAT_SERVICE.value
        ) 