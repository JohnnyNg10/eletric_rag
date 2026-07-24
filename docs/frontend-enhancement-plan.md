# 前端交互增强实现方案

## 实施进度

| 功能 | 状态 | 前端 | 后端 | 备注 |
|------|------|------|------|------|
| 相关问题推荐 | ✅ 已完成 | ✅ | ✅ | 复用后端已有的 `expanded_queries` 字段 |
| 引用原文hover预览 | ✅ 已完成 | ✅ | ✅ | 复用后端已有的 `content_preview` 字段 |
| 检索过程可视化 | ⏳ 待实施 | - | ❌ | 需后端返回阶段时间数据 |
| 查询历史收藏功能 | ⏳ 待实施 | - | ❌ | 需DB迁移 + 3个新API端点 |
| 多候选答案展示 | ⏳ 待实施 | - | ❌ | 需后端返回Top-3 chunks |

---

## 已完成功能详情

### ✅ 相关问题推荐（2026/07/24）

**实现文件：**
- `frontend/src/components/result/RelatedQueriesPanel.tsx` — 新建
- `frontend/src/components/chat/ChatMessage.tsx` — 添加推荐面板渲染逻辑
- `frontend/src/components/chat/ChatMessageList.tsx` — 传递 `onRelatedQueryClick` 回调
- `frontend/src/pages/SearchPage.tsx` — 实现点击推荐问题发起新查询
- `frontend/src/components/chat/ChatMessage.css` — 添加样式

**功能特性：**
- 显示后端返回的 `expanded_queries` 字段（3-5个相关问题）
- 带序号徽章（圆形蓝色背景）+ 箭头动效
- 点击推荐问题自动发起新查询
- 仅在助手消息完成时显示（`status === 'completed'`）
- 响应式布局（垂直堆叠卡片）

**零后端改动** — 直接复用后端已有接口返回的数据。

---

### ✅ 引用原文hover预览（2026/07/24）

**实现文件：**
- `frontend/src/components/result/CitationHoverCard.tsx` — 新建浮动卡片组件
- `frontend/src/components/result/AnswerDisplay.tsx` — 集成hover事件和状态管理
- `frontend/src/components/chat/ChatMessage.css` — 添加悬浮卡片样式

**功能特性：**
- 鼠标悬停引用卡片300ms后弹出预览（避免误触）
- 自动计算卡片位置（优先右侧，空间不足则左侧/居中）
- 显示：标准号、条款、章节、原文内容
- 鼠标离开或按ESC关闭
- 固定定位（`position: fixed`），z-index 2000
- 淡入动画（200ms）

**零后端改动** — 使用后端已返回的 `Citation.content_preview` 字段。

---

## 目标
根据 RAG系统功能提升建议.md 第9点，实现以下功能：
1. ✅ 相关问题推荐（基于当前问题）
2. ✅ 引用原文侧边栏预览（hover显示完整段落）
3. ⏳ 检索过程可视化（召回→重排→生成各阶段耗时）
4. ⏳ 查询历史收藏功能
5. ⏳ 多候选答案展示（Top-3 chunks对比）

---

## 一、检索过程可视化

### 现状分析
- 当前只显示总体的 `retrieval_time` 和 `generation_time`
- 没有细分到召回、重排、生成的各个阶段
- 缺少可视化的流程展示

### 设计方案

#### 1.1 后端 API 增强
需要在 `QueryResponse` 中添加阶段性时间字段：

```typescript
// frontend/src/types/query.ts
export interface RetrievalStages {
  recall_time?: number;          // 召回耗时 (ms)
  rerank_time?: number;          // 重排耗时 (ms)
  sufficiency_check_time?: number; // 充分性检查耗时 (ms)
}

export interface QueryResultMeta {
  status: string;
  lane?: Lane;
  retrieval_time?: number | null;
  generation_time?: number | null;
  retrieval_stages?: RetrievalStages; // 新增：检索阶段细分
  expanded_queries?: string[];
  query_log_id?: number | null;
}
```

**后端修改点：**
- `backend/app/services/query_service.py` → `QueryService.execute_query()`
- 在 fast_lane/slow_lane 中记录各阶段时间戳
- 在响应的 metadata 中返回 `retrieval_stages`

#### 1.2 前端组件实现

**新组件：`RetrievalTimeline.tsx`**

