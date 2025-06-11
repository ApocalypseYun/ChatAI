"""
ChatAI API Service

This module provides a FastAPI application that processes chat messages, 
identifies user intent, and returns appropriate responses.
"""

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

# 导入配置模块和处理模块
from src.config import init_config, reload_config
from src.process import process_message
from src.util import MessageRequest, MessageResponse
from src.logging_config import init_logging, get_logger, log_request

# 定义lifespan上下文管理器
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """
    Application lifespan context manager that handles startup and shutdown events.
    """
    # 启动时执行 - 初始化日志配置
    logging_config_path = Path("config/logging_config.json")
    if logging_config_path.exists():
        with open(logging_config_path, 'r', encoding='utf-8') as f:
            logging_config = json.load(f)
        init_logging(logging_config)
    else:
        init_logging()
    
    logger = get_logger("chatai-api")
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
    logger = get_logger("chatai-access")
    
    # 记录请求开始
    logger.info(f"收到HTTP请求", extra={
        'method': request.method,
        'url': str(request.url),
        'client_ip': request.client.host if request.client else 'unknown',
        'user_agent': request.headers.get('user-agent', 'unknown'),
        'request_id': id(request)
    })
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        # 记录请求完成
        logger.info(f"HTTP请求处理完成", extra={
            'method': request.method,
            'url': str(request.url),
            'status_code': response.status_code,
            'process_time': round(process_time, 3),
            'request_id': id(request)
        })
        
        return response
    except Exception as e:
        process_time = time.time() - start_time
        
        # 记录请求异常
        logger.error(f"HTTP请求处理异常", extra={
            'method': request.method,
            'url': str(request.url),
            'error': str(e),
            'process_time': round(process_time, 3),
            'request_id': id(request)
        }, exc_info=True)
        
        raise

# 重新加载配置的接口
@app.post("/reload_config", response_model=Dict[str, Any])
async def api_reload_config():
    """重新加载配置文件"""
    logger = get_logger("chatai-api")
    try:
        logger.info("管理员请求重新加载配置", extra={
            'operation': 'reload_config',
            'timestamp': time.time()
        })
        
        config = reload_config()
        business_types_count = len(config.get("business_types", {}))
        
        logger.info("配置重新加载成功", extra={
            'operation': 'reload_config',
            'business_types_count': business_types_count,
            'config_keys': list(config.keys()) if isinstance(config, dict) else 'not_dict'
        })
        
        return {
            "status": "success",
            "message": "配置重新加载成功",
            "business_types_count": business_types_count
        }
    except Exception as e:
        logger.error("配置重新加载失败", extra={
            'operation': 'reload_config',
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)
        raise HTTPException(status_code=500, detail=f"配置重新加载失败: {str(e)}") from e

# 处理消息的API接口
@app.post("/process", response_model=MessageResponse)
async def api_process_message(request: MessageRequest):
    """处理接收到的消息"""
    logger = get_logger("chatai-api")
    request_start_time = time.time()
    
    try:
        logger.info("开始处理消息请求", extra={
            'session_id': request.session_id,
            'user_id': getattr(request, 'user_id', 'unknown'),
            'message_type': getattr(request, 'type', None),
            'language': getattr(request, 'language', 'unknown'),
            'site': getattr(request, 'site', 'unknown'),
            'has_images': bool(getattr(request, 'images', [])),
            'has_history': bool(getattr(request, 'history', [])),
            'status': getattr(request, 'status', 'unknown'),
            'platform': getattr(request, 'platform', 'unknown')
        })
        
        # 记录请求日志
        log_request(
            session_id=request.session_id,
            user_id=getattr(request, 'user_id', None),
            message_type=getattr(request, 'type', None),
            language=getattr(request, 'language', 'unknown'),
            site=getattr(request, 'site', 'unknown')
        )
        
        # 调用处理函数，直接传递请求对象
        response = await process_message(request)
        
        processing_time = time.time() - request_start_time
        
        logger.info("消息处理完成", extra={
            'session_id': request.session_id,
            'user_id': getattr(request, 'user_id', 'unknown'),
            'processing_time': round(processing_time, 3),
            'final_status': response.status,
            'response_stage': response.stage,
            'transfer_human': response.transfer_human,
            'business_type': response.type,
            'response_length': len(response.response) if response.response else 0
        })
        
        return response
        
    except ValidationError as e:
        processing_time = time.time() - request_start_time
        logger.warning("请求参数验证错误", extra={
            'session_id': getattr(request, 'session_id', 'unknown'),
            'error': str(e),
            'error_type': 'validation_error',
            'processing_time': round(processing_time, 3)
        })
        raise HTTPException(status_code=422, detail=str(e)) from e
        
    except ValueError as e:
        processing_time = time.time() - request_start_time
        logger.warning("请求参数错误", extra={
            'session_id': getattr(request, 'session_id', 'unknown'),
            'error': str(e),
            'error_type': 'value_error',
            'processing_time': round(processing_time, 3)
        })
        raise HTTPException(status_code=422, detail=str(e)) from e
        
    except Exception as e:
        processing_time = time.time() - request_start_time
        logger.error("消息处理失败", extra={
            'session_id': getattr(request, 'session_id', 'unknown'),
            'user_id': getattr(request, 'user_id', 'unknown'),
            'error': str(e),
            'error_type': type(e).__name__,
            'processing_time': round(processing_time, 3)
        }, exc_info=True)
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
