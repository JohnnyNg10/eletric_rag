# 前端初始化说明

本目录已完成基于 React + TypeScript + Vite 的前端初始化，并按照 `docs/architecture/frontend/18-阶段B前端交互设计.md` 搭建了阶段 B 查询页面骨架。

## 已实现内容

- React + Vite + TypeScript 项目基础结构
- 顶部导航栏与连接配置
- 用户登录 / 手动粘贴 Access Token
- `POST /api/v1/query/preprocess` 预处理请求
- 路由建议卡片、澄清选项列表、确认面板
- `POST /api/v1/query` 执行查询
- 兼容当前后端 JSON 返回，以及后续 SSE 流式返回
- Markdown 答案展示与引用详情区域
- 会话内预处理缓存、请求取消、慢查询提示

## 本地启动

```bash
cd frontend
npm install
npm run dev
```

默认开发地址：`http://localhost:5173`

## 默认联调配置

- 前端默认 API：`http://localhost:8000/api/v1`
- 如果后端地址不同，可在页面右上角“连接设置”中修改
- 查询接口当前需要 Bearer Token，可通过登录接口或手动粘贴 token 使用

## 说明

当前后端代码中的 `/api/v1/query` 仍返回 JSON，尚未真正输出 SSE；前端已做兼容处理：

- 若后端返回 `application/json`，直接展示完整答案
- 若后续改为 `text/event-stream`，前端可直接按流式模式消费

## 后续建议

1. 为后端真正补齐 SSE `StreamingResponse`
2. 增加路由级页面拆分与 React Router
3. 增加单元测试 / 集成测试 / Playwright E2E
4. 补充用户历史记录、引用跳源文档和反馈入口
