# ChatAI Token 认证机制说明

## 概述

ChatAI系统实现了基于HMAC-SHA256的token认证机制，确保已登录用户的请求安全性。该机制通过用户ID、时间戳和特殊字符组合生成签名，提供了有效的身份验证和请求防伪造保护。

## 认证流程

### 1. Token生成算法

Token由以下部分组成：
```
token = user_id.timestamp.signature
```

其中：
- `user_id`: 用户唯一标识符
- `timestamp`: Unix时间戳（秒）
- `signature`: HMAC-SHA256签名

### 2. 签名生成过程

```python
# 1. 构建待签名字符串
special_chars = "@#$%"
message = f"{user_id}{special_chars}{timestamp}"

# 2. 使用HMAC-SHA256生成签名
signature = hmac.new(
    secret_key.encode('utf-8'),
    message.encode('utf-8'),
    hashlib.sha256
).hexdigest()

# 3. 组装最终token
token = f"{user_id}.{timestamp}.{signature}"
```

### 3. Token验证过程

服务端接收到请求后：
1. 解析token格式（`user_id.timestamp.signature`）
2. 验证时间戳是否在有效期内（默认1小时）
3. 使用相同算法重新生成签名
4. 使用时间安全的比较方法验证签名
5. 确认token中的user_id与请求中的user_id一致

## 配置说明

### 系统配置

在 `config/business_config.json` 中添加认证配置：

```json
{
  "auth": {
    "secret_key": "ChatAI_Production_Secret_Key_2024_@#$%^&*()",
    "token_max_age": 3600,
    "require_token_for_logged_users": true,
    "token_refresh_threshold": 300
  }
}
```

配置项说明：
- `secret_key`: 用于生成HMAC签名的密钥（生产环境必须使用强密钥）
- `token_max_age`: Token有效期（秒），默认3600秒（1小时）
- `require_token_for_logged_users`: 是否对已登录用户强制要求token验证
- `token_refresh_threshold`: Token刷新阈值（秒），预留功能

### 安全建议

1. **密钥管理**：
   - 生产环境使用至少32字符的强密钥
   - 定期轮换密钥
   - 不要在代码中硬编码密钥

2. **有效期设置**：
   - 根据业务需求调整token有效期
   - 建议不超过24小时
   - 敏感操作可使用更短的有效期

## API使用说明

### 请求格式

已登录用户（`status=1`）的请求必须包含有效的token：

```json
{
  "session_id": "user_session_123",
  "user_id": "user123",
  "platform": "web",
  "language": "zh",
  "status": 1,
  "messages": "我想查询充值状态",
  "token": "user123.1708123456.abc123def456...",
  "type": null,
  "history": [],
  "images": null,
  "metadata": null,
  "site": 1
}
```

### 响应说明

#### 成功响应
当token验证通过时，系统正常处理请求并返回业务响应。

#### 失败响应
当token验证失败时，系统返回验证错误：

```json
{
  "error": "Token验证失败: Token已过期"
}
```

常见错误类型：
- `缺少认证token`: 请求中没有提供token
- `Token格式错误`: token格式不符合要求
- `时间戳格式错误`: token中的时间戳无效
- `Token已过期`: token超过有效期
- `Token签名验证失败`: 签名不匹配
- `Token中的用户ID与请求中的用户ID不匹配`: 用户ID不一致

## 开发工具

### Token生成脚本

使用提供的脚本生成和验证token：

```bash
# 生成token
python generate_token.py user123

# 验证token
python generate_token.py user123 verify user123.1708123456.abc123def456...
```

### 代码集成示例

#### 生成Token

```python
from src.auth import generate_token

# 生成token
user_id = "user123"
token = generate_token(user_id)
print(f"Generated token: {token}")
```

#### 验证Token

```python
from src.auth import verify_token

# 验证token
is_valid, extracted_user_id, error_msg = verify_token(token)
if is_valid:
    print(f"Token valid for user: {extracted_user_id}")
else:
    print(f"Token validation failed: {error_msg}")
```

#### 在MessageRequest中使用

```python
from src.util import MessageRequest

# 创建带token的请求
request = MessageRequest(
    session_id="session123",
    user_id="user123",
    platform="web",
    language="zh",
    status=1,  # 已登录
    messages="查询充值状态",
    token="user123.1708123456.abc123def456..."
)

# 验证token
is_valid, error_msg = request.validate_token()
if not is_valid:
    print(f"Token validation failed: {error_msg}")
```

## 测试说明

### 功能测试

1. **Token生成测试**：
   ```bash
   python generate_token.py testuser
   ```

2. **Token验证测试**：
   ```bash
   python generate_token.py testuser verify [generated_token]
   ```

3. **API请求测试**：
   ```bash
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{
       "session_id": "test_session",
       "user_id": "testuser",
       "platform": "web",
       "language": "zh",
       "status": 1,
       "messages": "测试消息",
       "token": "[generated_token]"
     }'
   ```

### 安全测试

1. **过期Token测试**：使用超过有效期的token
2. **伪造Token测试**：使用错误签名的token
3. **用户ID不匹配测试**：使用其他用户的token
4. **格式错误测试**：使用格式不正确的token

## 性能考虑

1. **计算开销**：HMAC-SHA256计算对性能影响较小
2. **内存使用**：token验证不需要存储状态
3. **并发处理**：验证过程无状态，支持高并发

## 错误处理

系统对所有认证相关错误进行详细日志记录：

```python
logger.error(f"Token验证失败", extra={
    'session_id': request.session_id,
    'user_id': request.user_id,
    'token_error': token_error,
    'has_token': bool(request.token)
})
```

日志包含：
- 会话ID
- 用户ID  
- 具体错误信息
- 是否包含token

## 注意事项

1. **未登录用户**：`status=0`的用户不需要提供token
2. **向前兼容**：现有不带token的请求对未登录用户仍然有效
3. **时钟同步**：确保服务器时钟准确，避免时间戳偏差导致的验证失败
4. **HTTPS使用**：生产环境强烈建议使用HTTPS传输token

## 常见问题

### Q: Token可以重复使用吗？
A: 是的，在有效期内token可以重复使用。

### Q: 如何处理时钟偏差？
A: 可以在验证时加入少量时间容差，或者使用NTP同步服务器时钟。

### Q: 忘记token怎么办？
A: 重新调用token生成接口获取新的token。

### Q: 可以延长token有效期吗？
A: 修改配置中的`token_max_age`参数，或实现token刷新机制。 