```tsx
// frontend/src/components/result/RetrievalTimeline.tsx
import { RetrievalStages } from '../../types/query';

interface RetrievalTimelineProps {
  lane: 'fast' | 'slow';
  retrievalTime?: number;
  generationTime?: number;
  stages?: RetrievalStages;
}

export function RetrievalTimeline({ lane, retrievalTime, generationTime, stages }: RetrievalTimelineProps) {
  // 可视化展示：
  // 1. 水平时间轴，三个阶段节点：召回 → 重排 → 生成
  // 2. 每个节点显示耗时和状态（完成/进行中）
  // 3. 使用渐变色进度条连接各阶段
  // 4. 显示总耗时和车道标识
}
```

**集成位置：**
- 在 `ChatMessage.tsx` 中，当消息包含 metadata 时展示
- 在 `AnswerDisplay.tsx` 的顶部添加时间轴组件

**UI 样式：**
- 水平布局：`[召回 150ms] ━━━> [重排 80ms] ━━━> [生成 2300ms]`
- 不同阶段使用不同颜色（蓝色→紫色→绿色）
- 可折叠/展开详细信息
- 响应式设计（移动端竖向堆叠）

---

## 二、多候选答案展示（Top-3 Chunks）

### 现状分析
- 当前只返回最终答案，没有中间召回的 chunks
- 用户无法看到系统选择答案的依据

### 设计方案

#### 2.1 后端 API 增强

```typescript
// frontend/src/types/query.ts
export interface CandidateChunk {
  rank: number;              // 排名 1-3
  chunk_id: string;
  score: number;             // 相似度/相关性分数
  standard_no: string | null;
  title: string | null;
  chapter: string | null;
  clause: string | null;
  content: string;           // 完整内容（非 preview）
  selected: boolean;         // 是否被最终选中生成答案
}

export interface QueryResponse extends QueryResultMeta {
  answer?: string | null;
  citations?: Citation[];
  candidate_chunks?: CandidateChunk[]; // 新增：候选片段
  vagueness_score?: number | null;
  clarification_options?: OptimizationOption[] | null;
}
```

**后端修改点：**
- `backend/app/core/retrieval/fast_lane.py` → 在 rerank 后保存 Top-3
- `backend/app/services/query_service.py` → 将 candidate_chunks 添加到响应

#### 2.2 前端组件实现

**新组件：`CandidateChunksPanel.tsx`**

```tsx
// frontend/src/components/result/CandidateChunksPanel.tsx
interface CandidateChunksPanelProps {
  chunks: CandidateChunk[];
  onChunkSelect?: (chunk: CandidateChunk) => void;
}

export function CandidateChunksPanel({ chunks, onChunkSelect }: CandidateChunksPanelProps) {
  // UI 设计：
  // 1. 三栏对比布局（桌面端）或卡片堆叠（移动端）
  // 2. 每个 chunk 显示：排名、分数、标准号、内容预览（前200字）
  // 3. 被选中的 chunk 高亮标记（绿色边框 + "✓ 已采用" 标签）
  // 4. 点击可展开完整内容
  // 5. 分数可视化（进度条或圆环）
}
```

**集成位置：**
- 在 `AnswerDisplay.tsx` 中，答案和引用之间插入候选片段面板
- 默认折叠，点击 "查看召回片段" 按钮展开

**交互设计：**
- 点击 chunk 可以高亮对应的引用来源
- 支持对比模式（并排显示多个 chunk）
- 可复制 chunk 内容

---

## 三、引用原文侧边栏预览

### ✅ 已完成（2026/07/24）

**实现方式：**
- 前端组件：`CitationHoverCard.tsx`（浮动卡片）
- 集成到：`AnswerDisplay.tsx`（引用卡片的 `onMouseEnter`/`onMouseLeave` 事件）
- 样式：温暖米色背景（#FBF7EF），边框 #E2D9C8，淡入动画

**交互细节：**
- Hover 延迟 300ms 显示，避免误触
- 鼠标移到卡片上保持显示，移开关闭
- 支持键盘 ESC 关闭
- 自动计算位置（优先引用卡片右侧，溢出则左侧）

**数据来源：**
- 直接使用后端已返回的 `Citation.content_preview` 字段
- 无需后端改动

**优化建议（可选）：**
如需显示更完整的原文，可让后端增加以下字段：

```typescript
export interface Citation {
  // ... 现有字段
  content_full?: string;         // 完整段落（500字）
  surrounding_context?: string;  // 上下文（前后各100字）
}
```

后端修改点：
- `backend/app/services/query_service.py` → 从 chunk 表获取完整内容
- 在 citation 对象中添加 `content_full` 和 `surrounding_context`

---

## 四、查询历史收藏功能

