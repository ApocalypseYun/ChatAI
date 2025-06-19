import json
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from typing import Dict, Any
from src.util import call_backend_service
from src.config import get_config
from src.logging_config import get_logger

config = get_config()
internal_endpoint = config.get("default_endpoint", 'https://lodiapi-w-supervise2.lodirnd.com/aiChat')

# AES 加密相关常量
AES_KEY = 'c56f23sfhk935jqb'
AES_IV = AES_KEY[::-1]


def encrypt_payload(data: dict, key: str = AES_KEY, iv: str = AES_IV) -> str:
    """
    通用 AES-128-CBC 加密函数，返回 base64 编码密文
    :param data: 需要加密的字典数据
    :param key: 加密 key，默认使用 AES_KEY
    :param iv: 加密 iv，默认使用 key 的反转
    :return: base64 编码的密文字符串
    """
    data_str = json.dumps(data, separators=(',', ':'))
    data_bytes = data_str.encode('utf-8')
    padded_data = pad(data_bytes, AES.block_size)
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    encrypted = cipher.encrypt(padded_data)
    encrypted_b64 = base64.b64encode(encrypted).decode('utf-8')
    return encrypted_b64

# 示例：
# payload = {"site": 1, "session_id": "0528164322443322", "code": "A001", "params": {"orderNo": "202534545677456"}}
# encrypted_data = encrypt_payload(payload)
# print(encrypted_data)

# A001 充值 - 查询用户支付状态
async def query_recharge_status(session_id: str, order_no: str, site: int = 1) -> Dict[str, Any]:
    """
    查询用户支付状态
    参数：
        session_id: 会话ID
        order_no: 订单编号
        site: 站点ID，默认为1
    返回：
        接口响应 JSON
    """
    url = internal_endpoint   #TODO 更新为接口path
    payload = {
        "site": site,
        "session_id": session_id,
        "code": "A001",
        "params": {
            "orderNo": order_no
        }
    }
    encrypted_data = encrypt_payload(payload)
    headers = {"Content-Type": "application/json"}
    return await call_backend_service(url=url, method="POST", json_data={"data": encrypted_data}, headers=headers)


# A002 提现 - 查询用户提现状态
async def query_withdrawal_status(session_id: str, order_no: str, site: int = 1) -> Dict[str, Any]:
    """
    查询用户提现状态
    参数：
        session_id: 会话ID
        order_no: 订单编号
        site: 站点ID，默认为1
    返回：
        接口响应 JSON
    """
    url = internal_endpoint  #TODO 更新为接口path
    payload = {
        "site": site,
        "session_id": session_id,
        "code": "A002",
        "params": {
            "orderNo": order_no
        }
    }
    encrypted_data = encrypt_payload(payload)
    headers = {"Content-Type": "application/json"}
    return await call_backend_service(url=url, method="POST", json_data={"data": encrypted_data}, headers=headers)


# A003 活动 - 查询活动列表
async def query_activity_list(session_id: str, site: int = 1) -> Dict[str, Any]:
    """
    查询活动列表
    参数：
        session_id: 会话ID
        site: 站点ID，默认为1
    返回：
        接口响应 JSON，包括Agent、Deposit、Rebate等活动列表
    """
    url = internal_endpoint   #TODO 更新为接口path
    payload = {
        "site": site,
        "session_id": session_id,
        "code": "A003",
        "params": {}
    }
    encrypted_data = encrypt_payload(payload)
    headers = {"Content-Type": "application/json"}
    return await call_backend_service(url=url, method="POST", json_data={"data": encrypted_data}, headers=headers)


# A004 活动 - 查询用户条件是否满足领取需求
async def query_user_eligibility(session_id: str, active_name: str, site: int = 1) -> Dict[str, Any]:
    """
    查询用户条件是否满足领取需求
    参数：
        session_id: 会话ID
        active_name: 活动名称
        site: 站点ID，默认为1
    返回：
        接口响应 JSON
    """
    url = internal_endpoint  #TODO 更新为接口path
    payload = {
        "site": site,
        "session_id": session_id,
        "code": "A004",
        "params": {
            "activeName": active_name
        }
    }
    encrypted_data = encrypt_payload(payload)
    headers = {"Content-Type": "application/json"}
    return await call_backend_service(url=url, method="POST", json_data={"data": encrypted_data}, headers=headers)

