import hashlib
import hmac
import time
from typing import Optional, Tuple
from .logging_config import get_logger
from .config import get_config

logger = get_logger("chatai-auth")

# 默认密钥，实际使用时应该从配置文件读取
DEFAULT_SECRET_KEY = "ChatAI_Secret_Key_2025"

def generate_token(user_id: str, secret_key: Optional[str] = None, timestamp: Optional[int] = None) -> str:
    """
    生成用户token
    
    Args:
        user_id: 用户ID
        secret_key: 密钥，如果为None则使用配置文件中的密钥
        timestamp: 时间戳，如果为None则使用当前时间
        
    Returns:
        str: 生成的token
    """
    if secret_key is None:
        config = get_config()
        secret_key = config.get("auth", {}).get("secret_key", DEFAULT_SECRET_KEY)
    
    if timestamp is None:
        timestamp = int(time.time())
    
    # 构建待签名的字符串：user_id + timestamp + 特殊字符
    special_chars = "@#$%"
    message = f"{user_id}{special_chars}{timestamp}"
    
    # 使用HMAC-SHA256进行签名
    signature = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # 返回格式：用户ID.时间戳.签名
    token = f"{user_id}.{timestamp}.{signature}"
    
    logger.debug(f"生成token", extra={
        'user_id': user_id,
        'timestamp': timestamp,
        'token_length': len(token),
        'token_preview': token[:20] + '...'
    })
    
    return token

def verify_token(token: str, secret_key: Optional[str] = None, max_age: int = 3600) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    验证token的有效性
    
    Args:
        token: 要验证的token
        secret_key: 密钥，如果为None则使用配置文件中的密钥
        max_age: token的最大有效期（秒），默认1小时
        
    Returns:
        Tuple[bool, Optional[str], Optional[str]]: (是否有效, 用户ID, 错误信息)
    """
    logger.debug(f"开始验证token", extra={
        'token_length': len(token) if token else 0,
        'token_preview': token[:20] + '...' if token and len(token) > 20 else token,
        'max_age': max_age
    })
    
    if not token:
        logger.warning("Token为空")
        return False, None, "Token不能为空"
    
    # 解析token格式：用户ID.时间戳.签名
    parts = token.split('.')
    if len(parts) != 3:
        logger.warning(f"Token格式错误", extra={
            'parts_count': len(parts),
            'expected_parts': 3
        })
        return False, None, "Token格式错误"
    
    user_id, timestamp_str, provided_signature = parts
    
    try:
        timestamp = int(timestamp_str)
    except ValueError:
        logger.warning(f"时间戳格式错误", extra={
            'timestamp_str': timestamp_str,
            'user_id': user_id
        })
        return False, None, "时间戳格式错误"
    
    # 检查token是否过期
    current_time = int(time.time())
    if current_time - timestamp > max_age:
        logger.warning(f"Token已过期", extra={
            'user_id': user_id,
            'token_age': current_time - timestamp,
            'max_age': max_age,
            'expired_seconds': (current_time - timestamp) - max_age
        })
        return False, None, "Token已过期"
    
    # 重新生成签名进行比较
    if secret_key is None:
        config = get_config()
        secret_key = config.get("auth", {}).get("secret_key", DEFAULT_SECRET_KEY)
    
    expected_token = generate_token(user_id, secret_key, timestamp)
    expected_signature = expected_token.split('.')[2]
    
    # 使用时间安全的比较方法
    if not hmac.compare_digest(provided_signature, expected_signature):
        logger.warning(f"Token签名验证失败", extra={
            'user_id': user_id,
            'timestamp': timestamp,
            'provided_signature_preview': provided_signature[:10] + '...',
            'expected_signature_preview': expected_signature[:10] + '...'
        })
        return False, None, "Token签名验证失败"
    
    logger.info(f"Token验证成功", extra={
        'user_id': user_id,
        'timestamp': timestamp,
        'token_age': current_time - timestamp
    })
    
    return True, user_id, None

def extract_user_id_from_token(token: str) -> Optional[str]:
    """
    从token中提取用户ID（不验证签名）
    
    Args:
        token: token字符串
        
    Returns:
        Optional[str]: 用户ID，如果提取失败返回None
    """
    if not token:
        return None
    
    parts = token.split('.')
    if len(parts) != 3:
        return None
    
    return parts[0] 