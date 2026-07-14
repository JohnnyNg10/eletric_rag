# LaTeX 公式渲染测试

## 测试公式

### 行内公式
这是一个行内公式：$\gamma(%)$ 和 $\gamma_A$

### 块级公式

地区电网电压合格率计算公式：

$$
\gamma(\%) = 0.5\gamma_A + 0.5\left(\frac{\gamma_B + \gamma_C + \gamma_D}{3}\right)
$$

其中 $\gamma_A$、$\gamma_B$、$\gamma_C$、$\gamma_D$ 分别表示不同监测点的合格率。

月度平均合格率：

$$
\text{月度平均合格率}(\%) = \frac{\sum_{i=1}^{n}\text{单监测点合格率}_i}{n}
$$

### 复杂公式示例

功率因数计算：

$$
\cos\phi = \frac{P}{\sqrt{P^2 + Q^2}}
$$

短路电流计算：

$$
I_k = \frac{U_N}{\sqrt{3}Z_k}
$$

## 说明

- 行内公式使用单个 `$` 包裹
- 块级公式使用 `$$` 包裹
- 支持 LaTeX 数学符号和希腊字母
- 支持分数、根号、求和等复杂表达式
