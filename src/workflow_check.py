"""
工作流检查模块
"""

from typing import List, Dict, Any
from src.util import call_openapi_model  # 异步方法
from src.config import get_config

config = get_config()
api_key= config.get("api_key", "")

def _build_intent_prompt(messages: str, history: List[Dict[str, Any]], category: Dict[str, str] = None) -> str:
    """
    构造用于识别意图的提示语，要求AI只能从config中的business_types key+name中选择
    """
    config = get_config()
    business_types = config.get("business_types", {})
    options = "\n".join([f"{k}: {v.get('name', '')}" for k, v in business_types.items()])
    
    prompt = f"""
你是意图识别助理。
当前会话消息：{messages}
"""
    
    # 添加category信息作为意图识别的参考
    if category:
        prompt += f"用户意图分类参考：{category}\n"
        prompt += """
注意：category参数仅作为意图识别的参考，具体的意图识别需要结合用户的实际消息内容：

业务类型映射关系：
- Withdrawal相关 → S002 (提现查询)
- Deposit相关 → S001 (充值查询)  
- Promotion Bonus相关 → S003 (活动查询)
- 其他类型 → human_service (人工客服)

特殊处理规则：
1. 如果category显示为以下情况，直接用AI处理，不进行具体的S001/S002/S003业务流程：
   - "Withdrawal not received"
   - "Deposit not received"
   - "Check agent commission"
   - "Check rebate bonus"
   - "Check spin promotion"
   - "Check VIP salary"
   
2. 对于上述特殊情况，应该返回"human_service"让AI直接处理用户问题

"""
    
    prompt += "历史消息记录：\n"
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        prompt += f"{role}: {content}\n"
    
    prompt += f"""
请只从以下业务类型中选择最匹配的一个，返回其编号（key）：
{options}

判断原则：
1. 首先参考category参数的分类建议
2. 结合用户的具体消息内容进行最终判断
3. 对于需要AI直接处理的问题，返回"human_service"
4. 只返回编号（key），不要返回其他内容
"""
    
    return prompt.strip()

def _build_stage_prompt(intent: str, messages: str, history: List[Dict[str, Any]], category: Dict[str, str] = None) -> str:
    """
    构造用于识别会话阶段的提示语，要求AI只能从指定intent下的workflow key+step中选择
    """
    config = get_config()
    business_types = config.get("business_types", {})
    workflow = business_types.get(intent, {}).get("workflow", {})
    options = "\n".join([f"{k}: {v.get('step', '')}" for k, v in workflow.items()])
    prompt = f"""
你是会话流程判断助理。
当前业务类型编号：{intent}
当前会话消息：{messages}
"""

    # 针对S001/S002业务类型，添加订单号识别的特殊说明
    if intent in ["S001", "S002"]:
        prompt += """
重要：订单号识别规则
- 如果用户消息中包含18位纯数字（如：123456789012345678），这是订单号，应该识别为stage="3"
- 不要被其他内容干扰，只要包含18位数字就是提供了订单号
- 即使用户同时说了其他话（如"我的订单号是123456789012345678，什么时候到账？"），也应该识别为stage="3"

"""

    # 添加category信息作为stage识别的参考
    if category:
        prompt += f"用户意图分类参考：{category}\n"
        if intent == "S003":
            prompt += """
category信息解读指南（针对S003活动查询）：
- 如果category包含具体活动名称（如 {"Agent": "Yesterday Dividends"}），说明用户明确要查询该活动
- 此时应该识别为stage="1"或"2"，而不是stage="0"
- stage="0"仅用于完全不相关的询问

活动查询stage判断规则：
- stage="1": 用户询问活动或提供了具体活动名称（从category中获得）
- stage="2": 用户继续询问活动相关问题
- stage="0": 用户询问与活动完全无关的内容

"""

    prompt += "历史消息记录：\n"
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        prompt += f"{role}: {content}\n"
    
    prompt += f"""
请只从以下流程阶段中选择最匹配的一个，返回其编号（key）：
{options}

判断原则：
1. 优先检查是否包含18位订单号（适用于S001/S002）
2. 参考category参数提供的上下文信息
3. 结合用户的具体消息内容和历史对话
4. 特别注意：如果category提供了具体活动信息，通常不应该返回stage="0"

只返回编号（key），不要返回其他内容。"""
    return prompt.strip()

