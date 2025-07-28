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
from src.util import IntentRecognitionRequest, IntentRecognitionResponse
from src.util import call_openapi_model
from src.logging_config import init_logging, get_logger, log_request
from src.auth import verify_token

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

# 预定义意图列表
DEFAULT_INTENTS = [
    "没有收到款项",
    "收到款项订单已回调",
    "等待1-7个工作日退款", 
    "提供转账人信息",
    "提现处理中",
    "已出款成功",
    "重新提交提现申请",
    "等待第三方支付",
    "客户收款卡已限额",
    "客户收款卡号错误",
    "客户收款银行维护",
    "修改客户收款卡",
    "客户卡号异常",
    "请日切后重新提交订单",
    "订单款项已回冲",
    "订单已重新出款"
]

# 意图识别接口
@app.post("/recognize_intent", response_model=IntentRecognitionResponse)
async def recognize_intent(request: IntentRecognitionRequest):
    """意图识别接口，支持自定义意图列表或使用默认意图列表"""
    logger = get_logger("chatai-api")
    request_start_time = time.time()
    
    try:
        logger.info("开始处理意图识别请求", extra={
            'session_id': request.session_id,
            'user_id': request.user_id,
            'language': request.language,
            'text_length': len(request.text) if request.text else 0,
            'intents_count': len(request.intents) if request.intents else 0
        })
        
        # 验证token
        is_valid, token_user_id, error_msg = verify_token(request.token)
        if not is_valid:
            logger.warning("Token验证失败", extra={
                'session_id': request.session_id,
                'user_id': request.user_id,
                'error': error_msg
            })
            raise HTTPException(status_code=401, detail=f"Token验证失败: {error_msg}")
        
        # 验证token中的user_id与请求中的user_id是否一致
        if token_user_id != request.user_id:
            logger.warning("Token中的用户ID与请求不符", extra={
                'session_id': request.session_id,
                'request_user_id': request.user_id,
                'token_user_id': token_user_id
            })
            raise HTTPException(status_code=403, detail="Token中的用户ID与请求不符")
        
        text = request.text or ""
        # 如果用户没有提供意图列表，使用默认意图列表
        intents = request.intents if request.intents else DEFAULT_INTENTS
        
        # 如果没有文本，直接返回空意图
        if not text:
            logger.info("文本为空，返回空意图", extra={
                'session_id': request.session_id,
                'user_id': request.user_id,
                'has_text': bool(text)
            })
            return IntentRecognitionResponse(text=text, intent="")
        
        # 构造大模型提示词，根据语言调整
        language = request.language or "zh"  # 默认中文
        
        if language == "en":
            prompt = (
                "You are an intent recognition assistant. Please select the most matching intent from the intent list below for the user input. Only return the intent itself, do not return other content.\n"
                f"User input: {text}\n"
                f"Available intents: {', '.join(intents)}\n"
                "Please only return the most matching intent string. If no suitable intent is found, return an empty string."
            )
        elif language == "th":
            prompt = (
                "คุณเป็นผู้ช่วยในการจดจำความตั้งใจ กรุณาเลือกความตั้งใจที่ตรงกับการป้อนข้อมูลของผู้ใช้มากที่สุดจากรายการความตั้งใจด้านล่าง ส่งคืนเฉพาะความตั้งใจเท่านั้น ไม่ต้องส่งคืนเนื้อหาอื่น\n"
                f"การป้อนข้อมูลของผู้ใช้: {text}\n"
                f"ความตั้งใจที่มีอยู่: {', '.join(intents)}\n"
                "กรุณาส่งคืนเฉพาะสตริงความตั้งใจที่ตรงกันมากที่สุด หากไม่พบความตั้งใจที่เหมาะสม ให้ส่งคืนสตริงว่าง"
            )
        elif language == "tl":
            prompt = (
                "Ikaw ay isang intent recognition assistant. Mangyaring piliin ang pinakatugmang intent mula sa listahan ng intent sa ibaba para sa input ng user. Ibalik lang ang intent mismo, huwag magbalik ng ibang content.\n"
                f"Input ng user: {text}\n"
                f"Available na mga intent: {', '.join(intents)}\n"
                "Mangyaring ibalik lang ang pinakatugmang intent string. Kung walang suitable na intent, ibalik ang empty string."
            )
        elif language == "ja":
            prompt = (
                "あなたは意図認識アシスタントです。以下の意図リストからユーザー入力に最も適合する意図を選択してください。意図そのもののみを返し、その他の内容は返さないでください。\n"
                f"ユーザー入力: {text}\n"
                f"利用可能な意図: {', '.join(intents)}\n"
                "最も適合する意図文字列のみを返してください。適切な意図が見つからない場合は、空文字列を返してください。"
            )
        else:  # 默认中文
            prompt = (
                "你是一个意图识别助手。请从下面的意图列表中选择最符合用户输入的意图，只返回意图本身，不要返回其他内容。\n"
                f"用户输入: {text}\n"
                f"可选意图: {', '.join(intents)}\n"
                "请只返回最匹配的意图字符串，如果没有合适的意图请返回空字符串。"
            )
        
        try:
            llm_response = await call_openapi_model(prompt=prompt)
            intent = llm_response.strip().split('\n')[0]  # 只取第一行，防止多余内容
            
            # 验证返回的意图是否在候选列表中
            if intent not in intents:
                intent = ""
                
            processing_time = time.time() - request_start_time
            
            logger.info("意图识别完成", extra={
                'session_id': request.session_id,
                'user_id': request.user_id,
                'text': text,
                'recognized_intent': intent,
                'processing_time': round(processing_time, 3),
                'intent_found': bool(intent),
                'used_default_intents': not bool(request.intents)
            })
            
            return IntentRecognitionResponse(text=text, intent=intent)
            
        except Exception as llm_error:
            processing_time = time.time() - request_start_time
            logger.error("LLM调用失败，返回空意图", extra={
                'session_id': request.session_id,
                'user_id': request.user_id,
                'error': str(llm_error),
                'processing_time': round(processing_time, 3)
            }, exc_info=True)
            # LLM调用失败时返回空意图
            return IntentRecognitionResponse(text=text, intent="")
            
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        processing_time = time.time() - request_start_time
        logger.error("意图识别处理失败", extra={
            'session_id': getattr(request, 'session_id', 'unknown'),
            'user_id': getattr(request, 'user_id', 'unknown'),
            'error': str(e),
            'error_type': type(e).__name__,
            'processing_time': round(processing_time, 3)
        }, exc_info=True)
        raise HTTPException(status_code=500, detail=f"意图识别处理失败: {str(e)}") from e

# 获取可用意图列表接口
@app.get("/available_intents")
async def api_get_available_intents():
    """
    获取可用的意图列表
    """
    logger = get_logger("chatai-api")
    
    try:
        intents = DEFAULT_INTENTS.copy()
        
        logger.info("获取可用意图列表", extra={
            'intents_count': len(intents),
            'operation': 'get_available_intents'
        })
        
        return {
            "status": "success",
            "intents": intents,
            "count": len(intents),
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error("获取意图列表失败", extra={
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取意图列表失败: {str(e)}") from e

# 健康检查接口
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "service": "ChatAI", "timestamp": time.time()}

# 主函数
if __name__ == "__main__":
    # 启动服务
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
