# 电力国标PDF下载工具

自动下载国家标准委员会公开的电力强制国标PDF文件。

## 功能特点

- ✅ 自动下载48条电力强制国标PDF
- ✅ 断点续传（已下载的自动跳过）
- ✅ 反爬虫措施：
  - 随机延迟（2-6秒）
  - User-Agent轮换（5个不同浏览器）
  - 失败自动重试（最多3次）
  - 每10个标准后休息5-8秒
- ✅ 详细日志记录
- ✅ 文件完整性检查（排除错误页面）

## 依赖安装

```bash
pip install requests
```

## 使用方法

### 1. 基本使用

```bash
python download_standards.py
```

### 2. 查看进度

下载过程会在终端实时显示：
```
[1/48] Processing: F8C9E208891B7BB5AF1B3E64933693C2
  Standard: GB 50057-2010 - 建筑物防雷设计规范
✓ Downloaded: GB+50057-2010.pdf (1234.5 KB)

[2/48] Processing: ...
```

### 3. 查看日志

详细日志保存在 `download_standards.log`：
```bash
cat download_standards.log
```

### 4. 断点续传

如果中断了，再次运行即可继续：
```bash
python download_standards.py
```

已下载的文件会自动跳过。

## 输出目录

```
电力国标PDF/
  ├── GB+50057-2010.pdf
  ├── GB+3836.16-2024.pdf
  └── ...
```

## 配置说明

可以在脚本中修改配置：

```python
# 输出目录
downloader = StandardDownloader(output_dir="电力国标PDF")

# 页数和每页数量
downloader.run(max_pages=3, standards_per_page=20)

# 延迟时间（秒）
self._random_delay(min_sec=2.0, max_sec=5.0)

# 重试次数
self.download_standard(hcno, std_info, max_retries=3)
```

## 反爬虫策略

1. **随机延迟**：
   - 页面请求：2-4秒
   - 标准详情：3-6秒
   - 每10个标准：5-8秒

2. **User-Agent轮换**：
   - Chrome (Windows/Mac)
   - Firefox
   - Edge
   - 随机选择

3. **重试机制**：
   - 失败后等待5-10秒
   - 最多重试3次
   - 超时设置30-60秒

4. **会话保持**：
   - 使用Session对象
   - 保持连接复用
   - 模拟真实浏览器行为

## 常见问题

### 1. 下载速度慢

**原因**：为避免被反爬，有随机延迟。

**预计时间**：48个标准约需 15-20分钟。

### 2. 部分文件下载失败

**原因**：
- 网络波动
- 服务器临时不可用
- 该标准可能没有PDF

**解决**：
- 查看日志了解具体原因
- 再次运行脚本（会跳过已下载的）
- 手动访问网站下载失败的标准

### 3. 提示"File too small"

**原因**：下载的不是PDF而是错误页面。

**可能情况**：
- 该标准确实没有PDF文件
- 服务器返回了错误页面

**解决**：
- 检查日志中的HCNO
- 手动访问该标准页面确认

### 4. 连接超时

**原因**：网络不稳定。

**解决**：
```python
# 增加超时时间
response = self.session.get(..., timeout=120)  # 改为120秒
```

### 5. 被反爬虫拦截

**表现**：持续下载失败。

**解决**：
```python
# 增加延迟时间
self._random_delay(min_sec=5.0, max_sec=10.0)  # 改为5-10秒

# 减少并发请求
# 每5个标准后休息
if idx % 5 == 0:
    self._random_delay(10.0, 15.0)
```

## 合法性说明

本工具仅用于下载**国家标准委员会官方网站公开的标准文件**，符合以下条件：

1. ✅ 所有标准均为公开资源
2. ✅ 网站明确提供下载功能
3. ✅ 用于学习和研究目的
4. ✅ 遵守合理的请求频率

## 注意事项

1. **请勿滥用**：
   - 不要去掉延迟并发请求
   - 不要频繁运行脚本
   - 尊重服务器资源

2. **文件用途**：
   - 仅供个人学习研究
   - 请勿商业使用
   - 请勿二次传播

3. **版权声明**：
   - PDF文件版权归标准制定单位所有
   - 本工具仅提供便捷下载功能

## 技术细节

### 标准URL结构

```
列表页：
https://openstd.samr.gov.cn/bzgk/std/std_list?p.p1=1&p.p5=PUBLISHED&p.p6=29

详情页：
https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno={HCNO}

下载链接：
https://openstd.samr.gov.cn/bzgk/std/showGb?type=download&hcno={HCNO}&request_locale=zh
```

### HCNO

- 32位十六进制字符串
- 标准的唯一标识符
- 从列表页提取

### 文件命名

- 使用标准号作为文件名
- 替换特殊字符：`/` → `-`, 空格 → `+`
- 示例：`GB 50057-2010` → `GB+50057-2010.pdf`

## 开发说明

### 添加新分类

修改 `p.p6` 参数：
```python
def get_standard_list(self, page: int = 1, category: int = 29):
    # category: 29=电力, 其他分类需查询
    params = {
        'p.p6': category,
        ...
    }
```

### 调试模式

启用详细日志：
```python
logging.basicConfig(level=logging.DEBUG)
```

### 测试单个标准

```python
downloader = StandardDownloader()
hcno = "F8C9E208891B7BB5AF1B3E64933693C2"
std_info = downloader.get_standard_info(hcno)
downloader.download_standard(hcno, std_info)
```

## License

MIT
