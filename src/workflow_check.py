"""
工作流检查模块
"""

from typing import List, Dict, Any
from src.util import call_openapi_model  # 异步方法
from src.config import get_config

config = get_config()
api_key= config.get("api_key", "")

def _build_intent_prompt(messages: str, history: List[Dict[str, Any]]) -> str:
    """
    构造用于识别意图的提示语，要求AI只能从config中的business_types key+name中选择
    """
    config = get_config()
    business_types = config.get("business_types", {})
    options = "\n".join([f"{k}: {v.get('name', '')}" for k, v in business_types.items()])
    prompt = f"""
    你是意图识别助理。
    当前会话消息：{messages}
    历史消息记录：
    """
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        prompt += f"{role}: {content}\n"
    prompt += f"请只从以下业务类型中选择最匹配的一个，返回其编号（key）：\n{options}\n只返回编号（key），不要返回其他内容。"
    return prompt.strip()

def _build_stage_prompt(intent: str, messages: List[str], history: List[Dict[str, Any]]) -> str:
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
    for msg in messages:
        prompt += f"{msg}\n"
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

async def identify_intent(messages: str, history: List[Dict[str, Any]], language: str) -> str:
    # 先用关键词匹配
    matched_intent = match_intent_by_keywords(messages, language)
    if matched_intent:
        return matched_intent
    # 匹配不到再用 openai
    prompt = _build_intent_prompt(messages, history)
    reply = await call_openapi_model(prompt=prompt, api_key=api_key)
    ai_result = reply.strip()
    # 校验AI返回的key是否合法
    config = get_config()
    business_types = config.get("business_types", {})
    if ai_result in business_types:
        return ai_result
    # 返回不合法，转人工
    return "human_service"

async def identify_stage(intent: str, messages: List[str], history: List[Dict[str, Any]]) -> str:
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