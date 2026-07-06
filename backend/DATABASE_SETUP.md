# 数据库自动建表 - 快速启动指南

## 📋 前提条件

1. ✅ MySQL 8.0 已安装并运行
2. ✅ Python 3.13+ 已安装
3. ✅ 后端依赖已安装（uv 已配置）

---

## 🚀 快速启动（3步）

### 步骤1：配置数据库连接

```bash
# 1. 复制环境变量模板
cd backend
cp .env.example .env

# 2. 编辑 .env 文件，修改 MySQL 密码
# MYSQL_PASSWORD=your_mysql_password
```

### 步骤2：启动项目（自动建表）

```bash
# 激活虚拟环境（如果使用 uv）
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows

# 启动应用（会自动建表）
python -m app.main
# 或
uvicorn app.main:app --reload
```

### 步骤3：验证

访问：http://localhost:8000/health

看到以下输出说明成功：
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0"
}
```

---

## 📊 自动完成的操作

### 启动时自动执行

1. **检查数据库连接**
   - 连接 MySQL
   - 验证连接是否正常

2. **创建所有表**（10张）
   - documents（文档表）
   - chunks（文档块表）
   - users（用户表）
   - query_logs（查询日志表）
   - clarification_logs（澄清对话表）
   - badcase_tracking（难例追踪表）
   - term_dictionary（术语词典表）
   - test_cases（测试用例表）
   - clause_references（条款引用表）
   - ab_experiments（A/B测试表）

3. **插入初始数据**
   - 创建管理员账号：`admin` / `admin123`
   - 插入8条预置术语（PT、CT、10kV等）

---

## 🔍 查看日志

启动时会看到类似日志：

```
2026-07-06 16:30:00 - app.db.session - INFO - Initializing database...
2026-07-06 16:30:01 - app.db.session - INFO - All tables created successfully
2026-07-06 16:30:01 - app.db.session - INFO - Created default admin user
2026-07-06 16:30:01 - app.db.session - INFO - Created 8 default terms
2026-07-06 16:30:01 - app.db.session - INFO - Database initialization completed successfully
2026-07-06 16:30:01 - app.main - INFO - Application started successfully
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## ✅ 验证数据库

### 方法1：通过 API

```bash
curl http://localhost:8000/health
```

### 方法2：直接查询 MySQL

```bash
mysql -u root -p

USE electric_rag;

-- 查看所有表
SHOW TABLES;

-- 查看表数量（应该是10）
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = 'electric_rag';

-- 查看初始数据
SELECT * FROM users;
SELECT * FROM term_dictionary;
```

---

## 🔧 配置说明

### .env 文件关键配置

```bash
# 必须配置
MYSQL_HOST=localhost          # MySQL 主机
MYSQL_PORT=3306              # MySQL 端口
MYSQL_USER=root              # MySQL 用户名
MYSQL_PASSWORD=your_password # ⚠️ 必须修改
MYSQL_DB=electric_rag        # 数据库名（自动创建）

# 可选配置
DEBUG=True                   # 开发模式
LOG_LEVEL=INFO              # 日志级别
```

---

## ⚠️ 常见问题

### 问题1：数据库连接失败

```
ERROR - Database connection failed! Please check your MySQL configuration.
```

**解决方案**：
1. 检查 MySQL 是否启动：`mysql -u root -p`
2. 检查 `.env` 中的密码是否正确
3. 检查 MySQL 是否允许本地连接

### 问题2：数据库已存在

如果数据库已存在，启动时：
- ✅ 不会删除现有数据
- ✅ 只会创建缺失的表
- ✅ 不会重复插入初始数据（会检查）

### 问题3：表已存在但结构不同

**手动删除数据库重新创建**：
```sql
DROP DATABASE electric_rag;
```
然后重启应用。

### 问题4：缺少依赖包

```bash
# 确保安装了所有依赖
uv sync

# 或手动安装关键包
uv add sqlalchemy pymysql passlib[bcrypt]
```

---

## 🔄 重置数据库

如果需要完全重置：

```bash
# 1. 停止应用（Ctrl+C）

# 2. 删除数据库
mysql -u root -p -e "DROP DATABASE IF EXISTS electric_rag;"

# 3. 重新启动应用（会自动重建）
python -m app.main
```

---

## 📝 代码工作原理

### app/main.py（启动入口）

```python
@app.on_event("startup")
async def startup_event():
    # 1. 检查数据库连接
    check_db_connection()
    
    # 2. 初始化数据库（创建表 + 初始数据）
    init_db()
```

### app/db/session.py（初始化逻辑）

```python
def init_db():
    # 1. 创建所有表
    Base.metadata.create_all(bind=engine)
    
    # 2. 插入初始数据（检查是否已存在）
    # - 管理员用户
    # - 预置术语
```

### app/db/models.py（ORM 模型）

- 定义了10张表的 SQLAlchemy 模型
- 对应 `docs/sql/init_database.sql` 的表结构

---

## 🎯 下一步

数据库建表完成后，你可以：

1. **访问 API 文档**：http://localhost:8000/docs
2. **开始开发业务逻辑**：实现查询、文档管理等功能
3. **使用 Alembic 管理迁移**：后续表结构变更

---

## 📚 相关文档

- [数据库设计文档](../docs/architecture/backend/06-数据模型设计.md)
- [SQL 初始化脚本](../docs/sql/init_database.sql)
- [后端架构设计](../docs/architecture/backend/04-后端架构设计.md)

---

**创建日期**：2026-07-06  
**状态**：✅ 可用
