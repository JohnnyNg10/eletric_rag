# API 模式使用指南

本系统支持 **本地模型** 和 **远程 API** 双模式，可通过配置灵活切换。

## 配置说明

在 `.env` 文件中配置以下参数：

### 1. Embedding 模式切换

```bash
# 模式选择：local=本地模型, api=远程API
EMBEDDING_MODE=local

# API 配置（仅当 EMBEDDING_MODE=api 时生效）
EMBEDDING_API_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
EMBEDDING_API_KEY=your_api_key_here
EMBEDDING_API_MODEL=bge-large-zh-v1.5
```

### 2. Reranker 模式切换

```bash
# 模式选择：local=本地模型, api=远程API
RERANKER_MODE=local

# API 配置（仅当 RERANKER_MODE=api 时生效）
RERANKER_API_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
RERANKER_API_KEY=your_api_key_here
RERANKER_API_MODEL=bge-reranker-large
```

### 3. 自动下载控制

```bash
# 是否在启动时自动下载本地模型（local 模式需要）
AUTO_DOWNLOAD_MODELS=True
```

## 模式对比

| 特性 | 本地模式 (local) | API 模式 (api) |
|------|-----------------|----------------|
| **磁盘占用** | ~11 GB | 0 GB |
| **启动速度** | 慢（需加载模型） | 快 |
| **推理速度** | 快（本地 GPU/CPU） | 取决于网络和 API 响应 |
| **成本** | 免费（硬件成本） | 按调用量计费 |
| **稀疏向量** | 支持 (SPLADE) | 不支持 |
| **依赖** | PyTorch + transformers | httpx |

## 使用场景建议

### 推荐使用 API 模式

- **开发/测试阶段**：快速验证功能，无需下载大模型
- **资源受限环境**：磁盘空间 < 15 GB 或内存 < 8 GB
- **低频查询场景**：每日查询量 < 1000 次

### 推荐使用本地模式

- **生产环境**：高频查询，成本敏感
- **离线部署**：无法访问外网或对延迟敏感
- **需要稀疏向量**：系统架构依赖 SPLADE 稀疏编码

## 快速切换到 API 模式

1. 修改 `.env` 文件：

```bash
EMBEDDING_MODE=api
RERANKER_MODE=api
EMBEDDING_API_KEY=your_volcengine_api_key
RERANKER_API_KEY=your_volcengine_api_key
AUTO_DOWNLOAD_MODELS=False
```

2. 重启服务：

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

3. 验证日志输出：

```
[Embedder] Initializing in API mode
[TwoStageReranker] Initializing in API mode
```

## 支持的 API 提供商

当前实现基于 **OpenAI 兼容 API 格式**，支持：

- **火山引擎（豆包）**：`https://ark.cn-beijing.volces.com/api/v3`
- **阿里云通义千问**：`https://dashscope.aliyuncs.com/api/v1`
- **其他兼容提供商**：任何实现 OpenAI `/embeddings` 和 `/rerank` 接口的服务

## 注意事项

1. **稀疏向量限制**：API 模式下 `encode_sparse()` 返回空向量，如果系统强依赖稀疏检索，需保持本地模式
2. **API 密钥安全**：生产环境使用环境变量或密钥管理服务，不要将密钥提交到代码库
3. **混合模式**：可以 `EMBEDDING_MODE=api` + `RERANKER_MODE=local`，灵活组合
4. **成本监控**：API 模式建议配置调用量监控，避免超预算

## 故障降级

系统内置降级策略：

- **Embedding API 失败**：抛出异常，请求失败
- **Reranker API 失败**：降级为召回分数排序，请求继续
- **本地模型加载失败**：启动时报错，需修复配置或切换到 API 模式

## 性能基准参考

| 场景 | 本地模型 (GPU) | 本地模型 (CPU) | API 模式 |
|------|---------------|---------------|---------|
| 单次 embedding (1024 tokens) | ~50ms | ~200ms | ~150ms |
| 批量 rerank (20 文档) | ~100ms | ~500ms | ~300ms |
| 冷启动时间 | ~30s | ~60s | <1s |

*数据仅供参考，实际性能取决于硬件配置和网络条件*
