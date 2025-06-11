import time
import re
from typing import Dict, List, Any, Optional
from pydantic import BaseModel

# 导入配置和其他模块
from src.config import get_config, get_message_by_language
# 假设这些函数在其他模块中定义
from src.workflow_check import identify_intent, identify_stage
from src.reply import get_unauthenticated_reply, build_reply_with_prompt
from src.util import MessageRequest, MessageResponse, call_openapi_model  # 异步方法
from src.telegram import send_to_telegram
from src.request_internal import (
    query_recharge_status, query_withdrawal_status, query_activity_list, query_user_eligibility,
    extract_recharge_status, extract_withdrawal_status, extract_activity_list, extract_user_eligibility
)
from src.logging_config import get_logger, log_api_call

logger = get_logger("chatai-api")

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
    logger.info(f"开始处理会话 {request.session_id} 的消息", extra={
        'session_id': request.session_id,
        'user_id': getattr(request, 'user_id', 'unknown'),
        'message_length': len(str(request.messages)),
        'has_images': bool(request.images and len(request.images) > 0),
        'language': request.language,
        'platform': request.platform
    })
    
    # 验证必要字段
    if not request.session_id or not request.messages:
        logger.error(f"请求验证失败：缺少必要字段", extra={
            'session_id': request.session_id,
            'has_session_id': bool(request.session_id),
            'has_messages': bool(request.messages)
        })
        raise ValueError("缺少必要字段: session_id, messages")
    
    # 验证token（仅对已登录用户进行验证）
    if request.status == 1:  # 已登录用户需要验证token
        token_valid, token_error = request.validate_token()
        if not token_valid:
            logger.error(f"Token验证失败", extra={
                'session_id': request.session_id,
                'user_id': request.user_id,
                'token_error': token_error,
                'has_token': bool(request.token)
            })
            raise ValueError(f"Token验证失败: {token_error}")
        
        logger.debug(f"Token验证通过", extra={
            'session_id': request.session_id,
            'user_id': request.user_id
        })
    
    # 获取配置
    logger.debug(f"获取系统配置", extra={'session_id': request.session_id})
    config = get_config()
    
    # 初始化所有变量
    message_type = "unknown"
    response_text = ""
    response_image = []
    response_stage = "working"
    transfer_human = 0
    
    # 判断用户是否登录
    logger.debug(f"用户登录状态检查: status={request.status}", extra={
        'session_id': request.session_id,
        'user_status': request.status,
        'is_logged_in': request.status != 0
    })
    
    if request.status == 0:  # 未登录
        logger.info(f"用户未登录，返回登录提示", extra={
            'session_id': request.session_id,
            'language': request.language
        })
        # 调用reply.py中的函数获取未登录回复
        response_text = get_unauthenticated_reply(request.language)
        message_type = "unauthenticated"  # 设置message_type变量
        
        # 构建未登录响应
        response = MessageResponse(
            session_id=request.session_id,
            status="success",
            response=response_text,
            stage="unauthenticated",
            metadata={
                "timestamp": time.time()
            },
            site=request.site,
            type="",
            transfer_human=0
        )
    else:  # 已登录
        logger.debug(f"用户已登录，开始业务处理", extra={'session_id': request.session_id})
        message_type = request.type or "unknown"
        
        # 如果type为None，进行意图识别
        if message_type is None:
            logger.debug(f"未指定业务类型，开始意图识别", extra={
                'session_id': request.session_id,
                'message': str(request.messages)[:100] + '...' if len(str(request.messages)) > 100 else str(request.messages)
            })
            
            # 调用外部意图识别函数
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
        else:
            logger.debug(f"使用预设业务类型: {message_type}", extra={
                'session_id': request.session_id,
                'preset_type': message_type
            })

        if message_type == "human_service":
            logger.info(f"用户请求人工客服", extra={
                'session_id': request.session_id,
                'transfer_reason': 'user_request'
            })
            response_text = "您需要人工客服的帮助，请稍等。"
            response_stage = "working"
            transfer_human = 1
            
        else:
            # 识别流程步骤
            logger.debug(f"开始识别流程步骤", extra={
                'session_id': request.session_id,
                'business_type': message_type
            })
            
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
            business_types = config.get("business_types", {})
            workflow = business_types.get(message_type, {}).get("workflow", {})
            step_info = workflow.get(str(stage_number), {})
            status_messages = business_types.get(message_type, {}).get("status_messages", {})
            
            # 检查是否是0阶段（非相关业务询问）
            if str(stage_number) == "0":
                logger.warning(f"识别为0阶段，非{message_type}相关询问，转人工处理", extra={
                    'session_id': request.session_id,
                    'business_type': message_type,
                    'stage': stage_number,
                    'transfer_reason': 'non_business_inquiry'
                })
                response_text = get_message_by_language(
                    status_messages.get("non_business_inquiry", {}), 
                    request.language
                )
                transfer_human = 1
                response_stage = "finish"
            else:
                # S001充值查询流程
                if message_type == "S001":
                    logger.info(f"开始S001充值查询流程处理", extra={
                        'session_id': request.session_id,
                        'stage_number': stage_number,
                        'has_images': bool(request.images and len(request.images) > 0)
                    })
                    
                    # 获取S001的配置信息
                    business_types = config.get("business_types", {})
                    s001_config = business_types.get("S001", {})
                    status_messages = s001_config.get("status_messages", {})
                    
                    # 优先检查是否上传图片，不管在哪个阶段
                    if request.images and len(request.images) > 0:
                        logger.warning(f"检测到图片上传，转人工处理", extra={
                            'session_id': request.session_id,
                            'image_count': len(request.images),
                            'image_urls': request.images[:2],  # 只记录前两个URL以避免日志过长
                            'transfer_reason': 'image_upload'
                        })
                        
                        response_text = get_message_by_language(
                            status_messages.get("image_uploaded", {}), 
                            request.language
                        )
                        transfer_human = 1
                        response_stage = "finish"
                    elif str(stage_number) in ["1", "2", "4"]:
                        logger.debug(f"处理S001标准阶段: {stage_number}", extra={
                            'session_id': request.session_id,
                            'stage': stage_number,
                            'has_step_info': bool(step_info)
                        })
                        
                        # 获取推荐回复内容
                        stage_response = step_info.get("response", {})
                        stage_text = stage_response.get("text") or step_info.get("step", "")
                        
                        logger.debug(f"构建AI回复提示词", extra={
                            'session_id': request.session_id,
                            'stage_text_length': len(stage_text),
                            'has_history': bool(request.history)
                        })
                        
                        prompt = build_reply_with_prompt(request.history or [], request.messages, stage_text, request.language)
                        response_text = await call_openapi_model(prompt=prompt)
                        
                        stage_image = stage_response.get("image", "")
                        if stage_image:
                            logger.debug(f"添加阶段图片", extra={
                                'session_id': request.session_id,
                                'image_url': stage_image
                            })
                            response_image = [stage_image]
                        
                        response_stage = "working" if str(stage_number) in ["1", "2"] else "finish"
                        
                        logger.info(f"S001阶段{stage_number}处理完成", extra={
                            'session_id': request.session_id,
                            'stage': stage_number,
                            'response_stage': response_stage,
                            'has_image': bool(stage_image),
                            'response_length': len(response_text)
                        })
                    elif str(stage_number) == "3":
                        logger.info(f"S001阶段3：处理订单号查询", extra={
                            'session_id': request.session_id,
                            'stage': stage_number
                        })
                        
                        # 尝试提取订单号（图片检查已在上面处理）
                        order_no = extract_order_no(request.messages, request.history)
                        
                        if order_no:
                            logger.info(f"成功提取订单号", extra={
                                'session_id': request.session_id,
                                'order_no': order_no,
                                'order_length': len(order_no)
                            })
                            
                            # 调用A001接口查询充值状态
                            logger.debug(f"准备调用A001充值状态查询接口", extra={
                                'session_id': request.session_id,
                                'order_no': order_no,
                                'api_name': 'A001'
                            })
                            
                            log_api_call("A001_query_recharge_status", request.session_id, order_no=order_no)
                            
                            try:
                                api_result = await query_recharge_status(request.session_id, order_no, request.site)
                                logger.debug(f"A001接口调用完成", extra={
                                    'session_id': request.session_id,
                                    'order_no': order_no,
                                    'api_success': bool(api_result),
                                    'api_state': api_result.get('state') if api_result else None
                                })
                            except Exception as e:
                                logger.error(f"A001接口调用异常", extra={
                                    'session_id': request.session_id,
                                    'order_no': order_no,
                                    'error': str(e)
                                }, exc_info=True)
                                api_result = None
                            
                            # 验证session和处理错误
                            is_valid, error_message = validate_session_and_handle_errors(api_result, status_messages, request.language)
                            
                            if not is_valid:
                                logger.warning(f"A001接口验证失败", extra={
                                    'session_id': request.session_id,
                                    'order_no': order_no,
                                    'error_message': error_message,
                                    'transfer_reason': 'api_validation_failed'
                                })
                                response_text = error_message
                                transfer_human = 1
                                response_stage = "finish"
                            else:
                                logger.debug(f"开始提取充值状态数据", extra={
                                    'session_id': request.session_id,
                                    'order_no': order_no
                                })
                                
                                extracted_data = extract_recharge_status(api_result)
                                
                                if extracted_data["is_success"]:
                                    status = extracted_data["status"]
                                    logger.info(f"充值状态查询成功", extra={
                                        'session_id': request.session_id,
                                        'order_no': order_no,
                                        'status': status
                                    })
                                    
                                    if status == "Recharge successful":
                                        logger.info(f"充值成功", extra={
                                            'session_id': request.session_id,
                                            'order_no': order_no,
                                            'final_status': 'success'
                                        })
                                        # 支付成功，回复充值成功，请等待
                                        response_text = get_message_by_language(
                                            status_messages.get("recharge_successful", {}), 
                                            request.language
                                        )
                                        response_stage = "finish"
                                    elif status == "canceled":
                                        logger.info(f"充值已取消", extra={
                                            'session_id': request.session_id,
                                            'order_no': order_no,
                                            'final_status': 'canceled'
                                        })
                                        # 已取消，通知用户您已取消支付
                                        response_text = get_message_by_language(
                                            status_messages.get("payment_canceled", {}), 
                                            request.language
                                        )
                                        response_stage = "finish"
                                    elif status in ["pending", "rejected", "Recharge failed"]:
                                        logger.warning(f"充值状态异常，转人工处理", extra={
                                            'session_id': request.session_id,
                                            'order_no': order_no,
                                            'status': status,
                                            'transfer_reason': 'payment_issue'
                                        })
                                        # 待支付，已拒绝，支付失败，都转人工
                                        response_text = get_message_by_language(
                                            status_messages.get("payment_issue", {}), 
                                            request.language
                                        )
                                        transfer_human = 1
                                        response_stage = "finish"
                                    else:
                                        logger.warning(f"未知充值状态，转人工处理", extra={
                                            'session_id': request.session_id,
                                            'order_no': order_no,
                                            'unknown_status': status,
                                            'transfer_reason': 'unknown_status'
                                        })
                                        # 其他未知状态，转人工
                                        response_text = get_message_by_language(
                                            status_messages.get("status_unclear", {}), 
                                            request.language
                                        )
                                        transfer_human = 1
                                        response_stage = "finish"
                                    
                                    prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                                    response_text = await call_openapi_model(prompt=prompt)
                                else:
                                    # A001接口调用失败，转人工
                                    response_text = get_message_by_language(
                                        status_messages.get("query_failed", {}), 
                                        request.language
                                    )
                                    transfer_human = 1
                                    response_stage = "finish"
                        else:
                            logger.warning(f"S001: 未能从消息中提取到有效订单号", extra={
                                'session_id': request.session_id,
                                'message': str(request.messages)[:200] + '...' if len(str(request.messages)) > 200 else str(request.messages),
                                'has_history': bool(request.history),
                                'history_length': len(request.history or [])
                            })
                            # 未能提取到订单号，要求用户明确订单号
                            response_text = get_message_by_language(
                                status_messages.get("order_not_found", {}), 
                                request.language
                            )
                            response_stage = "working"
                # S003 活动查询流程
                if message_type == "S003":
                    logger.info(f"开始S003活动查询流程处理", extra={
                        'session_id': request.session_id,
                        'stage_number': stage_number
                    })
                    
                    # 获取S003的配置信息
                    business_types = config.get("business_types", {})
                    s003_config = business_types.get("S003", {})
                    status_messages = s003_config.get("status_messages", {})
                    
                    if str(stage_number) == "1":
                        logger.debug(f"S003阶段1：查询活动列表并识别用户想要的活动", extra={
                            'session_id': request.session_id,
                            'stage': stage_number
                        })
                        
                        # 第一步：通过A003接口读取活动列表
                        log_api_call("A003_query_activity_list", request.session_id)
                        try:
                            api_result = await query_activity_list(request.session_id, request.site)
                            logger.debug(f"A003接口调用完成", extra={
                                'session_id': request.session_id,
                                'api_success': bool(api_result)
                            })
                        except Exception as e:
                            logger.error(f"A003接口调用异常", extra={
                                'session_id': request.session_id,
                                'error': str(e)
                            }, exc_info=True)
                            api_result = None
                        
                        # 验证session和处理错误
                        is_valid, error_message = validate_session_and_handle_errors(api_result, status_messages, request.language)
                        if not is_valid:
                            logger.warning(f"A003接口验证失败", extra={
                                'session_id': request.session_id,
                                'error_message': error_message,
                                'transfer_reason': 'api_validation_failed'
                            })
                            response_text = error_message
                            transfer_human = 1
                            response_stage = "finish"
                            prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                            response_text = await call_openapi_model(prompt=prompt)
                        else:
                            extracted_data = extract_activity_list(api_result)
                            
                            if extracted_data["is_success"]:
                                # 构建所有活动的列表
                                all_activities = []
                                all_activities.extend(extracted_data["agent_activities"])
                                all_activities.extend(extracted_data["deposit_activities"])
                                all_activities.extend(extracted_data["rebate_activities"])
                                all_activities.extend(extracted_data["lucky_spin_activities"])
                                all_activities.extend(extracted_data["all_member_activities"])
                                all_activities.extend(extracted_data["sports_activities"])
                                
                                logger.debug(f"获取到活动列表", extra={
                                    'session_id': request.session_id,
                                    'activity_count': len(all_activities),
                                    'activities_preview': all_activities[:3] if all_activities else []
                                })
                                
                                if all_activities:
                                    # 使用大模型将聊天内容与活动列表对比，识别用户想要的活动
                                    if request.language == "en":
                                        activity_list_text = "Available activities:\n"
                                    else:
                                        activity_list_text = "可用活动列表：\n"
                                    
                                    for i, activity in enumerate(all_activities, 1):
                                        activity_list_text += f"{i}. {activity}\n"
                                    
                                    user_message = request.messages
                                    
                                    # 构建活动识别的提示词
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
                                    
                                    logger.debug(f"开始AI活动识别", extra={
                                        'session_id': request.session_id,
                                        'user_message_length': len(str(user_message)),
                                        'activity_count': len(all_activities)
                                    })
                                    
                                    identified_activity = await call_openapi_model(prompt=activity_prompt)
                                    
                                    logger.info(f"AI活动识别结果", extra={
                                        'session_id': request.session_id,
                                        'identified_activity': identified_activity.strip(),
                                        'is_unclear': identified_activity.strip().lower() == "unclear",
                                        'is_in_list': identified_activity.strip() in all_activities
                                    })
                                    
                                    # 检查是否成功识别到活动
                                    if identified_activity.strip().lower() == "unclear" or identified_activity.strip() not in all_activities:
                                        # 未能明确识别活动，要求用户明确
                                        logger.debug(f"未能识别到具体活动，提供活动列表", extra={
                                            'session_id': request.session_id,
                                            'identified_result': identified_activity.strip()
                                        })
                                        
                                        base_message = get_message_by_language(
                                            status_messages.get("unclear_activity", {}), 
                                            request.language
                                        )
                                        response_text = f"{base_message}\n{activity_list_text}"
                                        prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                                        response_text = await call_openapi_model(prompt=prompt)
                                        response_stage = "working"
                                    else:
                                        # 成功识别到活动，进入第二步查询领取状态
                                        logger.info(f"成功识别活动，查询领取状态", extra={
                                            'session_id': request.session_id,
                                            'activity_name': identified_activity.strip()
                                        })
                                        
                                        log_api_call("A004_query_user_eligibility", request.session_id, activity=identified_activity.strip())
                                        try:
                                            api_result = await query_user_eligibility(request.session_id, request.site)
                                            eligibility_data = extract_user_eligibility(api_result)
                                            
                                            if eligibility_data["is_success"]:
                                                status = eligibility_data["status"]
                                                message = eligibility_data["message"]
                                                
                                                logger.info(f"活动领取状态查询成功", extra={
                                                    'session_id': request.session_id,
                                                    'activity_status': status,
                                                    'activity_message': message
                                                })
                                                
                                                # 根据A004接口返回的具体状态进行处理
                                                if status == "Conditions not met":
                                                    # 未达到领取条件
                                                    base_message = get_message_by_language(
                                                        status_messages.get("conditions_not_met", {}), 
                                                        request.language
                                                    )
                                                    response_text = f"{base_message} {message}".strip()
                                                    response_stage = "finish"
                                                elif status == "Paid success":
                                                    # 已发放
                                                    response_text = get_message_by_language(
                                                        status_messages.get("paid_success", {}), 
                                                        request.language
                                                    )
                                                    response_stage = "finish"
                                                elif status == "Waiting paid":
                                                    # 满足条件，还未到发放时间
                                                    base_message = get_message_by_language(
                                                        status_messages.get("waiting_paid", {}), 
                                                        request.language
                                                    )
                                                    response_text = f"{base_message} {message}".strip()
                                                    response_stage = "finish"
                                                elif status == "Need paid":
                                                    # 满足条件，系统未发放彩金，需要人工发放
                                                    response_text = get_message_by_language(
                                                        status_messages.get("need_paid", {}), 
                                                        request.language
                                                    )
                                                    transfer_human = 1
                                                    response_stage = "finish"
                                                else:
                                                    # 其他未知状态，转人工处理
                                                    logger.warning(f"未知活动状态，转人工处理", extra={
                                                        'session_id': request.session_id,
                                                        'unknown_status': status,
                                                        'transfer_reason': 'unknown_activity_status'
                                                    })
                                                    response_text = get_message_by_language(
                                                        status_messages.get("unknown_status", {}), 
                                                        request.language
                                                    )
                                                    transfer_human = 1
                                                    response_stage = "finish"
                                                
                                                prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                                                response_text = await call_openapi_model(prompt=prompt)
                                            else:
                                                # A004接口调用失败，转人工
                                                logger.error(f"A004接口调用失败，转人工", extra={
                                                    'session_id': request.session_id,
                                                    'activity_name': identified_activity.strip(),
                                                    'transfer_reason': 'a004_api_failed'
                                                })
                                                response_text = get_message_by_language(
                                                    status_messages.get("query_failed", {}), 
                                                    request.language
                                                )
                                                transfer_human = 1
                                                response_stage = "finish"
                                                
                                                prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                                                response_text = await call_openapi_model(prompt=prompt)
                                        except Exception as e:
                                            logger.error(f"A004接口调用异常，转人工", extra={
                                                'session_id': request.session_id,
                                                'activity_name': identified_activity.strip(),
                                                'error': str(e),
                                                'transfer_reason': 'a004_api_exception'
                                            }, exc_info=True)
                                            response_text = get_message_by_language(
                                                status_messages.get("query_failed", {}), 
                                                request.language
                                            )
                                            transfer_human = 1
                                            response_stage = "finish"
                                            
                                            prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                                            response_text = await call_openapi_model(prompt=prompt)
                                else:
                                    # 没有可用活动
                                    logger.info(f"没有可用活动", extra={
                                        'session_id': request.session_id
                                    })
                                    response_text = get_message_by_language(
                                        status_messages.get("no_activities", {}), 
                                        request.language
                                    )
                                    response_stage = "finish"
                                    
                                    prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                                    response_text = await call_openapi_model(prompt=prompt)
                            else:
                                # A003接口调用失败
                                logger.error(f"A003接口调用失败，转人工", extra={
                                    'session_id': request.session_id,
                                    'transfer_reason': 'a003_api_failed'
                                })
                                response_text = get_message_by_language(
                                    status_messages.get("query_failed", {}), 
                                    request.language
                                )
                                transfer_human = 1
                                response_stage = "finish"
                                
                                prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                                response_text = await call_openapi_model(prompt=prompt)
                            
                    elif str(stage_number) == "2":
                        logger.debug(f"S003阶段2：用户明确活动后查询领取状态", extra={
                            'session_id': request.session_id,
                            'stage': stage_number
                        })
                        
                        # 第二步：用户明确活动后，查询领取状态
                        # 重新获取活动列表以验证用户输入
                        log_api_call("A003_query_activity_list", request.session_id, stage="2")
                        try:
                            api_result = await query_activity_list(request.session_id, request.site)
                            
                            # 验证session和处理错误
                            is_valid, error_message = validate_session_and_handle_errors(api_result, status_messages, request.language)
                            if not is_valid:
                                logger.warning(f"S003阶段2 A003接口验证失败", extra={
                                    'session_id': request.session_id,
                                    'error_message': error_message,
                                    'transfer_reason': 'a003_validation_failed'
                                })
                                response_text = error_message
                                transfer_human = 1
                                response_stage = "finish"
                            else:
                                # 提取用户输入的活动名称，并验证是否在活动列表中
                                extracted_data = extract_activity_list(api_result)
                                if extracted_data["is_success"]:
                                    all_activities = []
                                    all_activities.extend(extracted_data["agent_activities"])
                                    all_activities.extend(extracted_data["deposit_activities"])
                                    all_activities.extend(extracted_data["rebate_activities"])
                                    all_activities.extend(extracted_data["lucky_spin_activities"])
                                    all_activities.extend(extracted_data["all_member_activities"])
                                    all_activities.extend(extracted_data["sports_activities"])
                                    
                                    # 从用户消息中找出活动名称
                                    user_input = str(request.messages).strip()
                                    matched_activity = None
                                    
                                    # 简单匹配：看用户输入是否完全匹配某个活动名称
                                    for activity in all_activities:
                                        if activity.lower() in user_input.lower() or user_input.lower() in activity.lower():
                                            matched_activity = activity
                                            break
                                    
                                    if matched_activity:
                                        logger.info(f"S003阶段2匹配到活动：{matched_activity}", extra={
                                            'session_id': request.session_id,
                                            'matched_activity': matched_activity
                                        })
                                        
                                        # 查询该活动的领取状态
                                        log_api_call("A004_query_user_eligibility", request.session_id, activity=matched_activity)
                                        api_result = await query_user_eligibility(request.session_id, request.site)
                                        eligibility_data = extract_user_eligibility(api_result)
                                        
                                        if eligibility_data["is_success"]:
                                            status = eligibility_data["status"]
                                            message = eligibility_data["message"]
                                            
                                            logger.info(f"S003阶段2活动状态查询成功", extra={
                                                'session_id': request.session_id,
                                                'activity_status': status,
                                                'activity_message': message
                                            })
                                            
                                            # 处理结果（同阶段1）
                                            if status == "Conditions not met":
                                                base_message = get_message_by_language(
                                                    status_messages.get("conditions_not_met", {}), 
                                                    request.language
                                                )
                                                response_text = f"{base_message} {message}".strip()
                                                response_stage = "finish"
                                            elif status == "Paid success":
                                                response_text = get_message_by_language(
                                                    status_messages.get("paid_success", {}), 
                                                    request.language
                                                )
                                                response_stage = "finish"
                                            elif status == "Waiting paid":
                                                base_message = get_message_by_language(
                                                    status_messages.get("waiting_paid", {}), 
                                                    request.language
                                                )
                                                response_text = f"{base_message} {message}".strip()
                                                response_stage = "finish"
                                            elif status == "Need paid":
                                                response_text = get_message_by_language(
                                                    status_messages.get("need_paid", {}), 
                                                    request.language
                                                )
                                                transfer_human = 1
                                                response_stage = "finish"
                                            else:
                                                response_text = get_message_by_language(
                                                    status_messages.get("unknown_status", {}), 
                                                    request.language
                                                )
                                                transfer_human = 1
                                                response_stage = "finish"
                                                
                                            prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                                            response_text = await call_openapi_model(prompt=prompt)
                                        else:
                                            logger.error(f"S003阶段2 A004接口调用失败", extra={
                                                'session_id': request.session_id,
                                                'transfer_reason': 'a004_failed'
                                            })
                                            response_text = get_message_by_language(
                                                status_messages.get("query_failed", {}), 
                                                request.language
                                            )
                                            transfer_human = 1
                                            response_stage = "finish"
                                    else:
                                        # 仍然无法确定具体活动，转人工
                                        logger.warning(f"S003阶段2仍无法确定活动，转人工", extra={
                                            'session_id': request.session_id,
                                            'user_input': user_input,
                                            'transfer_reason': 'still_unclear_activity'
                                        })
                                        response_text = get_message_by_language(
                                            status_messages.get("still_unclear", {}), 
                                            request.language
                                        )
                                        transfer_human = 1
                                        response_stage = "finish"
                                else:
                                    logger.error(f"S003阶段2提取活动数据失败", extra={
                                        'session_id': request.session_id,
                                        'transfer_reason': 'extract_activities_failed'
                                    })
                                    response_text = get_message_by_language(
                                        status_messages.get("query_failed", {}), 
                                        request.language
                                    )
                                    transfer_human = 1
                                    response_stage = "finish"
                        except Exception as e:
                            logger.error(f"S003阶段2处理异常", extra={
                                'session_id': request.session_id,
                                'error': str(e),
                                'transfer_reason': 'stage2_exception'
                            }, exc_info=True)
                            response_text = get_message_by_language(
                                status_messages.get("query_failed", {}), 
                                request.language
                            )
                            transfer_human = 1
                            response_stage = "finish"
                    
                    else:
                        # 其他阶段，转人工处理
                        logger.warning(f"S003不支持的阶段，转人工处理", extra={
                            'session_id': request.session_id,
                            'stage': stage_number,
                            'transfer_reason': 'unsupported_stage'
                        })
                        response_text = get_message_by_language(
                            status_messages.get("query_failed", {}), 
                            request.language
                        )
                        transfer_human = 1
                        response_stage = "finish"
                
                    logger.info(f"S003处理完成", extra={
                        'session_id': request.session_id,
                        'stage': stage_number,
                        'transfer_human': transfer_human,
                        'response_stage': response_stage
                    })

                # S002提现查询流程
                if message_type == "S002":
                    logger.info(f"开始S002提现查询流程处理", extra={
                        'session_id': request.session_id,
                        'stage_number': stage_number,
                        'has_images': bool(request.images and len(request.images) > 0)
                    })
                    
                    # 获取S002的配置信息
                    business_types = config.get("business_types", {})
                    s002_config = business_types.get("S002", {})
                    status_messages = s002_config.get("status_messages", {})
                    
                    # 优先检查是否上传图片，不管在哪个阶段
                    if request.images and len(request.images) > 0:
                        logger.warning(f"检测到图片上传，转人工处理", extra={
                            'session_id': request.session_id,
                            'image_count': len(request.images),
                            'transfer_reason': 'image_upload'
                        })
                        response_text = get_message_by_language(
                            status_messages.get("image_uploaded", {}), 
                            request.language
                        )
                        transfer_human = 1
                        response_stage = "finish"
                    elif str(stage_number) in ["1", "2", "4"]:
                        logger.debug(f"处理S002标准阶段: {stage_number}", extra={
                            'session_id': request.session_id,
                            'stage': stage_number
                        })
                        
                        # 阶段1、2、4：使用原有的回复生成逻辑
                        stage_response = step_info.get("response", {})
                        stage_text = stage_response.get("text") or step_info.get("step", "")

                        prompt = build_reply_with_prompt(request.history or [], request.messages, stage_text, request.language)
                        response_text = await call_openapi_model(prompt=prompt)

                        # 返回图片（如果有）
                        stage_image = stage_response.get("image", "")
                        if stage_image:
                            logger.debug(f"添加阶段图片", extra={
                                'session_id': request.session_id,
                                'image_url': stage_image
                            })
                            response_image = [stage_image]

                        response_stage = "working" if str(stage_number) in ["1", "2"] else "finish"
                        
                        logger.info(f"S002阶段{stage_number}处理完成", extra={
                            'session_id': request.session_id,
                            'stage': stage_number,
                            'response_stage': response_stage,
                            'has_image': bool(stage_image)
                        })

                    elif str(stage_number) == "3":
                        logger.info(f"S002阶段3：处理订单号查询", extra={
                            'session_id': request.session_id,
                            'stage': stage_number
                        })
                        
                        # 阶段3：用户提供订单号，开始处理提现状态查询（图片检查已在上面处理）
                        
                        # 尝试提取订单号
                        order_no = extract_order_no(request.messages, request.history)

                        if order_no:
                            logger.info(f"成功提取订单号", extra={
                                'session_id': request.session_id,
                                'order_no': order_no
                            })
                            
                            # 调用A002接口查询提现状态
                            logger.debug(f"准备调用A002提现状态查询接口", extra={
                                'session_id': request.session_id,
                                'order_no': order_no,
                                'api_name': 'A002'
                            })
                            
                            log_api_call("A002_query_withdrawal_status", request.session_id, order_no=order_no)
                            
                            try:
                                api_result = await query_withdrawal_status(request.session_id, order_no, request.site)
                                logger.debug(f"A002接口调用完成", extra={
                                    'session_id': request.session_id,
                                    'order_no': order_no,
                                    'api_success': bool(api_result)
                                })
                            except Exception as e:
                                logger.error(f"A002接口调用异常", extra={
                                    'session_id': request.session_id,
                                    'order_no': order_no,
                                    'error': str(e)
                                }, exc_info=True)
                                api_result = None
                            
                            # 验证session和处理错误
                            is_valid, error_message = validate_session_and_handle_errors(api_result, status_messages, request.language)
                            if not is_valid:
                                logger.warning(f"A002接口验证失败", extra={
                                    'session_id': request.session_id,
                                    'order_no': order_no,
                                    'error_message': error_message,
                                    'transfer_reason': 'api_validation_failed'
                                })
                                response_text = error_message
                                transfer_human = 1
                                response_stage = "finish"
                            else:
                                logger.debug(f"开始提取提现状态数据", extra={
                                    'session_id': request.session_id,
                                    'order_no': order_no
                                })
                                
                                extracted_data = extract_withdrawal_status(api_result)
                                
                                if extracted_data["is_success"]:
                                    status = extracted_data["status"]
                                    logger.info(f"提现状态查询成功", extra={
                                        'session_id': request.session_id,
                                        'order_no': order_no,
                                        'status': status
                                    })
                                    
                                    if status == "Withdrawal successful":
                                        # 提现成功，通知用户提现成功
                                        logger.info(f"提现成功", extra={
                                            'session_id': request.session_id,
                                            'order_no': order_no,
                                            'final_status': 'success'
                                        })
                                        response_text = get_message_by_language(
                                            status_messages.get("withdrawal_successful", {}), 
                                            request.language
                                        )
                                        response_stage = "finish"
                                    elif status in ["pending", "obligation"]:
                                        # 待处理/待付款，回复用户处理中，请耐心等待
                                        logger.info(f"提现处理中", extra={
                                            'session_id': request.session_id,
                                            'order_no': order_no,
                                            'final_status': 'processing'
                                        })
                                        response_text = get_message_by_language(
                                            status_messages.get("withdrawal_processing", {}), 
                                            request.language
                                        )
                                        response_stage = "finish"
                                    elif status == "canceled":
                                        # 用户取消提款，通知用户提现已取消
                                        logger.info(f"提现已取消", extra={
                                            'session_id': request.session_id,
                                            'order_no': order_no,
                                            'final_status': 'canceled'
                                        })
                                        response_text = get_message_by_language(
                                            status_messages.get("withdrawal_canceled", {}), 
                                            request.language
                                        )
                                        response_stage = "finish"
                                    elif status in ["rejected", "prepare", "lock", "oblock", "refused"]:
                                        # 已拒绝/准备支付/锁定/待付款锁定/已拒绝，转人工
                                        logger.warning(f"提现状态异常，转人工处理", extra={
                                            'session_id': request.session_id,
                                            'order_no': order_no,
                                            'status': status,
                                            'transfer_reason': 'withdrawal_issue'
                                        })
                                        response_text = get_message_by_language(
                                            status_messages.get("withdrawal_issue", {}), 
                                            request.language
                                        )
                                        transfer_human = 1
                                        response_stage = "finish"
                                    elif status in ["Withdrawal failed", "confiscate"]:
                                        # 支付失败/没收，推送至TG群用户ID，订单号，状态，转人工
                                        logger.warning(f"提现失败，发送TG通知并转人工", extra={
                                            'session_id': request.session_id,
                                            'order_no': order_no,
                                            'status': status,
                                            'transfer_reason': 'withdrawal_failed'
                                        })
                                        
                                        bot_token = config.get("telegram_bot_token", "")
                                        chat_id = config.get("telegram_chat_id", "")
                                        if bot_token and chat_id:
                                            # 发送包含用户ID、订单号、状态的消息到TG群
                                            tg_message = f"⚠️ 提现异常\n用户ID: {request.user_id}\n订单号: {order_no}\n状态: {status}"
                                            try:
                                                await send_to_telegram([], bot_token, chat_id, username=request.user_id, custom_message=tg_message)
                                                logger.info(f"TG异常通知发送成功", extra={
                                                    'session_id': request.session_id,
                                                    'order_no': order_no
                                                })
                                            except Exception as e:
                                                logger.error(f"TG异常通知发送失败", extra={
                                                    'session_id': request.session_id,
                                                    'order_no': order_no,
                                                    'error': str(e)
                                                })
                                        
                                        response_text = get_message_by_language(
                                            status_messages.get("withdrawal_failed", {}), 
                                            request.language
                                        )
                                        transfer_human = 1
                                        response_stage = "finish"
                                    else:
                                        # 其他未知状态，转人工
                                        logger.warning(f"未知提现状态，转人工处理", extra={
                                            'session_id': request.session_id,
                                            'order_no': order_no,
                                            'unknown_status': status,
                                            'transfer_reason': 'unknown_status'
                                        })
                                        response_text = get_message_by_language(
                                            status_messages.get("withdrawal_issue", {}), 
                                            request.language
                                        )
                                        transfer_human = 1
                                        response_stage = "finish"
                                    
                                    prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                                    response_text = await call_openapi_model(prompt=prompt)
                                else:
                                    # A002接口调用失败，转人工
                                    logger.error(f"A002接口数据提取失败，转人工", extra={
                                        'session_id': request.session_id,
                                        'order_no': order_no,
                                        'transfer_reason': 'data_extraction_failed'
                                    })
                                    response_text = get_message_by_language(
                                        status_messages.get("query_failed", {}), 
                                        request.language
                                    )
                                    transfer_human = 1
                                    response_stage = "finish"
                        else:
                            logger.warning(f"S002: 未能从消息中提取到有效订单号", extra={
                                'session_id': request.session_id,
                                'message': str(request.messages)[:200] + '...' if len(str(request.messages)) > 200 else str(request.messages)
                            })
                            # 未能提取到订单号，要求用户明确订单号
                            response_text = get_message_by_language(
                                status_messages.get("order_not_found", {}), 
                                request.language
                            )
                            response_stage = "working"
                    
                    logger.info(f"S002处理完成", extra={
                        'session_id': request.session_id,
                        'stage': stage_number,
                        'transfer_human': transfer_human,
                        'response_stage': response_stage
                    })

        # 构建响应
        logger.debug(f"构建最终响应", extra={
            'session_id': request.session_id,
            'response_stage': response_stage,
            'transfer_human': transfer_human,
            'has_images': bool(response_image),
            'response_length': len(response_text)
        })
        
        response = MessageResponse(
            session_id=request.session_id,
            status="success",
            response=response_text,
            stage=response_stage,
            images=response_image,
            metadata={
                "intent": message_type,
                "timestamp": time.time()
            },
            site=request.site,
            type=message_type,
            transfer_human=transfer_human
        )
    
    logger.info(f"会话处理完成", extra={
        'session_id': request.session_id,
        'final_status': 'success',
        'business_type': message_type,
        'transfer_human': transfer_human,
        'stage': response_stage,
        'processing_time': round(time.time() - (response.metadata.get('timestamp', time.time())), 3)
    })
    return response

