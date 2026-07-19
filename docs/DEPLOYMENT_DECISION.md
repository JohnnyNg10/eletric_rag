# 快速部署决策树

帮助你快速选择正确的部署方案。

```
你在哪里部署？
├─ AutoDL 平台
│  │
│  ├─ 标准实例（容器环境）
│  │  └─ ✅ 使用：docs/AUTODL_CONTAINER_DEPLOYMENT.md
│  │     说明：原生部署（不使用 Docker）
│  │     时间：1-2 小时（首次）
│  │
│  └─ 裸机实例
│     └─ ✅ 使用：docs/AUTODL_DOCKER_INSTALL.md + docs/QUICK_START.md
│        说明：安装 Docker 后使用容器部署
│        时间：20 分钟
│
├─ 其他云服务器（阿里云、腾讯云、AWS 等）
│  │
│  ├─ 已有 Docker
│  │  └─ ✅ 使用：docs/QUICK_START.md
│  │     说明：直接使用 Docker Compose
│  │     时间：10 分钟
│  │
│  └─ 没有 Docker
│     └─ ✅ 使用：docs/AUTODL_DOCKER_INSTALL.md + docs/QUICK_START.md
│        说明：先安装 Docker，再部署
│        时间：20 分钟
│
└─ 本地开发机
   └─ ✅ 使用：docs/QUICK_START.md 或 CLAUDE.md
      说明：Docker 或本地开发环境
      时间：10-30 分钟
```

---

## 🤔 如何判断我的 AutoDL 实例类型？

### 方法 1: 查看 hostname

```bash
hostname
```

- 如果显示 `autodl-container-xxx`：**容器环境** → 使用原生部署
- 如果显示普通主机名：**裸机环境** → 可以使用 Docker

### 方法 2: 检查 systemd

```bash
systemctl status
```

- 如果报错 `System has not been booted with systemd`：**容器环境**
- 如果正常显示服务列表：**裸机环境**

### 方法 3: 检查 Docker

```bash
docker --version 2>/dev/null && echo "裸机环境" || echo "容器环境"
```

---

## 📊 部署方案对比

| 方案 | 环境 | 部署时间 | 维护难度 | 性能 | 推荐度 |
|------|------|---------|---------|------|--------|
| **AutoDL 原生部署** | 容器 | 1-2h（首次） | 中 | 100% | ⭐⭐⭐⭐ |
| **AutoDL Docker 部署** | 裸机 | 20min | 低 | 100% | ⭐⭐⭐⭐⭐ |
| **其他服务器 Docker** | 裸机/VM | 20min | 低 | 100% | ⭐⭐⭐⭐⭐ |

---

## 🚀 快速链接

### AutoDL 标准实例（容器）用户：
👉 **[AutoDL 容器环境部署指南](docs/AUTODL_CONTAINER_DEPLOYMENT.md)**

### AutoDL 裸机实例用户：
👉 **[在 AutoDL 上安装 Docker](docs/AUTODL_DOCKER_INSTALL.md)** → **[快速开始](docs/QUICK_START.md)**

### 已有 Docker 的用户：
👉 **[5分钟快速开始](docs/QUICK_START.md)**

---

## 💡 推荐方案

| 场景 | 推荐方案 | 理由 |
|------|---------|------|
| AutoDL 标准实例 | 原生部署 | 容器内无法使用 Docker |
| AutoDL 裸机实例 | Docker 部署 | 简单快速 |
| 阿里云/腾讯云等 | Docker 部署 | 标准方案 |
| 本地开发 | Docker 或 venv | 隔离环境 |

---

**不确定用哪个方案？** 先运行 `hostname` 查看你的环境类型！
