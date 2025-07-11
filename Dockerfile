# 使用官方Python运行时作为父镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 创建非root用户
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# 创建必要的目录
RUN mkdir -p /app/logs /app/config /app/src && \
    chown -R appuser:appgroup /app

# 复制项目文件
COPY --chown=appuser:appgroup ./src/ ./src/
COPY --chown=appuser:appgroup ./config/ ./config/
COPY --chown=appuser:appgroup ./app.py .

# 复制可选的启动脚本和工具
COPY --chown=appuser:appgroup ./generate_token.py* ./
COPY --chown=appuser:appgroup ./manage_logs.py* ./

# 切换到非root用户
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"] 