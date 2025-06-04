import httpx

async def send_to_telegram(images, bot_token, chat_id, username=None):
    """
    发送图片到Telegram
    :param images: 图片URL列表
    :param bot_token: Telegram Bot Token
    :param chat_id: Telegram Chat ID
    :param username: 用户名，可选
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    async with httpx.AsyncClient() as client:
        for img_url in images:
            data = {
                "chat_id": chat_id,
                "photo": img_url
            }
            if username:
                data["caption"] = f"用户: {username}"
            await client.post(url, data=data)
