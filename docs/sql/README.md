# 数据库初始化说明

## 📁 文件位置

```
docs/sql/init_database.sql
```

## 🚀 快速开始

### 方法1：命令行执行

```bash
# 本地 MySQL
mysql -u root -p < docs/sql/init_database.sql

# 指定主机和端口
mysql -h localhost -P 3306 -u root -p < docs/sql/init_database.sql
```

### 方法2：MySQL 客户端

```sql
SOURCE /path/to/docs/sql/init_database.sql;
```

### 方法3：使用 Python 脚本

```python
import pymysql

with open('docs/sql/init_database.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

connection = pymysql.connect(
    host='localhost',
    user='root',
    password='your_password',
    charset='utf8mb4'
)

cursor = connection.cursor()
for statement in sql.split(';'):
    if statement.strip():
        cursor.execute(statement)
connection.commit()
connection.close()
```

---

## 📋 脚本包含内容

### 1. 数据库创建
- 数据库名：`electric_rag`
- 字符集：`utf8mb4`
- 排序规则：`utf8mb4_unicode_ci`

### 2. 10张核心表

| # | 表名 | 说明 | 记录数 |
|---|------|------|--------|
| 1 | documents | 文档元数据 | 0 |
| 2 | chunks | 文档分块 | 0 |
| 3 | users | 用户管理 | 1（admin） |
| 4 | query_logs | 查询日志 | 0 |
| 5 | clarification_logs | 澄清对话 | 0 |
| 6 | badcase_tracking | 难例追踪 | 0 |
| 7 | term_dictionary | 术语词典 | 8（预置） |
| 8 | test_cases | 测试用例 | 0 |
| 9 | clause_references | 条款引用 | 0 |
| 10 | ab_experiments | A/B测试 | 0 |

### 3. 初始化数据

**默认管理员账号**：
- 用户名：`admin`
- 邮箱：`admin@electric-rag.com`
- 密码：`admin123`（⚠️ 需要在应用层重新设置hash）
- 角色：`admin`

**预置术语**（8条）：
- PT → 电压互感器
- CT → 电流互感器
- 刀闸 → 隔离开关
- 断路器
- 10kV/35kV/110kV/220kV 电压等级

---

## ✅ 验证安装

```sql
USE electric_rag;

-- 查看所有表
SHOW TABLES;

-- 查看表数量（应该是10）
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = 'electric_rag' AND table_type = 'BASE TABLE';

-- 查看预置数据
SELECT * FROM users;
SELECT * FROM term_dictionary;

-- 查看表结构
DESCRIBE documents;
DESCRIBE chunks;
```

---

## 🔧 配置建议

### MySQL 配置优化

在 `my.cnf` 或 `my.ini` 中添加：

```ini
[mysqld]
# 字符集
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci

# InnoDB 配置
innodb_buffer_pool_size=2G
innodb_log_file_size=256M
innodb_flush_log_at_trx_commit=2

# 连接数
max_connections=500

# 慢查询日志
slow_query_log=1
slow_query_log_file=/var/log/mysql/slow.log
long_query_time=2
```

### 性能监控

```sql
-- 查看表大小
SELECT
    table_name AS '表名',
    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS '大小(MB)'
FROM information_schema.tables
WHERE table_schema = 'electric_rag'
ORDER BY (data_length + index_length) DESC;

-- 查看索引使用情况
SELECT * FROM sys.schema_unused_indexes
WHERE object_schema = 'electric_rag';
```

---

## 🔄 迁移管理

### 使用 Alembic

```bash
# 初始化 Alembic
cd backend
alembic init alembic

# 生成初始迁移（基于 SQLAlchemy 模型）
alembic revision --autogenerate -m "Initial tables"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

### 手动迁移示例

```sql
-- 如需添加新字段
ALTER TABLE documents ADD COLUMN author VARCHAR(100) COMMENT '作者';

-- 如需添加索引
CREATE INDEX idx_author ON documents(author);

-- 如需修改字段
ALTER TABLE documents MODIFY COLUMN abstract LONGTEXT;
```

---

## 🛡️ 安全建议

### 1. 修改默认管理员密码

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
new_password = pwd_context.hash("your_secure_password")

# 更新数据库
# UPDATE users SET password_hash = 'new_hash' WHERE username = 'admin';
```

### 2. 创建应用专用数据库用户

```sql
-- 创建用户
CREATE USER 'electric_rag_app'@'localhost' IDENTIFIED BY 'strong_password';

-- 授权
GRANT SELECT, INSERT, UPDATE, DELETE ON electric_rag.* TO 'electric_rag_app'@'localhost';

-- 刷新权限
FLUSH PRIVILEGES;

-- 在应用中使用此用户连接数据库
```

### 3. 定期备份

```bash
# 每日备份脚本
#!/bin/bash
BACKUP_DIR="/backup/mysql"
DATE=$(date +%Y%m%d_%H%M%S)

mysqldump -u root -p electric_rag \
  --single-transaction \
  --quick \
  --lock-tables=false \
  > ${BACKUP_DIR}/electric_rag_${DATE}.sql

# 压缩
gzip ${BACKUP_DIR}/electric_rag_${DATE}.sql

# 保留最近7天的备份
find ${BACKUP_DIR} -name "electric_rag_*.sql.gz" -mtime +7 -delete
```

---

## ⚠️ 注意事项

1. **字符集**：必须使用 `utf8mb4`，否则无法存储表情符号和特殊字符
2. **时区**：脚本设置为 `+08:00`（北京时间），根据需要调整
3. **外键约束**：启用了外键，删除父表数据会级联删除子表
4. **JSON字段**：需要 MySQL 5.7.8+ 版本支持
5. **全文索引**：`term_dictionary.aliases` 使用了 FULLTEXT 索引，需要 InnoDB 引擎

---

## 📚 相关文档

- [06-数据模型设计.md](../architecture/backend/06-数据模型设计.md) - 完整的数据库设计文档
- [数据库设计修复报告-2026-07-06.md](../architecture/数据库设计修复报告-2026-07-06.md) - 修复说明

---

## 🐛 故障排查

### 问题1：字符集错误

```sql
-- 检查数据库字符集
SHOW CREATE DATABASE electric_rag;

-- 修改字符集
ALTER DATABASE electric_rag CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 问题2：外键约束失败

```sql
-- 临时禁用外键检查
SET FOREIGN_KEY_CHECKS=0;

-- 执行操作...

-- 重新启用
SET FOREIGN_KEY_CHECKS=1;
```

### 问题3：权限不足

```sql
-- 查看当前用户权限
SHOW GRANTS FOR CURRENT_USER;

-- 授予创建数据库权限
GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost';
FLUSH PRIVILEGES;
```

---

**创建日期**：2026-07-06  
**版本**：v2.0  
**状态**：✅ 可用
