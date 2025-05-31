from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import uvicorn
import json

# 导入配置模块和处理模块
from src.config import init_config, reload_config
from src.process import process_message

# 初始化FastAPI应用
app = FastAPI(title="ChatAI API", description="处理聊天消息的API服务", version="1.0.0")

# 定义请求模型
class MessageRequest(BaseModel):
    session_id: str
    user_id: str
    platform: str
    language: str = "en"
    status: int = 1
    type: str = ""
    messages: str
    history: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

# 定义响应模型
class MessageResponse(BaseModel):
    session_id: str
    status: str
    response: str
    stage: str
    metadata: Dict[str, Any]
    images: Optional[List[str]] = None

# 应用启动时初始化配置
@app.on_event("startup")
async def startup_event():
    """应用启动时执行的函数"""
    print("正在初始化配置...")
    config = init_config()
    print(f"配置初始化完成，已加载 {len(config.get('business_types', {}))} 种业务类型")

# 重新加载配置的接口
@app.post("/reload_config", response_model=Dict[str, Any])
async def api_reload_config():
    """重新加载配置文件"""
    try:
        config = reload_config()
        return {
            "status": "success",
            "message": "配置重新加载成功",
            "business_types_count": len(config.get("business_types", {}))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配置重新加载失败: {str(e)}")

# 处理消息的API接口
@app.post("/process", response_model=MessageResponse)
async def api_process_message(request: MessageRequest):
    """处理接收到的消息"""
    try:
        # 调用处理函数
        response = process_message(
            request.session_id,
            request.user_id,
            request.platform,
            request.language,
            request.status,
            request.type,
            request.messages,
            request.history or [],
            request.images or [],
            request.metadata or {}
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"消息处理失败: {str(e)}")

# 健康检查接口
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "service": "ChatAI"}

# 主函数
if __name__ == "__main__":
    # 启动服务
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True) 