def extract_order_no(messages, history):
    """
    从消息和历史中提取订单号（18位纯数字）
    改进算法：查找所有数字序列，返回长度恰好为18位的序列
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
    
    logger.debug(f"合并文本长度: {len(all_text)}", extra={
        'text_preview': all_text[:100] + '...' if len(all_text) > 100 else all_text
    })
    
    # 找到所有连续的数字序列
    number_sequences = re.findall(r'\d+', all_text)
    
    logger.debug(f"找到数字序列", extra={
        'sequence_count': len(number_sequences),
        'sequences': [f"{seq}({len(seq)}位)" for seq in number_sequences[:5]]  # 只记录前5个以避免日志过长
    })
    
    # 只返回长度恰好为18位的数字序列
    for seq in number_sequences:
        if len(seq) == 18:
            logger.info(f"成功提取18位订单号", extra={
                'order_no': seq,
                'source_text_length': len(all_text)
            })
            return seq
    
    logger.warning(f"未找到18位订单号", extra={
        'found_sequences': len(number_sequences),
        'sequence_lengths': [len(seq) for seq in number_sequences[:10]]  # 记录前10个序列的长度
    })
    return None

def validate_session_and_handle_errors(api_result, status_messages, language):
    """
    验证session_id和处理API调用错误
    """
    logger.debug(f"开始验证API调用结果", extra={
        'has_result': bool(api_result),
        'language': language
    })
    
    if not api_result:
        logger.error(f"API调用结果为空", extra={
            'api_result': api_result,
            'validation_result': False
        })
        return False, get_message_by_language(
            status_messages.get("query_failed", {}), 
            language
        )
    
    # 检查是否是session_id无效或其他错误
    state = api_result.get("state", -1)
    logger.debug(f"API调用状态码检查", extra={
        'state': state,
        'api_data_keys': list(api_result.keys()) if isinstance(api_result, dict) else 'not_dict'
    })
    
    if state == 886:  # Missing required parameters
        logger.warning(f"Session无效或参数缺失", extra={
            'state': state,
            'error_type': 'session_invalid',
            'validation_result': False
        })
        return False, get_message_by_language(
            status_messages.get("session_invalid", {}), 
            language
        )
    elif state == 887:  # 订单号格式正确但查询不到记录
        logger.warning(f"订单号格式正确但查询不到相关信息", extra={
            'state': state,
            'error_type': 'invalid_order_number',
            'validation_result': False
        })
        return False, get_message_by_language(
            status_messages.get("invalid_order_number", {}), 
            language
        )
    elif state != 0:  # 其他错误
        logger.warning(f"API调用返回错误状态", extra={
            'state': state,
            'error_type': 'api_error',
            'validation_result': False,
            'api_result_preview': str(api_result)[:200] + '...' if len(str(api_result)) > 200 else str(api_result)
        })
        return False, get_message_by_language(
            status_messages.get("query_failed", {}), 
            language
        )
    
    logger.debug(f"API调用结果验证通过", extra={
        'state': state,
        'validation_result': True
    })
    return True, ""
