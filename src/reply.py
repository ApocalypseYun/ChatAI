"""
回复模块
"""

def get_unauthenticated_reply(language: str) -> str:
    """
    获取未登录的回复
    """

    if language == "zh":
        return "您尚未登录，请先登录"
    else:
        return "You are not logged in, please log in first "
