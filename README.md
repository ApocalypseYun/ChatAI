# ChatAI API

一个简单的Flask应用，用于接收和处理消息。

## 安装

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 运行应用：

```bash
python app.py
```

应用将在 http://127.0.0.1:5000 上运行。

## API使用

### 发送消息

**端点**: `/api/message`

**方法**: POST

**请求头 Header**:

```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer sk-test-ai-chat-2025"
}
```

**请求体 Body**:

```json
{
  "session_id": "session_12345",
  "user_id": "u1001",
  "platform": "ph",
  "language": "en",
  "status": 1,
  "messages": "Hi, I need help.",
  "type":"", //业务种类
  "history": [
    { "role": "user", "content": "我家洗衣机坏了，想报修。" },
    { "role": "AI", "content": "请提供订单号和购买时间。" },
    { "role": "user", "content": "订单号：A123456，3月15日买的。" },
    { "role": "AI", "content": "收到，我们安排师傅三天内上门。" },
    { "role": "user", "content": "师傅今天能来吗？我白天在家。" },
    { "role": "AI", "content": "我来帮您查一下安排。" },
    { "role": "user", "content": "如果不行，能不能改到明天？" }
  ],
  "images": [
    "https://your-cdn.com/uploads/receipt1.jpg"
  ],
  "metadata": {
    "is_call": 1,
    "calls": [
      {
        "code": "A001",
        "args": {
          "user_id": "u1001"
        }
      },
      {
        "code": "A003",
        "args": {
          "month": "2025-04",
          "user_id": "u1001"
        }
      }
    ]
  }
}
```

**响应体 Body**:

```json
{
  "session_id": "session_12345",
  "status": "success",
  "response": "Sure! I can assist with your withdrawal. Please provide your transaction ID.",
  "images": [
    "https://your-cdn.com/uploads/receipt1.jpg"
  ],
  "stage": "working",
  "metadata": {
    "is_call": 1,
    "call_codes": ["A001", "A003"]
  }
}
```

**错误响应示例**:

```json
{
  "status": "error",
  "error_code": "1004",
  "error_message": "缺少必要字段: session_id, user_id, messages"
}
```

## 测试API

使用提供的测试脚本测试API：

```bash
python test_api.py
```