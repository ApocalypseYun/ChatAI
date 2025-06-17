"""
回复模块
"""

from .config import get_message_by_language

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

def get_follow_up_message(language: str) -> str:
    """
    获取后续询问消息
    
    Args:
        language: 语言
        
    Returns:
        str: 后续询问消息
    """
    messages = {
        "zh": "请问还有什么可以帮您？",
        "en": "Is there anything else I can help you with?",
        "th": "มีอะไรอื่นที่ฉันสามารถช่วยคุณได้อีกไหม?",
        "tl": "May iba pa bang maitutulong ko sa inyo?",
        "ja": "他に何かお手伝いできることはありますか？"
    }
    return get_message_by_language(messages, language)

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

def build_guidance_prompt(message_type: str, conversation_rounds: int, user_message: str, history: list, language: str) -> str:
    """
    构建引导用户回到正常流程的提示词
    
    Args:
        message_type: 业务类型 (S001, S002, S003)
        conversation_rounds: 当前对话轮次
        user_message: 用户当前消息
        history: 对话历史
        language: 语言
        
    Returns:
        str: 构建的提示词
    """
    # 业务类型对应的多语言描述
    business_descriptions = {
        "S001": {
            "zh": "充值查询",
            "en": "deposit inquiry",
            "th": "การสอบถามการฝาก",
            "tl": "pagtatanong sa deposito",
            "ja": "入金照会"
        },
        "S002": {
            "zh": "提现查询", 
            "en": "withdrawal inquiry",
            "th": "การสอบถามการถอน",
            "tl": "pagtatanong sa withdrawal",
            "ja": "出金照会"
        },
        "S003": {
            "zh": "活动查询",
            "en": "activity inquiry",
            "th": "การสอบถามกิจกรรม",
            "tl": "pagtatanong sa aktibidad",
            "ja": "アクティビティ照会"
        }
    }
    
    business_desc = business_descriptions.get(message_type, {}).get(language, message_type)
    
    # 根据对话轮次调整引导策略
    if conversation_rounds >= 7:
        if language == "zh":
            urgency_level = "高优先级：即将达到最大轮次限制，需要更积极地引导用户"
        elif language == "th":
            urgency_level = "ความสำคัญสูง: ใกล้ถึงขีดจำกัดการสนทนา ต้องการคำแนะนำที่เข้มงวดมากขึ้น"
        elif language == "tl":
            urgency_level = "MATAAS NA PRIYORIDAD: Malapit nang maabot ang maximum na rounds, kailangan ng mas aktibong gabay"
        elif language == "ja":
            urgency_level = "高優先度：最大ラウンド制限に近づいています、より積極的な誘導が必要です"
        else:
            urgency_level = "HIGH PRIORITY: Approaching maximum rounds, need more active guidance"
    elif conversation_rounds >= 5:
        if language == "zh":
            urgency_level = "中等优先级：应该更明确地引导用户提供必要信息"
        elif language == "th":
            urgency_level = "ความสำคัญปานกลาง: ควรให้คำแนะนำที่ชัดเจนมากขึ้นเพื่อให้ผู้ใช้ให้ข้อมูลที่จำเป็น"
        elif language == "tl":
            urgency_level = "KATAMTAMANG PRIYORIDAD: Dapat mas malinaw na gabayan ang user na magbigay ng kinakailangang impormasyon"
        elif language == "ja":
            urgency_level = "中優先度：ユーザーが必要な情報を提供するようより明確に誘導すべきです"
        else:
            urgency_level = "MEDIUM PRIORITY: Should more clearly guide user to provide necessary information"
    else:
        if language == "zh":
            urgency_level = "正常优先级：耐心引导"
        elif language == "th":
            urgency_level = "ความสำคัญปกติ: ให้คำแนะนำอย่างอดทน"
        elif language == "tl":
            urgency_level = "NORMAL NA PRIYORIDAD: Matyagang gabay"
        elif language == "ja":
            urgency_level = "通常優先度：忍耐強い誘導"
        else:
            urgency_level = "NORMAL PRIORITY: Patient guidance"
    
    # 构建聊天历史字符串
    history_text = ""
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if language == "zh":
            role_text = "用户" if role == "user" else "客服"
        elif language == "th":
            role_text = "ผู้ใช้" if role == "user" else "เจ้าหน้าที่"
        elif language == "tl":
            role_text = "User" if role == "user" else "Customer Service"
        elif language == "ja":
            role_text = "ユーザー" if role == "user" else "カスタマーサービス"
        else:
            role_text = "User" if role == "user" else "Assistant"
        history_text += f"{role_text}: {content}\n"
    
    # 构建引导提示词
    if language == "zh":
        guidance_instructions = f"""
你是一名专业的{business_desc}客服代表。你的目标是引导用户回到主要的{business_desc}流程。

业务背景：{message_type} - {business_desc}
当前对话轮次：{conversation_rounds}/10（10轮后转人工客服）
引导优先级：{urgency_level}

指导原则：
1. 耐心且乐于助人，但随着轮次增加要更加直接
2. 确认用户当前的问题/关切
3. 温和地引导他们回到主要的{business_desc}流程
4. 如果他们对{business_desc}有具体问题，鼓励他们提供必要信息（如S001/S002需要订单号，S003需要具体活动名称）
5. 如果他们的问题完全不相关，礼貌地重新引导
6. 使用鼓励性语言，表现出帮助的意愿
7. 如果对话轮次>5，温和地提及时间限制，鼓励聚焦讨论
8. 提供具体的信息需求示例

具体所需信息：
- S001（充值查询）：18位订单号
- S002（提现查询）：18位订单号
- S003（活动查询）：具体的活动名称

聊天历史：
{history_text}

用户当前消息：{user_message}

请自然地回应并引导用户回到{business_desc}流程，同时解决他们的关切。随着对话轮次增加，要更加直接和具体。
"""
    elif language == "th":
        guidance_instructions = f"""
คุณเป็นตัวแทนฝ่ายบริการลูกค้าระดับมืออาชีพสำหรับบริการ{business_desc} เป้าหมายของคุณคือการนำผู้ใช้กลับสู่กระบวนการหลักของ{business_desc}

บริบทธุรกิจ: {message_type} - {business_desc}
รอบการสนทนาปัจจุบัน: {conversation_rounds}/10 (หลังจาก 10 รอบจะโอนไปยังเจ้าหน้าที่จริง)
ลำดับความสำคัญในการแนะนำ: {urgency_level}

หลักการแนะนำ:
1. อดทนและเต็มใจช่วยเหลือ แต่เป็นการตรงไปตรงมามากขึ้นเมื่อรอบเพิ่มขึ้น
2. ยืนยันคำถาม/ความกังวลปัจจุบันของผู้ใช้
3. นำทางพวกเขากลับสู่กระบวนการหลักของ{business_desc}อย่างอ่อนโยน
4. หากพวกเขามีคำถามเฉพาะเกี่ยวกับ{business_desc} ให้กระตุ้นพวกเขาให้ข้อมูลที่จำเป็น
5. หากคำถามของพวกเขาไม่เกี่ยวข้องเลย ให้เปลี่ยนเส้นทางอย่างสุภาพ
6. ใช้ภาษาที่ให้กำลังใจและแสดงความเต็มใจที่จะช่วยเหลือ
7. หากรอบการสนทนา > 5 ให้กล่าวถึงข้อจำกัดเวลาอย่างอ่อนโยนและส่งเสริมการสนทนาที่มีจุดสนใจ
8. ให้ตัวอย่างเฉพาะของข้อมูลที่คุณต้องการเพื่อช่วยพวกเขา

ข้อมูลเฉพาะที่จำเป็น:
- S001 (การฝาก): หมายเลขคำสั่ง 18 หลัก
- S002 (การถอน): หมายเลขคำสั่ง 18 หลัก
- S003 (กิจกรรม): ชื่อกิจกรรมเฉพาะจากกิจกรรมที่มีอยู่

ประวัติการสนทนา:
{history_text}

ข้อความปัจจุบันของผู้ใช้: {user_message}

โปรดตอบสนองอย่างเป็นธรรมชาติและนำผู้ใช้กลับสู่กระบวนการ{business_desc}ขณะที่จัดการกับความกังวลของพวกเขา เป็นการตรงไปตรงมาและเฉพาะเจาะจงมากขึ้นเมื่อรอบการสนทนาเพิ่มขึ้น
"""
    elif language == "tl":
        guidance_instructions = f"""
Ikaw ay isang propesyonal na customer service representative para sa mga serbisyo ng {business_desc}. Ang inyong layunin ay gabayan ang user pabalik sa pangunahing proseso ng {business_desc}.

Business Context: {message_type} - {business_desc}
Kasalukuyang conversation round: {conversation_rounds}/10 (pagkatapos ng 10 rounds, ililipat sa human agent)
Guidance Priority: {urgency_level}

Mga Gabay na Prinsipyo:
1. Maging matiyaga at handang tumulong, ngunit mas direkta habang tumataas ang mga rounds
2. Kilalanin ang kasalukuyang tanong/alalahanin ng user
3. Mahinahong gabayan sila pabalik sa pangunahing proseso ng {business_desc}
4. Kung may mga tiyak na tanong sila tungkol sa {business_desc}, hikayatin silang magbigay ng kinakailangang impormasyon
5. Kung ang kanilang tanong ay hindi kaugnay, magalang na i-redirect sila
6. Gumamit ng nakahikayat na wika at magpakita ng kagustuhang tumulong
7. Kung conversation rounds > 5, mahinahong banggitin ang time limit at hikayatin ang nakatuon na talakayan
8. Magbigay ng mga tiyak na halimbawa ng impormasyon na kailangan mo para matulungan sila

Tiyak na Impormasyon na Kailangan:
- Para sa S001 (Deposit): 18-digit na order number
- Para sa S002 (Withdrawal): 18-digit na order number
- Para sa S003 (Activity): Tiyak na pangalan ng aktibidad mula sa mga available na aktibidad

Chat History:
{history_text}

Kasalukuyang Mensahe ng User: {user_message}

Mangyaring tumugon nang natural at gabayan ang user pabalik sa proseso ng {business_desc} habang tinutugunan ang kanilang alalahanin. Maging mas direkta at tiyak habang tumataas ang mga conversation rounds.
"""
    elif language == "ja":
        guidance_instructions = f"""
あなたは{business_desc}サービスの専門的なカスタマーサービス担当者です。ユーザーを主要な{business_desc}プロセスに戻すことが目標です。

ビジネスコンテキスト: {message_type} - {business_desc}
現在の会話ラウンド: {conversation_rounds}/10 (10ラウンド後は人間のエージェントに転送)
誘導優先度: {urgency_level}

誘導原則:
1. 忍耐強く親切に、しかしラウンドが増えるにつれてより直接的に
2. ユーザーの現在の質問/懸念を確認する
3. 彼らを{business_desc}の主要プロセスに優しく誘導する
4. {business_desc}について具体的な質問がある場合、必要な情報の提供を奨励する
5. 質問が完全に無関係な場合、丁寧にリダイレクトする
6. 励ましの言葉を使い、助ける意志を示す
7. 会話ラウンド > 5の場合、時間制限を優しく言及し、焦点を絞った議論を奨励する
8. 彼らを助けるために必要な情報の具体例を提供する

必要な具体的情報:
- S001（入金）: 18桁の注文番号
- S002（出金）: 18桁の注文番号
- S003（アクティビティ）: 利用可能なアクティビティからの具体的なアクティビティ名

チャット履歴:
{history_text}

ユーザーの現在のメッセージ: {user_message}

自然に応答し、ユーザーの懸念に対処しながら{business_desc}プロセスに戻すよう誘導してください。会話ラウンドが増えるにつれて、より直接的で具体的になってください。
"""
    else:
        guidance_instructions = f"""
You are a professional customer service representative for {business_desc} services. Your goal is to guide the user back to the main {business_desc} process.

Business Context: {message_type} - {business_desc}
Current conversation round: {conversation_rounds}/10 (after 10 rounds, transfer to human agent)
Guidance Priority: {urgency_level}

Guidelines:
1. Be patient and helpful, but progressively more direct as rounds increase
2. Acknowledge the user's current question/concern
3. Gently guide them back to the main {business_desc} process
4. If they have specific questions about {business_desc}, encourage them to provide necessary information (like order numbers for S001/S002, or specific activity names for S003)
5. If their question is completely unrelated, politely redirect them
6. Use encouraging language and show willingness to help
7. If conversation rounds > 5, gently mention the time limit and encourage focused discussion
8. Provide specific examples of what information you need to help them

Specific Information Needed:
- For S001 (Deposit): 18-digit order number
- For S002 (Withdrawal): 18-digit order number  
- For S003 (Activity): Specific activity name from available activities

Chat History:
{history_text}

Current User Message: {user_message}

Please respond naturally and guide the user back to the {business_desc} process while addressing their concern. Be progressively more direct and specific as conversation rounds increase.
"""
    
    return guidance_instructions