# 数据提取函数
def extract_recharge_status(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    从A001充值接口返回值中提取关键数据
    参数：
        response: API返回的完整响应
    返回：
        提取的关键数据字典
    """
    try:
        # 添加调试日志
        logger = get_logger("chatai-api")
        
        logger.info(f"A001 API响应结构", extra={
            'full_response': response,
            'state': response.get('state'),
            'data': response.get('data'),
            'api_message': response.get('message')
        })
        
        # 检查基本的响应结构
        if not isinstance(response, dict):
            logger.error(f"API响应不是字典格式", extra={'response_type': type(response)})
            return {
                "status": "error",
                "is_success": False,
                "message": "API响应格式错误"
            }
        
        state = response.get("state", -1)
        data = response.get("data", {})
        
        # 如果state不是0，表示API调用失败
        if state != 0:
            logger.info(f"API调用失败，state={state}", extra={'state': state, 'api_message': response.get('message')})
            return {
                "status": "api_failed",
                "is_success": False,
                "message": response.get("message", "API调用失败")
            }
        
        # 尝试不同的数据结构格式
        a001_data = data.get("A001", {})
        
        # 检查是否有A001数据
        if not a001_data:
            logger.warning(f"API响应中未找到A001数据", extra={
                'data_keys': list(data.keys()),
                'data': data
            })
            
            # 尝试其他可能的字段名
            for possible_key in ["result", "order", "payment", "recharge"]:
                if possible_key in data:
                    a001_data = data[possible_key]
                    logger.info(f"使用替代字段: {possible_key}", extra={'alt_data': a001_data})
                    break
        
        # 提取状态信息
        status = a001_data.get("status", "")
        
        # 如果仍然没有状态信息，检查其他可能的字段
        if not status:
            for status_field in ["state", "result", "payment_status"]:
                if status_field in a001_data:
                    status = a001_data[status_field]
                    logger.info(f"使用替代状态字段: {status_field}={status}")
                    break
        
        # 如果仍然没有状态，返回特定错误
        if not status:
            logger.error(f"无法从API响应中提取状态信息", extra={
                'a001_data': a001_data,
                'data_structure': data
            })
            return {
                "status": "no_status_data",
                "is_success": False,
                "message": "API响应中缺少状态信息"
            }
        
        result = {
            "status": status,
            "is_success": True,  # state=0表示API调用成功
            "message": response.get("message", "")
        }
        
        logger.info(f"A001 提取结果", extra={
            'extracted_data': result,
            'a001_data': a001_data
        })
        
        return result
        
    except Exception as e:
        logger.error(f"数据提取异常", extra={'error': str(e)}, exc_info=True)
        return {
            "status": "extraction_error",
            "is_success": False,
            "message": f"数据提取失败: {str(e)}"
        }


def extract_withdrawal_status(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    从A002提现接口返回值中提取关键数据
    参数：
        response: API返回的完整响应
    返回：
        提取的关键数据字典
    """
    try:
        data = response.get("data", {})
        a002_data = data.get("A002", {})
        return {
            "status": a002_data.get("status", "unknown"),
            "userId": a002_data.get("userId", ""),
            "is_success": response.get("state", -1) == 0,
            "message": response.get("message", "")
        }
    except Exception as e:
        return {
            "status": "error",
            "userId": "",
            "is_success": False,
            "message": f"数据提取失败: {str(e)}"
        }


def extract_activity_list(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    从A003活动接口返回值中提取关键数据
    参数：
        response: API返回的完整响应
    返回：
        提取的关键数据字典
    """
    try:
        data = response.get("data", {})
        a003_data = data.get("A003", {})
        activity_list = a003_data.get("list", {})
        
        return {
            "agent_activities": activity_list.get("Agent", []),
            "deposit_activities": activity_list.get("Deposit", []),
            "rebate_activities": activity_list.get("Rebate", []),
            "lucky_spin_activities": activity_list.get("Lucky Spin", []),
            "all_member_activities": activity_list.get("All member", []),
            "sports_activities": activity_list.get("Sports", []),
            "total_activities": sum(len(v) for v in activity_list.values()),
            "is_success": response.get("state", -1) == 0,
            "message": response.get("message", "")
        }
    except Exception as e:
        return {
            "agent_activities": [],
            "deposit_activities": [],
            "rebate_activities": [],
            "lucky_spin_activities": [],
            "all_member_activities": [],
            "sports_activities": [],
            "total_activities": 0,
            "is_success": False,
            "message": f"数据提取失败: {str(e)}"
        }


def extract_user_eligibility(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    从A004用户条件接口返回值中提取关键数据
    参数：
        response: API返回的完整响应
    返回：
        提取的关键数据字典
    """
    try:
        data = response.get("data", {})
        a004_data = data.get("A004", {})
        
        status = a004_data.get("status", "unknown")
        
        return {
            "status": status,
            "userId": a004_data.get("username", ""),
            "message": a004_data.get("msg", ""),
            "is_waiting": status == "Waiting paid",
            "is_success": response.get("state", -1) == 0,
            "api_message": response.get("message", "")
        }
    except Exception as e:
        return {
            "status": "error",
            "userId": "",
            "message": "",
            "is_waiting": False,
            "is_success": False,
            "api_message": f"数据提取失败: {str(e)}"
        }


# 通用数据提取函数
def extract_api_response(response: Dict[str, Any], api_code: str) -> Dict[str, Any]:
    """
    通用API响应数据提取函数
    参数：
        response: API返回的完整响应
        api_code: API代码 (A001, A002, A003, A004)
    返回：
        提取的关键数据字典
    """
    extractors = {
        "A001": extract_recharge_status,
        "A002": extract_withdrawal_status,
        "A003": extract_activity_list,
        "A004": extract_user_eligibility
    }
    
    extractor = extractors.get(api_code)
    if extractor:
        return extractor(response)
    else:
        return {
            "error": f"不支持的API代码: {api_code}",
            "is_success": False
        }
