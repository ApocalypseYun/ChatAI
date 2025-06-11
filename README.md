# 🤖 ChatAI - 智能对话API服务

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.95.2-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 一个基于FastAPI构建的高性能智能对话API服务，支持多语言意图识别、会话管理和智能回复生成。

## 📖 概述

ChatAI是一个基于FastAPI的智能客服系统，专为在线平台的充值、提现、活动查询等业务场景设计。系统集成了大语言模型、意图识别、多语言支持、图片处理等功能，为用户提供智能化的客服体验。

## 🚀 核心功能

### 业务流程支持
- **S001 充值查询**：订单状态查询、支付问题处理、图片上传转人工
- **S002 提现查询**：提现状态查询、异常处理、TG群推送、图片上传转人工
- **S003 活动查询**：活动列表获取、领取状态查询、条件判断

### 智能特性
- **多语言支持**：中文、英文、日文、泰文、他加禄语
- **意图自动识别**：基于关键词和AI模型的双重识别机制
- **阶段智能跟踪**：多轮对话状态管理
- **图片智能处理**：自动检测图片上传并转人工客服

### 系统集成
- **OpenAI模型集成**：智能回复生成
- **Token认证机制**：基于HMAC-SHA256的用户身份验证
- **Telegram群推送**：异常状态实时通知
- **内部API调用**：充值、提现、活动接口集成
- **配置热重载**：支持运行时配置更新
- **完整日志系统**：多级别日志分离、自动轮转、JSON格式、性能监控

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip 包管理器
- FastAPI 0.68+
- httpx
- pydantic
- cryptography

### 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd ChatAI
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **启动服务**
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **验证服务**
   
   访问 http://127.0.0.1:8000/health 检查服务状态
   
   或访问 http://127.0.0.1:8000/docs 查看API文档

5. **测试日志功能**
   
   ```bash
   # 测试日志系统
   python test_logging.py
   
   # 查看日志文件
   python manage_logs.py stats
   ```

## 📚 API 文档

### 🏥 健康检查

```http
GET /health
```

**响应示例：**
```json
{
  "status": "ok",
  "service": "ChatAI",
  "timestamp": 1749502827.845137
}
```

### ⚙️ 配置重载

```http
POST /reload_config
```

**响应示例：**
```json
{
  "status": "success",
  "message": "配置重新加载成功",
  "business_types_count": 2
}
```

### 💬 消息处理

```http
POST /process
Content-Type: application/json
```

**请求参数：**

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| session_id | string | ✅ | 会话唯一标识 |
| user_id | string | ✅ | 用户唯一标识 |
| platform | string | ✅ | 平台标识 (web/mobile/app) |
| language | string | ✅ | 语言代码 (zh/en/th/tl) |
| status | integer | ✅ | 消息状态 |
| messages | string | ✅ | 用户消息内容 |
| type | string | ❌ | 业务类型 |
| history | array | ❌ | 历史对话记录 |
| images | array | ❌ | 图片URL列表 |
| metadata | object | ❌ | 元数据信息 |
| site | integer | ❌ | 站点标识 |
| token | string | ❌ | 认证token (已登录用户必填) |
| transfer_human | integer | ❌ | 转人工标识 |

**请求示例：**
```json
{
  "session_id": "session_12345",
  "user_id": "u1001",
  "platform": "web",
  "language": "th",
  "status": 1,
  "messages": "我需要充值",
  "type": "S001",
  "history": [
    { "role": "user", "content": "你好" },
    { "role": "AI", "content": "您好，有什么可以帮助您的吗？" }
  ],
  "images": ["https://example.com/image.jpg"],
  "token": "u1001.1749634097.25b6fbdac6de3b5fd5157591196740340fd470cfed59495a8412155ae0bfba5a",
  "metadata": {
    "is_call": 1,
    "calls": [
      {
        "code": "A001",
        "args": { "user_id": "u1001" }
      }
    ]
  },
  "site": 1,
  "transfer_human": 0
}
```

**响应示例：**
```json
{
  "session_id": "session_12345",
  "status": "success",
  "response": "好的，我来帮您处理充值业务。请提供您的订单号。",
  "stage": "working",
  "metadata": {
    "intent": "S001",
    "api_results": {},
    "timestamp": 1749502827.845137
  },
  "images": null,
  "site": 1,
  "type": "S001",
  "transfer_human": 0
}
```

## 🎯 业务流程详解

### S001 充值查询流程

#### 阶段1：询问订单号
- **触发**：用户提及充值相关问题
- **响应**：询问用户订单编号
- **状态**：working

