import json
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from typing import Dict, Any
from src.util import call_backend_service
from src.config import get_config

config = get_config()
internal_endpoint = config.get("internal_endpoint", 'default_endpoint')

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
async def query_recharge_status(session_id: str, order_no: str) -> Dict[str, Any]:
    """
    查询用户支付状态
    参数：
        session_id: 会话ID
        order_no: 订单编号
    返回：
        接口响应 JSON
    """
    url = internal_endpoint   #TODO 更新为接口path
    payload = {
        "site": 1,
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
async def query_withdrawal_status(session_id: str, order_no: str) -> Dict[str, Any]:
    """
    查询用户提现状态
    参数：
        session_id: 会话ID
        order_no: 订单编号
    返回：
        接口响应 JSON
    """
    url = internal_endpoint  #TODO 更新为接口path
    payload = {
        "site": 1,
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
async def query_activity_list(session_id: str,) -> Dict[str, Any]:
    """
    查询活动列表
    参数：
        session_id: 会话ID
    返回：
        接口响应 JSON，包括Agent、Deposit、Rebate等活动列表
    """
    url = internal_endpoint   #TODO 更新为接口path
    payload = {
        "site": 1,
        "session_id": session_id,
        "code": "A003",
        "params": {}
    }
    encrypted_data = encrypt_payload(payload)
    headers = {"Content-Type": "application/json"}
    return await call_backend_service(url=url, method="POST", json_data={"data": encrypted_data}, headers=headers)


# A004 活动 - 查询用户条件是否满足领取需求
async def query_user_eligibility(session_id: str,) -> Dict[str, Any]:
    """
    查询用户条件是否满足领取需求
    参数：
        session_id: 会话ID
    返回：
        接口响应 JSON
    """
    url = internal_endpoint  #TODO 更新为接口path
    payload = {
        "site": 1,
        "session_id": session_id,
        "code": "A004",
        "params": {}
    }
    encrypted_data = encrypt_payload(payload)
    headers = {"Content-Type": "application/json"}
    return await call_backend_service(url=url, method="POST", json_data={"data": encrypted_data}, headers=headers)
