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

def _build_stage_prompt(intent: str, messages: str, history: List[Dict[str, Any]]) -> str:
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
当前会话消息：
"""

    prompt += f"{messages}\n"
    prompt += "历史消息记录：\n"
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        prompt += f"{role}: {content}\n"
    prompt += f"请只从以下流程阶段中选择最匹配的一个，返回其编号（key）：\n{options}\n只返回编号（key），不要返回其他内容。"
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

async def identify_stage(intent: str, messages: str, history: List[Dict[str, Any]]) -> str:
    prompt = _build_stage_prompt(intent, messages, history)
    reply = await call_openapi_model(prompt=prompt, api_key=api_key)
    ai_result = reply.strip()
    # 校验AI返回的key是否合法
    config = get_config()
    workflow = config.get("business_types", {}).get(intent, {}).get("workflow", {})
    if ai_result in workflow:
        return ai_result
    # 返回不合法，转人工
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
        "Is there anything else I can help you with",
        "มีอะไรอื่นที่ฉันสามารถช่วยคุณได้อีกไหม",
        "May iba pa bang maitutulong ko sa inyo",
        "他に何かお手伝いできることはありますか"
    ]
    
    return any(keyword in last_ai_message for keyword in follow_up_keywords)