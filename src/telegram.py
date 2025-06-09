import httpx

async def send_to_telegram(images, bot_token, chat_id, username=None, custom_message=None):
    """
    发送图片或文本消息到Telegram
    :param images: 图片URL列表
    :param bot_token: Telegram Bot Token  
    :param chat_id: Telegram Chat ID
    :param username: 用户名，可选
    :param custom_message: 自定义文本消息，如果提供则直接发送文本而不是图片
    """
    async with httpx.AsyncClient() as client:
        # 如果有自定义消息，发送文本消息
        if custom_message:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": custom_message
            }
            await client.post(url, data=data)
        
        # 发送图片（如果有）
        if images:
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            for img_url in images:
                data = {
                    "chat_id": chat_id,
                    "photo": img_url
                }
                if username:
                    data["caption"] = f"用户: {username}"
                await client.post(url, data=data)
