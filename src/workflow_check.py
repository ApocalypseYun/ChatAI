"""
工作流检查模块
"""

from typing import List, Dict, Any
from util import call_openapi_model  # 异步方法
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # 从环境变量读取

def _build_intent_prompt(messages: str, history: List[Dict[str, Any]], language: str) -> str:
    """
    构造用于识别意图的提示语
    """
    prompt = f"""
你是意图识别助理。
当前会话消息：{messages}
历史消息记录：
"""
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        prompt += f"{role}: {content}\n"
    prompt += f"请根据上述内容，用{language}语言返回简明意图关键词。"
    return prompt.strip()

def _build_stage_prompt(intent: str, messages: List[str], history: List[Dict[str, Any]], language: str) -> str:
    """
    构造用于识别会话阶段的提示语
    """
    prompt = f"""
你是会话流程判断助理。
已识别意图：{intent}
当前会话消息：
"""
    for msg in messages:
        prompt += f"{msg}\n"

    prompt += "历史消息记录：\n"
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        prompt += f"{role}: {content}\n"

    prompt += f"请根据以上内容，用{language}语言返回当前会话流程的阶段标签。"
    return prompt.strip()

async def identify_intent(messages: str, history: List[Dict[str, Any]], language: str) -> str:
    prompt = _build_intent_prompt(messages, history, language)
    reply = await call_openapi_model(prompt=prompt, api_key=OPENAI_API_KEY)
    return reply.strip()

async def identify_stage(intent: str, messages: List[str], history: List[Dict[str, Any]], language: str) -> str:
    prompt = _build_stage_prompt(intent, messages, history, language)
    reply = await call_openapi_model(prompt=prompt, api_key=OPENAI_API_KEY)
    return reply.strip()