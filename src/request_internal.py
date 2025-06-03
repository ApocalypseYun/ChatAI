from typing import Dict, Any
from src.util import call_backend_service
from src.config import get_config

config = get_config()
internal_endpoint = config.get("internal_endpoint", 'default_endpoint')

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
    url = internal_endpoint + "/query/recharge_status"   #TODO 更新为接口path
    payload = {
        "site": 1,
        "session_id": session_id,
        "code": "A001",
        "params": {
            "orderNo": order_no
        }
    }
    return await call_backend_service(url=url, method="GET", json_data=payload)


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
    url = internal_endpoint + "/query/withdrawal_status"  #TODO 更新为接口path
    payload = {
        "site": 1,
        "session_id": session_id,
        "code": "A002",
        "params": {
            "orderNo": order_no
        }
    }
    return await call_backend_service(url=url, method="GET", json_data=payload)


# A003 活动 - 查询活动列表
async def query_activity_list(session_id: str,) -> Dict[str, Any]:
    """
    查询活动列表
    参数：
        session_id: 会话ID
    返回：
        接口响应 JSON，包括Agent、Deposit、Rebate等活动列表
    """
    url = internal_endpoint + "/query/activity_list"   #TODO 更新为接口path
    payload = {
        "site": 1,
        "session_id": session_id,
        "code": "A003",
        "params": {}
    }
    return await call_backend_service(url=url, method="GET", json_data=payload)


# A004 活动 - 查询用户条件是否满足领取需求
async def query_user_eligibility(session_id: str,) -> Dict[str, Any]:
    """
    查询用户条件是否满足领取需求
    参数：
        session_id: 会话ID
    返回：
        接口响应 JSON
    """
    url = internal_endpoint + "/query/user_eligibility"  #TODO 更新为接口path
    payload = {
        "site": 1,
        "session_id": session_id,
        "code": "A004",
        "params": {}
    }
    return await call_backend_service(url=url, method="POST", json_data=payload)
