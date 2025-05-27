import requests
import json

def test_message_api():
    """测试消息API"""
    url = "http://127.0.0.1:5000/api/message"
    
    # 请求头
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-test-ai-chat-2025"
    }
    
    # 请求体
    payload = {
        "session_id": "session_12345",
        "user_id": "u1001",
        "platform": "ph",
        "language": "en",
        "status": 1,
        "messages": "Hi, I need help.",
        "history": [
            {"role": "user", "content": "我家洗衣机坏了，想报修。"},
            {"role": "AI", "content": "请提供订单号和购买时间。"},
            {"role": "user", "content": "订单号：A123456，3月15日买的。"},
            {"role": "AI", "content": "收到，我们安排师傅三天内上门。"},
            {"role": "user", "content": "师傅今天能来吗？我白天在家。"},
            {"role": "AI", "content": "我来帮您查一下安排。"},
            {"role": "user", "content": "如果不行，能不能改到明天？"}
        ],
        "images": ["https://your-cdn.com/uploads/receipt1.jpg"],
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
    
    try:
        print("发送请求...")
        print(f"请求头: {json.dumps(headers, indent=2, ensure_ascii=False)}")
        print(f"请求体: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        
        print(f"\n状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"请求出错: {e}")

if __name__ == "__main__":
    print("开始测试API...")
    test_message_api()
    print("测试完成。") 