#### 阶段2：提供指引图片
- **触发**：用户不知道订单号
- **响应**：返回指引图片，教用户查找订单号
- **状态**：working

#### 阶段3：处理订单号或图片
- **情况A - 图片上传**：立即转人工，发送到TG群
- **情况B - 提供订单号**：
  - 提取18位订单号
  - 调用A001接口查询状态
  - 根据状态进行不同处理：
    - `Recharge successful`：充值成功提示
    - `canceled`：已取消提示
    - `pending/rejected/failed`：转人工处理

#### 阶段4：流程结束
- **状态**：finish

### S002 提现查询流程

#### 阶段1：询问订单号
- **触发**：用户提及提现相关问题
- **响应**：询问用户提现订单编号

#### 阶段2：提供指引图片
- **触发**：用户不知道提现订单号
- **响应**：返回提现指引图片

#### 阶段3：处理订单号或图片（核心功能）
- **优先图片检查**：无论哪个阶段，有图片立即转人工
- **订单号处理**：
  - 提取18位提现订单号
  - 调用A002接口查询状态
  - 11种状态智能处理：
    - `Withdrawal successful`：提现成功
    - `pending/obligation`：处理中，请耐心等待
    - `canceled`：用户取消，已取消提示
    - `rejected/prepare/lock/oblock/refused`：转人工

#### 阶段4：流程结束

### S003 活动查询流程

#### 阶段1：活动识别
- **API调用**：A003获取活动列表
- **AI识别**：匹配用户想查询的具体活动
- **分支处理**：
  - 识别成功：直接查询领取状态
  - 识别失败：要求用户明确活动

#### 阶段2：明确活动
- **用户输入**：明确具体活动名称
- **状态查询**：A004接口查询领取状态
- **结果处理**：
  - `Conditions not met`：未达条件
  - `Paid success`：已发放
  - `Waiting paid`：等待发放
  - `Need paid`：转人工发放

## 🖼️ 图片处理机制

### 优先检测策略
无论用户处于哪个对话阶段，系统都会优先检测图片上传：

```python
# 优先检查是否上传图片，不管在哪个阶段
if request.images and len(request.images) > 0:
    # 发送到TG群
    await send_to_telegram(request.images, bot_token, chat_id, username=user_id)
    # 转人工处理
    transfer_human = 1
    response_stage = "finish"
```

### TG群推送
- **充值图片**：用户ID + 图片链接
- **提现图片**：用户ID + 图片链接  
- **异常状态**：用户ID + 订单号 + 状态信息

## 🔢 订单号识别算法

### 精确识别逻辑
```python
def extract_order_no(messages, history):
    # 找到所有连续的数字序列
    number_sequences = re.findall(r'\d+', all_text)
    # 只返回长度恰好为18位的数字序列
    for seq in number_sequences:
        if len(seq) == 18:
            return seq
    return None
```

### 验证规则
- ✅ 18位数字：正确识别
- ❌ 17位数字：拒绝识别
- ❌ 19位数字：拒绝识别
- ❌ 非纯数字：拒绝识别

## 🌍 多语言支持

### 支持语言
- **zh**：简体中文
- **en**：英语
- **ja**：日语
- **th**：泰语
- **tl**：他加禄语

### 配置示例
```json
{
  "keywords": {
    "zh": ["充值", "充钱"],
    "en": ["deposit", "recharge"],
    "ja": ["入金", "チャージ"]
  },
  "responses": {
    "zh": "您正在进行充值业务，请按照提示操作。",
    "en": "You are making a deposit. Please follow the instructions."
  }
}
```

## 🚨 错误处理

### 参数验证
- **必填字段**：session_id, messages
- **状态值**：0（未登录）或1（已登录）
- **语言代码**：支持的语言列表
- **返回码**：422（参数错误）

### 异常处理
- **API调用失败**：自动转人工
- **订单查询异常**：转人工处理
- **图片上传失败**：记录日志并转人工

## 🧪 测试验证

### 自动化测试套件
```bash
python comprehensive_test.py
```

**测试覆盖：**
- **基础功能测试**：健康检查、配置重载
- **用户状态测试**：登录/未登录处理
- **意图识别测试**：中英文意图识别
- **业务流程测试**：S001/S002/S003完整流程
- **订单号提取测试**：边界情况验证
- **多语言测试**：4种语言支持
- **错误处理测试**：参数验证、异常处理
- **性能测试**：响应时间、并发能力
- **配置测试**：文件完整性检查

**性能指标：**
- **平均响应时间**：< 2ms
- **并发处理能力**：> 500 req/s
- **测试成功率**：80%+

