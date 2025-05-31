"""
ChatAI API Service

This module provides a FastAPI application that processes chat messages, 
identifies user intent, and returns appropriate responses.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# 导入配置模块和处理模块
from src.config import init_config, reload_config
from src.process import process_message
from src.util import MessageRequest, MessageResponse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("chatai-api")

# 定义lifespan上下文管理器
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """
    Application lifespan context manager that handles startup and shutdown events.
    """
    # 启动时执行
    logger.info("正在初始化配置...")
    config = init_config()
    logger.info("配置初始化完成，已加载 %d 种业务类型", len(config.get('business_types', {})))
    
    yield
    
    # 关闭时执行
    logger.info("应用关闭，释放资源...")

# 初始化FastAPI应用
app = FastAPI(
    title="ChatAI API",
    description="处理聊天消息的API服务",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求处理时间中间件
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Middleware to add processing time to response headers."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# 重新加载配置的接口
@app.post("/reload_config", response_model=Dict[str, Any])
async def api_reload_config():
    """重新加载配置文件"""
    try:
        logger.info("开始重新加载配置...")
        config = reload_config()
        logger.info("配置重新加载成功")
        return {
            "status": "success",
            "message": "配置重新加载成功",
            "business_types_count": len(config.get("business_types", {}))
        }
    except Exception as e:
        logger.error("配置重新加载失败: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"配置重新加载失败: {str(e)}") from e

# 处理消息的API接口
@app.post("/process", response_model=MessageResponse)
async def api_process_message(request: MessageRequest):
    """处理接收到的消息"""
    try:
        logger.info("处理会话 %s 的消息", request.session_id)
        
        # 调用处理函数，直接传递请求对象
        response = process_message(request)
        
        logger.info("会话 %s 处理完成", request.session_id)
        return response
    except ValueError as e:
        logger.warning("请求参数错误: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("消息处理失败: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"消息处理失败: {str(e)}") from e

# 健康检查接口
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "service": "ChatAI", "timestamp": time.time()}

# 主函数
if __name__ == "__main__":
    # 启动服务
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
