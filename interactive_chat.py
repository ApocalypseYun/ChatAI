#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChatAI 交互式多轮对话测试工具

使用说明：
1. 启动ChatAI服务：uvicorn app:app --host 0.0.0.0 --port 8000 --reload
2. 运行此脚本：python interactive_chat.py
3. 输入消息进行对话，输入'quit'或'exit'退出，输入'help'查看帮助

功能特性：
- 模拟真实用户多轮对话
- 自动维护对话历史
- 支持图片上传测试
- 支持多语言切换
- 支持登录状态切换
- 彩色输出，美化界面
- 会话记录保存
"""

import requests
import json
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any
import sys

# 彩色输出支持
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class ChatSession:
    """对话会话管理"""
    
    def __init__(self, api_url: str = "http://127.0.0.1:8000"):
        self.api_url = api_url
        self.session_id = f"interactive_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        self.history = []
        self.language = "zh"
        self.status = 1  # 1=已登录, 0=未登录
        self.platform = "web"
        self.site = 1
        self.conversation_log = []
        
        print(f"{Colors.HEADER}🤖 ChatAI 交互式对话测试工具{Colors.ENDC}")
        print(f"{Colors.OKBLUE}会话ID: {self.session_id}{Colors.ENDC}")
        print(f"{Colors.OKBLUE}用户ID: {self.user_id}{Colors.ENDC}")
        print(f"{Colors.OKCYAN}输入 'help' 查看帮助，输入 'quit' 或 'exit' 退出{Colors.ENDC}")
        print("-" * 80)
    
    def print_help(self):
        """显示帮助信息"""
        help_text = f"""
{Colors.HEADER}📖 ChatAI 对话测试工具帮助{Colors.ENDC}

{Colors.BOLD}基本命令：{Colors.ENDC}
  help                    显示此帮助信息
  quit / exit            退出程序
  clear                  清空对话历史
  status                 显示当前会话状态
  save                   保存对话记录到文件

{Colors.BOLD}设置命令：{Colors.ENDC}
  /lang <zh|en|ja|th|tl>  切换语言 (中文|英语|日语|泰语|他加禄语)
  /login                  切换到已登录状态
  /logout                 切换到未登录状态
  /platform <web|mobile>  切换平台类型
  /user <user_id>         设置用户ID

{Colors.BOLD}测试场景命令：{Colors.ENDC}
  /charge                 开始充值查询场景 (S001)
  /withdraw               开始提现查询场景 (S002)  
  /activity               开始活动查询场景 (S003)
  /image <url>            发送图片链接测试图片处理
  /order <18位数字>        发送订单号测试订单识别

{Colors.BOLD}快速测试命令：{Colors.ENDC}
  /test_charge_18         测试18位充值订单号识别
  /test_withdraw_19       测试19位数字拒绝（提现场景）
  /test_image_upload      测试图片上传转人工
  /test_multilang         测试多语言支持

{Colors.BOLD}对话示例：{Colors.ENDC}
  {Colors.OKGREEN}我的充值还没有到账{Colors.ENDC}              → 触发S001充值查询流程
  {Colors.OKGREEN}我的提现什么时候到账{Colors.ENDC}            → 触发S002提现查询流程
  {Colors.OKGREEN}我想查询首存奖励{Colors.ENDC}               → 触发S003活动查询流程
  {Colors.OKGREEN}我要找人工客服{Colors.ENDC}                → 转人工客服
  {Colors.OKGREEN}123456789012345678{Colors.ENDC}         → 提供18位订单号

{Colors.BOLD}状态说明：{Colors.ENDC}
  • 绿色 ✅ = 正常响应
  • 黄色 ⚠️  = 警告或注意事项  
  • 红色 ❌ = 错误或失败
  • 蓝色 🔄 = 转人工或状态变化