### 交互式多轮对话测试

#### 🚀 快速开始
```bash
# 启动ChatAI服务
uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# 启动交互式对话测试（新终端窗口）
python interactive_chat.py
```

#### 📖 基本使用
```bash
# 指定API地址和语言
python interactive_chat.py --api http://127.0.0.1:8000 --lang zh --status 1

# 查看所有参数选项
python interactive_chat.py --help
```

#### 🎮 内置命令

**基本命令：**
```bash
help                    # 显示帮助信息
quit / exit            # 退出程序
clear                  # 清空对话历史
status                 # 显示当前会话状态
save                   # 保存对话记录到文件
```

**设置命令：**
```bash
/lang <zh|en|ja|th|tl>  # 切换语言 (中文|英语|日语|泰语|他加禄语)
/login                  # 切换到已登录状态
/logout                 # 切换到未登录状态
/platform <web|mobile>  # 切换平台类型
/user <user_id>         # 设置用户ID
```

**测试场景命令：**
```bash
/charge                 # 开始充值查询场景 (S001)
/withdraw               # 开始提现查询场景 (S002)  
/activity               # 开始活动查询场景 (S003)
/image <url>            # 发送图片链接测试图片处理
/order <18位数字>        # 发送订单号测试订单识别
```

**快速测试命令：**
```bash
/test_charge_18         # 测试18位充值订单号识别
/test_withdraw_19       # 测试19位数字拒绝（提现场景）
/test_image_upload      # 测试图片上传转人工
/test_multilang         # 测试多语言支持
```

#### 💬 对话示例

**充值查询流程：**
```
💬 请输入消息: 我的充值还没有到账
🤖 AI: 您需要查询的【订单编号】是多少？
🎯 识别意图: S001
📋 当前阶段: working (进行中)

💬 请输入消息: 我不知道订单号
🤖 AI: 按照下面图片的指引进行操作
📷 返回图片: https://img.lodirnd.com/lodi/depositOrder.webp

💬 请输入消息: 123456789012345678
🤖 AI: 充值成功，请等待。
📋 当前阶段: finish (已完成)
```

**提现查询流程：**
```
💬 请输入消息: /withdraw
🤖 AI: 您需要查询的【订单编号】是多少？

💬 请输入消息: 987654321098765432
🤖 AI: 您的提现正在处理中，请耐心等待。
```

**图片上传测试：**
```
💬 请输入消息: /test_image_upload
🧪 测试图片上传转人工...

💬 请输入消息: 我的充值还没有到账
🤖 AI: 您需要查询的【订单编号】是多少？

💬 请输入消息: 这是我的充值截图
📷 图片: https://example.com/payment-screenshot.jpg
🤖 AI (转人工): 您上传了图片，已为您转接人工客服。
🔄 已转接人工客服
```

**多语言测试：**
```
💬 请输入消息: /lang en
✅ 语言已切换到: en

💬 请输入消息: I need deposit help
🤖 AI: You are making a deposit. Please follow the instructions.
🎯 识别意图: S001
```

#### 🎯 测试场景覆盖

**核心业务流程：**
- ✅ S001充值查询：4个阶段完整测试
- ✅ S002提现查询：11种状态处理
- ✅ S003活动查询：活动识别与状态查询
- ✅ 人工客服转接：图片上传、异常状态

**智能识别测试：**
- ✅ 意图自动识别：中英文关键词识别
- ✅ 订单号精确提取：18位数字识别，拒绝19位
- ✅ 阶段智能跟踪：多轮对话状态维护
- ✅ 图片优先检测：任意阶段图片转人工

**多语言支持：**
- ✅ 中文(zh)：我的充值还没有到账
- ✅ 英文(en)：I need deposit help
- ✅ 日文(ja)：入金について教えてください
- ✅ 泰文(th)：ฉันต้องการความช่วยเหลือเรื่องการเติมเงิน

#### 📊 会话记录管理

**自动保存：**
- 对话记录自动保存为JSON格式
- 包含完整的会话信息和元数据
- 支持手动保存：输入 `save` 命令

**记录格式：**
```json
{
  "session_info": {
    "session_id": "interactive_1749502827_a1b2c3d4",
    "user_id": "test_user_e5f6g7h8",
    "language": "zh",
    "status": 1,
    "platform": "web",
    "total_rounds": 5
  },
  "conversation": [
    {
      "timestamp": "2025-06-10T15:30:45",
      "user_message": "我的充值还没有到账",
      "ai_response": "您需要查询的【订单编号】是多少？",
      "intent": "S001",
      "stage": "working",
      "transfer_human": 0
    }
  ]
}
```