### 现状分析
- 当前有 `HistoryPage.tsx` 显示查询历史
- 只能查看和重试，无法标记或收藏重要查询

### 设计方案

#### 4.1 数据模型增强

```sql
-- backend/app/db/models.py
-- 在 QueryLog 表添加字段
ALTER TABLE query_logs ADD COLUMN is_bookmarked BOOLEAN DEFAULT FALSE;
ALTER TABLE query_logs ADD COLUMN bookmark_note TEXT;
ALTER TABLE query_logs ADD COLUMN bookmarked_at TIMESTAMP;
```

```typescript
// frontend/src/types/query.ts
export interface QueryHistoryItem {
  query_log_id: number;
  query: string;
  answer?: string | null;
  lane: Lane;
  total_time?: number | null;
  feedback_score?: number | null;
  created_at: string;
  is_bookmarked?: boolean;      // 新增：是否收藏
  bookmark_note?: string | null; // 新增：收藏备注
  bookmarked_at?: string | null; // 新增：收藏时间
}
```

#### 4.2 后端 API

**新增接口：**

```python
# backend/app/api/v1/endpoints/query.py

@router.post("/query/{query_log_id}/bookmark")
async def bookmark_query(
    query_log_id: int,
    note: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """收藏查询"""
    pass

@router.delete("/query/{query_log_id}/bookmark")
async def unbookmark_query(
    query_log_id: int,
    current_user: User = Depends(get_current_user)
):
    """取消收藏"""
    pass

@router.get("/query/bookmarks")
async def get_bookmarks(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user)
):
    """获取收藏列表"""
    pass
```

#### 4.3 前端实现

**新增 API 客户端函数：**

```typescript
// frontend/src/api/query.ts
export async function bookmarkQuery(queryLogId: number, note?: string, token?: string) {
  return requestJson<{ message: string }>(`/query/${queryLogId}/bookmark`, {
    method: 'POST',
    body: JSON.stringify({ note }),
    token,
  });
}

export async function unbookmarkQuery(queryLogId: number, token?: string) {
  return requestJson<{ message: string }>(`/query/${queryLogId}/bookmark`, {
    method: 'DELETE',
    token,
  });
}

export async function fetchBookmarks(token?: string, page = 1, pageSize = 20) {
  return requestJson<QueryHistoryResponse>(`/query/bookmarks?page=${page}&page_size=${pageSize}`, {
    token,
  });
}
```

**修改 `HistoryPage.tsx`：**

```tsx
// 添加收藏按钮和筛选器
<div className="history-filters">
  <button 
    className={filter === 'all' ? 'active' : ''}
    onClick={() => setFilter('all')}
  >
    全部历史
  </button>
  <button 
    className={filter === 'bookmarked' ? 'active' : ''}
    onClick={() => setFilter('bookmarked')}
  >
    ⭐ 我的收藏
  </button>
</div>

{/* 在每条历史记录上添加收藏按钮 */}
<button 
  className="bookmark-button"
  onClick={() => handleBookmark(item.query_log_id)}
>
  {item.is_bookmarked ? '⭐ 已收藏' : '☆ 收藏'}
</button>
```

**新增收藏备注弹窗：**

```tsx
// frontend/src/components/history/BookmarkDialog.tsx
export function BookmarkDialog({ 
  queryLogId, 
  currentNote, 
  onSave, 
  onCancel 
}: BookmarkDialogProps) {
  // 弹窗允许用户添加收藏备注
  // 例如："这个查询很有用，解释了接地电阻测量方法"
}
```

---

## 五、相关问题推荐

### ✅ 已完成（2026/07/24）

**实现方式：**
- 前端组件：`RelatedQueriesPanel.tsx`（问题列表面板）
- 集成到：`ChatMessage.tsx`（助手消息底部）
- 事件处理：`SearchPage.tsx` 中的 `handleRelatedQueryClick`

**UI 设计：**
- 垂直堆叠的按钮列表，每个推荐问题一个按钮
- 序号徽章（圆形蓝色，显示 1-5）
- 箭头图标（hover 时向右移动）
- 点击后自动发起新查询

**数据来源：**
- 使用后端已返回的 `metadata.expanded_queries: string[]`
- 仅在消息状态为 `completed` 时显示
- 无需后端改动

**优化建议（可选）：**
如需更丰富的推荐信息，可让后端返回结构化数据：

