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
        response = await _build_response(request, result, start_time)
        
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
                transfer_human=1,  # 用户满意结束对话时转人工，便于人工进行后续服务或关闭工单
                message_type=request.type or ""
            )
    
    # 首先检查是否为明确的deposit/withdrawal没到账问题
    explicit_business_type = await check_explicit_not_received_inquiry(str(request.messages), request.language)
    if explicit_business_type:
        logger.info(f"检测到明确的没到账问题，直接进入{explicit_business_type}流程", extra={
            'session_id': request.session_id,
            'business_type': explicit_business_type,
            'user_message': str(request.messages)[:100]
        })
        request.type = explicit_business_type
        return await _handle_business_process(request, explicit_business_type)
    
    # 然后检查是否为模糊的deposit/withdrawal询问
    ambiguous_type = await check_ambiguous_inquiry(str(request.messages), request.language)
    if ambiguous_type:
        return await handle_ambiguous_inquiry(ambiguous_type, request)
    
    # 检查是否为澄清后的回复（用户之前收到过模糊询问的回复）
    if request.history and len(request.history) >= 2:
        # 检查历史记录中是否有模糊询问的回复
        last_ai_message = None
        for message in reversed(request.history):
            if message.get("role") == "assistant":
                last_ai_message = message.get("content", "")
                break
        
        if last_ai_message and ("请问您具体想了解什么" in last_ai_message or 
                              "Could you please be more specific" in last_ai_message or
                              "คุณช่วยบอกให้ชัดเจนกว่านี้" in last_ai_message or
                              "maging mas specific" in last_ai_message or
                              "もう少し具体的に" in last_ai_message):
            # 检查是否有对应的模糊类型
            if "充值" in last_ai_message or "deposit" in last_ai_message or "ฝาก" in last_ai_message or "入金" in last_ai_message:
                return await handle_clarified_inquiry(request, "deposit_ambiguous")
            elif "提现" in last_ai_message or "withdrawal" in last_ai_message or "ถอน" in last_ai_message or "出金" in last_ai_message:
                return await handle_clarified_inquiry(request, "withdrawal_ambiguous")
    
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
    
    # 检查是否有category信息，如果有活动相关的category则直接识别为活动查询
    if hasattr(request, 'category') and request.category:
        activity_categories = ["Agent", "Rebate", "Lucky Spin", "All member", "Sports"]
        category_str = str(request.category)
        if any(cat in category_str for cat in activity_categories):
            logger.info(f"基于category信息识别为活动查询", extra={
                'session_id': request.session_id,
                'category': request.category,
                'identified_type': BusinessType.ACTIVITY_QUERY.value
            })
            return BusinessType.ACTIVITY_QUERY.value
    
    # 检查历史对话中是否有业务类型上下文，如果当前消息是订单号
    current_message = str(request.messages).strip()
    if len(current_message) == Constants.ORDER_NUMBER_LENGTH and current_message.isdigit():
        # 当前消息是18位订单号，检查历史对话判断业务类型
        if request.history:
            for message in request.history:
                content = message.get("content", "").lower()
                # 检查充值相关关键词
                deposit_keywords = ["deposit", "recharge", "充值", "ฝาก", "入金", "mag-deposit"]
                withdrawal_keywords = ["withdrawal", "withdraw", "提现", "ถอน", "出金", "mag-withdraw"]
                
                if any(keyword in content for keyword in deposit_keywords):
                    logger.info(f"根据历史对话和订单号识别为充值查询", extra={
                        'session_id': request.session_id,
                        'order_no': current_message,
                        'identified_type': BusinessType.RECHARGE_QUERY.value
                    })
                    return BusinessType.RECHARGE_QUERY.value
                elif any(keyword in content for keyword in withdrawal_keywords):
                    logger.info(f"根据历史对话和订单号识别为提现查询", extra={
                        'session_id': request.session_id,
                        'order_no': current_message,
                        'identified_type': BusinessType.WITHDRAWAL_QUERY.value
                    })
                    return BusinessType.WITHDRAWAL_QUERY.value
    
    # 进行意图识别
    logger.debug(f"未指定业务类型，开始意图识别", extra={
        'session_id': request.session_id,
        'user_message': str(request.messages)[:100] + '...' if len(str(request.messages)) > 100 else str(request.messages)
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
        request.history or [],
        request.category  # 传递category信息辅助stage识别
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


async def _build_response(request: MessageRequest, result: ProcessingResult, start_time: float) -> MessageResponse:
    """构建最终响应"""
    conversation_rounds = len(request.history or []) // 2
    
    # 优先使用request.type，如果没有则使用result.message_type
    response_type = request.type if request.type is not None and request.type != "" else result.message_type
    
    # 语言保障机制：在最终返回前，统一用目标语言重新生成回复
    final_response_text = result.text
    if result.text and not result.transfer_human:  # 只有非转人工的情况才需要语言保障
        try:
            # 检查是否是业务查询的状态结果
            is_business_status = response_type in [BusinessType.RECHARGE_QUERY.value, BusinessType.WITHDRAWAL_QUERY.value]
            
            # 检查是否包含明确的状态信息，如果是则跳过语言保障避免改变状态信息
            status_indicators = [
                "successful", "failed", "pending", "canceled", "rejected", 
                "成功", "失败", "处理中", "已取消", "已拒绝",
                "สำเร็จ", "ล้มเหลว", "รอดำเนินการ", "ยกเลิก", "ปฏิเสธ",
                "tagumpay", "nabigo", "naghihintay", "nakansela", "tinanggihan",
                "成功", "失敗", "処理中", "キャンセル", "拒否"
            ]
            
            has_status_info = any(indicator in result.text for indicator in status_indicators)
            
            if has_status_info and is_business_status:
                # 如果包含状态信息，不进行语言保障以保持准确性
                logger.debug(f"检测到状态信息，跳过语言保障机制", extra={
                    'session_id': request.session_id,
                    'contains_status': True,
                    'skip_language_guarantee': True
                })
                final_response_text = result.text
            else:
                # 构建增强的prompt来确保语言正确性，同时保持状态信息的准确性
                language_guarantee_prompt = build_reply_with_prompt(
                    request.history or [], 
                    request.messages, 
                    result.text, 
                    request.language,
                    is_status_result=is_business_status  # 传递状态标识
                )
                # 调用AI模型重新生成，确保语言正确
                final_response_text = await call_openapi_model(prompt=language_guarantee_prompt)
                
                logger.debug(f"语言保障机制已执行", extra={
                    'session_id': request.session_id,
                    'target_language': request.language,
                    'original_length': len(result.text),
                    'final_length': len(final_response_text),
                    'is_business_status': is_business_status,
                    'applied_language_guarantee': True
                })
        except Exception as e:
            # 如果语言保障失败，使用原始回复
            logger.warning(f"语言保障机制执行失败，使用原始回复", extra={
                'session_id': request.session_id,
                'error': str(e),
                'fallback_to_original': True
            })
            final_response_text = result.text
    
    logger.debug(f"构建最终响应", extra={
        'session_id': request.session_id,
        'response_stage': result.stage,
        'transfer_human': result.transfer_human,
        'has_images': bool(result.images),
        'response_length': len(final_response_text),
        'conversation_rounds': conversation_rounds,
        'request_type': request.type,
        'result_message_type': result.message_type,
        'final_type': response_type,
        'target_language': request.language
    })
    
    return MessageResponse(
        session_id=request.session_id,
        status="success",
        response=final_response_text,
        stage=result.stage,
        images=result.images,
        metadata={
            "intent": response_type,
            "timestamp": time.time(),
            "conversation_rounds": conversation_rounds,
            "max_rounds": Constants.MAX_CONVERSATION_ROUNDS,
            "has_preset_type": request.type is not None,
            "processing_time": round(time.time() - start_time, 3),
            "language_guaranteed": True  # 标记已应用语言保障机制
        },
        site=request.site,
        type=response_type,
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
        
        stage_images = stage_response.get("images", [])
        response_stage = ResponseStage.WORKING.value if stage_number in ["1", "2"] else ResponseStage.FINISH.value
        
        result = ProcessingResult(
            text=stage_text,
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
    
    # 优先检查当前消息是否包含18位订单号，如果包含则直接进入stage 3处理
    current_message_order_no = extract_order_no(request.messages, [])  # 只检查当前消息，不包括历史
    if current_message_order_no:
        logger.info(f"检测到当前消息包含18位订单号，直接进入stage 3处理", extra={
            'session_id': request.session_id,
            'order_no': current_message_order_no,
            'original_stage': stage_number,
            'override_to_stage': 3
        })
        return await _handle_order_query_s001(request, status_messages, workflow)
    
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
    
    logger.info(f"S001订单查询开始", extra={
        'session_id': request.session_id,
        'extracted_order_no': order_no,
        'user_message': request.messages
    })
    
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
        logger.info(f"A001 API调用完成", extra={
            'session_id': request.session_id,
            'order_no': order_no,
            'api_result': api_result
        })
    except Exception as e:
        logger.error(f"A001接口调用异常", extra={
            'session_id': request.session_id,
            'order_no': order_no,
            'error': str(e)
        }, exc_info=True)
        api_result = None
    
    # 验证API结果
    is_valid, error_message, error_type = validate_session_and_handle_errors(api_result, status_messages, request.language)
    logger.info(f"API结果验证", extra={
        'session_id': request.session_id,
        'is_valid': is_valid,
        'error_message': error_message,
        'error_type': error_type
    })
    
    if not is_valid:
        if error_type == "user_input":
            # state=886: 订单号不对，不转人工
            response_text = get_message_by_language(
                status_messages.get("invalid_order_number", {}), 
                request.language
            )
            logger.info(f"订单号验证失败，返回错误消息", extra={
                'session_id': request.session_id,
                'response_text': response_text
            })
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
    logger.info(f"数据提取完成", extra={
        'session_id': request.session_id,
        'extracted_data': extracted_data
    })
    
    if not extracted_data["is_success"]:
        # 根据不同的错误类型处理
        error_status = extracted_data["status"]
        
        if error_status in ["api_failed", "extraction_error", "no_status_data"]:
            # 这些是系统或数据格式问题，转人工
            response_text = get_message_by_language(
                status_messages.get("query_failed", {}), 
                request.language
            )
            logger.warning(f"系统错误，转人工处理", extra={
                'session_id': request.session_id,
                'error_status': error_status,
                'error_message': extracted_data["message"]
            })
            return ProcessingResult(
                text=response_text,
                transfer_human=1,
                stage=ResponseStage.FINISH.value,
                message_type=BusinessType.RECHARGE_QUERY.value
            )
        else:
            # 其他错误，可能是订单号问题，不转人工
            response_text = get_message_by_language(
                status_messages.get("invalid_order_number", {}), 
                request.language
            )
            logger.info(f"可能的用户输入错误，不转人工", extra={
                'session_id': request.session_id,
                'error_status': error_status,
                'response_text': response_text
            })
            return ProcessingResult(
                text=response_text,
                transfer_human=0,
                stage=ResponseStage.WORKING.value,
                message_type=BusinessType.RECHARGE_QUERY.value
            )
    
    # 根据状态处理
    logger.info(f"查询成功，处理状态", extra={
        'session_id': request.session_id,
        'status': extracted_data["status"]
    })
    return await _process_recharge_status(extracted_data["status"], status_messages, workflow, request)


async def _process_recharge_status(status: str, status_messages: Dict, workflow: Dict, 
                                 request: MessageRequest) -> ProcessingResult:
    """处理充值状态"""
    logger.info(f"开始处理充值状态", extra={
        'session_id': request.session_id,
        'status': status,
        'available_status_messages': list(status_messages.keys())
    })
    
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
    
    logger.info(f"状态映射结果", extra={
        'session_id': request.session_id,
        'input_status': status,
        'mapped_message_key': message_key,
        'mapped_stage': stage,
        'mapped_transfer_human': transfer_human
    })
    
    response_text = get_message_by_language(
        status_messages.get(message_key, {}), 
        request.language
    )
    
    logger.info(f"获取到的回复文本", extra={
        'session_id': request.session_id,
        'message_key': message_key,
        'response_text': response_text,
        'language': request.language
    })
    
    # 添加成功状态的图片
    response_images = []
    if status == "Recharge successful":
        stage_4_info = workflow.get("4", {})
        response_images = stage_4_info.get("response", {}).get("images", [])
    
    result = ProcessingResult(
        text=response_text,
        images=response_images,
        stage=stage,
        transfer_human=transfer_human
    )
    
    logger.info(f"充值状态处理完成", extra={
        'session_id': request.session_id,
        'final_result': {
            'text_length': len(result.text),
            'stage': result.stage,
            'transfer_human': result.transfer_human,
            'has_images': bool(result.images)
        }
    })
    
    # 为非转人工的结果添加后续询问
    return _add_follow_up_to_result(result, request.language)


async def _handle_s002_process(request: MessageRequest, stage_number: int, workflow: Dict, 
                             status_messages: Dict, config: Dict) -> ProcessingResult:
    """处理S002提现查询流程"""
    # 检查图片上传
    if request.images and len(request.images) > 0:
        return await StageHandler.handle_image_upload(request, status_messages, BusinessType.WITHDRAWAL_QUERY.value)
    
    # 优先检查当前消息是否包含18位订单号，如果包含则直接进入stage 3处理
    current_message_order_no = extract_order_no(request.messages, [])  # 只检查当前消息，不包括历史
    if current_message_order_no:
        logger.info(f"检测到当前消息包含18位订单号，直接进入stage 3处理", extra={
            'session_id': request.session_id,
            'order_no': current_message_order_no,
            'original_stage': stage_number,
            'override_to_stage': 3
        })
        return await _handle_order_query_s002(request, status_messages, workflow, config)
    
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
    
    result = ProcessingResult(
        text=response_text,
        images=response_images,
        stage=stage,
        transfer_human=transfer_human
    )
    
    # 为非转人工的结果添加后续询问
    return _add_follow_up_to_result(result, request.language)


async def _send_telegram_notification(config: Dict, request: MessageRequest, order_no: str, status: str) -> None:
    """发送Telegram通知"""
    bot_token = config.get("telegram_bot_token", "")
    telegram_config = config.get("telegram_notifications", {})
    
    # 根据状态选择对应的群和消息内容
    if status == "confiscate":
        chat_id = telegram_config.get("confiscate_chat_id", "")
        tg_message = f"🚨 资金没收\n用户ID: {request.user_id}\n订单号: {order_no}\n状态: {status}"
        notification_type = "confiscate"
    elif status == "Withdrawal failed":
        chat_id = telegram_config.get("payment_failed_chat_id", "")
        tg_message = f"⚠️ 支付失败\n用户ID: {request.user_id}\n订单号: {order_no}\n状态: {status}"
        notification_type = "payment_failed"
    else:
        # 其他状态默认发到支付失败群
        chat_id = telegram_config.get("payment_failed_chat_id", "")
        tg_message = f"⚠️ 异常状态\n用户ID: {request.user_id}\n订单号: {order_no}\n状态: {status}"
        notification_type = "payment_failed"
    
    if bot_token and chat_id:
        try:
            logger.info(f"发送Telegram通知", extra={
                'session_id': request.session_id,
                'status': status,
                'chat_id': chat_id,
                'user_id': request.user_id,
                'order_no': order_no,
                'notification_type': notification_type
            })
            await send_to_telegram([], bot_token, chat_id, username=request.user_id, custom_message=tg_message)
        except Exception as e:
            logger.error(f"TG异常通知发送失败", extra={
                'session_id': request.session_id,
                'status': status,
                'chat_id': chat_id,
                'error': str(e)
            })
    else:
        logger.warning(f"Telegram通知配置不完整，跳过发送", extra={
            'session_id': request.session_id,
            'status': status,
            'has_bot_token': bool(bot_token),
            'has_chat_id': bool(chat_id),
            'notification_type': notification_type
        })


async def _handle_s003_process(request: MessageRequest, stage_number: int, 
                             status_messages: Dict, config: Dict) -> ProcessingResult:
    """处理S003活动查询流程"""
    
    # 优先检查是否有category信息，如果有则直接处理，无论stage是什么
    if hasattr(request, 'category') and request.category:
        activity_categories = ["Agent", "Rebate", "Lucky Spin", "All member", "Sports"]
        category_str = str(request.category)
        if any(cat in category_str for cat in activity_categories):
            logger.info(f"检测到有效的活动category，直接处理活动查询", extra={
                'session_id': request.session_id,
                'category': request.category,
                'stage_number': stage_number,
                'bypass_stage_check': True
            })
            return await _handle_category_based_activity_query(request, status_messages)
    
    # 没有category信息或category无效，按stage处理
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


async def _handle_category_based_activity_query(request: MessageRequest, status_messages: Dict) -> ProcessingResult:
    """
    处理基于category的活动查询（前端选择的特定活动）
    先调用A003确认活动在列表中，再查询A004用户资格
    
    Args:
        request: 用户请求
        status_messages: 状态消息
        
    Returns:
        ProcessingResult: 处理结果
    """
    logger = get_logger("chatai-api")
    
    logger.info(f"处理基于category的活动查询", extra={
        'session_id': request.session_id,
        'category': request.category,
        'user_message': request.messages
    })
    
    # 从category中提取活动名称
    activity_name = None
    if isinstance(request.category, dict):
        # category格式: {"Agent": "Yesterday Dividends"}
        for category_type, activity in request.category.items():
            if activity:
                activity_name = activity
                break
    elif isinstance(request.category, str):
        # 如果category是字符串，直接使用
        activity_name = request.category
    
    # 如果没有从category中获取到活动名称，尝试从消息中获取
    if not activity_name:
        activity_name = str(request.messages).strip()
    
    if not activity_name:
        # 没有具体活动名称，转为常规活动查询
        logger.warning(f"无法从category中提取活动名称，转为常规查询", extra={
            'session_id': request.session_id,
            'category': request.category
        })
        return await _handle_activity_query(request, status_messages)
    
    logger.info(f"提取到活动名称，开始验证活动是否存在", extra={
        'session_id': request.session_id,
        'activity_name': activity_name,
        'source': 'category'
    })
    
    # 第一步：调用A003查询活动列表，确认活动是否存在
    log_api_call("A003_query_activity_list", request.session_id)
    try:
        api_result = await query_activity_list(request.session_id, request.site)
    except Exception as e:
        logger.error(f"A003接口调用异常", extra={
            'session_id': request.session_id,
            'error': str(e)
        }, exc_info=True)
        api_result = None
    
    # 验证API结果
    is_valid, error_message, error_type = validate_session_and_handle_errors(api_result, status_messages, request.language)
    if not is_valid:
        logger.error(f"A003接口调用失败", extra={
            'session_id': request.session_id,
            'error_type': error_type,
            'error_message': error_message
        })
        # API失败，转人工处理
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
    
    # 解析活动列表
    extracted_data = extract_activity_list(api_result)
    if not extracted_data["is_success"]:
        logger.error(f"A003活动列表解析失败", extra={
            'session_id': request.session_id,
            'extracted_data': extracted_data
        })
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
    
    # 构建所有活动列表
    all_activities = []
    all_activities.extend(extracted_data["agent_activities"])
    all_activities.extend(extracted_data["deposit_activities"])
    all_activities.extend(extracted_data["rebate_activities"])
    all_activities.extend(extracted_data["lucky_spin_activities"])
    all_activities.extend(extracted_data["all_member_activities"])
    all_activities.extend(extracted_data["sports_activities"])
    
    # 检查活动是否在列表中（不区分大小写匹配）
    activity_found = False
    matched_activity_name = activity_name
    
    # 首先尝试精确匹配
    if activity_name in all_activities:
        activity_found = True
        matched_activity_name = activity_name
    else:
        # 精确匹配失败，尝试不区分大小写匹配
        activity_name_lower = activity_name.lower()
        for available_activity in all_activities:
            if available_activity.lower() == activity_name_lower:
                activity_found = True
                matched_activity_name = available_activity  # 使用API返回的准确名称
                logger.info(f"通过不区分大小写匹配找到活动", extra={
                    'session_id': request.session_id,
                    'input_activity': activity_name,
                    'matched_activity': available_activity
                })
                break
    
    if not activity_found:
        logger.warning(f"活动不在A003返回的活动列表中", extra={
            'session_id': request.session_id,
            'activity_name': activity_name,
            'available_activities': all_activities,
            'activity_count': len(all_activities)
        })
        
        response_text = get_message_by_language(
            status_messages.get("activity_not_found", {}), 
            request.language
        )
        return ProcessingResult(
            text=response_text,
            transfer_human=1,
            stage=ResponseStage.FINISH.value,
            message_type=BusinessType.ACTIVITY_QUERY.value
        )
    
    logger.info(f"活动在A003列表中，继续查询A004用户资格", extra={
        'session_id': request.session_id,
        'activity_name': matched_activity_name,
        'original_input': activity_name,
        'confirmed_in_list': True
    })
    
    # 第二步：活动确认存在，查询用户资格（使用匹配到的准确名称）
    return await _query_user_activity_eligibility(request, matched_activity_name, status_messages)


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
            
        return ProcessingResult(
            text=response_text,
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
        return ProcessingResult(
            text=response_text,
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
        result = ProcessingResult(
            text=response_text,
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
    if identified_activity.strip().lower() == "unclear":
        return await _handle_unclear_activity(request, status_messages, activity_list_text)
    
    # 检查活动是否在列表中（精确匹配）
    exact_match = None
    for activity in all_activities:
        if identified_activity.strip() == activity:
            exact_match = activity
            break
    
    if exact_match:
        # 精确匹配到活动，直接查询
        return await _query_user_activity_eligibility(request, exact_match, status_messages)
    
    # 没有精确匹配，尝试模糊匹配
    similar_activities = await _find_similar_activities(identified_activity.strip(), all_activities, request.language)
    
    if similar_activities:
        # 找到相似活动，请用户确认
        return await _request_activity_confirmation(request, identified_activity.strip(), similar_activities, status_messages)
    else:
        # 完全不在活动列表中，转人工
        logger.warning(f"活动不在列表中，转人工处理", extra={
            'session_id': request.session_id,
            'user_input': identified_activity.strip(),
            'available_activities': len(all_activities),
            'transfer_reason': 'activity_not_in_list'
        })
        
        response_text = get_message_by_language(
            status_messages.get("activity_not_found", {}), 
            request.language
        )
        return ProcessingResult(
            text=response_text,
            stage=ResponseStage.FINISH.value,
            transfer_human=1,
            message_type=BusinessType.ACTIVITY_QUERY.value
        )


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
- If category shows "Agent" → Focus on agent-related activities like "Yesterday Dividends", "Weekly Dividends", "Monthly Dividends", "Realtime rebate"
- If category shows "Rebate" → Focus on rebate-related activities like "Daily Rebate bonus", "Weekly Rebate bonus", "Monthly Rebate bonus"  
- If category shows "Lucky Spin" → Focus on lucky spin activities like "Lucky Spin Jackpot"
- If category shows "All member" → Focus on VIP/member activities like "VIP Weekly salary", "VIP Monthly salary"
- If category shows "Sports" → Focus on sports betting related activities

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
- 如果category显示"Agent" → 重点关注代理相关活动，如"Yesterday Dividends"、"Weekly Dividends"、"Monthly Dividends"、"Realtime rebate"
- 如果category显示"Rebate" → 重点关注返水相关活动，如"Daily Rebate bonus"、"Weekly Rebate bonus"、"Monthly Rebate bonus"
- 如果category显示"Lucky Spin" → 重点关注幸运转盘活动，如"Lucky Spin Jackpot"
- 如果category显示"All member" → 重点关注VIP/会员活动，如"VIP Weekly salary"、"VIP Monthly salary"
- 如果category显示"Sports" → 重点关注体育投注相关活动

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
    
    return ProcessingResult(
        text=response_text,
        stage=ResponseStage.WORKING.value,
        message_type=BusinessType.ACTIVITY_QUERY.value
    )


async def _find_similar_activities(user_input: str, all_activities: List[str], language: str) -> List[str]:
    """
    查找与用户输入相似的活动
    
    Args:
        user_input: 用户输入的活动名称
        all_activities: 所有可用活动列表
        language: 语言
        
    Returns:
        相似活动列表（最多3个）
    """
    if language == "en":
        prompt = f"""
You are an activity matching assistant. Find activities from the activity list that are similar to the user's input.

User input: {user_input}

Available activities:
{chr(10).join([f"{i+1}. {activity}" for i, activity in enumerate(all_activities)])}

Please find activities that are semantically similar to the user's input. Consider:
- Similar keywords or themes
- Activities that might be what the user meant despite typos or different wording
- Related activity types

Return only the exact activity names that are similar, one per line. Maximum 3 results.
If no similar activities are found, return "none".
"""
    else:  # 默认中文
        prompt = f"""
你是活动匹配助手。从活动列表中找出与用户输入相似的活动。

用户输入：{user_input}

可用活动：
{chr(10).join([f"{i+1}. {activity}" for i, activity in enumerate(all_activities)])}

请找出与用户输入语义相似的活动。考虑：
- 相似的关键词或主题
- 用户可能因为拼写错误或不同表达方式想要的活动
- 相关的活动类型

只返回相似的确切活动名称，每行一个。最多3个结果。
如果没有找到相似活动，返回"none"。
"""
    
    try:
        response = await call_openapi_model(prompt=prompt)
        lines = response.strip().split('\n')
        
        similar_activities = []
        for line in lines:
            line = line.strip()
            if line and line.lower() != "none":
                # 移除可能的编号前缀
                if '. ' in line:
                    line = line.split('. ', 1)[1]
                
                # 确保活动在原始列表中
                if line in all_activities:
                    similar_activities.append(line)
        
        return similar_activities[:3]  # 最多返回3个
        
    except Exception as e:
        logger.error(f"相似活动匹配失败", extra={
            'error': str(e),
            'user_input': user_input
        })
        return []


async def _request_activity_confirmation(request: MessageRequest, user_input: str, 
                                       similar_activities: List[str], status_messages: Dict) -> ProcessingResult:
    """
    请求用户确认是否是相似的活动
    
    Args:
        request: 用户请求
        user_input: 用户原始输入
        similar_activities: 相似活动列表
        status_messages: 状态消息
        
    Returns:
        ProcessingResult: 处理结果
    """
    logger.info(f"找到相似活动，请求用户确认", extra={
        'session_id': request.session_id,
        'user_input': user_input,
        'similar_activities': similar_activities,
        'similar_count': len(similar_activities)
    })
    
    # 构建确认消息
    if request.language == "en":
        confirmation_text = f"I couldn't find the exact activity '{user_input}', but I found these similar activities:\n\n"
        for i, activity in enumerate(similar_activities, 1):
            confirmation_text += f"{i}. {activity}\n"
        confirmation_text += "\nIs one of these the activity you're looking for? Please specify which one."
    else:  # 默认中文
        confirmation_text = f"我没有找到完全匹配的活动 '{user_input}'，但找到了这些相似的活动：\n\n"
        for i, activity in enumerate(similar_activities, 1):
            confirmation_text += f"{i}. {activity}\n"
        confirmation_text += "\n请问其中有您要查询的活动吗？请明确指出是哪一个。"
    
    return ProcessingResult(
        text=confirmation_text,
        stage=ResponseStage.WORKING.value,
        transfer_human=0,
        message_type=BusinessType.ACTIVITY_QUERY.value
    )


async def _query_user_activity_eligibility(request: MessageRequest, activity_name: str, 
                                         status_messages: Dict) -> ProcessingResult:
    """查询用户活动资格"""
    log_api_call("A004_query_user_eligibility", request.session_id, activity=activity_name)
    
    try:
        api_result = await query_user_eligibility(request.session_id, activity_name, request.site)
        
        logger.info(f"A004接口调用完成", extra={
            'session_id': request.session_id,
            'activity_name': activity_name,
            'api_result': api_result
        })
        
        eligibility_data = extract_user_eligibility(api_result)
        
        logger.info(f"A004数据提取完成", extra={
            'session_id': request.session_id,
            'activity_name': activity_name,
            'eligibility_data': eligibility_data
        })
        
        if not eligibility_data["is_success"]:
            # A004接口能调通但查询失败，由于活动已通过A003验证存在，这里应该是系统问题
            logger.error(f"A004查询失败，但活动已通过A003验证存在", extra={
                'session_id': request.session_id,
                'activity_name': activity_name,
                'eligibility_data': eligibility_data,
                'error_reason': 'a004_query_failed_after_a003_validation'
            })
            
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
        
        # 处理资格状态
        return await _process_activity_eligibility(eligibility_data, status_messages, request)
        
    except Exception as e:
        logger.error(f"A004接口调用异常", extra={
            'session_id': request.session_id,
            'activity_name': activity_name,
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
    
    result = ProcessingResult(
        text=response_text,
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
    
    # 处理messages - 支持更多类型
    if messages is not None:
        if isinstance(messages, list):
            all_text += " ".join([str(m) for m in messages])
        elif isinstance(messages, dict):
            # 如果是字典，尝试提取文本内容
            if 'content' in messages:
                all_text += str(messages['content'])
            elif 'text' in messages:
                all_text += str(messages['text'])
            else:
                all_text += str(messages)
        else:
            all_text += str(messages)
    
    # 处理history
    if history:
        for turn in history:
            if isinstance(turn, dict):
                content = turn.get("content", "")
                all_text += " " + str(content)
            else:
                all_text += " " + str(turn)
    
    logger.debug(f"提取到的文本内容", extra={
        'all_text': all_text[:200] + '...' if len(all_text) > 200 else all_text,
        'text_length': len(all_text)
    })
    
    # 找到所有连续的数字序列
    number_sequences = re.findall(r'\d+', all_text)
    
    logger.debug(f"找到的数字序列", extra={
        'sequences': number_sequences[:10],  # 只显示前10个，避免日志过长
        'sequence_count': len(number_sequences),
        'sequence_lengths': [len(seq) for seq in number_sequences[:10]]
    })
    
    # 优先查找恰好18位的数字序列
    eighteen_digit_sequences = [seq for seq in number_sequences if len(seq) == Constants.ORDER_NUMBER_LENGTH]
    
    if eighteen_digit_sequences:
        # 如果有多个18位数字，取第一个（通常是用户最新提供的）
        order_no = eighteen_digit_sequences[0]
        logger.info(f"成功提取18位订单号", extra={
            'order_no': order_no,
            'source_text_length': len(all_text),
            'extraction_successful': True,
            'found_count': len(eighteen_digit_sequences),
            'extraction_method': 'exact_match'
        })
        return order_no
    
    # 如果没有找到18位数字，尝试更aggressive的匹配
    # 移除所有非数字字符，看是否能组成18位数字
    digits_only = re.sub(r'\D', '', all_text)
    if len(digits_only) == Constants.ORDER_NUMBER_LENGTH:
        logger.info(f"通过移除非数字字符提取到18位订单号", extra={
            'order_no': digits_only,
            'original_text': all_text[:100] + '...' if len(all_text) > 100 else all_text,
            'extraction_method': 'digits_only'
        })
        return digits_only
    
    # 尝试查找接近18位的数字序列（17-19位），可能是用户输入时的小错误
    close_sequences = [seq for seq in number_sequences if 17 <= len(seq) <= 19]
    if close_sequences:
        logger.warning(f"找到接近18位的数字序列", extra={
            'close_sequences': close_sequences,
            'sequence_lengths': [len(seq) for seq in close_sequences],
            'original_text': all_text[:100] + '...' if len(all_text) > 100 else all_text
        })
    
    logger.warning(f"未找到18位订单号", extra={
        'found_sequences': len(number_sequences),
        'sequence_lengths': [len(seq) for seq in number_sequences[:10]],
        'digits_only_length': len(digits_only),
        'digits_only_preview': digits_only[:20] + '...' if len(digits_only) > 20 else digits_only,
        'original_messages': str(messages)[:200] if messages else None
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
            'user_message': messages[:100]
        })
        # 默认返回normal_chat，避免误判
        return "normal_chat"


async def identify_customer_service_question(messages: str, language: str) -> str:
    """
    识别是否为客服问题：正常闲聊 vs 客服问题
    
    Args:
        messages: 用户消息
        language: 语言
        
    Returns:
        str: "normal_chat" - 正常闲聊, "customer_service" - 客服问题, "ai_handled" - AI可处理的问题
    """
    logger = get_logger("chatai-api")
    
    # AI可以处理的问题（不需要转人工）
    ai_handled_keywords = [
        "withdrawal not received", "提现未到账", "ยังไม่ได้รับการถอน", "hindi pa natatanggap ang withdrawal", "出金が届いていない",
        "deposit not received", "充值未到账", "ยังไม่ได้รับการฝาก", "hindi pa natatanggap ang deposit", "入金が届いていない",
        "check agent commission", "查询代理佣金", "ตรวจสอบค่าคอมมิชชั่นตัวแทน", "tingnan ang commission ng agent", "エージェントコミッションを確認",
        "check rebate bonus", "查询返水奖金", "ตรวจสอบโบนัสคืน", "tingnan ang rebate bonus", "リベートボーナスを確認",
        "check spin promotion", "查询转盘活动", "ตรวจสอบโปรโมชั่นหมุน", "tingnan ang spin promotion", "スピンプロモーションを確認",
        "check vip salary", "查询vip工资", "ตรวจสอบเงินเดือน VIP", "tingnan ang VIP salary", "VIP給与を確認"
    ]
    
    # 需要转人工的客服问题关键词
    customer_service_keywords = [
        # Withdrawal相关
        "withdrawal options", "withdrawal problem", "withdrawal prohibited", "withdrawal", "提现选项", "提现问题", "提现被禁止", "提现",
        "ตัวเลือกการถอน", "ปัญหาการถอน", "ถอนเงินถูกห้าม", "การถอน",
        "mga option sa withdrawal", "problema sa withdrawal", "ipinagbawal ang withdrawal", "withdrawal",
        "出金オプション", "出金問題", "出金禁止", "出金",
        
        # Deposit相关  
        "followup deposit", "payment options", "payment problem", "deposit", "后续充值", "支付选项", "支付问题", "充值",
        "ติดตามการฝาก", "ตัวเลือกการชำระเงิน", "ปัญหาการชำระเงิน", "การฝาก",
        "sundan ang deposit", "mga option sa payment", "problema sa payment", "deposit",
        "フォローアップ入金", "支払いオプション", "支払い問題", "入金",
        
        # Account相关
        "how to register", "otp problem", "forgot username", "forgot password", "kyc", "add bank", "delete bank", 
        "scam report", "hacked account", "login issue", "如何注册", "otp问题", "忘记用户名", "忘记密码", "实名认证", "添加银行", "删除银行",
        "诈骗举报", "账户被盗", "登录问题",
        "วิธีการลงทะเบียน", "ปัญหา OTP", "ลืมชื่อผู้ใช้", "ลืมรหัสผ่าน", "การยืนยันตัวตน", "เพิ่มธนาคาร", "ลบธนาคาร",
        "รายงานการฉ้อโกง", "บัญชีถูกแฮก", "ปัญหาการเข้าสู่ระบบ",
        "paano mag-register", "problema sa otp", "nakalimutan ang username", "nakalimutan ang password", "kyc", "magdagdag ng bank", "magtanggal ng bank",
        "report ng scam", "na-hack na account", "problema sa login",
        "登録方法", "OTP問題", "ユーザー名を忘れた", "パスワードを忘れた", "本人確認", "銀行追加", "銀行削除",
        "詐欺報告", "アカウントハッキング", "ログイン問題",
        
        # Affiliate Agent相关
        "agent commission", "agent referral", "agent bonus", "become an agent", "affiliate team", "ppa official link",
        "代理佣金", "代理推荐", "代理奖金", "成为代理", "代理团队", "官方链接",
        "ค่าคอมมิชชั่นตัวแทน", "การอ้างอิงตัวแทน", "โบนัสตัวแทน", "เป็นตัวแทน", "ทีมพันธมิตร", "ลิงก์อย่างเป็นทางการ",
        "commission ng agent", "referral ng agent", "bonus ng agent", "maging agent", "affiliate team", "official link ng ppa",
        "エージェントコミッション", "エージェント紹介", "エージェントボーナス", "エージェントになる", "アフィリエイトチーム", "公式リンク"
    ]
    
    # 先检查是否是AI可处理的问题
    message_lower = messages.lower()
    for keyword in ai_handled_keywords:
        if keyword.lower() in message_lower:
            logger.info(f"识别为AI可处理的问题", extra={
                'user_message': messages[:100],
                'matched_keyword': keyword
            })
            return "ai_handled"
    
    if language == "en":
        prompt = f"""
You are a customer service question classifier. Determine if the user's message is a normal chat or a customer service question.

User message: {messages}

Customer service question categories include:
- Withdrawal issues (except "withdrawal not received" which AI handles)
- Deposit issues (except "deposit not received" which AI handles)  
- Account problems (registration, login, KYC, bank account management)
- Affiliate/Agent questions (except commission checks which AI handles)
- Payment problems
- Security issues

Normal chat includes:
- General conversation
- Greetings
- Weather, sports, entertainment topics
- Personal life discussions

Respond with only:
- "normal_chat" - for casual conversation
- "customer_service" - for questions that need human customer service

Focus on the intent behind the message, not just keywords.
"""
    elif language == "th":
        prompt = f"""
คุณเป็นผู้จำแนกคำถามบริการลูกค้า ให้กำหนดว่าข้อความของผู้ใช้เป็นการแชทธรรมดาหรือคำถามบริการลูกค้า

ข้อความของผู้ใช้: {messages}

หมวดหมู่คำถามบริการลูกค้าประกอบด้วย:
- ปัญหาการถอน (ยกเว้น "ยังไม่ได้รับการถอน" ที่ AI จัดการ)
- ปัญหาการฝาก (ยกเว้น "ยังไม่ได้รับการฝาก" ที่ AI จัดการ)
- ปัญหาบัญชี (การลงทะเบียน, การเข้าสู่ระบบ, KYC, การจัดการบัญชีธนาคาร)
- คำถามพันธมิตร/ตัวแทน (ยกเว้นการตรวจสอบค่าคอมมิชชั่นที่ AI จัดการ)
- ปัญหาการชำระเงิน
- ปัญหาความปลอดภัย

การแชทธรรมดาประกอบด้วย:
- การสนทนาทั่วไป
- การทักทาย
- หัวข้อเกี่ยวกับสภาพอากาศ, กีฬา, บันเทิง
- การพูดคุยเรื่องส่วนตัว

ตอบเพียง:
- "normal_chat" - สำหรับการสนทนาสบายๆ
- "customer_service" - สำหรับคำถามที่ต้องการบริการลูกค้าจากมนุษย์

มุ่งเน้นไปที่เจตนาเบื้องหลังข้อความ ไม่ใช่แค่คำสำคัญ
"""
    elif language == "tl":
        prompt = f"""
Ikaw ay isang customer service question classifier. Tukuyin kung ang mensahe ng user ay normal na chat o customer service question.

Mensahe ng user: {messages}

Ang mga kategorya ng customer service question ay kasama ang:
- Mga problema sa withdrawal (maliban sa "hindi pa natatanggap ang withdrawal" na hinahawakan ng AI)
- Mga problema sa deposit (maliban sa "hindi pa natatanggap ang deposit" na hinahawakan ng AI)
- Mga problema sa account (registration, login, KYC, bank account management)
- Mga tanong sa Affiliate/Agent (maliban sa commission checks na hinahawakan ng AI)
- Mga problema sa payment
- Mga isyu sa security

Ang normal na chat ay kasama ang:
- General na pag-uusap
- Pagbati
- Weather, sports, entertainment na mga paksa
- Personal life na mga diskusyon

Tumugon lamang ng:
- "normal_chat" - para sa casual conversation
- "customer_service" - para sa mga tanong na kailangan ng human customer service

Tumuon sa intent sa likod ng mensahe, hindi lang sa mga keyword.
"""
    elif language == "ja":
        prompt = f"""
あなたはカスタマーサービス質問分類器です。ユーザーのメッセージが通常のチャットかカスタマーサービスの質問かを判断してください。

ユーザーメッセージ: {messages}

カスタマーサービス質問のカテゴリには以下が含まれます：
- 出金問題（AIが処理する「出金が届いていない」を除く）
- 入金問題（AIが処理する「入金が届いていない」を除く）
- アカウント問題（登録、ログイン、KYC、銀行口座管理）
- アフィリエイト/エージェント質問（AIが処理するコミッション確認を除く）
- 支払い問題
- セキュリティ問題

通常のチャットには以下が含まれます：
- 一般的な会話
- 挨拶
- 天気、スポーツ、エンターテイメントの話題
- 個人的な生活の議論

以下のみで回答してください：
- "normal_chat" - カジュアルな会話の場合
- "customer_service" - 人間のカスタマーサービスが必要な質問の場合

キーワードだけでなく、メッセージの背後にある意図に焦点を当ててください。
"""
    else:  # 默认中文
        prompt = f"""
你是客服问题分类器。判断用户的消息是正常闲聊还是客服问题。

用户消息：{messages}

客服问题类别包括：
- 提现问题（除了AI处理的"提现未到账"）
- 充值问题（除了AI处理的"充值未到账"）
- 账户问题（注册、登录、实名认证、银行账户管理）
- 代理/联盟问题（除了AI处理的佣金查询）
- 支付问题
- 安全问题

正常闲聊包括：
- 一般性对话
- 问候
- 天气、体育、娱乐话题
- 个人生活讨论

请只回复：
- "normal_chat" - 休闲对话
- "customer_service" - 需要人工客服的问题

重点关注消息背后的意图，而不仅仅是关键词。
"""
    
    try:
        response = await call_openapi_model(prompt=prompt)
        result = response.strip().lower()
        
        # 如果模型无法准确判断，使用关键词辅助判断
        if result not in ["normal_chat", "customer_service"]:
            message_lower = messages.lower()
            for keyword in customer_service_keywords:
                if keyword.lower() in message_lower:
                    logger.info(f"通过关键词识别为客服问题", extra={
                        'user_message': messages[:100],
                        'matched_keyword': keyword
                    })
                    return "customer_service"
            return "normal_chat"
        
        return result
    except Exception as e:
        logger.error(f"客服问题识别失败", extra={
            'error': str(e),
            'user_message': messages[:100]
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
            transfer_human=0
        )
    
    # 先识别是否为不当言论
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
            transfer_human=0
        )
    
    # 识别是否为客服问题
    service_question_type = await identify_customer_service_question(request.messages, request.language)
    
    if service_question_type == "ai_handled":
        # AI可以处理的问题，但在闲聊模式下，引导用户使用具体业务功能
        logger.info(f"识别为AI可处理的问题，但在闲聊模式下引导用户", extra={
            'session_id': request.session_id,
            'message_preview': request.messages[:50]
        })
        
        response_text = get_message_by_language({
            "zh": "我理解您想查询相关信息。为了更好地为您服务，建议您点击相应的功能按钮进行具体查询，这样我可以为您提供更准确的信息。如果有其他问题，我也很乐意帮助您！",
            "en": "I understand you want to check related information. For better service, I suggest you click the corresponding function button for specific inquiries, so I can provide you with more accurate information. If you have other questions, I'm happy to help!",
            "th": "ฉันเข้าใจว่าคุณต้องการตรวจสอบข้อมูลที่เกี่ยวข้อง เพื่อการบริการที่ดีขึ้น ฉันแนะนำให้คุณคลิกปุ่มฟังก์ชั่นที่เกี่ยวข้องเพื่อสอบถามเฉพาะเจาะจง เพื่อที่ฉันจะได้ให้ข้อมูลที่แม่นยำกว่า หากมีคำถามอื่นๆ ฉันยินดีช่วยเหลือ!",
            "tl": "Naiintindihan ko na gusto ninyong tingnan ang kaugnay na impormasyon. Para sa mas magandang serbisyo, inirerekomenda kong i-click ninyo ang kaukulang function button para sa mga tukoy na pagtatanong, para mas tumpak ang impormasyon na maibibigay ko. Kung may iba pang mga tanong, masayang tutulong!",
            "ja": "関連情報を確認したいということですね。より良いサービスのために、対応する機能ボタンをクリックして具体的にお問い合わせいただくことをお勧めします。そうすればより正確な情報を提供できます。他にもご質問があれば、喜んでお手伝いします！"
        }, request.language)
        
        return ProcessingResult(
            text=response_text,
            stage=ResponseStage.WORKING.value,
            transfer_human=0
        )
    
    elif service_question_type == "customer_service":
        # 需要人工客服的问题，直接转人工
        logger.info(f"闲聊中识别为客服问题，转人工处理", extra={
            'session_id': request.session_id,
            'message_preview': request.messages[:50],
            'transfer_reason': 'customer_service_question_in_chat'
        })
        
        response_text = get_message_by_language({
            "zh": "我理解您的问题需要专业的客服协助。现在为您转接人工客服，请稍等片刻。",
            "en": "I understand your question requires professional customer service assistance. I'm now transferring you to a human agent, please wait a moment.",
            "th": "ฉันเข้าใจว่าคำถามของคุณต้องการความช่วยเหลือจากบริการลูกค้าที่เป็นมืออาชีพ ตอนนี้กำลังโอนให้กับเจ้าหน้าที่ กรุณารอสักครู่",
            "tl": "Naiintindihan ko na ang inyong tanong ay nangangailangan ng propesyonal na customer service assistance. Inililipat ko na kayo sa human agent, mangyaring maghintay saglit.",
            "ja": "お客様のご質問には専門のカスタマーサービスによるサポートが必要だと理解いたします。人間のエージェントにお繋ぎいたしますので、少々お待ちください。"
        }, request.language)
        
        return ProcessingResult(
            text=response_text,
            stage=ResponseStage.FINISH.value,
            transfer_human=1
        )
    
    # 处理正常闲聊
    logger.info(f"处理正常闲聊", extra={
        'session_id': request.session_id,
        'conversation_rounds': conversation_rounds
    })
    
    # 构建闲聊回复的prompt
    if request.language == "en":
        chat_prompt = f"""
You are a friendly customer service assistant. The user is having a casual conversation with you. Please provide a warm, helpful response to their message.

User message: {request.messages}

Please respond naturally to their message. Keep your response friendly, concise, and professional.
DO NOT add any question like "Is there anything I can help you with?" at the end - we will handle that separately.
"""
    elif request.language == "th":
        chat_prompt = f"""
คุณเป็นผู้ช่วยบริการลูกค้าที่เป็นมิตร ผู้ใช้กำลังสนทนาสบายๆ กับคุณ กรุณาให้การตอบกลับที่อบอุ่นและเป็นประโยชน์ต่อข้อความของพวกเขา

ข้อความของผู้ใช้: {request.messages}

กรุณาตอบสนองต่อข้อความของพวกเขาอย่างเป็นธรรมชาติ ให้การตอบกลับของคุณเป็นมิตร กระชับ และเป็นมืออาชีพ
อย่าเพิ่มคำถามเช่น "มีอะไรที่ฉันช่วยคุณได้ไหม?" ต่อท้าย - เราจะจัดการส่วนนั้นแยกต่างหาก
"""
    elif request.language == "tl":
        chat_prompt = f"""
Ikaw ay isang friendly na customer service assistant. Ang user ay nakikipag-casual conversation sa iyo. Mangyaring magbigay ng mainit at nakakatulong na tugon sa kanilang mensahe.

Mensahe ng user: {request.messages}

Mangyaring tumugon nang natural sa kanilang mensahe. Panatilihin ang inyong tugon na friendly, concise, at professional.
HUWAG magdagdag ng tanong tulad ng "May maitutulong ba ako sa inyo?" sa dulo - hahawakin namin yun hiwalay.
"""
    elif request.language == "ja":
        chat_prompt = f"""
あなたは親しみやすいカスタマーサービスアシスタントです。ユーザーはあなたとカジュアルな会話をしています。彼らのメッセージに温かく有用な回答を提供してください。

ユーザーメッセージ: {request.messages}

彼らのメッセージに自然に応答してください。回答は親しみやすく、簡潔で、プロフェッショナルに保ってください。
最後に「何かお手伝いできることはありますか？」のような質問を追加しないでください - それは別途処理します。
"""
    else:  # 默认中文
        chat_prompt = f"""
你是一个友好的客服助手。用户正在与你进行闲聊对话。请对他们的消息提供温暖、有帮助的回复。

用户消息：{request.messages}

请自然地回应他们的消息。保持你的回复友好、简洁、专业。
不要在结尾添加"有什么问题要帮您的？"之类的询问 - 我们会单独处理那部分。
"""
    
    try:
        response_text = await call_openapi_model(prompt=chat_prompt)
        
        # 添加询问，但要智能地检查是否已经包含
        help_questions = {
            "zh": ["有什么问题要帮您的？", "有什么可以帮助您的吗？", "还有其他问题吗？"],
            "en": ["Is there anything I can help you with?", "Can I help you with anything else?", "Do you have any other questions?"],
            "th": ["มีอะไรที่ฉันช่วยคุณได้ไหม?", "มีอะไรอื่นที่ฉันช่วยได้ไหม?", "คุณมีคำถามอื่นไหม?"],
            "tl": ["May maitutulong ba ako sa inyo?", "May iba pa bang maitutulong ko?", "May iba pa bang tanong?"],
            "ja": ["何かお手伝いできることはありますか？", "他に何かお手伝いできることはありますか？", "他にご質問はありますか？"]
        }
        
        # 检查回复是否已经包含类似的询问
        current_questions = help_questions.get(request.language, help_questions["zh"])
        already_has_question = any(
            question.lower() in response_text.lower() or
            any(word in response_text.lower() for word in question.lower().split() if len(word) > 2)
            for question in current_questions
        )
        
        if not already_has_question:
            help_question = get_message_by_language({
                "zh": "有什么问题要帮您的？",
                "en": "Is there anything I can help you with?",
                "th": "มีอะไรที่ฉันช่วยคุณได้ไหม?",
                "tl": "May maitutulong ba ako sa inyo?",
                "ja": "何かお手伝いできることはありますか？"
            }, request.language)
            response_text = f"{response_text} {help_question}"
        
        return ProcessingResult(
            text=response_text,
            stage=ResponseStage.WORKING.value,
            transfer_human=0
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
            transfer_human=0
        ) 


async def check_explicit_not_received_inquiry(messages: str, language: str) -> Optional[str]:
    """
    检查用户是否明确表达了deposit/withdrawal没到账的问题
    
    Args:
        messages: 用户消息
        language: 语言
        
    Returns:
        Optional[str]: 如果是明确的没到账问题，返回业务类型("S001" 或 "S002")，否则返回None
    """
    logger = get_logger("chatai-api")
    
    message_lower = messages.lower().strip()
    
    # 明确的没到账关键词组合
    explicit_not_received_patterns = {
        "deposit": {
            "zh": ["充值没到账", "充值未到账", "充值没收到", "存款没到账", "存款未到账", "deposit没到账", "deposit没收到", "充钱没到账"],
            "en": ["deposit not received", "deposit didn't arrive", "haven't received deposit", "didn't get deposit", "deposit missing", "deposit not credited", "i don't receive my deposit", "i dont receive my deposit"],
            "th": ["เงินฝากไม่ได้รับ", "ฝากเงินแล้วไม่ถึง", "deposit ไม่ได้รับ"],
            "tl": ["deposit hindi natatanggap", "hindi natatanggap ang deposit", "walang natanggap na deposit", "hindi pumasok deposit", "hindi dumating deposit", "hindi pa pumasok deposit", "deposit ko hindi pumasok"],
            "ja": ["入金が届いていない", "入金が受け取れない", "depositが届いていない"]
        },
        "withdrawal": {
            "zh": ["提现没到账", "提现未到账", "提现没收到", "出金没到账", "出金未到账", "withdrawal没到账", "withdrawal没收到", "取钱没到账"],
            "en": ["withdrawal not received", "withdrawal didn't arrive", "haven't received withdrawal", "didn't get withdrawal", "withdrawal missing", "withdrawal not credited", "i don't receive my withdrawal", "i dont receive my withdrawal"],
            "th": ["เงินถอนไม่ได้รับ", "ถอนเงินแล้วไม่ถึง", "withdrawal ไม่ได้รับ"],
            "tl": ["withdrawal hindi natatanggap", "hindi natatanggap ang withdrawal", "walang natanggap na withdrawal", "hindi pumasok withdrawal", "hindi dumating withdrawal", "hindi pa pumasok withdrawal", "withdrawal ko hindi pumasok"],
            "ja": ["出金が届いていない", "出金が受け取れない", "withdrawalが届いていない"]
        }
    }
    
    # 检查明确的没到账表述
    for biz_type, patterns in explicit_not_received_patterns.items():
        current_patterns = patterns.get(language, patterns["en"])
        for pattern in current_patterns:
            if pattern.lower() in message_lower:
                business_code = "S001" if biz_type == "deposit" else "S002"
                logger.info(f"检测到明确的{biz_type}没到账问题", extra={
                    'user_message': messages,
                    'matched_pattern': pattern,
                    'business_type': business_code
                })
                return business_code
    
    return None


async def check_ambiguous_inquiry(messages: str, language: str) -> Optional[str]:
    """
    检查用户是否提出了模糊的deposit/withdrawal询问
    
    Args:
        messages: 用户消息
        language: 语言
        
    Returns:
        Optional[str]: 如果是模糊询问，返回业务类型("deposit_ambiguous" 或 "withdrawal_ambiguous")，否则返回None
    """
    logger = get_logger("chatai-api")
    
    message_lower = messages.lower().strip()
    
    # 定义模糊关键词
    ambiguous_keywords = {
        "deposit": {
            "zh": ["充值", "充钱", "存钱"],
            "en": ["deposit", "recharge", "top up"],
            "th": ["เติมเงิน", "ฝากเงิน"],
            "tl": ["mag-deposit", "deposit", "pag-deposit"],
            "ja": ["入金", "チャージ"]
        },
        "withdrawal": {
            "zh": ["提现", "取钱", "出金"],
            "en": ["withdraw", "withdrawal", "cash out"],
            "th": ["ถอนเงิน"],
            "tl": ["mag-withdraw", "withdrawal", "pag-withdraw"],
            "ja": ["出金", "引き出し"]
        }
    }
    
    # 明确的查询关键词，这些不算模糊询问
    specific_keywords = {
        "zh": ["没到账", "未到账", "没收到", "没有到", "什么时候到", "怎么操作", "如何操作", "订单号", "状态", "查询", "充值没到账", "充值未到账", "充值没收到", "提现没到账", "提现未到账", "提现没收到"],
        "en": ["not received", "haven't received", "didn't receive", "when will", "how to", "order number", "status", "check", "deposit not received", "deposit didn't arrive", "withdrawal not received", "withdrawal didn't arrive", "i don't receive", "i dont receive"],
        "th": ["ไม่ได้รับ", "ยังไม่ได้", "เมื่อไหร่", "วิธีการ", "หมายเลขคำสั่ง", "สถานะ", "เงินฝากไม่ได้รับ", "เงินถอนไม่ได้รับ"],
        "tl": ["hindi natatanggap", "hindi pa", "kailan", "paano", "order number", "status", "deposit hindi natatanggap", "withdrawal hindi natatanggap", "hindi pumasok", "hindi dumating"],
        "ja": ["届いていない", "受け取っていない", "いつ", "方法", "注文番号", "状況", "入金が届いていない", "出金が届いていない"]
    }
    
    # 如果包含明确的查询关键词，不算模糊询问
    current_specific = specific_keywords.get(language, specific_keywords["en"])
    if any(keyword in message_lower for keyword in current_specific):
        return None
    
    # 检查是否只是简单提到了deposit或withdrawal
    for biz_type, keywords in ambiguous_keywords.items():
        current_keywords = keywords.get(language, keywords["en"])
        for keyword in current_keywords:
            if keyword.lower() in message_lower:
                # 检查是否只是简单提到关键词，而没有具体问题
                # 如果消息很短且只包含关键词，认为是模糊询问
                words = message_lower.split()
                if len(words) <= 3 and any(word == keyword.lower() for word in words):
                    logger.info(f"检测到模糊{biz_type}询问", extra={
                        'user_message': messages,
                        'matched_keyword': keyword,
                        'business_type': biz_type
                    })
                    return f"{biz_type}_ambiguous"
    
    return None


async def handle_ambiguous_inquiry(business_type: str, request: MessageRequest) -> ProcessingResult:
    """
    处理模糊的业务询问，提供具体选项，并增加重试标记
    
    Args:
        business_type: "deposit_ambiguous" 或 "withdrawal_ambiguous"
        request: 用户请求
        
    Returns:
        ProcessingResult: 处理结果
    """
    logger = get_logger("chatai-api")
    
    logger.info(f"处理模糊业务询问", extra={
        'session_id': request.session_id,
        'business_type': business_type,
        'user_message': request.messages
    })
    
    # 检查是否已经是第二次尝试（特别针对菲律宾语）
    conversation_rounds = len(request.history or []) // 2
    is_retry = False
    
    if request.history and conversation_rounds >= 1:
        # 检查历史中是否有过模糊询问的回复
        for message in request.history:
            if message.get("role") == "assistant":
                content = message.get("content", "")
                if ("请问您具体想了解什么" in content or 
                    "Could you please be more specific" in content or
                    "คุณช่วยบอกให้ชัดเจนกว่านี้" in content or
                    "maging mas specific" in content or
                    "もう少し具体的に" in content):
                    is_retry = True
                    break
    
    # 如果是菲律宾语且是重试，直接转人工
    if is_retry and request.language == "tl":
        logger.info(f"菲律宾语用户第二次模糊询问，直接转人工", extra={
            'session_id': request.session_id,
            'business_type': business_type,
            'transfer_reason': 'filipino_language_second_attempt'
        })
        
        response_text = get_message_by_language({
            "tl": "Pasensya na, mukhang may kumplikadong tanong kayo tungkol sa deposit/withdrawal. Ililipat ko kayo sa customer service para sa mas detalyadong tulong.",
            "zh": "抱歉，看起来您的充值/提现问题比较复杂，已为您转接人工客服获得更详细的帮助。",
            "en": "Sorry, it seems you have a complex deposit/withdrawal question. I'll transfer you to customer service for more detailed assistance."
        }, request.language)
        
        return ProcessingResult(
            text=response_text,
            stage=ResponseStage.FINISH.value,
            transfer_human=1,
            message_type="human_service"
        )
    
    is_deposit = business_type == "deposit_ambiguous"
    business_name = "充值" if is_deposit else "提现"
    
    if request.language == "en":
        business_name_en = "deposit" if is_deposit else "withdrawal"
        response_text = f"""What specific help do you need with {business_name_en}?

1. {business_name_en.capitalize()} not received
2. How to {business_name_en}
3. Other {business_name_en} questions

Please choose an option or describe your issue."""
        
    elif request.language == "th":
        business_name_th = "การฝากเงิน" if is_deposit else "การถอนเงิน"
        response_text = f"""คุณต้องการความช่วยเหลือเรื่องอะไรเกี่ยวกับ{business_name_th}?

1. {'เงินฝาก' if is_deposit else 'เงินถอน'}ยังไม่ได้รับ
2. วิธีการ{'ฝากเงิน' if is_deposit else 'ถอนเงิน'}
3. คำถามอื่นๆ เกี่ยวกับ{business_name_th}

กรุณาเลือกตัวเลือกหรือบอกปัญหาของคุณ"""
        
    elif request.language == "tl":
        business_name_tl = "deposit" if is_deposit else "withdrawal"
        response_text = f"""Anong specific na tulong ang kailangan ninyo sa {business_name_tl}?

1. Hindi pa natatanggap ang {business_name_tl}
2. Paano mag-{business_name_tl}
3. Iba pang tanong tungkol sa {business_name_tl}

Mangyaring pumili ng option o ilarawan ang inyong problema."""
        
    elif request.language == "ja":
        business_name_ja = "入金" if is_deposit else "出金"
        response_text = f"""{business_name_ja}について具体的にどのようなサポートが必要ですか？

1. {business_name_ja}が届いていない
2. {business_name_ja}の方法について
3. その他の{business_name_ja}関連の質問

選択肢を選ぶか、具体的な問題を説明してください。"""
        
    else:  # 默认中文
        response_text = f"""您需要什么{business_name}方面的帮助？

1. {business_name}没到账
2. 怎么{business_name}
3. 其他{business_name}问题

请选择选项或详细描述您的问题。"""
    
    return ProcessingResult(
        text=response_text,
        stage=ResponseStage.WORKING.value,
        transfer_human=0,
        message_type=business_type
    )


async def handle_clarified_inquiry(request: MessageRequest, original_ambiguous_type: str) -> ProcessingResult:
    """
    处理用户澄清后的询问
    
    Args:
        request: 用户请求
        original_ambiguous_type: 原始的模糊业务类型
        
    Returns:
        ProcessingResult: 处理结果
    """
    logger = get_logger("chatai-api")
    
    logger.info(f"处理澄清后的询问", extra={
        'session_id': request.session_id,
        'original_type': original_ambiguous_type,
        'user_message': request.messages
    })
    
    message_lower = request.messages.lower().strip()
    is_deposit = original_ambiguous_type == "deposit_ambiguous"
    
    # 检查用户选择了哪个选项 - 注意选项顺序已调整
    not_received_keywords = {
        "zh": ["1", "没到账", "未到账", "没收到", "没有到"],
        "en": ["1", "not received", "haven't received", "didn't receive"],
        "th": ["1", "ไม่ได้รับ", "ยังไม่ได้"],
        "tl": ["1", "hindi natatanggap", "hindi pa"],
        "ja": ["1", "届いていない", "受け取っていない"]
    }
    
    how_to_keywords = {
        "zh": ["2", "怎么", "如何", "方法"],
        "en": ["2", "how to", "how do", "method"],
        "th": ["2", "วิธีการ", "อย่างไร"],
        "tl": ["2", "paano", "method"],
        "ja": ["2", "方法", "どうやって"]
    }
    
    other_keywords = {
        "zh": ["3", "其他", "别的"],
        "en": ["3", "other", "else"],
        "th": ["3", "อื่นๆ", "อื่น"],
        "tl": ["3", "iba", "other"],
        "ja": ["3", "その他", "他の"]
    }
    
    current_not_received = not_received_keywords.get(request.language, not_received_keywords["en"])
    current_how_to = how_to_keywords.get(request.language, how_to_keywords["en"])
    current_other = other_keywords.get(request.language, other_keywords["en"])
    
    # 选择1：没到账 - 现在是第一个选项
    if any(keyword in message_lower for keyword in current_not_received):
        # 进入对应的业务流程
        business_type = "S001" if is_deposit else "S002"
        logger.info(f"用户选择{('充值' if is_deposit else '提现')}没到账，进入{business_type}流程", extra={
            'session_id': request.session_id,
            'choice': 'not_received',
            'business_type': business_type
        })
        
        # 设置请求类型并处理
        request.type = business_type
        return await _handle_business_process(request, business_type)
    
    # 选择2：怎么操作 - 现在是第二个选项
    elif any(keyword in message_lower for keyword in current_how_to):
        # 转人工处理操作指导
        logger.info(f"用户选择操作指导，转人工处理", extra={
            'session_id': request.session_id,
            'choice': 'how_to',
            'transfer_reason': 'user_requested_operation_guide'
        })
        
        response_text = get_message_by_language({
            "zh": f"关于如何{('充值' if is_deposit else '提现')}的操作步骤，我为您转接人工客服来详细指导。",
            "en": f"For guidance on how to {'deposit' if is_deposit else 'withdraw'}, I'll transfer you to customer service for detailed instructions.",
            "th": f"เพื่อคำแนะนำในการ{'ฝากเงิน' if is_deposit else 'ถอนเงิน'} ฉันจะโอนคุณไปยังฝ่ายบริการลูกค้าเพื่อคำแนะนำโดยละเอียด",
            "tl": f"Para sa gabay kung paano mag-{'deposit' if is_deposit else 'withdraw'}, ililipat kita sa customer service para sa detalyadong tagubilin.",
            "ja": f"{'入金' if is_deposit else '出金'}方法についてのガイダンスのため、詳細な指示についてカスタマーサービスにお繋ぎします。"
        }, request.language)
        
        return ProcessingResult(
            text=response_text,
            stage=ResponseStage.FINISH.value,
            transfer_human=1,
            message_type="human_service"
        )
    
    # 选择3：其他问题
    elif any(keyword in message_lower for keyword in current_other):
        # 转人工处理
        logger.info(f"用户选择其他问题，转人工处理", extra={
            'session_id': request.session_id,
            'choice': 'other',
            'transfer_reason': 'user_selected_other_issues'
        })
        
        response_text = get_message_by_language({
            "zh": f"关于其他{('充值' if is_deposit else '提现')}相关问题，我为您转接人工客服来协助处理。",
            "en": f"For other {'deposit' if is_deposit else 'withdrawal'} related questions, I'll transfer you to customer service for assistance.",
            "th": f"สำหรับคำถามอื่นๆ ที่เกี่ยวข้องกับ{'การฝาก' if is_deposit else 'การถอน'} ฉันจะโอนคุณไปยังฝ่ายบริการลูกค้าเพื่อความช่วยเหลือ",
            "tl": f"Para sa ibang mga tanong na related sa {'deposit' if is_deposit else 'withdrawal'}, ililipat kita sa customer service para sa tulong.",
            "ja": f"その他の{'入金' if is_deposit else '出金'}関連のご質問については、サポートのためカスタマーサービスにお繋ぎします。"
        }, request.language)
        
        return ProcessingResult(
            text=response_text,
            stage=ResponseStage.FINISH.value,
            transfer_human=1,
            message_type="human_service"
        )
    
    # 用户没有明确选择，再次识别是否是没到账的查询
    else:
        # 用第二次识别来判断是否是到账查询
        logger.info(f"用户回复不明确，进行第二次识别", extra={
            'session_id': request.session_id,
            'user_message': request.messages
        })
        
        # 检查是否包含"没到账"相关的表达
        not_received_extended = {
            "zh": ["没到账", "未到账", "没收到", "没有到", "到账", "收到", "状态", "查询", "订单"],
            "en": ["not received", "haven't received", "didn't receive", "received", "status", "check", "order"],
            "th": ["ไม่ได้รับ", "ยังไม่ได้", "ได้รับ", "สถานะ", "ตรวจสอบ"],
            "tl": ["hindi natatanggap", "hindi pa", "natatanggap", "status", "check"],
            "ja": ["届いていない", "受け取っていない", "届いた", "状況", "確認"]
        }
        
        current_extended = not_received_extended.get(request.language, not_received_extended["en"])
        if any(keyword in message_lower for keyword in current_extended):
            # 识别为到账查询，进入对应流程
            business_type = "S001" if is_deposit else "S002"
            logger.info(f"第二次识别为{('充值' if is_deposit else '提现')}到账查询，进入{business_type}流程", extra={
                'session_id': request.session_id,
                'business_type': business_type,
                'matched_keywords': [kw for kw in current_extended if kw in message_lower]
            })
            
            request.type = business_type
            return await _handle_business_process(request, business_type)
        else:
            # 仍然不明确，转人工
            logger.info(f"第二次识别仍不明确，转人工处理", extra={
                'session_id': request.session_id,
                'transfer_reason': 'unclear_after_second_identification'
            })
            
            response_text = get_message_by_language({
                "zh": f"抱歉，我没有完全理解您的{('充值' if is_deposit else '提现')}问题，已为您转接人工客服来协助解决。",
                "en": f"Sorry, I didn't fully understand your {'deposit' if is_deposit else 'withdrawal'} question. I've transferred you to customer service for assistance.",
                "th": f"ขออภัย ฉันไม่เข้าใจคำถามเกี่ยวกับ{'การฝาก' if is_deposit else 'การถอน'}ของคุณทั้งหมด ฉันได้โอนคุณไปยังฝ่ายบริการลูกค้าเพื่อความช่วยเหลือแล้ว",
                "tl": f"Pasensya na, hindi ko lubos na naintindihan ang inyong tanong tungkol sa {'deposit' if is_deposit else 'withdrawal'}. Na-transfer na kayo sa customer service para sa tulong.",
                "ja": f"申し訳ございませんが、お客様の{'入金' if is_deposit else '出金'}に関するご質問を完全に理解できませんでした。サポートのためカスタマーサービスにお繋ぎします。"
            }, request.language)
            
            return ProcessingResult(
                text=response_text,
                stage=ResponseStage.FINISH.value,
                transfer_human=1,
                message_type="human_service"
            )