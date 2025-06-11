#!/usr/bin/env python3
"""
Token生成脚本
用于生成和验证用户认证token
"""

import sys
import time
from src.auth import generate_token, verify_token

def main():
    print("=== ChatAI Token 生成器 ===\n")
    
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python generate_token.py <user_id>")
        print("  python generate_token.py <user_id> verify <token>")
        print("\n示例:")
        print("  python generate_token.py user123")
        print("  python generate_token.py user123 verify user123.1708123456.abc123def456...")
        return
    
    user_id = sys.argv[1]
    
    if len(sys.argv) >= 4 and sys.argv[2] == "verify":
        # 验证token
        token = sys.argv[3]
        print(f"验证用户 {user_id} 的token...")
        print(f"Token: {token}\n")
        
        is_valid, extracted_user_id, error_msg = verify_token(token)
        
        if is_valid:
            print("✅ Token验证成功!")
            print(f"用户ID: {extracted_user_id}")
            print(f"Token有效期: 1小时")
            
            # 检查用户ID是否匹配
            if extracted_user_id == user_id:
                print("✅ 用户ID匹配")
            else:
                print(f"❌ 用户ID不匹配 (Token中的ID: {extracted_user_id})")
        else:
            print("❌ Token验证失败!")
            print(f"错误信息: {error_msg}")
    
    else:
        # 生成token
        print(f"为用户 {user_id} 生成token...")
        
        # 生成当前时间的token
        token = generate_token(user_id)
        current_time = int(time.time())
        
        print(f"\n✅ Token生成成功!")
        print(f"用户ID: {user_id}")
        print(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))}")
        print(f"有效期: 1小时")
        print(f"\nToken: {token}")
        
        # 验证生成的token
        print(f"\n--- 验证生成的token ---")
        is_valid, extracted_user_id, error_msg = verify_token(token)
        
        if is_valid:
            print("✅ 验证成功!")
        else:
            print(f"❌ 验证失败: {error_msg}")
        
        # 生成测试用的curl命令
        print(f"\n--- 测试用的API调用示例 ---")
        print("使用curl测试:")
        print(f"""curl -X POST http://localhost:8000/chat \\
  -H "Content-Type: application/json" \\
  -d '{{
    "session_id": "test_session_123",
    "user_id": "{user_id}",
    "platform": "web",
    "language": "zh",
    "status": 1,
    "messages": "我想查询充值状态",
    "token": "{token}"
  }}'""")

if __name__ == "__main__":
    main() 