## 📊 监控与运维

### 📋 日志系统

ChatAI 集成了强大的本地日志保存功能，为开发调试和生产监控提供全面的日志支持。

#### 🚀 日志功能特性

1. **多级别日志分离** - 支持按日志级别分别保存
2. **文件自动轮转** - 当日志文件达到指定大小时自动切分
3. **JSON格式输出** - 结构化的日志格式，便于分析和处理
4. **自动清理** - 自动删除过期的日志文件
5. **API调用追踪** - 专门的API调用日志，便于调试
6. **访问日志记录** - 记录所有API请求的详细信息

#### 📁 日志文件类型

日志系统会在 `logs/` 目录下创建以下类型的日志文件：

- **`chatai_all.log`** - 完整的应用日志，包含所有级别的日志
- **`chatai_error.log`** - 仅包含ERROR及以上级别的日志
- **`chatai_access.log`** - API访问和请求日志
- **`chatai_api.log`** - 外部API调用日志，用于调试和监控

#### 🔄 日志轮转机制

当日志文件大小超过10MB时，系统会自动创建新的日志文件，旧文件会被重命名为：
- `chatai_all.log.1`
- `chatai_all.log.2`
- 等等...

最多保留10个备份文件，超过30天的日志会被自动清理。

#### ⚙️ 日志配置

**主配置文件** (`config/logging_config.json`)：
```json
{
    "log_dir": "logs",                    // 日志目录
    "level": "INFO",                      // 默认日志级别
    "console_output": true,               // 是否在控制台输出
    "file_output": true,                  // 是否输出到文件
    "json_format": true,                  // 是否使用JSON格式
    "max_file_size": "10MB",             // 最大文件大小
    "backup_count": 10,                   // 备份文件数量
    "retention_days": 30,                 // 日志保留天数
    "separate_error_log": true            // 是否分离错误日志
}
```

**业务配置** (`config/business_config.json`)：
```json
{
    "logging": {
        "enabled": true,                  // 是否启用日志
        "config_file": "config/logging_config.json",
        "log_level": "INFO",
        "log_api_calls": true,            // 是否记录API调用
        "log_user_messages": false,       // 是否记录用户消息
        "log_sensitive_data": false,      // 是否记录敏感数据
        "performance_monitoring": true    // 是否启用性能监控
    }
}
```

#### 🛠️ 日志管理工具

项目提供了 `manage_logs.py` 脚本来管理日志文件：

```bash
# 查看帮助
python manage_logs.py --help

# 列出所有日志文件
python manage_logs.py list

# 显示日志统计信息
python manage_logs.py stats

# 清理30天前的日志文件（预览模式）
python manage_logs.py cleanup --days 30 --dry-run

# 实际清理30天前的日志文件
python manage_logs.py cleanup --days 30

# 查看最后50行全量日志
python manage_logs.py tail --type all --lines 50

# 查看最后100行错误日志
python manage_logs.py tail --type error --lines 100
```

**命令说明：**
- **`list`** - 列出所有日志文件及其大小、修改时间
- **`stats`** - 显示详细的日志统计信息，包括文件数量、总大小、按类型分组等
- **`cleanup`** - 清理过期的日志文件
- **`tail`** - 查看日志文件的尾部内容

#### 📊 日志格式说明

**JSON格式日志**（文件保存）：
```json
{
    "timestamp": "2024-01-01T12:00:00.000000",
    "level": "INFO",
    "logger": "chatai-api",
    "message": "处理会话 session123 的消息",
    "module": "process",
    "function": "process_message",
    "line": 54,
    "thread_id": 12345,
    "process_id": 6789,
    "session_id": "session123",
    "user_id": "user456"
}
```

**控制台格式日志**：
```
2024-01-01 12:00:00,000 - chatai-api - INFO - 处理会话 session123 的消息
```

#### 🔍 日志分析

可以使用以下工具分析JSON格式的日志：

```bash
# 统计错误数量
grep '"level": "ERROR"' logs/chatai_all.log | wc -l

# 查找特定会话的日志
grep '"session_id": "session123"' logs/chatai_all.log

# 使用jq工具分析JSON日志
cat logs/chatai_all.log | jq '.timestamp, .message'
```

#### ⚡ 性能监控

日志系统集成了性能监控功能：

1. **请求处理时间** - 记录每个API请求的处理时间
2. **API调用统计** - 统计外部API调用的频率和响应时间
3. **内存使用情况** - 监控应用的内存使用
4. **错误率统计** - 自动统计错误发生率

