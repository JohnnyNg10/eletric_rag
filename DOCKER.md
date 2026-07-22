# Electric RAG System - Docker 部署指南

## 快速启动

### 1. 环境准备

确保已安装：
- Docker 20.10+
- Docker Compose 2.0+
- 至少 8GB 可用内存
- 至少 20GB 可用磁盘空间

### 2. 配置环境变量

复制并编辑环境变量文件：

```bash
cp .env.docker .env
```

**必须修改的配置：**

```bash
# LLM API Key（必填，否则生成功能不可用）
ARK_API_KEY=your_volcengine_api_key_here
```

其他配置使用默认值即可。

### 3. 启动所有服务

```bash
# 后台启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend
docker-compose logs -f celery-worker
docker-compose logs -f mineru
```

### 4. 访问服务

- **前端 UI**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **MinIO 控制台**: http://localhost:9001 (minioadmin / minioadmin)
- **Qdrant 控制台**: http://localhost:6333/dashboard

### 5. 健康检查

```bash
# 检查所有服务状态
docker-compose ps

# 测试后端健康
curl http://localhost:8000/health

# 测试 MinerU 健康
curl http://localhost:8001/health
```

## 服务说明

### 核心服务

| 服务 | 端口 | 说明 |
|------|------|------|
| frontend | 3000 | React 前端 |
| backend | 8000 | FastAPI 后端 |
| celery-worker | - | 异步任务处理 |
| mineru | 8001 | PDF 解析服务 |

### 基础设施

| 服务 | 端口 | 说明 |
|------|------|------|
| mysql | 3306 | 数据库 |
| redis | 6379 | 缓存 + 消息队列 |
| qdrant | 6333 | 向量数据库 |
| elasticsearch | 9200 | 全文检索 |
| minio | 9000, 9001 | 对象存储 |

## 首次使用

### 1. 等待模型下载

首次启动时，backend 会自动下载约 3.3GB 的 AI 模型：
- bge-large-zh-v1.5 (Embedding)
- bge-reranker-large (Rerank)
- efficient-splade (稀疏向量)

可通过日志查看进度：

```bash
docker-compose logs -f backend | grep -i "model"
```

### 2. 数据库初始化

Backend 启动时会自动：
- 创建所有表
- 插入默认管理员账号：`admin` / `admin123`
- 初始化术语词典

### 3. 登录系统

访问 http://localhost:3000，使用默认账号登录。

## 常见操作

### 停止服务

```bash
# 停止所有服务
docker-compose stop

# 停止特定服务
docker-compose stop backend celery-worker
```

### 重启服务

```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart backend
```

### 查看资源占用

```bash
docker stats
```

### 清理数据（危险操作）

```bash
# 停止并删除所有容器、网络
docker-compose down

# 同时删除所有数据卷（会丢失数据库、向量库等所有数据）
docker-compose down -v
```

### 更新镜像

```bash
# 重新构建镜像
docker-compose build

# 强制重新构建（不使用缓存）
docker-compose build --no-cache

# 重新构建特定服务
docker-compose build backend
```

## 生产环境配置

### 1. 修改默认密码

编辑 `.env` 文件，修改：

```bash
MYSQL_PASSWORD=strong_password_here
MINIO_ACCESS_KEY=custom_access_key
MINIO_SECRET_KEY=custom_secret_key
```

修改后需要删除旧的数据卷：

```bash
docker-compose down -v
docker-compose up -d
```

### 2. 开启 HTTPS

在 `docker/nginx.conf` 中配置 SSL 证书，并在 `docker-compose.yml` 中映射证书文件。

### 3. 资源限制

在 `docker-compose.yml` 中为各服务添加资源限制：

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          memory: 2G
```

### 4. GPU 支持（MinerU hybrid-engine 模式）

取消 `docker-compose.yml` 中 mineru 服务的 GPU 配置注释：

```yaml
mineru:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

确保宿主机已安装 `nvidia-docker2`。

## 故障排查

### Backend 启动失败

```bash
# 查看日志
docker-compose logs backend

# 常见原因：
# 1. MySQL 未就绪 → 等待 30 秒后重启
# 2. 模型下载失败 → 检查网络，可能需要配置代理
# 3. 端口占用 → 修改 docker-compose.yml 中的端口映射
```

### Celery Worker 无法连接 Redis

```bash
# 检查 Redis 是否运行
docker-compose ps redis

# 检查 Celery 日志
docker-compose logs celery-worker
```

### MinerU 解析失败

```bash
# 查看 MinerU 日志
docker-compose logs mineru

# 重启 MinerU
docker-compose restart mineru
```

### 磁盘空间不足

```bash
# 查看 Docker 磁盘占用
docker system df

# 清理未使用的镜像、容器、网络
docker system prune -a

# 清理未使用的数据卷
docker volume prune
```

## 数据备份

### 备份数据库

```bash
docker exec electric-rag-mysql mysqldump -u root -p电力国标PDF electric_rag > backup.sql
```

### 备份向量库

```bash
docker cp electric-rag-qdrant:/qdrant/storage ./qdrant_backup
```

### 备份对象存储

```bash
docker cp electric-rag-minio:/data ./minio_backup
```

## 监控

推荐使用 Prometheus + Grafana 监控：
- Backend 提供 `/metrics` 端点（需添加 prometheus-fastapi-instrumentator）
- Qdrant 提供内置 metrics
- MySQL、Redis 可使用官方 exporter

## 技术支持

- GitHub Issues: https://github.com/your-repo/issues
- 文档: `docs/` 目录
- API 文档: http://localhost:8000/docs
