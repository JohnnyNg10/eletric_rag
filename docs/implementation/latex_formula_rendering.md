# LaTeX 公式渲染功能实施总结

## 问题描述

前端无法正常显示 Markdown 中的 LaTeX 数学公式，例如：

```
[ \gamma(%) = 0.5\gamma_A + 0.5\left(\frac{\gamma_B + \gamma_C + \gamma_D}{3}\right) ]
```

以及行内公式如 `(\gamma_A、\gamma_B、\gamma_C、\gamma_D)`

---

## 解决方案

### 技术栈
- **remark-math**：Markdown 中识别数学公式语法（`$...$` 和 `$$...$$`）
- **rehype-katex**：将数学公式渲染为 HTML
- **KaTeX**：高性能 LaTeX 数学公式渲染库

### 实施步骤

#### 1. 安装依赖

```bash
cd frontend
npm install remark-math rehype-katex katex
```

#### 2. 修改 `AnswerDisplay.tsx`

添加导入：
```typescript
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';  // KaTeX 样式
```

配置 ReactMarkdown：
```typescript
<ReactMarkdown
  remarkPlugins={[remarkMath]}
  rehypePlugins={[rehypeKatex]}
>
  {answer}
</ReactMarkdown>
```

---

## 支持的公式格式

### 1. 行内公式（Inline）

**语法**：使用单个 `$` 包裹

```markdown
这是行内公式 $\gamma_A$ 和 $\cos\phi$
```

**渲染效果**：这是行内公式 γ_A 和 cosφ

---

### 2. 块级公式（Display）

**语法**：使用 `$$` 包裹

```markdown
$$
\gamma(\%) = 0.5\gamma_A + 0.5\left(\frac{\gamma_B + \gamma_C + \gamma_D}{3}\right)
$$
```

**渲染效果**：公式会居中显示在独立行

---

### 3. 常用公式示例

#### 地区电网电压合格率

```markdown
$$
\gamma(\%) = 0.5\gamma_A + 0.5\left(\frac{\gamma_B + \gamma_C + \gamma_D}{3}\right)
$$
```

#### 月度平均合格率

```markdown
$$
\text{月度平均合格率}(\%) = \frac{\sum_{i=1}^{n}\text{单监测点合格率}_i}{n}
$$
```

#### 功率因数

```markdown
$$
\cos\phi = \frac{P}{\sqrt{P^2 + Q^2}}
$$
```

#### 短路电流

```markdown
$$
I_k = \frac{U_N}{\sqrt{3}Z_k}
$$
```

---

## 测试验证

### 本地测试

1. 启动前端开发服务器：
   ```bash
   cd frontend
   npm run dev
   ```

2. 访问：`http://localhost:5173`

3. 登录后输入查询，等待包含公式的答案返回

### 测试用例

可以使用以下查询来测试公式渲染：

1. **"地区电网电压合格率如何计算？"**
   - 预期：返回包含 γ(%) 公式的答案

2. **"功率因数的计算公式"**
   - 预期：返回 cosφ 公式

3. **"短路电流计算方法"**
   - 预期：返回包含 I_k 公式的答案

---

## 常见问题

### Q1: 公式显示为原始 LaTeX 代码

**原因**：KaTeX CSS 未正确加载

**解决**：确保 `import 'katex/dist/katex.min.css'` 在文件顶部

---

### Q2: 公式渲染错误或乱码

**原因**：LaTeX 语法错误

**解决**：
- 检查括号是否配对：`\left(` 必须有对应的 `\right)`
- 特殊字符需要转义：`%` → `\%`
- 中文文本需要用 `\text{}`：`\text{月度平均合格率}`

---

### Q3: 行内公式和块级公式混淆

**规则**：
- `$...$` → 行内（与文本在同一行）
- `$$...$$` → 块级（独立一行，居中显示）

---

## 支持的 LaTeX 符号

### 希腊字母
- `\alpha, \beta, \gamma, \delta` → α, β, γ, δ
- `\phi, \theta, \omega` → φ, θ, ω

### 运算符
- `\frac{a}{b}` → 分数
- `\sqrt{x}` → 根号
- `\sum_{i=1}^{n}` → 求和
- `\int_{a}^{b}` → 积分

### 上下标
- `x^2` → 上标
- `x_i` → 下标
- `x_i^2` → 同时使用

### 括号
- `\left( ... \right)` → 自适应大小的圆括号
- `\left[ ... \right]` → 方括号
- `\left\{ ... \right\}` → 花括号

---

## 性能优化建议

1. **按需加载**：如果答案不包含公式，KaTeX 不会执行渲染
2. **SSR 支持**：KaTeX 支持服务端渲染，未来可以预渲染公式
3. **CDN 加速**：生产环境可以使用 KaTeX CDN 减少包体积

---

## 后续改进方向

1. **化学公式支持**：可添加 `mhchem` 扩展支持化学方程式
2. **公式编号**：支持公式自动编号和交叉引用
3. **复制功能**：点击公式复制 LaTeX 源码
4. **错误提示**：LaTeX 语法错误时显示友好提示

---

## 文件清单

- ✅ `frontend/src/components/result/AnswerDisplay.tsx` - 答案显示组件（已修改）
- ✅ `frontend/package.json` - 依赖配置（已更新）
- ✅ `frontend/FORMULA_TEST.md` - 公式测试文档（新增）

---

## 部署清单

### 开发环境
- ✅ 依赖已安装
- ✅ 代码已修改
- ✅ 开发服务器运行中（http://localhost:5173）

### 生产环境部署
1. 确保 `package.json` 包含所有依赖
2. 运行 `npm install` 安装依赖
3. 运行 `npm run build` 构建生产版本
4. 部署 `dist/` 目录

---

**实施时间**：2026-07-13  
**状态**：✅ 已完成  
**测试状态**：待用户验证