def match_intent_by_keywords(messages: str, language: str) -> str:
    """
    通过关键词匹配业务类型
    Args:
        messages: 当前消息内容
        language: 语言
    Returns:
        str: 匹配到的业务类型 key，未匹配到返回空字符串
    """
    config = get_config()
    business_types = config.get("business_types", {})
    for bkey, btype in business_types.items():
        keywords = btype.get("keywords", {}).get(language, [])
        for kw in keywords:
            if kw in messages:
                return bkey
    return ""

async def identify_intent(messages: str, history: List[Dict[str, Any]], language: str, category: Dict[str, str] = None) -> str:
    # 首先检查category信息，如果有活动相关的category，直接返回S003
    if category and isinstance(category, dict):
        activity_categories = ["Agent", "Rebate", "Lucky Spin", "All member", "Sports"]
        for cat_key, cat_value in category.items():
            if cat_key in activity_categories and cat_value:
                return "S003"
    
    # 其次检查是否是需要直接转人工的特殊问题
    special_human_service_keywords = {
        "zh": ["kyc", "实名认证", "身份验证", "如何注册", "怎么注册", "忘记密码", "忘记用户名", "账户被盗", "登录问题", 
               "添加银行", "删除银行", "绑定银行卡", "解绑银行卡", "修改银行卡", "银行卡问题",
               "如何充值", "怎么充值", "充值方法", "如何提现", "怎么提现", "提现方法",
               "成为代理", "代理申请", "代理问题"],
        "en": ["kyc", "how to register", "registration", "forgot password", "forgot username", "account hacked", 
               "login issue", "login problem", "add bank", "delete bank", "bind bank card", "unbind bank card",
               "how to deposit", "deposit method", "how to withdraw", "withdrawal method", "withdrawal options",
               "become agent", "agent application", "how to make kyc", "verification"],
        "th": ["kyc", "วิธีการลงทะเบียน", "ลืมรหัสผ่าน", "ลืมชื่อผู้ใช้", "บัญชีถูกแฮก", "ปัญหาการเข้าสู่ระบบ",
               "เพิ่มธนาคาร", "ลบธนาคาร", "วิธีฝากเงิน", "วิธีถอนเงิน", "เป็นตัวแทน"],
        "tl": ["kyc", "paano mag-register", "nakalimutan ang password", "nakalimutan ang username", "na-hack na account",
               "problema sa login", "magdagdag ng bank", "magtanggal ng bank", "paano mag-deposit", "paano mag-withdraw",
               "maging agent"],
        "ja": ["kyc", "登録方法", "パスワードを忘れた", "ユーザー名を忘れた", "アカウントハッキング", "ログイン問題",
               "銀行追加", "銀行削除", "入金方法", "出金方法", "エージェントになる"]
    }
    
    # 检查特殊关键词
    current_special_keywords = special_human_service_keywords.get(language, special_human_service_keywords["en"])
    message_lower = messages.lower()
    
    for keyword in current_special_keywords:
        if keyword.lower() in message_lower:
            return "human_service"
    
    # 先用关键词匹配
    matched_intent = match_intent_by_keywords(messages, language)
    if matched_intent:
        return matched_intent
    # 匹配不到再用 openai，结合category参数
    prompt = _build_intent_prompt(messages, history, category)
    reply = await call_openapi_model(prompt=prompt, api_key=api_key)
    ai_result = reply.strip()
    # 校验AI返回的key是否合法
    config = get_config()
    business_types = config.get("business_types", {})
    if ai_result in business_types:
        return ai_result
    # 返回不合法，判断是否为闲聊还是需要人工
    # 如果是明确的人工客服请求，返回human_service，否则返回chat_service
    human_service_keywords = {
        "zh": ["人工", "客服", "转人工", "人工客服", "客服人员"],
        "en": ["human", "agent", "customer service", "representative", "support staff"],
        "th": ["มนุษย์", "เจ้าหน้าที่", "บริการลูกค้า"],
        "tl": ["tao", "customer service", "representative"],
        "ja": ["人間", "担当者", "カスタマーサービス"]
    }
    
    keywords = human_service_keywords.get(language, human_service_keywords["en"])
    if any(keyword in messages.lower() for keyword in keywords):
        return "human_service"
    else:
        return "chat_service"

