import requests
import json
import time
from typing import Dict, Any, List

"""
ChatAI API 完整测试脚本

这个测试脚本包含了对ChatAI API服务的全面测试，包括：
1. 健康检查接口测试
2. 配置重新加载接口测试
3. 消息处理接口测试（包括各种场景）
4. 错误处理测试
5. 参数验证测试

注意：消息处理接口涉及外部依赖（如OpenAI API），可能会有部分测试失败，
这是正常现象，主要用于验证API结构和错误处理。
"""

class APITester:
    """API测试类"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.results = []
        
    def log_result(self, test_name: str, success: bool, message: str = "", details: Dict = None):
        """记录测试结果"""
        result = {
            "test_name": test_name,
            "success": success,
            "message": message,
            "details": details or {},
            "timestamp": time.time()
        }
        self.results.append(result)
        
        status = "✓" if success else "✗"
        print(f"{status} {test_name}: {message}")
        if details:
            print(f"   详情: {json.dumps(details, ensure_ascii=False, indent=2)}")
    
    def test_health_check(self):
        """测试健康检查接口"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok" and data.get("service") == "ChatAI":
                    self.log_result("健康检查", True, "接口正常", data)
                    return True
                else:
                    self.log_result("健康检查", False, "响应数据格式错误", data)
                    return False
            else:
                self.log_result("健康检查", False, f"HTTP状态码错误: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_result("健康检查", False, f"请求异常: {str(e)}")
            return False
    
    def test_reload_config(self):
        """测试重新加载配置接口"""
        try:
            response = requests.post(f"{self.base_url}/reload_config", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    self.log_result("配置重新加载", True, "配置重新加载成功", data)
                    return True
                else:
                    self.log_result("配置重新加载", False, "配置重新加载失败", data)
                    return False
            else:
                self.log_result("配置重新加载", False, f"HTTP状态码错误: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_result("配置重新加载", False, f"请求异常: {str(e)}")
            return False
    
    def test_process_unauthenticated(self):
        """测试未登录用户消息处理"""
        payload = {
            "session_id": "test_session_unauth",
            "user_id": "test_user_unauth",
            "platform": "web",
            "language": "zh",
            "status": 0,  # 未登录
            "messages": "你好，我需要帮助",
            "site": 1,
            "transfer_human": 0
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/process", 
                json=payload, 
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if (data.get("session_id") == payload["session_id"] and 
                    data.get("stage") == "unauthenticated"):
                    self.log_result("未登录用户处理", True, "未登录用户处理正常", {
                        "response": data.get("response", "")[:100]
                    })
                    return True
                else:
                    self.log_result("未登录用户处理", False, "响应格式错误", data)
                    return False
            else:
                self.log_result("未登录用户处理", False, f"HTTP状态码错误: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_result("未登录用户处理", False, f"请求异常: {str(e)}")
            return False
    
    def test_process_authenticated_basic(self):
        """测试已登录用户基本消息处理"""
        payload = {
            "session_id": "test_session_auth",
            "user_id": "test_user_auth",
            "platform": "web",
            "language": "zh",
            "status": 1,  # 已登录
            "messages": "为什么我的充值还没有到账",
            "history": [],
            "site": 1,
            "transfer_human": 0
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/process", 
                json=payload, 
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("session_id") == payload["session_id"]:
                    self.log_result("已登录用户基本处理", True, "已登录用户处理正常", {
                        "response": data.get("response", "")[:100],
                        "intent": data.get("metadata", {}).get("intent", ""),
                        "stage": data.get("stage", "")
                    })
                    return True
                else:
                    self.log_result("已登录用户基本处理", False, "响应格式错误", data)
                    return False
            else:
                error_detail = ""
                try:
                    error_data = response.json()
                    error_detail = error_data.get("detail", "")
                except:
                    error_detail = response.text[:200]
                
                self.log_result("已登录用户基本处理", False, 
                               f"HTTP状态码错误: {response.status_code}", 
                               {"error": error_detail})
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_result("已登录用户基本处理", False, f"请求异常: {str(e)}")
            return False
    
    def test_process_with_history(self):
        """测试带历史记录的消息处理"""
        payload = {
            "session_id": "test_session_history",
            "user_id": "test_user_history",
            "platform": "web",
            "language": "zh",
            "status": 1,
            "messages": "我的订单号是1234567890",
            "history": [
                {"role": "user", "content": "我需要查询充值状态"},
                {"role": "AI", "content": "请提供您的订单号"}
            ],
            "site": 1,
            "transfer_human": 0
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/process", 
                json=payload, 
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("带历史记录处理", True, "带历史记录处理正常", {
                    "response": data.get("response", "")[:100]
                })
                return True
            else:
                self.log_result("带历史记录处理", False, f"HTTP状态码错误: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_result("带历史记录处理", False, f"请求异常: {str(e)}")
            return False
    
    def test_process_invalid_params(self):
        """测试无效参数处理"""
        # 测试缺少必要字段
        payload = {
            "user_id": "test_user",
            "platform": "web"
            # 缺少 session_id 和 messages
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/process", 
                json=payload, 
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 422:  # Validation error
                self.log_result("无效参数测试", True, "正确处理了无效参数")
                return True
            else:
                self.log_result("无效参数测试", False, f"未正确处理无效参数，状态码: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_result("无效参数测试", False, f"请求异常: {str(e)}")
            return False
    
    def test_process_with_images(self):
        """测试带图片的消息处理"""
        payload = {
            "session_id": "test_session_image",
            "user_id": "test_user_image",
            "platform": "mobile",
            "language": "zh",
            "status": 1,
            "messages": "这是我的充值截图",
            "images": ["https://example.com/test-image.jpg"],
            "type": "S001",
            "site": 1,
            "transfer_human": 0
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/process", 
                json=payload, 
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("带图片处理", True, "带图片处理正常", {
                    "response": data.get("response", "")[:100]
                })
                return True
            else:
                self.log_result("带图片处理", False, f"HTTP状态码错误: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_result("带图片处理", False, f"请求异常: {str(e)}")
            return False
    
    def test_nonexistent_endpoint(self):
        """测试不存在的端点"""
        try:
            response = requests.get(f"{self.base_url}/nonexistent", timeout=5)
            
            if response.status_code == 404:
                self.log_result("不存在端点测试", True, "正确返回404错误")
                return True
            else:
                self.log_result("不存在端点测试", False, f"未正确处理不存在端点，状态码: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_result("不存在端点测试", False, f"请求异常: {str(e)}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始运行ChatAI API完整测试套件...")
        print("=" * 60)
        
        tests = [
            ("基础功能测试", [
                self.test_health_check,
                self.test_reload_config,
                self.test_nonexistent_endpoint
            ]),
            ("消息处理测试", [
                self.test_process_unauthenticated,
                self.test_process_authenticated_basic,
                self.test_process_with_history,
                self.test_process_with_images
            ]),
            ("错误处理测试", [
                self.test_process_invalid_params
            ])
        ]
        
        total_tests = 0
        passed_tests = 0
        
        for category, test_functions in tests:
            print(f"\n📋 {category}")
            print("-" * 40)
            
            for test_func in test_functions:
                total_tests += 1
                if test_func():
                    passed_tests += 1
                time.sleep(0.5)  # 避免请求过于频繁
        
        # 生成测试报告
        self.generate_report(total_tests, passed_tests)
    
    def generate_report(self, total_tests: int, passed_tests: int):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("📊 测试报告")
        print("=" * 60)
        
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"总测试数: {total_tests}")
        print(f"通过测试: {passed_tests}")
        print(f"失败测试: {total_tests - passed_tests}")
        print(f"成功率: {success_rate:.1f}%")
        
        if success_rate >= 80:
            print("🎉 测试整体表现良好！")
        elif success_rate >= 60:
            print("⚠️  测试表现一般，建议检查失败的测试")
        else:
            print("🚨 测试表现较差，需要检查服务配置")
        
        # 显示失败的测试详情
        failed_tests = [r for r in self.results if not r["success"]]
        if failed_tests:
            print(f"\n❌ 失败的测试详情:")
            for test in failed_tests:
                print(f"  • {test['test_name']}: {test['message']}")
        
        print("=" * 60)
        
        # 保存详细结果到文件
        try:
            with open("test_results.json", "w", encoding="utf-8") as f:
                json.dump({
                    "summary": {
                        "total_tests": total_tests,
                        "passed_tests": passed_tests,
                        "success_rate": success_rate,
                        "timestamp": time.time()
                    },
                    "details": self.results
                }, f, ensure_ascii=False, indent=2)
            print("📄 详细测试结果已保存到 test_results.json")
        except Exception as e:
            print(f"⚠️  保存测试结果失败: {str(e)}")

def main():
    """主函数"""
    tester = APITester()
    tester.run_all_tests()

if __name__ == "__main__":
    main() 