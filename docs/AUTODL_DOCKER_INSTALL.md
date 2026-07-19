# 在 AutoDL 上安装 Docker 并部署

AutoDL 实例默认**没有安装 Docker**，但安装非常简单。本文档说明如何在 AutoDL 上安装 Docker + nvidia-docker，然后使用 Docker Compose 一键部署整个系统。

---

## 🚀 快速部署流程

```
租用 AutoDL 实例 → 安装 Docker (5分钟) → 安装 nvidia-docker (2分钟) → docker compose up -d ✅
```

---

## 📋 第一步：租用 AutoDL 实例

1. 访问 [AutoDL](https://www.autodl.com/)
2. 选择配置:
   - **GPU**: Tesla V100 16GB 或更高
   - **镜像**: 任意镜像都可以（我们会安装 Docker）
   - **数据盘**: 100GB+
3. 开机并连接

```bash
ssh -p <端口> root@<IP地址>
```

---

## 📦 第二步：安装 Docker

### 方法 1: 官方一键安装脚本（推荐）

```bash
# 下载并执行 Docker 官方安装脚本
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# 启动 Docker
systemctl start docker
systemctl enable docker

# 验证安装
docker --version
docker run hello-world
```

### 方法 2: 使用国内镜像加速安装

```bash
# 使用阿里云镜像
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun

# 启动 Docker
systemctl start docker
systemctl enable docker

# 验证
docker --version
```

### 安装 Docker Compose

```bash
# 下载 Docker Compose v2
curl -SL https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-linux-x86_64 \
  -o /usr/local/bin/docker-compose

# 添加执行权限
chmod +x /usr/local/bin/docker-compose

# 验证
docker compose version
```

---

## 🎮 第三步：安装 nvidia-docker（GPU 支持）

这是最关键的一步，让 Docker 容器可以使用 GPU！

```bash
# 1. 设置 nvidia-docker 仓库
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  tee /etc/apt/sources.list.d/nvidia-docker.list

# 2. 安装 nvidia-container-toolkit
apt-get update
apt-get install -y nvidia-container-toolkit

# 3. 重启 Docker
systemctl restart docker

# 4. 验证 GPU 支持（最重要！）
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

**如果上面的命令能显示 GPU 信息，说明 GPU Docker 环境配置成功！✅**

---

## 🏗️ 第四步：克隆项目并部署

```bash
# 1. 克隆项目
cd /root
git clone <your-repo-url> electric-rag
cd electric-rag

# 2. 配置环境变量
cp .env.autodl .env
vim .env
```

**必须修改的配置**:
```bash
MYSQL_PASSWORD=your_strong_password_2024       # MySQL 密码
ARK_API_KEY=your_doubao_api_key_here          # 豆包 API Key
SECRET_KEY=your_random_32_chars_secret_key    # 安全密钥
```

```bash
# 3. 构建 Docker 镜像（首次约 20 分钟）
docker compose build

# 4. 启动所有服务
docker compose up -d

# 5. 查看日志
docker compose logs -f
```

### 等待服务启动

首次启动约需 **5-10 分钟**，因为要下载 AI 模型 (~3.3GB)。

检查状态：
```bash
docker compose ps
```

应该看到 9 个容器都是 `Up` 或 `Up (healthy)` 状态。

---

## ✅ 第五步：验证部署

### 1. 检查所有容器

```bash
docker compose ps
```

预期输出：
```
NAME                          STATUS
electric-rag-backend          Up (healthy)
electric-rag-celery           Up
electric-rag-elasticsearch    Up (healthy)
electric-rag-frontend         Up
electric-rag-mineru           Up (healthy)
electric-rag-minio            Up (healthy)
electric-rag-mysql            Up (healthy)
electric-rag-qdrant           Up (healthy)
electric-rag-redis            Up (healthy)
```

### 2. 验证 GPU 使用

```bash
# Backend 容器使用 GPU
docker compose exec backend nvidia-smi

# MinerU 容器使用 GPU
docker compose exec mineru nvidia-smi

# Celery Worker 容器使用 GPU
docker compose exec celery-worker nvidia-smi
```

### 3. 测试 API

```bash
# 健康检查
curl http://localhost:8000/health

# 登录测试
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### 4. 配置 AutoDL 端口映射

在 AutoDL 控制台添加以下端口映射：

| 容器端口 | 服务名称 |
|---------|---------|
| 8000 | Backend API |
| 3000 | Frontend |
| 8001 | MinerU API |

保存后即可通过外网访问：
- Frontend: `https://<实例ID>-3000.sh.autodl.com`
- Backend: `https://<实例ID>-8000.sh.autodl.com/docs`

---

## 🎯 完整安装脚本（一键执行）

如果你想快速安装，可以使用这个一键脚本：

```bash
#!/bin/bash
set -e

echo "===== 安装 Docker ====="
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
systemctl start docker
systemctl enable docker
docker --version

echo "===== 安装 Docker Compose ====="
curl -SL https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-linux-x86_64 \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
docker compose version

echo "===== 安装 nvidia-docker ====="
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  tee /etc/apt/sources.list.d/nvidia-docker.list
apt-get update
apt-get install -y nvidia-container-toolkit
systemctl restart docker

echo "===== 验证 GPU Docker ====="
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

echo "===== Docker 安装完成 ====="
echo "现在可以运行: docker compose up -d"
```

保存为 `install_docker.sh`，然后执行：

```bash
chmod +x install_docker.sh
./install_docker.sh
```

---

## 🔧 常用 Docker 命令

### 查看日志

```bash
docker compose logs -f                    # 所有服务
docker compose logs -f backend            # 单个服务
docker compose logs --tail=100 backend    # 最近 100 行
```

### 重启服务

```bash
docker compose restart                    # 重启所有
docker compose restart backend            # 重启单个
```

### 停止/启动

```bash
docker compose down                       # 停止所有（保留数据）
docker compose up -d                      # 启动所有
docker compose stop backend               # 停止单个
docker compose start backend              # 启动单个
```

### 进入容器

```bash
docker compose exec backend bash          # 进入 Backend 容器
docker compose exec mysql bash            # 进入 MySQL 容器
```

### 查看资源使用

```bash
docker stats                              # 实时监控容器资源
```

### 更新代码

```bash
git pull origin main
docker compose down
docker compose build
docker compose up -d
```

---

## 🐛 常见问题

### 1. Docker 安装失败

```bash
# 检查系统版本
cat /etc/os-release

# 如果是 Ubuntu 20.04/22.04，手动安装
apt-get update
apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io
```

### 2. nvidia-docker 验证失败

```bash
# 检查 CUDA 是否安装
nvidia-smi

# 如果 nvidia-smi 可用，重新配置 nvidia-docker
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

# 重新测试
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### 3. 容器无法启动

```bash
# 查看详细错误
docker compose logs backend

# 检查端口占用
netstat -tulpn | grep :8000

# 强制重建
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

### 4. 磁盘空间不足

```bash
# 清理未使用的镜像和容器
docker system prune -a

# 查看磁盘使用
df -h
docker system df
```

### 5. 模型下载慢

```bash
# 进入容器设置镜像
docker compose exec backend bash
export HF_ENDPOINT=https://hf-mirror.com

# 或在 .env 中添加
echo "HF_ENDPOINT=https://hf-mirror.com" >> .env
docker compose restart backend
```

---

## 📊 性能对比

| 部署方式 | 安装时间 | 维护难度 | 隔离性 | 推荐度 |
|---------|---------|---------|--------|--------|
| Docker | 30 分钟 | 低 | 高 | ⭐⭐⭐⭐⭐ |
| 原生部署 | 2 小时+ | 高 | 低 | ⭐⭐ |

**Docker 的优势**:
- ✅ 所有依赖自动安装（MySQL、Redis、Qdrant 等）
- ✅ 一键启动/停止
- ✅ 数据持久化，容器删除数据不丢
- ✅ 环境隔离，不污染宿主机
- ✅ 易于更新和回滚

---

## 🎉 总结

在 AutoDL 上使用 Docker 部署的完整流程：

1. **安装 Docker** (5 分钟)
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```

2. **安装 nvidia-docker** (2 分钟)
   ```bash
   apt-get install -y nvidia-container-toolkit
   systemctl restart docker
   ```

3. **验证 GPU Docker** (1 分钟)
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
   ```

4. **部署项目** (5-10 分钟)
   ```bash
   docker compose build
   docker compose up -d
   ```

**总耗时: 15-20 分钟即可完成整个系统部署！**

---

## 📚 相关文档

- **Docker 部署 FAQ**: `docs/DOCKER_FAQ.md`
- **快速开始**: `docs/QUICK_START.md`
- **完整部署指南**: `docs/AUTODL_DEPLOYMENT.md`
- **部署检查清单**: `docs/DEPLOYMENT_CHECKLIST.md`

---

**祝部署顺利！🚀**
