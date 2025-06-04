# 🤖 ChatAI - 智能对话API服务

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.95.2-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 一个基于FastAPI构建的高性能智能对话API服务，支持多语言意图识别、会话管理和智能回复生成。

## ✨ 核心特性

- 🎯 **智能意图识别** - 准确识别用户意图，支持多种业务场景
- 🌍 **多语言支持** - 支持中文、英文、泰文、菲律宾语等多种语言
- 💾 **会话状态管理** - 智能管理对话上下文和历史记录
- 🖼️ **多媒体处理** - 支持图片等多媒体内容处理
- ⚡ **高性能异步** - 基于FastAPI的异步处理架构
- 🔧 **热重载配置** - 支持运行时配置更新，无需重启服务
- 📊 **完整测试覆盖** - 包含功能测试和性能测试的完整测试套件
- 🔄 **工作流引擎** - 灵活的业务流程定义和执行

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip 包管理器

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
   python app.py
   ```

4. **验证服务**
   
   访问 http://127.0.0.1:8000/health 检查服务状态
   
   或访问 http://127.0.0.1:8000/docs 查看API文档

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
  "timestamp": 1704067200.123
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
    "timestamp": 1704067200.123
  },
  "images": null,
  "site": 1,
  "type": "S001",
  "transfer_human": 0
}
```

## 🧪 测试

### 交互式测试运行器

推荐使用交互式测试运行器：

```bash
python run_tests.py
```

### 功能测试

测试所有API接口和业务逻辑：

```bash
python test_api.py
```

**测试覆盖：**
- ✅ 健康检查接口
- ✅ 配置重载接口  
- ✅ 消息处理核心功能
- ✅ 错误处理和边界情况
- ✅ 参数验证

### 性能测试

评估系统性能指标：

```bash
python test_performance.py
```

**性能指标：**
- 🏃‍♂️ 响应时间 (平均/最大/最小)
- 🚀 并发处理能力
- ⏱️ 系统稳定性
- 📊 请求吞吐量

**测试结果文件：**
- `test_results.json` - 功能测试详细报告
- `performance_test_results.json` - 性能测试报告

## 📁 项目结构

```
ChatAI/
├── 📄 app.py                       # FastAPI主应用入口
├── 📄 requirements.txt             # 项目依赖列表
├── 📄 run_tests.py                 # 交互式测试运行器
├── 📄 test_api.py                  # API功能测试套件
├── 📄 test_performance.py          # 性能测试套件
├── 📄 .gitignore                   # Git忽略文件配置
├── 📁 src/                         # 核心源代码目录
│   ├── 📄 __init__.py             # 包初始化文件
│   ├── 📄 config.py               # 配置管理模块
│   ├── 📄 process.py              # 消息处理核心逻辑
│   ├── 📄 workflow_check.py       # 工作流检查和执行
│   ├── 📄 reply.py                # 智能回复生成
│   ├── 📄 util.py                 # 通用工具函数和数据模型
│   ├── 📄 telegram.py             # Telegram平台集成
│   └── 📄 request_internal.py     # 内部请求处理
├── 📁 config/                      # 配置文件目录
│   └── 📄 business_config.json    # 业务配置文件
├── 📁 .github/                     # GitHub工作流配置
└── 📄 README.md                    # 项目文档 (本文件)
```

## ⚙️ 配置管理

### 业务配置

业务配置位于 `config/business_config.json`，包含：

- **业务类型定义** - 不同业务场景的配置
- **多语言关键词** - 各语言的意图识别关键词
- **工作流程配置** - 业务流程的定义和规则
- **API密钥配置** - 外部服务的认证信息

### 配置热重载

系统支持运行时配置更新：

```bash
curl -X POST http://127.0.0.1:8000/reload_config
```

## 🔧 开发指南

### 添加新业务类型

1. **定义业务配置**
   ```json
   // config/business_config.json
   {
     "business_types": {
       "NEW_TYPE": {
         "name": "新业务类型",
         "keywords": {
           "zh": ["关键词1", "关键词2"],
           "en": ["keyword1", "keyword2"]
         }
       }
     }
   }
   ```

2. **实现处理逻辑**
   ```python
   # src/workflow_check.py
   async def handle_new_type(request):
       # 实现业务逻辑
       return response
   ```

3. **运行测试**
   ```bash
   python test_api.py
   ```

### 调试和日志

应用提供详细的日志输出：

- 📊 **配置加载状态** - 启动时显示配置加载情况
- 🔍 **请求处理过程** - 详细的请求处理日志  
- ❌ **错误信息** - 完整的错误堆栈信息
- ⏱️ **性能指标** - 请求处理时间等性能数据

## 🛠️ 技术栈

- **Web框架**: FastAPI - 高性能异步Web框架
- **数据验证**: Pydantic - 数据验证和序列化
- **ASGI服务器**: Uvicorn - 高性能ASGI服务器
- **配置管理**: python-dotenv - 环境变量管理
- **文件处理**: aiofiles - 异步文件操作
- **数据库**: asyncpg - PostgreSQL异步驱动
- **日志**: loguru - 强大的日志处理

## 📈 性能优化

- **异步处理** - 全异步架构，支持高并发
- **连接池** - 数据库连接池优化
- **缓存策略** - 配置缓存和会话缓存
- **请求优化** - 请求参数验证和响应压缩

## 🔒 安全考虑

- **CORS配置** - 跨域请求安全控制
- **参数验证** - 严格的输入参数验证
- **错误处理** - 安全的错误信息返回
- **API限流** - 可配置的请求频率限制

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

---

**开始使用 ChatAI，构建您的智能对话应用！** 🚀