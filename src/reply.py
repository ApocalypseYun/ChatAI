"""
回复模块
"""

from src.util import call_openapi_model
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def get_unauthenticated_reply(language: str) -> str:
    """
    获取未登录的回复
    """

    if language == "zh":
        return "您尚未登录，请先登录"
    elif language == "th":
        return "คุณยังไม่ได้เข้าสู่ระบบ กรุณาเข้าสู่ระบบก่อน"
    elif language == "tl":
        return "Hindi ka pa naka-login, mangyaring mag-login muna."
    else:
        return "You are not logged in, please log in first "

def build_reply_with_prompt(history, current_messages, stage_response_text, language):
    """
    根据历史、当前消息、阶段response中的text和目标语言，构建prompt让AI生成一句回复
    Args:
        history: 聊天历史（list of dict）
        current_messages: 当前消息（list of str 或 str）
        stage_response_text: 当前阶段推荐回复内容（str）
        language: 目标语言
    Returns:
        str: AI生成的回复
    """
    if isinstance(current_messages, list):
        current = "\n".join(current_messages)
    else:
        current = str(current_messages)
    prompt = f"""
你是一个智能客服助理，请根据历史对话、用户当前消息和系统建议回复内容，生成一句自然、简洁且符合{language}语言习惯的回复。

历史消息：
"""
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        prompt += f"{role}: {content}\n"
    prompt += f"\n用户当前消息：\n{current}\n"
    prompt += f"\n系统建议回复内容：\n{stage_response_text}\n"
    prompt += f"\n请用{language}语言生成一句自然回复。"
    # 调用大模型生成
    # 注意：此函数需在异步环境下await调用
    return prompt