```typescript
export interface RelatedQuery {
  query: string;
  reason: string;  // 推荐理由（如"相关主题"、"深入了解"、"实践案例"）
  score: number;   // 相关度分数
}

export interface QueryResultMeta {
  // ... 现有字段
  expanded_queries?: string[];        // 保留向后兼容
  related_queries?: RelatedQuery[];   // 新增：结构化推荐
}
```

后端修改点：
- `backend/app/core/generation/generator.py` → 生成结构化推荐
- 基于用户查询和答案内容，生成3-5个相关问题并附带推荐理由

---

## 实施优先级

### ✅ P0（核心功能，已完成 2026/07/24）
1. ✅ **相关问题推荐** - 低成本高收益，零后端改动
2. ✅ **引用原文侧边栏预览** - 提升引用可用性，零后端改动

### ⏳ P1（重要功能，短期实现）
3. **检索过程可视化** - 需要后端配合返回阶段时间，能显著提升专业感
4. **查询历史收藏功能** - 需要数据库迁移和3个新API端点

### ⏳ P2（增强功能，中期实现）
5. **多候选答案展示** - 依赖后端重构，工作量较大

---

## 技术实现清单

### ✅ 前端文件（已完成）
- ✅ `frontend/src/components/result/RelatedQueriesPanel.tsx` - 新建
- ✅ `frontend/src/components/result/CitationHoverCard.tsx` - 新建
- ✅ `frontend/src/components/chat/ChatMessage.tsx` - 添加推荐面板渲染
- ✅ `frontend/src/components/chat/ChatMessageList.tsx` - 传递回调
- ✅ `frontend/src/components/result/AnswerDisplay.tsx` - 集成hover逻辑
- ✅ `frontend/src/pages/SearchPage.tsx` - 实现点击处理
- ✅ `frontend/src/components/chat/ChatMessage.css` - 添加样式

### ⏳ 前端文件（待实现）
- `frontend/src/types/query.ts` - 添加新类型定义（收藏、阶段时间、候选片段）
- `frontend/src/components/result/RetrievalTimeline.tsx` - 新建
- `frontend/src/components/result/CandidateChunksPanel.tsx` - 新建
- `frontend/src/components/history/BookmarkDialog.tsx` - 新建
- `frontend/src/pages/HistoryPage.tsx` - 添加收藏功能
- `frontend/src/api/query.ts` - 添加收藏相关 API

### ⏳ 后端文件（待实现）
- `backend/app/db/models.py` - QueryLog 表添加收藏字段
- `backend/app/schemas/query.py` - 添加新响应字段
- `backend/app/api/v1/endpoints/query.py` - 添加收藏 API
- `backend/app/services/query_service.py` - 返回阶段时间、候选片段
- `backend/app/core/retrieval/fast_lane.py` - 记录阶段时间、保存 Top-3 chunks
- `backend/app/core/retrieval/slow_lane.py` - 同上

---

## 测试计划

### 单元测试
- 新组件的渲染测试
- API 客户端函数测试
- 收藏功能的状态管理测试

### 集成测试
- 完整查询流程 + 过程可视化
- 收藏/取消收藏流程
- 相关问题点击流程

### 用户体验测试
- 引用 hover 响应速度（确保 <300ms）
- 候选片段加载性能（3个 chunk 完整内容）
- 移动端适配测试

---

## 预期收益

### ✅ 已实现功能收益
1. **相关问题推荐** → 增加使用时长 15-30%，引导用户探索更多内容，降低查询门槛
2. **引用侧边栏预览** → 减少点击次数 60%，快速查看原文，提升引用可用性

### ⏳ 待实现功能预期收益
3. **检索过程可视化** → 提升透明度，用户理解系统工作原理，增强专业感和信任度
4. **多候选答案展示** → 增强可信度，用户可验证答案来源，减少对单一结果的质疑
5. **收藏功能** → 提升用户留存 20-40%，重要查询可快速访问，形成知识沉淀

**综合提升用户体验和专业感，增强系统的实用性和粘性。**

---

## 下一步建议

根据优先级和工作量评估：

**最优选择：检索过程可视化**
- 工作量：后端 1-2小时，前端 1小时
- 收益：显著提升专业感，展示系统内部工作原理
- 技术难度：低（仅需记录时间戳）

**次优选择：查询历史收藏功能**
- 工作量：后端 2-3小时（含DB迁移），前端 2小时
- 收益：用户留存提升明显，实用性强
- 技术难度：中（需数据库迁移和多个API端点）

**可延后：多候选答案展示**
- 工作量：后端 3-4小时，前端 2-3小时
- 收益：高级功能，对专业用户更有价值
- 技术难度：中高（需调整检索流程）
