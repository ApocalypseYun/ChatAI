import logging
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
            # S001充值查询流程
            if message_type == "S001":
                # 获取S001的配置信息
                business_types = config.get("business_types", {})
                s001_config = business_types.get("S001", {})
                status_messages = s001_config.get("status_messages", {})
                
                # 优先检查是否上传图片，不管在哪个阶段
                if request.images and len(request.images) > 0:
                    bot_token = config.get("telegram_bot_token", "")
                    chat_id = config.get("telegram_chat_id", "")
                    if bot_token and chat_id:
                        await send_to_telegram(request.images, bot_token, chat_id, username=request.user_id)
                    
                    response_text = get_message_by_language(
                        status_messages.get("image_uploaded", {}), 
                        request.language
                    )
                    transfer_human = 1
                    response_stage = "finish"
                elif str(stage_number) in ["1", "2", "4"]:
                    # 获取推荐回复内容
                    stage_response = step_info.get("response", {})
                    stage_text = stage_response.get("text") or step_info.get("step", "")
                    prompt = build_reply_with_prompt(request.history or [], request.messages, stage_text, request.language)
                    response_text = await call_openapi_model(prompt=prompt)
                    stage_image = stage_response.get("image", "")
                    if stage_image:
                        response_image = [stage_image]
                    response_stage = "working" if str(stage_number) in ["1", "2"] else "finish"
                elif str(stage_number) == "3":
                    # 尝试提取订单号（图片检查已在上面处理）
                    order_no = extract_order_no(request.messages, request.history)
                    if order_no:
                        # 调用A001接口查询充值状态
                        api_result = await query_recharge_status(request.session_id, order_no)
                        extracted_data = extract_recharge_status(api_result)
                        
                        if extracted_data["is_success"]:
                            status = extracted_data["status"]
                            
                            if status == "Recharge successful":
                                # 支付成功，回复充值成功，请等待
                                response_text = get_message_by_language(
                                    status_messages.get("recharge_successful", {}), 
                                    request.language
                                )
                                response_stage = "finish"
                            elif status == "canceled":
                                # 已取消，通知用户您已取消支付
                                response_text = get_message_by_language(
                                    status_messages.get("payment_canceled", {}), 
                                    request.language
                                )
                                response_stage = "finish"
                            elif status in ["pending", "rejected", "Recharge failed"]:
                                # 待支付，已拒绝，支付失败，都转人工
                                response_text = get_message_by_language(
                                    status_messages.get("payment_issue", {}), 
                                    request.language
                                )
                                transfer_human = 1
                                response_stage = "finish"
                            else:
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
                        # 未能提取到订单号，要求用户明确订单号
                        response_text = get_message_by_language(
                            status_messages.get("order_not_found", {}), 
                            request.language
                        )
                        response_stage = "working"
            # S003 活动查询流程
            if message_type == "S003":
                # 获取S003的配置信息
                business_types = config.get("business_types", {})
                s003_config = business_types.get("S003", {})
                status_messages = s003_config.get("status_messages", {})
                
                if str(stage_number) == "1":
                    # 第一步：通过A003接口读取活动列表
                    api_result = await query_activity_list(request.session_id)
                    extracted_data = extract_activity_list(api_result)
                    
                    if extracted_data["is_success"]:
                        # 构建所有活动的列表
                        all_activities = []
                        all_activities.extend(extracted_data["agent_activities"])
                        all_activities.extend(extracted_data["deposit_activities"])
                        all_activities.extend(extracted_data["rebate_activities"])
                        
                        if all_activities:
                            # 使用大模型将聊天内容与活动列表对比，识别用户想要的活动
                            if request.language == "en":
                                activity_list_text = "Available activities:\n"
                            else:
                                activity_list_text = "可用活动列表：\n"
                            
                            for i, activity in enumerate(all_activities, 1):
                                activity_list_text += f"{i}. {activity}\n"
                            
                            user_message = request.messages[-1] if request.messages else ""
                            
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
                            
                            identified_activity = await call_openapi_model(prompt=activity_prompt)
                            
                            # 检查是否成功识别到活动
                            if identified_activity.strip().lower() == "unclear" or identified_activity.strip() not in all_activities:
                                # 未能明确识别活动，要求用户明确
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
                                api_result = await query_user_eligibility(request.session_id)
                                eligibility_data = extract_user_eligibility(api_result)
                                
                                if eligibility_data["is_success"]:
                                    status = eligibility_data["status"]
                                    message = eligibility_data["message"]
                                    
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
                            response_text = get_message_by_language(
                                status_messages.get("no_activities", {}), 
                                request.language
                            )
                            response_stage = "finish"
                            
                            prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                            response_text = await call_openapi_model(prompt=prompt)
                    else:
                        # A003接口调用失败
                        response_text = get_message_by_language(
                            status_messages.get("query_failed", {}), 
                            request.language
                        )
                        transfer_human = 1
                        response_stage = "finish"
                        
                        prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                        response_text = await call_openapi_model(prompt=prompt)
                        
                elif str(stage_number) == "2":
                    # 第二步：用户明确活动后，查询领取状态
                    # 重新获取活动列表以验证用户输入
                    api_result = await query_activity_list(request.session_id)
                    extracted_data = extract_activity_list(api_result)
                    
                    if extracted_data["is_success"]:
                        all_activities = []
                        all_activities.extend(extracted_data["agent_activities"])
                        all_activities.extend(extracted_data["deposit_activities"])
                        all_activities.extend(extracted_data["rebate_activities"])
                        
                        user_message = request.messages[-1] if request.messages else ""
                        
                        # 使用大模型再次匹配用户明确的活动
                        if request.language == "en":
                            activity_list_text = "Available activities:\n"
                        else:
                            activity_list_text = "可用活动列表：\n"
                        
                        for i, activity in enumerate(all_activities, 1):
                            activity_list_text += f"{i}. {activity}\n"
                        
                        if request.language == "en":
                            activity_prompt = f"""
Based on the user's message, find the specific activity the user wants to query from the activity list.

User message: {user_message}

{activity_list_text}

Please return the most matching complete activity name directly. If still unable to determine, return "unclear".
"""
                        else:
                            activity_prompt = f"""
根据用户的消息，从活动列表中找出用户想要查询的具体活动。

用户消息：{user_message}

{activity_list_text}

请直接返回最匹配的活动完整名称，如果仍然无法确定，返回"unclear"。
"""
                        
                        identified_activity = await call_openapi_model(prompt=activity_prompt)
                        
                        if identified_activity.strip().lower() == "unclear" or identified_activity.strip() not in all_activities:
                            response_text = get_message_by_language(
                                status_messages.get("still_unclear", {}), 
                                request.language
                            )
                            transfer_human = 1
                            response_stage = "finish"
                        else:
                            # 确定活动后，用A004查询领取状态
                            api_result = await query_user_eligibility(request.session_id)
                            eligibility_data = extract_user_eligibility(api_result)
                            
                            if eligibility_data["is_success"]:
                                status = eligibility_data["status"]
                                message = eligibility_data["message"]
                                
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
                                    response_text = get_message_by_language(
                                        status_messages.get("unknown_status", {}), 
                                        request.language
                                    )
                                    transfer_human = 1
                                    response_stage = "finish"
                                
                                prompt = build_reply_with_prompt(request.history or [], request.messages, response_text, request.language)
                                response_text = await call_openapi_model(prompt=prompt)
                            else:
                                response_text = get_message_by_language(
                                    status_messages.get("query_failed", {}), 
                                    request.language
                                )
                                transfer_human = 1
                                response_stage = "finish"
                    else:
                        response_text = get_message_by_language(
                            status_messages.get("query_failed", {}), 
                            request.language
                        )
                        transfer_human = 1
                        response_stage = "finish"
            
            # S002提现查询流程
            if message_type == "S002":
                # 获取S002的配置信息
                business_types = config.get("business_types", {})
                s002_config = business_types.get("S002", {})
                status_messages = s002_config.get("status_messages", {})
                
                # 优先检查是否上传图片，不管在哪个阶段
                if request.images and len(request.images) > 0:
                    bot_token = config.get("telegram_bot_token", "")
                    chat_id = config.get("telegram_chat_id", "")
                    if bot_token and chat_id:
                        await send_to_telegram(request.images, bot_token, chat_id, username=request.user_id)
                    
                    response_text = get_message_by_language(
                        status_messages.get("image_uploaded", {}), 
                        request.language
                    )
                    transfer_human = 1
                    response_stage = "finish"
                elif str(stage_number) in ["1", "2", "4"]:
                    # 阶段1、2、4：使用原有的回复生成逻辑
                    stage_response = step_info.get("response", {})
                    stage_text = stage_response.get("text") or step_info.get("step", "")

                    prompt = build_reply_with_prompt(request.history or [], request.messages, stage_text, request.language)
                    response_text = await call_openapi_model(prompt=prompt)

                    # 返回图片（如果有）
                    stage_image = stage_response.get("image", "")
                    if stage_image:
                        response_image = [stage_image]

                    response_stage = "working" if str(stage_number) in ["1", "2"] else "finish"

                elif str(stage_number) == "3":
                    # 阶段3：用户提供订单号，开始处理提现状态查询（图片检查已在上面处理）
                    
                    # 尝试提取订单号
                    order_no = extract_order_no(request.messages, request.history)

                    if order_no:
                        # 调用A002接口查询提现状态
                        api_result = await query_withdrawal_status(request.session_id, order_no)
                        extracted_data = extract_withdrawal_status(api_result)

                        if extracted_data["is_success"]:
                            status = extracted_data["status"]
                            
                            if status == "Withdrawal successful":
                                # 提现成功，通知用户提现成功
                                response_text = get_message_by_language(
                                    status_messages.get("withdrawal_successful", {}), 
                                    request.language
                                )
                                response_stage = "finish"
                            elif status in ["pending", "obligation"]:
                                # 待处理/待付款，回复用户处理中，请耐心等待
                                response_text = get_message_by_language(
                                    status_messages.get("withdrawal_processing", {}), 
                                    request.language
                                )
                                response_stage = "finish"
                            elif status == "canceled":
                                # 用户取消提款，通知用户提现已取消
                                response_text = get_message_by_language(
                                    status_messages.get("withdrawal_canceled", {}), 
                                    request.language
                                )
                                response_stage = "finish"
                            elif status in ["rejected", "prepare", "lock", "oblock", "refused"]:
                                # 已拒绝/准备支付/锁定/待付款锁定/已拒绝，转人工
                                response_text = get_message_by_language(
                                    status_messages.get("withdrawal_issue", {}), 
                                    request.language
                                )
                                transfer_human = 1
                                response_stage = "finish"
                            elif status in ["Withdrawal failed", "confiscate"]:
                                # 支付失败/没收，推送至TG群用户ID，订单号，状态，转人工
                                bot_token = config.get("telegram_bot_token", "")
                                chat_id = config.get("telegram_chat_id", "")
                                if bot_token and chat_id:
                                    # 发送包含用户ID、订单号、状态的消息到TG群
                                    tg_message = f"⚠️ 提现异常\n用户ID: {request.user_id}\n订单号: {order_no}\n状态: {status}"
                                    await send_to_telegram([], bot_token, chat_id, username=request.user_id, custom_message=tg_message)
                                
                                response_text = get_message_by_language(
                                    status_messages.get("withdrawal_failed", {}), 
                                    request.language
                                )
                                transfer_human = 1
                                response_stage = "finish"
                            else:
                                # 其他未知状态，转人工
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
                            response_text = get_message_by_language(
                                status_messages.get("query_failed", {}), 
                                request.language
                            )
                            transfer_human = 1
                            response_stage = "finish"
                    else:
                        # 未能提取到订单号，要求用户明确订单号
                        response_text = get_message_by_language(
                            status_messages.get("order_not_found", {}), 
                            request.language
                        )
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
    从消息和历史中提取订单号（18位纯数字）
    改进算法：查找所有数字序列，返回长度恰好为18位的序列
    """
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
        if len(seq) == 18:
            return seq
    
    return None
