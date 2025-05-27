from flask import Flask, request, jsonify
import json

app = Flask(__name__)

@app.route('/api/message', methods=['POST'])
def receive_message():
    """接收消息并进行处理"""
    if not request.is_json:
        return jsonify({
            "status": "error",
            "error_code": "1001",
            "error_message": "请求必须是JSON格式"
        }), 400
    
    # 获取请求头和请求体
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({
            "status": "error",
            "error_code": "1002",
            "error_message": "缺少有效的Authorization头"
        }), 401
    
    # 验证API Token (简单示例)
    api_token = auth_header.split(' ')[1]
    if api_token != "sk-test-ai-chat-2025":
        return jsonify({
            "status": "error",
            "error_code": "1003",
            "error_message": "无效的API Token"
        }), 401
    
    data = request.get_json()
    
    # 检查必要的字段
    required_fields = ['session_id', 'user_id', 'messages']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({
            "status": "error",
            "error_code": "1004",
            "error_message": f"缺少必要字段: {', '.join(missing_fields)}"
        }), 400
    
    # 提取请求数据
    session_id = data.get('session_id')
    user_id = data.get('user_id')
    platform = data.get('platform', 'default')
    language = data.get('language', 'en')
    status = data.get('status', 0)
    messages = data.get('messages')
    history = data.get('history', [])
    images = data.get('images', [])
    metadata = data.get('metadata', {})
    
    # 处理消息
    response_data = process_message(
        session_id, 
        user_id, 
        platform, 
        language,
        status,
        messages, 
        history, 
        images, 
        metadata
    )
    
    return jsonify(response_data)

def process_message(session_id, user_id, platform, language, status, messages, history, images, metadata):
    """处理接收到的消息"""
    # 示例处理逻辑，根据需求修改
    
    # 检查是否需要调用API
    is_call = 0
    call_codes = []
    
    if metadata and metadata.get('is_call') == 1 and 'calls' in metadata:
        is_call = 1
        for call in metadata['calls']:
            if 'code' in call:
                call_codes.append(call['code'])
                
                # 这里可以添加实际的API调用逻辑
                # 例如: result = call_external_api(call['code'], call.get('args', {}))
    
    # 构建响应
    response = {
        "session_id": session_id,
        "status": "success",
        "response": f"我已收到您的消息: '{messages}'。您的用户ID是{user_id}，平台是{platform}，语言是{language}。",
        "stage": "working",
        "metadata": {
            "is_call": is_call,
            "call_codes": call_codes
        }
    }
    
    # 如果有图片，也返回图片
    if images:
        response["images"] = images
    
    return response

if __name__ == '__main__':
    app.run(debug=True)
