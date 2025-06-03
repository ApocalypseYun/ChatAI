from typing import Optional, Dict, Any
from src.util import call_backend_service

# A001 充值 - 查询用户支付状态
async def query_recharge_status(session_id: str, order_no: str, url: str) -> Dict[str, Any]:
    """
    查询用户支付状态
    参数：
        session_id: 会话ID
        order_no: 订单编号
        url: 具体接口URL，调用方补充
    返回：
        接口响应 JSON
    """
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
async def query_withdrawal_status(session_id: str, order_no: str, url: str) -> Dict[str, Any]:
    """
    查询用户提现状态
    参数：
        session_id: 会话ID
        order_no: 订单编号
        url: 具体接口URL，调用方补充
    返回：
        接口响应 JSON
    """
    payload = {
        "site": 1,
        "session_id": session_id,
        "code": "A002",  # 注意code是A002，和示例里A001需要确认一致，我按A002写
        "params": {
            "orderNo": order_no
        }
    }
    return await call_backend_service(url=url, method="GET", json_data=payload)


# A003 活动 - 查询活动列表
async def query_activity_list(session_id: str, url: str) -> Dict[str, Any]:
    """
    查询活动列表
    参数：
        session_id: 会话ID
        url: 具体接口URL，调用方补充
    返回：
        接口响应 JSON，包括Agent、Deposit、Rebate等活动列表
    """
    payload = {
        "site": 1,
        "session_id": session_id,
        "code": "A003",
        "params": {}
    }
    return await call_backend_service(url=url, method="GET", json_data=payload)


# A004 活动 - 查询用户条件是否满足领取需求
async def query_user_eligibility(session_id: str, url: str) -> Dict[str, Any]:
    """
    查询用户条件是否满足领取需求
    参数：
        session_id: 会话ID
        url: 具体接口URL，调用方补充
    返回：
        接口响应 JSON
    """
    payload = {
        "site": 1,
        "session_id": session_id,
        "code": "A004",
        "params": {}
    }
    return await call_backend_service(url=url, method="POST", json_data=payload)