"""
        print(help_text)
    
    def print_status(self):
        """显示当前会话状态"""
        status_text = "已登录" if self.status == 1 else "未登录"
        print(f"\n{Colors.HEADER}📊 当前会话状态{Colors.ENDC}")
        print(f"  会话ID: {Colors.OKCYAN}{self.session_id}{Colors.ENDC}")
        print(f"  用户ID: {Colors.OKCYAN}{self.user_id}{Colors.ENDC}")
        print(f"  语言: {Colors.OKCYAN}{self.language}{Colors.ENDC}")
        print(f"  状态: {Colors.OKCYAN}{status_text}{Colors.ENDC}")
        print(f"  平台: {Colors.OKCYAN}{self.platform}{Colors.ENDC}")
        print(f"  对话轮次: {Colors.OKCYAN}{len(self.history)//2}{Colors.ENDC}")
        print(f"  历史记录: {Colors.OKCYAN}{len(self.history)} 条{Colors.ENDC}")
    
    def save_conversation(self):
        """保存对话记录"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chat_log_{timestamp}.json"
        
        chat_data = {
            "session_info": {
                "session_id": self.session_id,
                "user_id": self.user_id,
                "language": self.language,
                "status": self.status,
                "platform": self.platform,
                "start_time": self.conversation_log[0]["timestamp"] if self.conversation_log else "",
                "end_time": datetime.now().isoformat(),
                "total_rounds": len(self.conversation_log)
            },
            "conversation": self.conversation_log
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(chat_data, f, ensure_ascii=False, indent=2)
            print(f"{Colors.OKGREEN}✅ 对话记录已保存到: {filename}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}❌ 保存失败: {str(e)}{Colors.ENDC}")
    
    def clear_history(self):
        """清空对话历史"""
        self.history.clear()
        self.conversation_log.clear()
        print(f"{Colors.OKGREEN}✅ 对话历史已清空{Colors.ENDC}")
    
    def send_message(self, message: str, images: List[str] = None) -> Dict[str, Any]:
        """发送消息到ChatAI API"""
        payload = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "platform": self.platform,
            "language": self.language,
            "status": self.status,
            "messages": message,
            "history": self.history,
            "site": self.site,
            "transfer_human": 0
        }
        
        if images:
            payload["images"] = images
        
        try:
            response = requests.post(
                f"{self.api_url}/process",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"请求异常: {str(e)}"}
    
    def process_command(self, command: str) -> bool:
        """处理特殊命令，返回True表示继续对话，False表示退出"""
        command = command.strip()
        
        if command in ['quit', 'exit']:
            return False
        
        elif command == 'help':
            self.print_help()
            
        elif command == 'clear':
            self.clear_history()
            
        elif command == 'status':
            self.print_status()
            
        elif command == 'save':
            self.save_conversation()
            
        elif command.startswith('/lang '):
            lang = command.split(' ', 1)[1].strip()
            if lang in ['zh', 'en', 'ja', 'th', 'tl']:
                self.language = lang
                print(f"{Colors.OKGREEN}✅ 语言已切换到: {lang}{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}⚠️  支持的语言: zh, en, ja, th, tl{Colors.ENDC}")
                
        elif command == '/login':
            self.status = 1
            print(f"{Colors.OKGREEN}✅ 已切换到登录状态{Colors.ENDC}")
            
        elif command == '/logout':
            self.status = 0
            print(f"{Colors.OKGREEN}✅ 已切换到未登录状态{Colors.ENDC}")
            
        elif command.startswith('/platform '):
            platform = command.split(' ', 1)[1].strip()
            if platform in ['web', 'mobile']:
                self.platform = platform
                print(f"{Colors.OKGREEN}✅ 平台已切换到: {platform}{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}⚠️  支持的平台: web, mobile{Colors.ENDC}")
                
        elif command.startswith('/user '):
            user_id = command.split(' ', 1)[1].strip()
            self.user_id = user_id
            print(f"{Colors.OKGREEN}✅ 用户ID已设置为: {user_id}{Colors.ENDC}")
            
        # 场景测试命令
        elif command == '/charge':
            self.send_and_display("我的充值还没有到账")
            
        elif command == '/withdraw':
            self.send_and_display("我的提现什么时候到账")
            
        elif command == '/activity':
            self.send_and_display("我想查询首存奖励")
            
        elif command.startswith('/image '):
            image_url = command.split(' ', 1)[1].strip()
            self.send_and_display("这是我的截图", [image_url])
            
        elif command.startswith('/order '):
            order_no = command.split(' ', 1)[1].strip()
            self.send_and_display(f"我的订单号是{order_no}")
            
        # 快速测试命令
        elif command == '/test_charge_18':
            print(f"{Colors.OKCYAN}🧪 测试充值18位订单号识别...{Colors.ENDC}")
            self.send_and_display("我的充值还没有到账")
            self.send_and_display("我的订单号是123456789012345678")
            
        elif command == '/test_withdraw_19':
            print(f"{Colors.OKCYAN}🧪 测试提现19位数字拒绝...{Colors.ENDC}")
            self.send_and_display("我的提现还没有到账")
            self.send_and_display("这个号码1234567890123456789是我的电话")
            
        elif command == '/test_image_upload':
            print(f"{Colors.OKCYAN}🧪 测试图片上传转人工...{Colors.ENDC}")
            self.send_and_display("我的充值还没有到账")
            self.send_and_display("这是我的充值截图", ["https://example.com/payment-screenshot.jpg"])
            
        elif command == '/test_multilang':
            print(f"{Colors.OKCYAN}🧪 测试多语言支持...{Colors.ENDC}")
            original_lang = self.language
            for lang, message in [
                ("zh", "我需要充值帮助"),
                ("en", "I need deposit help"), 
                ("ja", "入金について教えてください"),
                ("th", "ฉันต้องการความช่วยเหลือเรื่องการเติมเงิน")
            ]:
                self.language = lang
                print(f"\n{Colors.OKCYAN}测试语言: {lang}{Colors.ENDC}")
                self.send_and_display(message)
            self.language = original_lang
            
        else:
            print(f"{Colors.WARNING}⚠️  未知命令: {command}，输入 'help' 查看帮助{Colors.ENDC}")
            
        return True
    
    def send_and_display(self, message: str, images: List[str] = None):
        """发送消息并显示结果"""
        print(f"\n{Colors.BOLD}👤 用户:{Colors.ENDC} {message}")
        if images:
            print(f"{Colors.OKCYAN}📷 图片: {', '.join(images)}{Colors.ENDC}")
        
        # 记录到历史
        self.history.append({"role": "user", "content": message})
        
        # 发送请求
        result = self.send_message(message, images)
        
        if result["success"]:
            data = result["data"]
            response = data.get("response", "")
            stage = data.get("stage", "")
            transfer_human = data.get("transfer_human", 0)
            response_images = data.get("images", [])
            intent = data.get("metadata", {}).get("intent", "")
            
            # 显示AI响应
            if transfer_human == 1:
                print(f"{Colors.OKBLUE}🤖 AI (转人工):{Colors.ENDC} {response}")
                print(f"{Colors.WARNING}🔄 已转接人工客服{Colors.ENDC}")
            else:
                print(f"{Colors.OKGREEN}🤖 AI:{Colors.ENDC} {response}")
            
            # 显示附加信息
            if response_images:
                print(f"{Colors.OKCYAN}📷 返回图片: {', '.join(response_images)}{Colors.ENDC}")
            
            if intent:
                print(f"{Colors.OKCYAN}🎯 识别意图: {intent}{Colors.ENDC}")
            
            if stage:
                stage_text = "进行中" if stage == "working" else "已完成"
                print(f"{Colors.OKCYAN}📋 当前阶段: {stage} ({stage_text}){Colors.ENDC}")
            
            # 记录到历史
            self.history.append({"role": "AI", "content": response})
            
            # 记录到对话日志
            self.conversation_log.append({
                "timestamp": datetime.now().isoformat(),
                "user_message": message,
                "user_images": images or [],
                "ai_response": response,
                "intent": intent,
                "stage": stage,
                "transfer_human": transfer_human,
                "response_images": response_images
            })
            
        else:
            print(f"{Colors.FAIL}❌ 请求失败: {result['error']}{Colors.ENDC}")
    
    def check_api_health(self) -> bool:
        """检查API服务状态"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"{Colors.OKGREEN}✅ ChatAI服务连接正常{Colors.ENDC}")
                return True
            else:
                print(f"{Colors.FAIL}❌ ChatAI服务响应异常: {response.status_code}{Colors.ENDC}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"{Colors.FAIL}❌ 无法连接到ChatAI服务: {str(e)}{Colors.ENDC}")
            print(f"{Colors.WARNING}💡 请确保ChatAI服务已启动: uvicorn app:app --host 0.0.0.0 --port 8000{Colors.ENDC}")
            return False
    
    def run(self):
        """运行交互式对话"""
        # 检查API服务
        if not self.check_api_health():
            return
        
        try:
            while True:
                try:
                    user_input = input(f"\n{Colors.BOLD}💬 请输入消息: {Colors.ENDC}").strip()
                    
                    if not user_input:
                        continue
                    
                    # 处理命令
                    if user_input.startswith('/') or user_input in ['help', 'quit', 'exit', 'clear', 'status', 'save']:
                        if not self.process_command(user_input):
                            break
                        continue
                    
                    # 发送普通消息
                    self.send_and_display(user_input)
                    
                except KeyboardInterrupt:
                    print(f"\n{Colors.WARNING}⚠️  检测到Ctrl+C，正在退出...{Colors.ENDC}")
                    break
                except EOFError:
                    print(f"\n{Colors.WARNING}⚠️  检测到EOF，正在退出...{Colors.ENDC}")
                    break
                    
        finally:
            # 保存对话记录
            if self.conversation_log:
                save_choice = input(f"\n{Colors.OKCYAN}💾 是否保存对话记录？ (y/N): {Colors.ENDC}").strip().lower()
                if save_choice in ['y', 'yes']:
                    self.save_conversation()
            
            print(f"\n{Colors.OKGREEN}👋 谢谢使用ChatAI对话测试工具！{Colors.ENDC}")
            print(f"{Colors.OKCYAN}📊 本次会话统计: {len(self.conversation_log)} 轮对话{Colors.ENDC}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ChatAI交互式对话测试工具")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="ChatAI API地址")
    parser.add_argument("--lang", default="zh", choices=["zh", "en", "ja", "th", "tl"], help="默认语言")
    parser.add_argument("--status", default=1, type=int, choices=[0, 1], help="用户状态 (0=未登录, 1=已登录)")
    
    args = parser.parse_args()
    
    # 创建会话并运行
    session = ChatSession(api_url=args.api)
    session.language = args.lang
    session.status = args.status
    
    session.run()

if __name__ == "__main__":
    main()