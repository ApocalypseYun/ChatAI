# ChatAI Docker 部署指南

本文档介绍如何使用Docker容器化部署ChatAI应用。

## 文件说明

- `Dockerfile` - Docker镜像构建文件
- `docker-compose.yml` - Docker Compose编排文件
- `.dockerignore` - Docker构建忽略文件

## 快速开始

### 使用 Docker Compose（推荐）

1. **构建并启动服务**
   ```bash
   # 构建镜像并启动容器
   docker-compose up -d --build
   ```

2. **查看服务状态**
   ```bash
   # 查看运行状态
   docker-compose ps
   
   # 查看日志
   docker-compose logs -f chatai
   ```

3. **测试服务**
   ```bash
   # 健康检查
   curl http://localhost:8000/health
   ```

4. **停止服务**
   ```bash
   docker-compose down
   ```

### 使用 Docker 命令

1. **构建镜像**
   ```bash
   docker build -t chatai:latest .
   ```

2. **运行容器**
   ```bash
   docker run -d \
     --name chatai-service \
     -p 8000:8000 \
     -v $(pwd)/logs:/app/logs \
     --restart unless-stopped \
     chatai:latest
   ```

3. **查看容器状态**
   ```bash
   # 查看运行状态
   docker ps
   
   # 查看日志
   docker logs -f chatai-service
   ```

## 配置说明

### 环境变量

可以通过环境变量自定义配置：

```yaml
environment:
  - PYTHONPATH=/app
  - PYTHONUNBUFFERED=1
  # 可添加更多自定义环境变量
```

### 卷挂载

#### 日志目录
```yaml
volumes:
  - ./logs:/app/logs
```
将容器内的日志目录挂载到主机，便于查看和备份日志。

#### 配置目录（可选）
```yaml
volumes:
  - ./config:/app/config:ro
```
如需在运行时修改配置，可挂载配置目录（建议只读模式）。

### 端口映射

- 容器内端口：8000
- 主机端口：8000（可自定义）

修改主机端口：
```yaml
ports:
  - "9000:8000"  # 将服务映射到主机的9000端口
```

## 生产环境部署

### 1. 性能优化

在生产环境中，建议修改启动命令以支持多进程：

```dockerfile
# 在Dockerfile中修改CMD
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

或在docker-compose.yml中覆盖：
```yaml
command: ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 2. 添加反向代理

取消注释docker-compose.yml中的nginx配置，并创建nginx.conf：

```nginx
events {
    worker_connections 1024;
}

http {
    upstream chatai {
        server chatai:8000;
    }

    server {
        listen 80;
        server_name your-domain.com;

        location / {
            proxy_pass http://chatai;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

### 3. 资源限制

在docker-compose.yml中添加资源限制：

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
    reservations:
      cpus: '0.5'
      memory: 512M
```

## 监控和维护

### 健康检查

服务包含内置健康检查：
- 检查间隔：30秒
- 超时时间：10秒
- 重试次数：3次

### 日志管理

日志文件位置：
- 容器内：`/app/logs/`
- 主机上：`./logs/`

建议定期清理或轮转日志文件。

### 备份和恢复

重要文件备份：
```bash
# 备份配置文件
tar -czf config-backup.tar.gz config/

# 备份日志文件
tar -czf logs-backup.tar.gz logs/
```

## 故障排除

### 常见问题

1. **端口被占用**
   ```bash
   # 检查端口占用
   lsof -i :8000
   
   # 修改docker-compose.yml中的端口映射
   ```

2. **权限问题**
   ```bash
   # 确保日志目录有正确权限
   sudo chown -R 1000:1000 logs/
   ```

3. **配置文件错误**
   ```bash
   # 检查配置文件语法
   python -m json.tool config/business_config.json
   ```

### 查看详细日志

```bash
# 查看容器启动日志
docker-compose logs chatai

# 查看应用日志
tail -f logs/chatai.log

# 进入容器调试
docker-compose exec chatai bash
```

## 升级部署

1. **拉取最新代码**
   ```bash
   git pull origin main
   ```

2. **重新构建和部署**
   ```bash
   docker-compose down
   docker-compose up -d --build
   ```

3. **验证升级**
   ```bash
   curl http://localhost:8000/health
   ```

## 安全建议

1. **使用非root用户**（已在Dockerfile中配置）
2. **限制网络访问**
3. **定期更新基础镜像**
4. **使用HTTPS**（通过nginx配置）
5. **设置防火墙规则**

## 扩展部署

对于高可用部署，可以：
1. 使用多个容器实例
2. 配置负载均衡器
3. 使用外部数据库
4. 配置分布式日志收集 