async def identify_stage(intent: str, messages: str, history: List[Dict[str, Any]], category: Dict[str, str] = None) -> str:
    from src.logging_config import get_logger
    logger = get_logger("workflow-check")
    
    # 对于S001/S002业务类型，优先检查是否包含18位订单号
    if intent in ["S001", "S002"]:
        import re
        
        # 查找所有数字序列
        number_sequences = re.findall(r'\d+', messages)
        # 检查是否有18位数字
        for seq in number_sequences:
            if len(seq) == 18:  # 18位订单号
                logger.info(f"检测到18位订单号，直接返回stage 3", extra={
                    'intent': intent,
                    'order_no': seq,
                    'user_message': messages[:100],
                    'stage_override': True,
                    'returned_stage': "3"
                })
                return "3"  # 直接返回stage 3（订单号查询）
        
        logger.debug(f"未检测到18位订单号，继续AI识别", extra={
            'intent': intent,
            'found_sequences': number_sequences,
            'sequence_lengths': [len(seq) for seq in number_sequences],
            'user_message': messages[:100]
        })
    
    prompt = _build_stage_prompt(intent, messages, history, category)
    reply = await call_openapi_model(prompt=prompt, api_key=api_key)
    ai_result = reply.strip()
    
    # 添加AI识别结果的日志
    logger.info(f"AI stage识别完成", extra={
        'intent': intent,
        'ai_result': ai_result,
        'user_message': messages[:100],
        'history_length': len(history) if history else 0
    })
    
    # 校验AI返回的key是否合法
    config = get_config()
    workflow = config.get("business_types", {}).get(intent, {}).get("workflow", {})
    if ai_result in workflow:
        return ai_result
    
    # 返回不合法，转人工
    logger.warning(f"AI返回的stage不合法，转人工处理", extra={
        'intent': intent,
        'invalid_ai_result': ai_result,
        'valid_stages': list(workflow.keys()),
        'fallback_to': 'human_service'
    })
    return "human_service"

def is_follow_up_satisfaction_check(request) -> bool:
    """
    检查是否为后续询问的回复
    通过检查历史记录中最后一条AI回复是否包含"请问还有什么可以帮您"
    
    Args:
        request: MessageRequest对象
        
    Returns:
        bool: 是否为后续询问的回复
    """
    if not request.history or len(request.history) < 1:
        return False
    
    # 获取最后一条AI回复
    last_ai_message = None
    for message in reversed(request.history):
        if message.get("role") == "assistant":
            last_ai_message = message.get("content", "")
            break
    
    if not last_ai_message:
        return False
    
    # 检查是否包含后续询问的关键词
    follow_up_keywords = [
        "请问还有什么可以帮您",
        "还有其他问题吗",
        "有什么问题要帮您的",
        "Is there anything else I can help you with",
        "Is there anything else you'd like to know",
        "Can I help you with anything else",
        "Do you have any other questions",
        "มีอะไรอื่นที่ฉันสามารถช่วยคุณได้อีกไหม",
        "คุณมีคำถามอื่นๆ อีกไหม",
        "May iba pa bang maitutulong ko sa inyo",
        "May iba pang tanong",
        "他に何かお手伝いできることはありますか",
        "他にご質問はありますか"
    ]
    
    return any(keyword in last_ai_message for keyword in follow_up_keywords)