"""
回复模块
"""

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
    elif language == "ja":
        return "ログインしていません。まずログインしてください。"
    else:
        return "You are not logged in, please log in first"

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
    
    # 根据语言构建不同的prompt
    if language == "zh":
        prompt = f"""
你是一个智能客服助理，请根据历史对话、用户当前消息和系统建议回复内容，生成一句自然、简洁且符合中文语言习惯的回复。

历史消息：
"""
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            prompt += f"{role}: {content}\n"
        prompt += f"\n用户当前消息：\n{current}\n"
        prompt += f"\n系统建议回复内容：\n{stage_response_text}\n"
        prompt += f"\n请用中文生成一句自然回复。"
    
    elif language == "en":
        prompt = f"""
You are an intelligent customer service assistant. Based on the chat history, current user message, and system suggested reply content, generate a natural, concise response that follows English language conventions.

Chat History:
"""
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            prompt += f"{role}: {content}\n"
        prompt += f"\nCurrent User Message:\n{current}\n"
        prompt += f"\nSystem Suggested Reply:\n{stage_response_text}\n"
        prompt += f"\nPlease generate a natural reply in English."
    
    elif language == "th":
        prompt = f"""
คุณเป็นผู้ช่วยฝ่ายบริการลูกค้าอัจฉริยะ โปรดใช้ประวัติการสนทนา ข้อความปัจจุบันของผู้ใช้ และเนื้อหาการตอบกลับที่ระบบแนะนำ เพื่อสร้างการตอบกลับที่เป็นธรรมชาติ กระชับ และเป็นไปตามธรรมเนียมภาษาไทย

ประวัติการสนทนา:
"""
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            prompt += f"{role}: {content}\n"
        prompt += f"\nข้อความปัจจุบันของผู้ใช้:\n{current}\n"
        prompt += f"\nการตอบกลับที่ระบบแนะนำ:\n{stage_response_text}\n"
        prompt += f"\nโปรดสร้างการตอบกลับที่เป็นธรรมชาติเป็นภาษาไทย"
    
    elif language == "tl":
        prompt = f"""
Ikaw ay isang matalinong customer service assistant. Batay sa kasaysayan ng chat, kasalukuyang mensahe ng user, at iminungkahing sagot ng system, bumuo ng natural, maikling sagot na sumusunod sa mga kaugalian ng wikang Filipino.

Kasaysayan ng Chat:
"""
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            prompt += f"{role}: {content}\n"
        prompt += f"\nKasalukuyang Mensahe ng User:\n{current}\n"
        prompt += f"\nIminungkahing Sagot ng System:\n{stage_response_text}\n"
        prompt += f"\nPakibuo ang natural na sagot sa wikang Filipino."
    
    elif language == "ja":
        prompt = f"""
あなたは知能的なカスタマーサービスアシスタントです。チャット履歴、現在のユーザーメッセージ、システム推奨返信内容に基づいて、日本語の言語習慣に従った自然で簡潔な返信を生成してください。

チャット履歴:
"""
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            prompt += f"{role}: {content}\n"
        prompt += f"\n現在のユーザーメッセージ:\n{current}\n"
        prompt += f"\nシステム推奨返信:\n{stage_response_text}\n"
        prompt += f"\n日本語で自然な返信を生成してください。"
    
    else:
        # 默认使用英文
        prompt = f"""
You are an intelligent customer service assistant. Based on the chat history, current user message, and system suggested reply content, generate a natural, concise response.

Chat History:
"""
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            prompt += f"{role}: {content}\n"
        prompt += f"\nCurrent User Message:\n{current}\n"
        prompt += f"\nSystem Suggested Reply:\n{stage_response_text}\n"
        prompt += f"\nPlease generate a natural reply in {language}."
    
    return prompt
