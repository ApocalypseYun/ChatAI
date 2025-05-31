# 定义请求模型
from pydantic import BaseModel
from typing import Dict, List, Any, Optional

class MessageRequest(BaseModel):
    session_id: str
    user_id: str
    platform: str
    language: str = "en"
    status: int = 1  # 0：未登录，1：已登录
    type: Optional[str] = None
    messages: str
    history: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    site: int = 1
    transfer_human: int = 0

class MessageResponse(BaseModel):
    session_id: str
    status: str
    response: str
    stage: str = "working"
    metadata: Dict[str, Any] = {}
    images: Optional[List[str]] = None
    site: int = 1
    type: Optional[str] = None
    transfer_human: int = 0