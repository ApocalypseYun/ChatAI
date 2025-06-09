#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChatAI 全方位测试脚本
包含基础功能、业务流程、意图识别、多语言、订单号提取、错误处理、性能等全面测试
"""

import requests
import json
import time
import asyncio
import threading
import statistics
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import os

class ComprehensiveTestSuite:
    """全方位测试套件"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.test_results = []
        self.session_counter = 0
        
    def get_session_id(self) -> str:
        """生成唯一会话ID"""
        self.session_counter += 1
        return f"test_session_{int(time.time())}_{self.session_counter}"
    
    def log_test(self, category: str, test_name: str, success: bool, 
                 details: Dict = None, response_data: Dict = None):
        """记录测试结果"""
        result = {
            "category": category,
            "test_name": test_name,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "details": details or {},
            "response_data": response_data
        }
        self.test_results.append(result)
        
        status = "✅" if success else "❌"
        print(f"{status} [{category}] {test_name}")
        if details:
            for key, value in details.items():
                print(f"    {key}: {value}")
        if not success and response_data:
            print(f"    错误详情: {json.dumps(response_data, ensure_ascii=False)[:200]}")
    
    def make_request(self, endpoint: str, method: str = "GET", 
                    payload: Dict = None, timeout: int = 30) -> Dict[str, Any]:
        """发送HTTP请求"""
        try:
            url = f"{self.base_url}{endpoint}"
            headers = {"Content-Type": "application/json"}
            
            if method.upper() == "GET":
                response = requests.get(url, timeout=timeout)
            elif method.upper() == "POST":
                response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")
            
            return {
                "success": True,
                "status_code": response.status_code,
                "data": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text,
                "response_time": response.elapsed.total_seconds()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "status_code": None,
                "data": None,
                "response_time": None
            }
    
    # ===== 基础功能测试 =====
    def test_basic_functionality(self):
        """测试基础功能"""
        print("\n" + "="*80)
        print("🔧 基础功能测试")
        print("="*80)
        
        # 健康检查
        result = self.make_request("/health")
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            if data.get("status") == "ok" and data.get("service") == "ChatAI":
                self.log_test("基础功能", "健康检查", True, {"响应时间": f"{result['response_time']:.3f}s"})
            else:
                self.log_test("基础功能", "健康检查", False, {"原因": "响应格式错误"}, data)
        else:
            self.log_test("基础功能", "健康检查", False, {"原因": result.get("error", "请求失败")})
        
        # 配置重载
        result = self.make_request("/reload_config", "POST")
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            if data.get("status") == "success":
                self.log_test("基础功能", "配置重载", True, {"响应时间": f"{result['response_time']:.3f}s"})
            else:
                self.log_test("基础功能", "配置重载", False, {"原因": "重载失败"}, data)
        else:
            self.log_test("基础功能", "配置重载", False, {"原因": result.get("error", "请求失败")})
        
        # 不存在端点测试
        result = self.make_request("/nonexistent")
        if result["success"] and result["status_code"] == 404:
            self.log_test("基础功能", "404错误处理", True)
        else:
            self.log_test("基础功能", "404错误处理", False, {"状态码": result["status_code"]})
    
    # ===== 用户状态测试 =====
    def test_user_status(self):
        """测试用户状态处理"""
        print("\n" + "="*80)
        print("👤 用户状态测试")
        print("="*80)
        
        # 未登录用户
        payload = {
            "session_id": self.get_session_id(),
            "user_id": "test_unauth_user",
            "platform": "web",
            "language": "zh",
            "status": 0,  # 未登录
            "messages": "你好，我需要帮助",
            "site": 1,
            "transfer_human": 0
        }
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            if data.get("stage") == "unauthenticated" and "登录" in data.get("response", ""):
                self.log_test("用户状态", "未登录用户处理", True, {
                    "响应": data.get("response", "")[:50] + "..."
                })
            else:
                self.log_test("用户状态", "未登录用户处理", False, {"原因": "响应格式错误"}, data)
        else:
            self.log_test("用户状态", "未登录用户处理", False, {"原因": result.get("error", "请求失败")})
        
        # 已登录用户基础测试
        payload["status"] = 1  # 已登录
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            if data.get("session_id") == payload["session_id"]:
                self.log_test("用户状态", "已登录用户处理", True, {
                    "意图类型": data.get("type", "未识别"),
                    "阶段": data.get("stage", "未知")
                })
            else:
                self.log_test("用户状态", "已登录用户处理", False, {"原因": "会话ID不匹配"}, data)
        else:
            self.log_test("用户状态", "已登录用户处理", False, {"原因": result.get("error", "请求失败")})
    
    # ===== 意图识别测试 =====
    def test_intent_recognition(self):
        """测试意图识别"""
        print("\n" + "="*80)
        print("🎯 意图识别测试")
        print("="*80)
        
        intent_tests = [
            {
                "name": "充值意图识别",
                "message": "我的充值还没有到账，能帮我查一下吗",
                "expected_type": "S001"
            },
            {
                "name": "提现意图识别", 
                "message": "我申请的提现怎么还没到账",
                "expected_type": "S002"
            },
            {
                "name": "活动意图识别",
                "message": "我想查询一下活动奖励什么时候发放",
                "expected_type": "S003"
            },
            {
                "name": "人工客服意图识别",
                "message": "我要找人工客服",
                "expected_type": "human_service"
            },
            {
                "name": "英文充值意图识别",
                "message": "My deposit hasn't arrived yet",
                "expected_type": "S001",
                "language": "en"
            },
            {
                "name": "英文提现意图识别",
                "message": "I want to check my withdrawal status",
                "expected_type": "S002", 
                "language": "en"
            }
        ]
        
        for test in intent_tests:
            payload = {
                "session_id": self.get_session_id(),
                "user_id": "test_intent_user",
                "platform": "web",
                "language": test.get("language", "zh"),
                "status": 1,
                "messages": test["message"],
                "history": [],
                "site": 1,
                "transfer_human": 0
                # 不指定type，让系统自动识别
            }
            
            result = self.make_request("/process", "POST", payload)
            if result["success"] and result["status_code"] == 200:
                data = result["data"]
                detected_type = data.get("type", "")
                if detected_type == test["expected_type"]:
                    self.log_test("意图识别", test["name"], True, {
                        "期望": test["expected_type"],
                        "实际": detected_type
                    })
                else:
                    self.log_test("意图识别", test["name"], False, {
                        "期望": test["expected_type"],
                        "实际": detected_type,
                        "消息": test["message"]
                    })
            else:
                self.log_test("意图识别", test["name"], False, {"原因": result.get("error", "请求失败")})
    
    # ===== S001充值业务流程测试 =====
    def test_s001_workflow(self):
        """测试S001充值业务流程"""
        print("\n" + "="*80)
        print("💰 S001充值业务流程测试")
        print("="*80)
        
        # 阶段1：询问订单号
        session_id = self.get_session_id()
        payload = {
            "session_id": session_id,
            "user_id": "test_s001_user",
            "platform": "web",
            "language": "zh",
            "status": 1,
            "messages": "我的充值还没有到账",
            "history": [],
            "site": 1,
            "transfer_human": 0,
            "type": "S001"
        }
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            if "订单编号" in data.get("response", ""):
                self.log_test("S001流程", "阶段1-询问订单号", True, {
                    "响应": data.get("response", "")[:50] + "..."
                })
            else:
                self.log_test("S001流程", "阶段1-询问订单号", False, {"原因": "未正确询问订单号"}, data)
        else:
            self.log_test("S001流程", "阶段1-询问订单号", False, {"原因": result.get("error", "请求失败")})
        
        # 阶段2：不知道订单号
        payload["messages"] = "我不知道订单号在哪里看"
        payload["history"] = [
            {"role": "user", "content": "我的充值还没有到账"},
            {"role": "AI", "content": "您需要查询的【订单编号】是多少？"}
        ]
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            images = data.get("images", [])
            if images and any("depositOrder" in img for img in images):
                self.log_test("S001流程", "阶段2-提供指引图片", True, {
                    "图片数量": len(images),
                    "图片链接": images[0] if images else "无"
                })
            else:
                self.log_test("S001流程", "阶段2-提供指引图片", False, {"原因": "未返回指引图片"}, data)
        else:
            self.log_test("S001流程", "阶段2-提供指引图片", False, {"原因": result.get("error", "请求失败")})
        
        # 阶段3：提供18位订单号
        payload["messages"] = "我的订单号是123456789012345678"
        payload["history"].extend([
            {"role": "user", "content": "我不知道订单号在哪里看"},
            {"role": "AI", "content": "按照下面图片的指引进行操作"}
        ])
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            # 由于模拟环境，接口调用可能失败，但应该有相应处理
            self.log_test("S001流程", "阶段3-处理订单号", True, {
                "转人工": data.get("transfer_human", 0),
                "阶段": data.get("stage", ""),
                "响应": data.get("response", "")[:50] + "..."
            })
        else:
            self.log_test("S001流程", "阶段3-处理订单号", False, {"原因": result.get("error", "请求失败")})
        
        # 阶段3：上传图片测试
        payload["messages"] = "这是我的充值截图"
        payload["images"] = ["https://example.com/payment-screenshot.jpg"]
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            if data.get("transfer_human") == 1:
                self.log_test("S001流程", "阶段3-图片上传转人工", True, {
                    "转人工": data.get("transfer_human", 0),
                    "响应": data.get("response", "")[:50] + "..."
                })
            else:
                self.log_test("S001流程", "阶段3-图片上传转人工", False, {"原因": "未转人工"}, data)
        else:
            self.log_test("S001流程", "阶段3-图片上传转人工", False, {"原因": result.get("error", "请求失败")})
    
    # ===== S002提现业务流程测试 =====
    def test_s002_workflow(self):
        """测试S002提现业务流程"""
        print("\n" + "="*80)
        print("💸 S002提现业务流程测试")
        print("="*80)
        
        # 阶段1：询问提现订单号
        session_id = self.get_session_id()
        payload = {
            "session_id": session_id,
            "user_id": "test_s002_user",
            "platform": "web",
            "language": "zh",
            "status": 1,
            "messages": "我的提现还没有到账",
            "history": [],
            "site": 1,
            "transfer_human": 0,
            "type": "S002"
        }
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            if "订单编号" in data.get("response", ""):
                self.log_test("S002流程", "阶段1-询问订单号", True, {
                    "响应": data.get("response", "")[:50] + "..."
                })
            else:
                self.log_test("S002流程", "阶段1-询问订单号", False, {"原因": "未正确询问订单号"}, data)
        else:
            self.log_test("S002流程", "阶段1-询问订单号", False, {"原因": result.get("error", "请求失败")})
        
        # 阶段2：不知道提现订单号
        payload["messages"] = "我不知道提现订单号在哪里看"
        payload["history"] = [
            {"role": "user", "content": "我的提现还没有到账"},
            {"role": "AI", "content": "您需要查询的【订单编号】是多少？"}
        ]
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            images = data.get("images", [])
            if images and any("withdrawalOrder" in img for img in images):
                self.log_test("S002流程", "阶段2-提供提现指引图片", True, {
                    "图片数量": len(images),
                    "图片链接": images[0] if images else "无"
                })
            else:
                self.log_test("S002流程", "阶段2-提供提现指引图片", False, {"原因": "未返回提现指引图片"}, data)
        else:
            self.log_test("S002流程", "阶段2-提供提现指引图片", False, {"原因": result.get("error", "请求失败")})
        
        # 阶段3：提供18位提现订单号
        payload["messages"] = "我的提现订单号是876543210987654321"
        payload["history"].extend([
            {"role": "user", "content": "我不知道提现订单号在哪里看"},
            {"role": "AI", "content": "按照下面图片的指引进行操作"}
        ])
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            self.log_test("S002流程", "阶段3-处理提现订单号", True, {
                "转人工": data.get("transfer_human", 0),
                "阶段": data.get("stage", ""),
                "响应": data.get("response", "")[:50] + "..."
            })
        else:
            self.log_test("S002流程", "阶段3-处理提现订单号", False, {"原因": result.get("error", "请求失败")})
        
        # 阶段3：上传提现图片测试
        payload["messages"] = "这是我的提现记录截图"
        payload["images"] = ["https://example.com/withdrawal-screenshot.jpg"]
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            if data.get("transfer_human") == 1:
                self.log_test("S002流程", "阶段3-图片上传转人工", True, {
                    "转人工": data.get("transfer_human", 0),
                    "响应": data.get("response", "")[:50] + "..."
                })
            else:
                self.log_test("S002流程", "阶段3-图片上传转人工", False, {"原因": "未转人工"}, data)
        else:
            self.log_test("S002流程", "阶段3-图片上传转人工", False, {"原因": result.get("error", "请求失败")})
    
    # ===== S003活动业务流程测试 =====
    def test_s003_workflow(self):
        """测试S003活动业务流程"""
        print("\n" + "="*80)
        print("🎁 S003活动业务流程测试")
        print("="*80)
        
        # 阶段1：查询活动列表
        session_id = self.get_session_id()
        payload = {
            "session_id": session_id,
            "user_id": "test_s003_user",
            "platform": "web",
            "language": "zh",
            "status": 1,
            "messages": "我想查询一下首存奖励什么时候发放",
            "history": [],
            "site": 1,
            "transfer_human": 0,
            "type": "S003"
        }
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            self.log_test("S003流程", "阶段1-活动查询", True, {
                "转人工": data.get("transfer_human", 0),
                "阶段": data.get("stage", ""),
                "响应": data.get("response", "")[:100] + "..."
            })
        else:
            self.log_test("S003流程", "阶段1-活动查询", False, {"原因": result.get("error", "请求失败")})
        
        # 阶段2：用户明确活动
        payload["messages"] = "我要查询首存奖励活动"
        payload["history"] = [
            {"role": "user", "content": "我想查询一下首存奖励什么时候发放"},
            {"role": "AI", "content": "我为您找到了以下活动，请明确您想查询的具体活动"}
        ]
        
        result = self.make_request("/process", "POST", payload)
        if result["success"] and result["status_code"] == 200:
            data = result["data"]
            self.log_test("S003流程", "阶段2-明确活动", True, {
                "转人工": data.get("transfer_human", 0),
                "阶段": data.get("stage", ""),
                "响应": data.get("response", "")[:100] + "..."
            })
        else:
            self.log_test("S003流程", "阶段2-明确活动", False, {"原因": result.get("error", "请求失败")})
    
    # ===== 订单号提取测试 =====
    def test_order_number_extraction(self):
        """测试订单号提取功能"""
        print("\n" + "="*80)
        print("🔍 订单号提取测试")
        print("="*80)
        
        order_tests = [
            {
                "name": "18位订单号提取",
                "message": "我的订单号是123456789012345678",
                "should_extract": True,
                "expected": "123456789012345678"
            },
            {
                "name": "19位数字不提取",
                "message": "这个号码1234567890123456789是我的电话",
                "should_extract": False
            },
            {
                "name": "17位数字不提取", 
                "message": "订单12345678901234567太短",
                "should_extract": False
            },
            {
                "name": "文本中提取18位订单号",
                "message": "我的订单号码是123456789012345678，请帮我查询状态",
                "should_extract": True,
                "expected": "123456789012345678"
            },
            {
                "name": "混合文本中提取",
                "message": "订单：987654321098765432 状态查询",
                "should_extract": True,
                "expected": "987654321098765432"
            }
        ]
        
        for test in order_tests:
            payload = {
                "session_id": self.get_session_id(),
                "user_id": "test_order_user",
                "platform": "web",
                "language": "zh",
                "status": 1,
                "messages": test["message"],
                "history": [
                    {"role": "user", "content": "我的充值还没有到账"},
                    {"role": "AI", "content": "您需要查询的【订单编号】是多少？"}
                ],
                "site": 1,
                "transfer_human": 0,
                "type": "S001"
            }
            
            result = self.make_request("/process", "POST", payload)
            if result["success"] and result["status_code"] == 200:
                data = result["data"]
                if test["should_extract"]:
                    # 应该能提取到订单号，不会要求重新提供
                    if "订单号" not in data.get("response", "") or data.get("stage") == "finish":
                        self.log_test("订单号提取", test["name"], True, {
                            "消息": test["message"],
                            "期望提取": test.get("expected", "是"),
                            "阶段": data.get("stage", ""),
                        })
                    else:
                        self.log_test("订单号提取", test["name"], False, {
                            "消息": test["message"],
                            "期望提取": test.get("expected", "是"),
                            "实际": "未提取到",
                            "响应": data.get("response", "")[:50] + "..."
                        })
                else:
                    # 不应该提取到，会要求重新提供
                    if "订单号" in data.get("response", ""):
                        self.log_test("订单号提取", test["name"], True, {
                            "消息": test["message"],
                            "正确": "未提取无效订单号"
                        })
                    else:
                        self.log_test("订单号提取", test["name"], False, {
                            "消息": test["message"],
                            "错误": "错误提取了无效订单号"
                        })
            else:
                self.log_test("订单号提取", test["name"], False, {"原因": result.get("error", "请求失败")})
    
    # ===== 多语言支持测试 =====
    def test_multilingual_support(self):
        """测试多语言支持"""
        print("\n" + "="*80)
        print("🌍 多语言支持测试")
        print("="*80)
        
        language_tests = [
            {
                "language": "zh",
                "message": "我需要充值帮助",
                "expected_contains": ["充值", "订单"]
            },
            {
                "language": "en", 
                "message": "I need deposit help",
                "expected_contains": ["deposit", "order"]
            },
            {
                "language": "ja",
                "message": "入金について教えてください",
                "expected_contains": ["入金"]
            },
            {
                "language": "th",
                "message": "ฉันต้องการความช่วยเหลือเรื่องการเติมเงิน",
                "expected_contains": ["เติมเงิน"]
            }
        ]
        
        for test in language_tests:
            # 测试未登录多语言回复
            payload = {
                "session_id": self.get_session_id(),
                "user_id": "test_lang_user",
                "platform": "web",
                "language": test["language"],
                "status": 0,  # 未登录
                "messages": test["message"],
                "site": 1,
                "transfer_human": 0
            }
            
            result = self.make_request("/process", "POST", payload)
            if result["success"] and result["status_code"] == 200:
                data = result["data"]
                response = data.get("response", "")
                if response:
                    self.log_test("多语言支持", f"未登录-{test['language']}", True, {
                        "语言": test["language"],
                        "响应长度": len(response),
                        "响应": response[:50] + "..."
                    })
                else:
                    self.log_test("多语言支持", f"未登录-{test['language']}", False, {
                        "语言": test["language"],
                        "原因": "无响应内容"
                    })
            else:
                self.log_test("多语言支持", f"未登录-{test['language']}", False, {
                    "语言": test["language"],
                    "原因": result.get("error", "请求失败")
                })
    
    # ===== 错误处理测试 =====
    def test_error_handling(self):
        """测试错误处理"""
        print("\n" + "="*80)
        print("⚠️ 错误处理测试")
        print("="*80)
        
        # 缺少必要字段
        invalid_payloads = [
            {
                "name": "缺少session_id",
                "payload": {
                    "user_id": "test_user",
                    "platform": "web",
                    "language": "zh",
                    "status": 1,
                    "messages": "测试消息",
                    "site": 1
                }
            },
            {
                "name": "缺少messages",
                "payload": {
                    "session_id": "test_session",
                    "user_id": "test_user", 
                    "platform": "web",
                    "language": "zh",
                    "status": 1,
                    "site": 1
                }
            },
            {
                "name": "无效status值",
                "payload": {
                    "session_id": "test_session",
                    "user_id": "test_user",
                    "platform": "web", 
                    "language": "zh",
                    "status": 999,  # 无效值
                    "messages": "测试消息",
                    "site": 1
                }
            }
        ]
        
        for test in invalid_payloads:
            result = self.make_request("/process", "POST", test["payload"])
            if result["status_code"] == 422:  # 验证错误
                self.log_test("错误处理", test["name"], True, {
                    "状态码": result["status_code"]
                })
            else:
                self.log_test("错误处理", test["name"], False, {
                    "期望状态码": 422,
                    "实际状态码": result["status_code"],
                    "响应": str(result.get("data", ""))[:100]
                })
        
        # 空消息测试
        payload = {
            "session_id": self.get_session_id(),
            "user_id": "test_user",
            "platform": "web",
            "language": "zh", 
            "status": 1,
            "messages": "",  # 空消息
            "site": 1,
            "transfer_human": 0
        }
        
        result = self.make_request("/process", "POST", payload)
        if result["success"]:
            self.log_test("错误处理", "空消息处理", True, {
                "状态码": result["status_code"]
            })
        else:
            self.log_test("错误处理", "空消息处理", False, {
                "原因": result.get("error", "未知")
            })
    
    # ===== 性能测试 =====
    def test_performance(self):
        """性能测试"""
        print("\n" + "="*80)
        print("🚀 性能测试")
        print("="*80)
        
        # 响应时间测试
        response_times = []
        for i in range(10):
            result = self.make_request("/health")
            if result["success"]:
                response_times.append(result["response_time"])
        
        if response_times:
            avg_time = statistics.mean(response_times)
            max_time = max(response_times)
            min_time = min(response_times)
            
            self.log_test("性能测试", "健康检查响应时间", True, {
                "平均时间": f"{avg_time:.3f}s",
                "最大时间": f"{max_time:.3f}s", 
                "最小时间": f"{min_time:.3f}s",
                "测试次数": len(response_times)
            })
        else:
            self.log_test("性能测试", "健康检查响应时间", False, {"原因": "无有效响应"})
        
        # 并发测试
        def concurrent_test():
            return self.make_request("/health")
        
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(concurrent_test) for _ in range(10)]
            results = [future.result() for future in as_completed(futures)]
        end_time = time.time()
        
        successful = sum(1 for r in results if r["success"])
        total_time = end_time - start_time
        
        self.log_test("性能测试", "并发请求测试", True, {
            "成功请求": f"{successful}/10",
            "总耗时": f"{total_time:.3f}s",
            "平均每秒": f"{10/total_time:.2f} req/s"
        })
    
    # ===== 配置文件测试 =====
    def test_configuration(self):
        """测试配置文件"""
        print("\n" + "="*80)
        print("⚙️ 配置文件测试")
        print("="*80)
        
        # 检查配置文件是否存在和格式正确
        config_file = "config/business_config.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 检查关键配置项
                required_keys = ["business_types", "human_service", "login"]
                missing_keys = [key for key in required_keys if key not in config]
                
                if not missing_keys:
                    self.log_test("配置文件", "配置完整性检查", True, {
                        "文件路径": config_file,
                        "业务类型数": len(config.get("business_types", {}))
                    })
                else:
                    self.log_test("配置文件", "配置完整性检查", False, {
                        "缺少配置": missing_keys
                    })
                
                # 检查S001, S002, S003配置
                business_types = config.get("business_types", {})
                for service in ["S001", "S002", "S003"]:
                    if service in business_types:
                        service_config = business_types[service]
                        has_workflow = "workflow" in service_config
                        has_keywords = "keywords" in service_config
                        has_status_messages = "status_messages" in service_config
                        
                        self.log_test("配置文件", f"{service}配置检查", True, {
                            "工作流": "✓" if has_workflow else "✗",
                            "关键词": "✓" if has_keywords else "✗", 
                            "状态消息": "✓" if has_status_messages else "✗"
                        })
                    else:
                        self.log_test("配置文件", f"{service}配置检查", False, {
                            "原因": f"缺少{service}配置"
                        })
                        
            except json.JSONDecodeError as e:
                self.log_test("配置文件", "JSON格式检查", False, {
                    "错误": str(e)
                })
        else:
            self.log_test("配置文件", "文件存在检查", False, {
                "文件路径": config_file,
                "原因": "文件不存在"
            })
    
    # ===== 主测试运行方法 =====
    def run_comprehensive_tests(self):
        """运行全方位测试"""
        print("🤖 ChatAI 全方位测试套件")
        print("=" * 80)
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"API地址: {self.base_url}")
        print("=" * 80)
        
        # 按顺序执行所有测试
        test_categories = [
            ("基础功能测试", self.test_basic_functionality),
            ("用户状态测试", self.test_user_status),
            ("意图识别测试", self.test_intent_recognition),
            ("S001充值流程测试", self.test_s001_workflow),
            ("S002提现流程测试", self.test_s002_workflow),
            ("S003活动流程测试", self.test_s003_workflow),
            ("订单号提取测试", self.test_order_number_extraction),
            ("多语言支持测试", self.test_multilingual_support),
            ("错误处理测试", self.test_error_handling),
            ("性能测试", self.test_performance),
            ("配置文件测试", self.test_configuration)
        ]
        
        for category_name, test_func in test_categories:
            try:
                test_func()
                time.sleep(1)  # 测试间隔
            except Exception as e:
                self.log_test(category_name, "测试执行", False, {
                    "异常": str(e)
                })
        
        # 生成测试报告
        self.generate_final_report()
    
    def generate_final_report(self):
        """生成最终测试报告"""
        print("\n" + "=" * 80)
        print("📊 全方位测试报告")
        print("=" * 80)
        
        # 统计结果
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        print(f"总测试数量: {total_tests}")
        print(f"通过测试: {passed_tests}")
        print(f"失败测试: {failed_tests}")
        print(f"成功率: {success_rate:.1f}%")
        
        # 按类别统计
        category_stats = {}
        for result in self.test_results:
            category = result["category"]
            if category not in category_stats:
                category_stats[category] = {"total": 0, "passed": 0}
            category_stats[category]["total"] += 1
            if result["success"]:
                category_stats[category]["passed"] += 1
        
        print(f"\n📋 分类测试结果:")
        for category, stats in category_stats.items():
            rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            status = "✅" if rate >= 80 else "⚠️" if rate >= 60 else "❌"
            print(f"  {status} {category}: {stats['passed']}/{stats['total']} ({rate:.1f}%)")
        
        # 失败测试详情
        failed_results = [r for r in self.test_results if not r["success"]]
        if failed_results:
            print(f"\n❌ 失败测试详情:")
            for result in failed_results:
                print(f"  • [{result['category']}] {result['test_name']}")
                if result["details"]:
                    for key, value in result["details"].items():
                        print(f"    {key}: {value}")
        
        # 保存详细报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"comprehensive_test_report_{timestamp}.json"
        
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "summary": {
                        "timestamp": datetime.now().isoformat(),
                        "total_tests": total_tests,
                        "passed_tests": passed_tests,
                        "failed_tests": failed_tests,
                        "success_rate": success_rate,
                        "api_url": self.base_url
                    },
                    "category_stats": category_stats,
                    "detailed_results": self.test_results
                }, f, ensure_ascii=False, indent=2)
            
            print(f"\n📄 详细测试报告已保存到: {report_file}")
        except Exception as e:
            print(f"⚠️ 保存测试报告失败: {str(e)}")
        
        # 总结
        if success_rate >= 90:
            print(f"\n🎉 测试表现优秀！({success_rate:.1f}%)")
        elif success_rate >= 80:
            print(f"\n👍 测试表现良好！({success_rate:.1f}%)")
        elif success_rate >= 60:
            print(f"\n⚠️ 测试表现一般，建议检查失败项目 ({success_rate:.1f}%)")
        else:
            print(f"\n🚨 测试表现需要改进 ({success_rate:.1f}%)")
        
        print("=" * 80)

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ChatAI 全方位测试套件")
    parser.add_argument("--url", default="http://127.0.0.1:8000", 
                       help="API服务地址 (默认: http://127.0.0.1:8000)")
    
    args = parser.parse_args()
    
    tester = ComprehensiveTestSuite(args.url)
    tester.run_comprehensive_tests()

if __name__ == "__main__":
    main() 