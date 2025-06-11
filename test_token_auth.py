#!/usr/bin/env python3
"""
Token认证功能测试脚本
"""

import time
import asyncio
from src.auth import generate_token, verify_token
from src.util import MessageRequest
from src.process import process_message

async def test_token_generation():
    """测试token生成功能"""
    print("=== 测试Token生成功能 ===")
    
    user_id = "test_user_123"
    token = generate_token(user_id)
    
    print(f"用户ID: {user_id}")
    print(f"生成的Token: {token}")
    
    # 验证生成的token
    is_valid, extracted_user_id, error_msg = verify_token(token)
    
    assert is_valid, f"Token验证失败: {error_msg}"
    assert extracted_user_id == user_id, f"用户ID不匹配: {extracted_user_id} != {user_id}"
    
    print("✅ Token生成测试通过")
    return token

async def test_token_validation():
    """测试token验证功能"""
    print("\n=== 测试Token验证功能 ===")
    
    user_id = "test_user_456"
    token = generate_token(user_id)
    
    # 测试有效token
    is_valid, extracted_user_id, error_msg = verify_token(token)
    assert is_valid, f"有效token验证失败: {error_msg}"
    assert extracted_user_id == user_id, f"用户ID不匹配"
    print("✅ 有效token验证通过")
    
    # 测试格式错误的token
    invalid_token = "invalid.token.format"
    is_valid, _, error_msg = verify_token(invalid_token)
    assert not is_valid, "格式错误的token不应该通过验证"
    print("✅ 格式错误token验证正确拒绝")
    
    # 测试空token
    is_valid, _, error_msg = verify_token("")
    assert not is_valid, "空token不应该通过验证"
    print("✅ 空token验证正确拒绝")
    
    # 测试伪造签名的token
    fake_token = f"{user_id}.{int(time.time())}.fake_signature"
    is_valid, _, error_msg = verify_token(fake_token)
    assert not is_valid, "伪造签名的token不应该通过验证"
    print("✅ 伪造签名token验证正确拒绝")

async def test_expired_token():
    """测试过期token"""
    print("\n=== 测试过期Token ===")
    
    user_id = "test_user_expired"
    # 生成1小时之前的token（过期）
    old_timestamp = int(time.time()) - 3700  # 超过1小时
    expired_token = generate_token(user_id, timestamp=old_timestamp)
    
    is_valid, _, error_msg = verify_token(expired_token)
    assert not is_valid, "过期token不应该通过验证"
    assert "已过期" in error_msg, f"错误信息应该包含'已过期': {error_msg}"
    print("✅ 过期token验证正确拒绝")

async def test_message_request_validation():
    """测试MessageRequest中的token验证"""
    print("\n=== 测试MessageRequest Token验证 ===")
    
    user_id = "test_user_request"
    token = generate_token(user_id)
    
    # 测试有效请求
    request = MessageRequest(
        session_id="test_session",
        user_id=user_id,
        platform="web",
        language="zh",
        status=1,  # 已登录
        messages="测试消息",
        token=token
    )
    
    is_valid, error_msg = request.validate_token()
    assert is_valid, f"有效请求验证失败: {error_msg}"
    print("✅ 有效MessageRequest验证通过")
    
    # 测试用户ID不匹配
    request_mismatch = MessageRequest(
        session_id="test_session",
        user_id="different_user",  # 不同的用户ID
        platform="web", 
        language="zh",
        status=1,
        messages="测试消息",
        token=token
    )
    
    is_valid, error_msg = request_mismatch.validate_token()
    assert not is_valid, "用户ID不匹配的请求不应该通过验证"
    assert "不匹配" in error_msg, f"错误信息应该包含'不匹配': {error_msg}"
    print("✅ 用户ID不匹配请求正确拒绝")
    
    # 测试缺少token的已登录用户请求
    request_no_token = MessageRequest(
        session_id="test_session",
        user_id=user_id,
        platform="web",
        language="zh", 
        status=1,  # 已登录但没有token
        messages="测试消息"
        # 没有token字段
    )
    
    is_valid, error_msg = request_no_token.validate_token()
    assert not is_valid, "缺少token的已登录用户请求不应该通过验证"
    assert "缺少认证token" in error_msg, f"错误信息应该包含'缺少认证token': {error_msg}"
    print("✅ 缺少token的请求正确拒绝")

async def test_unauthenticated_user():
    """测试未登录用户不需要token"""
    print("\n=== 测试未登录用户 ===")
    
    # 未登录用户不需要token
    request = MessageRequest(
        session_id="test_session_unauth",
        user_id="unauth_user",
        platform="web",
        language="zh",
        status=0,  # 未登录
        messages="测试消息"
        # 没有token，但status=0不需要验证
    )
    
    # 直接测试process_message函数
    try:
        response = await process_message(request)
        assert response.status == "success", "未登录用户请求应该成功"
        print("✅ 未登录用户请求处理成功")
    except ValueError as e:
        if "Token验证失败" in str(e):
            assert False, "未登录用户不应该要求token验证"
        else:
            # 其他业务相关错误是正常的
            print("✅ 未登录用户不要求token验证（业务处理正常）")

async def test_authenticated_user_with_invalid_token():
    """测试已登录用户使用无效token"""
    print("\n=== 测试已登录用户使用无效Token ===")
    
    request = MessageRequest(
        session_id="test_session_invalid",
        user_id="auth_user",
        platform="web",
        language="zh",
        status=1,  # 已登录
        messages="测试消息",
        token="invalid.token.here"
    )
    
    try:
        response = await process_message(request)
        assert False, "无效token的已登录用户请求应该失败"
    except ValueError as e:
        assert "Token验证失败" in str(e), f"应该是token验证错误: {e}"
        print("✅ 无效token的已登录用户请求正确拒绝")

async def test_authenticated_user_with_valid_token():
    """测试已登录用户使用有效token"""
    print("\n=== 测试已登录用户使用有效Token ===")
    
    user_id = "valid_auth_user"
    token = generate_token(user_id)
    
    request = MessageRequest(
        session_id="test_session_valid",
        user_id=user_id,
        platform="web",
        language="zh",
        status=1,  # 已登录
        messages="我想查询充值状态",
        token=token
    )
    
    try:
        response = await process_message(request)
        assert response.status == "success", "有效token的已登录用户请求应该成功"
        print("✅ 有效token的已登录用户请求处理成功")
    except ValueError as e:
        if "Token验证失败" in str(e):
            assert False, f"有效token验证不应该失败: {e}"
        else:
            # 其他业务相关错误是正常的
            print("✅ 有效token验证通过（业务处理正常）")

async def run_all_tests():
    """运行所有测试"""
    print("开始运行Token认证功能测试...")
    print("=" * 50)
    
    try:
        await test_token_generation()
        await test_token_validation()
        await test_expired_token()
        await test_message_request_validation()
        await test_unauthenticated_user()
        await test_authenticated_user_with_invalid_token()
        await test_authenticated_user_with_valid_token()
        
        print("\n" + "=" * 50)
        print("🎉 所有测试通过！Token认证功能正常工作。")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return False
    except Exception as e:
        print(f"\n💥 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    result = asyncio.run(run_all_tests())
    exit(0 if result else 1) 