#### 🔧 测试日志功能

可以使用测试脚本验证日志功能：

```bash
# 运行日志功能测试
python test_logging.py
```

该脚本会测试各种日志级别、请求记录、API调用记录等功能，并检查日志文件是否正确创建。

#### 🛡️ 最佳实践

**生产环境建议：**
1. **日志级别设置为INFO** - 平衡详细程度和性能
2. **启用日志轮转** - 防止单个日志文件过大
3. **定期清理日志** - 设置合适的保留天数
4. **监控日志大小** - 定期检查日志目录的磁盘使用

**开发环境建议：**
1. **日志级别设置为DEBUG** - 获取更详细的调试信息
2. **关闭JSON格式** - 提高可读性
3. **启用API调用日志** - 便于调试外部API问题

**安全注意事项：**
1. **不要记录敏感信息** - 如密码、令牌等
2. **定期备份重要日志** - 用于审计和问题追踪
3. **限制日志文件访问权限** - 确保只有授权人员可以访问

### 配置管理
- **热重载**：支持运行时配置更新
- **环境隔离**：开发/测试/生产环境配置分离
- **版本控制**：配置文件版本化管理

### 健康检查
```bash
curl http://localhost:8000/health
```

## 🔧 开发指南

### 添加新业务类型
1. 在`business_config.json`中添加新的业务类型
2. 在`process.py`中添加对应的处理逻辑
3. 编写相应的测试用例
4. 更新文档

### 扩展语言支持
1. 在配置文件中添加新语言的关键词和响应
2. 在`get_message_by_language`函数中支持新语言
3. 添加相应的测试用例

### 自定义AI模型
1. 修改`util.py`中的`call_openapi_model`函数
2. 调整模型参数和API地址
3. 测试模型响应质量

## ⚠️ 注意事项

### 安全考虑
- **API密钥管理**：使用环境变量存储敏感信息
- **输入验证**：严格验证所有用户输入
- **权限控制**：实现适当的访问控制机制

### 性能优化
- **连接池**：使用httpx的连接池优化外部API调用
- **缓存策略**：对配置文件和常用数据进行缓存
- **异步处理**：充分利用asyncio提升并发能力

### 维护建议
- **定期更新**：保持依赖库和AI模型的最新版本
- **监控告警**：设置适当的监控和告警机制
- **备份策略**：重要配置和数据的定期备份

## 📞 技术支持

如有技术问题或功能建议，请通过以下方式联系：
- 提交Issue到项目仓库
- 发送邮件到技术支持团队
- 查看项目Wiki获取更多信息

---

**版本**：v1.0.0  
**更新时间**：2025-06-10  
**维护团队**：ChatAI开发组

## 🤝 贡献指南

1. Fork 项目仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

## 📝 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 支持与联系

如果您遇到问题或有任何建议，请：

- 📋 提交 [Issue](../../issues)
- 💬 发起 [Discussion](../../discussions)
- 📧 发送邮件至项目维护者

## 🔐 Token认证机制

ChatAI系统实现了基于HMAC-SHA256的token认证机制，确保已登录用户的请求安全性。

### 快速使用

#### 1. 生成Token
```bash
# 为用户生成token
python generate_token.py user123

# 输出示例：
# Token: user123.1749634097.25b6fbdac6de3b5fd5157591196740340fd470cfed59495a8412155ae0bfba5a
```

#### 2. 验证Token  
```bash
# 验证token有效性
python generate_token.py user123 verify user123.1749634097.25b6fbdac6de3b5fd5157591196740340fd470cfed59495a8412155ae0bfba5a
```

#### 3. API调用示例
```json
{
  "session_id": "session123",
  "user_id": "user123", 
  "platform": "web",
  "language": "zh",
  "status": 1,
  "messages": "我想查询充值状态",
  "token": "user123.1749634097.25b6fbdac6de3b5fd5157591196740340fd470cfed59495a8412155ae0bfba5a"
}
```

### 认证规则

- **未登录用户** (`status=0`)：无需提供token
- **已登录用户** (`status=1`)：必须提供有效token，否则请求会被拒绝
- **Token有效期**：默认1小时，可在配置文件中调整
- **安全机制**：使用HMAC-SHA256签名，防止伪造和篡改

### 错误处理

常见认证错误：
```json
{
  "error": "Token验证失败: Token已过期"
}
```

### 详细文档

完整的token认证机制说明请参考：[TOKEN_AUTH_README.md](TOKEN_AUTH_README.md)

---

**开始使用 ChatAI，构建您的智能对话应用！** 🚀