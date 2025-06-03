import json
import os
from typing import Dict, List, Optional, Any

# 业务配置文件路径
BUSINESS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '../config/business_config.json')

# 缓存业务配置
_business_config_cache = None

def load_business_config() -> Dict:
    """
    从外部JSON文件加载业务配置
    
    Returns:
        Dict: 业务配置字典
    """
    global _business_config_cache
    
    # 如果已有缓存，直接返回
    if _business_config_cache is not None:
        return _business_config_cache
    
    try:
        # 检查配置文件是否存在
        if not os.path.exists(BUSINESS_CONFIG_PATH):
            # 如果配置文件不存在，创建默认配置
            default_config = {
                "business_types": {
                    "S001": {
                        "name": "deposit",
                        "keywords": {
                            "zh": ["充值", "充钱"],
                            "en": ["deposit", "recharge", "top up"],
                            "ja": ["入金", "チャージ"],
                            "th": ["เติมเงิน"],
                            "tl": ["mag-deposit"]
                        },
                        "responses": {
                            "zh": "您正在进行充值业务，请按照提示操作。",
                            "en": "You are making a deposit. Please follow the instructions.",
                            "ja": "入金手続きを行っています。指示に従ってください。",
                            "th": "คุณกำลังทำธุรกรรมการเติมเงิน โปรดทำตามคำแนะนำ",
                            "tl": "Ikaw ay gumagawa ng deposit. Mangyaring sundin ang mga tagubilin."
                        },
                        "workflow": {
                            "1": {"step": "询问用户需要查询的【订单编号】","response": {"text": "您需要查询的【订单编号】是多少？"},"image":""},
                            "2": {"step": "不知道【订单编号】","response":{"text": "按照下面图片的指引进行操作"},"image":""}},
                            "3": {"step": "提供【订单编号】"},
                        
                    },
                    "S002": {
                        "name": "withdrawal",
                        "keywords": {
                            "zh": ["提现", "取钱"],
                            "en": ["withdraw", "cash out"],
                            "ja": ["出金", "引き出し"],
                            "th": ["ถอนเงิน"],
                            "tl": ["mag-withdraw"]
                        },
                        "responses": {
                            "zh": "您正在进行提现业务，请按照提示操作。",
                            "en": "You are making a withdrawal. Please follow the instructions.",
                            "ja": "出金手続きを行っています。指示に従ってください。",
                            "th": "คุณกำลังทำธุรกรรมการถอนเงิน โปรดทำตามคำแนะนำ",
                            "tl": "Ikaw ay gumagawa ng withdrawal. Mangyaring sundin ang mga tagubilin."
                        }
                    }
                },
                "human_service": {
                    "keywords": {
                        "zh": ["人工", "客服", "人员"],
                        "en": ["agent", "human", "staff", "customer service"],
                        "ja": ["オペレーター", "担当者"],
                        "th": ["พนักงาน", "เจ้าหน้าที่"],
                        "tl": ["tao", "customer", "ahente"]
                    },
                    "responses": {
                        "zh": "您的请求较为复杂，正在为您转接人工客服，请稍候...",
                        "en": "Your request is complex. We are connecting you to a human agent. Please wait...",
                        "ja": "ご要望が複雑なため、オペレーターに接続しています。少々お待ちください...",
                        "th": "คำขอของคุณซับซ้อน เรากำลังเชื่อมต่อคุณกับเจ้าหน้าที่ โปรดรอสักครู่...",
                        "tl": "Ang iyong kahilingan ay komplikado. Kinokonekta ka namin sa isang ahente. Mangyaring maghintay..."
                    }
                },
                "login": {
                    "responses": {
                        "zh": "请先登录后再继续操作。",
                        "en": "Please login first to continue.",
                        "ja": "続行するには、まずログインしてください。",
                        "th": "โปรดเข้าสู่ระบบก่อนเพื่อดำเนินการต่อ",
                        "tl": "Mangyaring mag-login muna upang magpatuloy."
                    }
                },
                "default_language": "en"
            }
            
            # 确保配置目录存在
            os.makedirs(os.path.dirname(BUSINESS_CONFIG_PATH), exist_ok=True)
            
            # 写入默认配置
            with open(BUSINESS_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            
            _business_config_cache = default_config
        else:
            # 读取配置文件
            with open(BUSINESS_CONFIG_PATH, 'r', encoding='utf-8') as f:
                _business_config_cache = json.load(f)
        
        return _business_config_cache
    except Exception as e:
        print(f"加载业务配置文件失败: {str(e)}")
        # 返回空配置
        return {}

def reload_config() -> Dict:
    """
    强制重新加载配置
    
    Returns:
        Dict: 更新后的业务配置字典
    """
    global _business_config_cache
    _business_config_cache = None
    return load_business_config()

def get_config() -> Dict:
    """
    获取当前业务配置
    
    Returns:
        Dict: 业务配置字典
    """
    return load_business_config()

def get_message_by_language(messages_dict: Dict[str, str], language: str, default_language: str = None) -> str:
    """
    根据语言获取对应的消息
    
    Args:
        messages_dict: 包含不同语言消息的字典
        language: 目标语言
        default_language: 默认语言，如果为None则使用配置中的默认语言
        
    Returns:
        str: 对应语言的消息
    """
    if default_language is None:
        config = get_config()
        default_language = config.get("default_language", "en")
        
    return messages_dict.get(language, messages_dict.get(default_language, ""))

# 初始化配置
def init_config():
    """
    初始化配置，确保配置文件存在并加载
    """
    return load_business_config() 