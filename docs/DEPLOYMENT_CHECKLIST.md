# AutoDL 部署检查清单

部署前请逐项核对以下清单，确保配置正确。

## ✅ 部署前检查

### 1. 硬件资源
- [ ] GPU: Tesla V100/T4/A100，至少 16GB 显存
- [ ] 内存: 32GB+
- [ ] 磁盘: 100GB+ 可用空间
- [ ] 网络: 稳定的互联网连接 (下载模型需要)

### 2. 软件环境
- [ ] Ubuntu 20.04/22.04
- [ ] CUDA 12.1+ (`nvcc --version`)
- [ ] Docker 20.10+ (`docker --version`)
- [ ] Docker Compose 2.0+ (`docker compose version`)
- [ ] nvidia-docker 运行时 (`docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi`)

### 3. 配置文件
- [ ] 已复制 `.env.autodl` 到项目根目录的 `.env`
- [ ] 已修改 `MYSQL_PASSWORD` (强密码)
- [ ] 已修改 `MINIO_SECRET_KEY` (建议修改)
- [ ] 已修改 `SECRET_KEY` (至少 32 字符随机字符串)
- [ ] 已填写 `ARK_API_KEY` (豆包 API 密钥)
- [ ] 如果启用 VLM，已填写 `DOUBAO_API_KEY` 和 `DOUBAO_MODEL`
- [ ] 已根据 GPU 显存调整 `RERANKER_BATCH_SIZE` (16GB 显存建议 16-32)

### 4. 网络配置
- [ ] 已在 AutoDL 控制台配置端口映射:
  - 8000 (Backend API)
  - 3000 (Frontend)
  - 8001 (MinerU，可选)
  - 6333 (Qdrant，可选)
  - 9000/9001 (MinIO，可选)

## ✅ 部署过程检查

### 5. 构建阶段
- [ ] `docker compose build` 成功完成
- [ ] 所有镜像构建无错误
- [ ] 网络下载稳定 (CUDA 基础镜像 ~5GB)

### 6. 启动阶段
- [ ] `docker compose up -d` 成功执行
- [ ] `docker compose ps` 显示所有服务 "Up" 或 "Up (healthy)"
- [ ] MySQL 健康检查通过 (`docker compose exec mysql mysqladmin ping`)
- [ ] Redis 健康检查通过 (`docker compose exec redis redis-cli ping`)
- [ ] Qdrant 健康检查通过 (`curl http://localhost:6333/`)
- [ ] Elasticsearch 健康检查通过 (`curl http://localhost:9200/`)
- [ ] MinIO 健康检查通过 (`curl http://localhost:9000/minio/health/live`)
- [ ] MinerU 健康检查通过 (`curl http://localhost:8001/health`)
- [ ] Backend 健康检查通过 (`curl http://localhost:8000/health`)

### 7. GPU 验证
- [ ] Backend 容器可以访问 GPU (`docker compose exec backend nvidia-smi`)
- [ ] MinerU 容器可以访问 GPU (`docker compose exec mineru nvidia-smi`)
- [ ] Celery Worker 容器可以访问 GPU (`docker compose exec celery-worker nvidia-smi`)
- [ ] GPU 显存未溢出 (`nvidia-smi` 显示显存使用合理)

### 8. 模型下载
- [ ] BGE Embedding 模型已下载 (`ls backend/models/BAAI/bge-large-zh-v1.5/`)
- [ ] Reranker 模型已下载 (`ls backend/models/BAAI/bge-reranker-large/`)
- [ ] 首次查询可以成功触发模型加载
- [ ] 后续查询速度正常 (模型已加载到 GPU)

### 9. 功能测试
- [ ] 登录接口正常 (`curl -X POST http://localhost:8000/api/v1/auth/login ...`)
- [ ] 查询接口正常 (`curl -X POST http://localhost:8000/api/v1/query ...`)
- [ ] 文档上传功能正常 (通过 Frontend 或 API)
- [ ] Celery 任务执行正常 (`docker compose logs -f celery-worker`)
- [ ] MinerU PDF 解析正常 (`curl -X POST http://localhost:8001/parse/pdf ...`)

### 10. 外网访问
- [ ] Frontend 可通过 AutoDL 外网地址访问 (`https://<实例ID>-3000.sh.autodl.com`)
- [ ] Backend API 可通过外网地址访问 (`https://<实例ID>-8000.sh.autodl.com`)
- [ ] 前端可以正常调用后端 API
- [ ] 跨域 (CORS) 配置正确

## ✅ 部署后检查

### 11. 性能验证
- [ ] 查询响应时间 < 5s (包含 rerank)
- [ ] GPU 利用率合理 (推理时 30-80%)
- [ ] 显存使用在安全范围内 (< 14GB / 16GB)
- [ ] CPU 使用率正常
- [ ] 内存使用率正常

### 12. 日志检查
- [ ] Backend 日志无严重错误 (`docker compose logs backend | grep ERROR`)
- [ ] Celery 日志无任务失败 (`docker compose logs celery-worker | grep ERROR`)
- [ ] MySQL/Redis/Qdrant 日志正常
- [ ] 无频繁的连接失败或超时

### 13. 数据持久化
- [ ] MySQL 数据持久化正常 (重启后数据不丢失)
- [ ] Qdrant 向量数据持久化正常
- [ ] MinIO 对象存储正常
- [ ] Redis 数据持久化正常 (AOF 已启用)

### 14. 安全检查
- [ ] 已修改所有默认密码
- [ ] API 密钥未泄露到日志或代码中
- [ ] 防火墙配置正确 (仅开放必要端口)
- [ ] HTTPS 证书配置 (生产环境)

### 15. 备份计划
- [ ] 已规划 MySQL 定期备份策略
- [ ] 已规划 Qdrant 向量库备份策略
- [ ] 已规划 MinIO 对象存储备份策略
- [ ] 已测试备份恢复流程

## ✅ 监控和运维

### 16. 监控配置
- [ ] 已设置 GPU 使用监控 (`watch -n 1 nvidia-smi`)
- [ ] 已设置容器资源监控 (`docker stats`)
- [ ] 已设置日志收集 (可选)
- [ ] 已设置告警通知 (可选)

### 17. 运维文档
- [ ] 已保存所有配置文件备份
- [ ] 已记录外网访问地址
- [ ] 已记录管理员账号信息
- [ ] 已记录常用运维命令

## 🚨 常见问题快速排查

| 问题 | 检查命令 | 解决方案 |
|------|---------|---------|
| 容器无法使用 GPU | `docker compose exec backend nvidia-smi` | 安装 nvidia-container-toolkit |
| 模型下载失败 | `docker compose logs backend \| grep download` | 配置 HuggingFace 镜像或手动下载 |
| 显存溢出 | `nvidia-smi` | 降低 RERANKER_BATCH_SIZE 或使用 base 模型 |
| MySQL 连接失败 | `docker compose logs mysql` | 等待启动完成或检查密码 |
| Celery 无任务 | `docker compose logs celery-worker` | 检查 Redis 连接和任务队列 |
| API 502 错误 | `docker compose ps` | 检查 backend 容器状态 |

## 📋 完成标记

- [ ] **所有检查项均已通过**
- [ ] **系统运行稳定，无错误日志**
- [ ] **已完成首次功能测试**
- [ ] **已交付外网访问地址给用户**

---

**部署负责人**: _____________  
**部署日期**: _____________  
**实例 ID**: _____________  
**外网地址**: _____________  
