"""
意图识别服务模块
"""

from typing import Dict, List, Any, Optional
from src.auth import verify_token
from src.logging_config import get_logger
from src.util import MessageRequest, MessageResponse
import time

logger = get_logger("intent-service")

# 预定义的意图列表
PREDEFINED_INTENTS = [
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

class IntentRequest:
    """意图识别请求类"""
    def __init__(self, user_id: str, session_id: str, message: str, token: str, language: str = "zh"):
        self.user_id = user_id
        self.session_id = session_id
        self.message = message
        self.token = token
        self.language = language
    
    def validate_token(self) -> tuple[bool, Optional[str]]:
        """验证token"""
        is_valid, extracted_user_id, error_msg = verify_token(self.token)
        if not is_valid:
            return False, error_msg
        
        if extracted_user_id != self.user_id:
            return False, "Token中的用户ID与请求中的用户ID不匹配"
        
        return True, None

class IntentResponse:
    """意图识别响应类"""
    def __init__(self, intent: str, confidence: float, status: str = "success", error: str = None):
        self.intent = intent
        self.confidence = confidence
        self.status = status
        self.error = error
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "status": self.status,
            "intent": self.intent,
            "confidence": self.confidence,
            "timestamp": self.timestamp
        }
        
        if self.error:
            result["error"] = self.error
            
        return result

async def identify_customer_intent(request: IntentRequest) -> IntentResponse:
    """
    识别客户意图
    
    Args:
        request: 意图识别请求
        
    Returns:
        IntentResponse: 意图识别结果
    """
    start_time = time.time()
    
    logger.info(f"开始处理意图识别请求", extra={
        'user_id': request.user_id,
        'session_id': request.session_id,
        'message_length': len(request.message),
        'language': request.language
    })
    
    try:
        # 验证token
        is_valid, error_msg = request.validate_token()
        if not is_valid:
            logger.warning(f"Token验证失败", extra={
                'user_id': request.user_id,
                'session_id': request.session_id,
                'error': error_msg
            })
            return IntentResponse(
                intent="",
                confidence=0.0,
                status="error",
                error=f"认证失败: {error_msg}"
            )
        
        # 进行意图识别
        intent, confidence = await _perform_intent_recognition(request.message, request.language)
        
        processing_time = time.time() - start_time
        
        logger.info(f"意图识别完成", extra={
            'user_id': request.user_id,
            'session_id': request.session_id,
            'identified_intent': intent,
            'confidence': confidence,
            'processing_time': processing_time
        })
        
        return IntentResponse(
            intent=intent,
            confidence=confidence,
            status="success"
        )
        
    except Exception as e:
        processing_time = time.time() - start_time
        
        logger.error(f"意图识别处理异常", extra={
            'user_id': request.user_id,
            'session_id': request.session_id,
            'error': str(e),
            'processing_time': processing_time
        }, exc_info=True)
        
        return IntentResponse(
            intent="",
            confidence=0.0,
            status="error",
            error=f"处理异常: {str(e)}"
        )

async def _perform_intent_recognition(message: str, language: str) -> tuple[str, float]:
    """
    执行意图识别
    
    Args:
        message: 用户消息
        language: 语言
        
    Returns:
        tuple[str, float]: (识别的意图, 置信度)
    """
    from src.util import call_openapi_model
    from src.config import get_config
    
    config = get_config()
    api_key = config.get("api_key", "")
    
    # 构建提示语
    intents_text = "\n".join([f"{i+1}. {intent}" for i, intent in enumerate(PREDEFINED_INTENTS)])
    
    prompt = f"""
你是一个专业的客户服务意图识别助理。请根据用户的消息内容，从以下预定义的意图列表中选择最匹配的一个：

{intents_text}

用户消息：{message}
语言：{language}

请分析用户消息的核心意图，选择最匹配的意图。

要求：
1. 只返回意图编号（1-{len(PREDEFINED_INTENTS)}）
2. 如果无法匹配任何意图，返回0
3. 只返回数字，不要其他内容

分析原则：
- 仔细理解用户消息的核心诉求
- 考虑语言表达的习惯和语境
- 优先匹配最直接相关的意图
- 如果消息模糊或不相关，返回0
"""
    
    try:
        # 调用AI模型进行识别
        reply = await call_openapi_model(prompt=prompt, api_key=api_key)
        result = reply.strip()
        
        # 解析结果
        try:
            intent_index = int(result)
            if intent_index == 0:
                return "未知意图", 0.0
            elif 1 <= intent_index <= len(PREDEFINED_INTENTS):
                intent = PREDEFINED_INTENTS[intent_index - 1]
                # 基于AI返回的确定性给出置信度
                confidence = 0.85  # 默认置信度
                return intent, confidence
            else:
                logger.warning(f"AI返回无效的意图编号: {intent_index}")
                return "未知意图", 0.0
                
        except ValueError:
            logger.warning(f"AI返回非数字结果: {result}")
            return "未知意图", 0.0
            
    except Exception as e:
        logger.error(f"调用AI模型失败: {str(e)}")
        return "识别失败", 0.0

def get_available_intents() -> List[str]:
    """
    获取可用的意图列表
    
    Returns:
        List[str]: 意图列表
    """
    return PREDEFINED_INTENTS.copy()

def update_intents(new_intents: List[str], admin_token: str) -> Dict[str, Any]:
    """
    更新意图列表（管理员功能）
    
    Args:
        new_intents: 新的意图列表
        admin_token: 管理员token
        
    Returns:
        Dict[str, Any]: 更新结果
    """
    # TODO: 实现管理员验证逻辑
    # 这里可以添加管理员token验证
    
    logger.info(f"意图列表更新请求", extra={
        'new_intents_count': len(new_intents),
        'old_intents_count': len(PREDEFINED_INTENTS)
    })
    
    try:
        # 验证新意图列表的有效性
        if not new_intents:
            return {
                "status": "error",
                "message": "意图列表不能为空"
            }
        
        if len(new_intents) > 50:
            return {
                "status": "error", 
                "message": "意图列表长度不能超过50个"
            }
        
        # 更新全局意图列表
        global PREDEFINED_INTENTS
        old_intents = PREDEFINED_INTENTS.copy()
        PREDEFINED_INTENTS.clear()
        PREDEFINED_INTENTS.extend(new_intents)
        
        logger.info(f"意图列表更新成功", extra={
            'old_intents': old_intents,
            'new_intents': new_intents
        })
        
        return {
            "status": "success",
            "message": "意图列表更新成功",
            "old_count": len(old_intents),
            "new_count": len(new_intents)
        }
        
    except Exception as e:
        logger.error(f"意图列表更新失败: {str(e)}")
        return {
            "status": "error",
            "message": f"更新失败: {str(e)}"
        }
