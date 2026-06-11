# MCN_Deploy_Agent — M1 Sprint 5 任务指令（TikHub 独立池化部署）

> 角色：MCN_Deploy_Agent（运维/部署 Claude）
> 工作目录：`backend/`
> PM 生成时间：2026-06-10
> 前置条件：后端接口已通过测试
> 完成后：回传 PM，等待前端联调

---

## M1 Sprint 5 目标

将 TikHub 从通用 Key 池迁移到独立池，确保数据平滑迁移且不丢失。

---

## 一、部署检查清单

### 1.1 数据库备份

**执行前必须备份：**

```bash
# 备份当前数据库
pg_dump -h localhost -U postgres -d mcn_m1 > backup_before_tikhub_migration_$(date +%Y%m%d_%H%M%S).sql

# 验证备份文件
ls -lh backup_before_tikhub_migration_*.sql
```

### 1.2 检查现有 TikHub 配置

```sql
-- 查询现有 TikHub 配置数量
SELECT COUNT(*) FROM service_credentials WHERE provider = 'tikhub';

-- 查看现有 TikHub 配置详情
SELECT id, label, status, weight FROM service_credentials WHERE provider = 'tikhub';
```

**预期结果：**
- 应该至少有 1 条 TikHub 配置记录
- 记录这些 ID 和 label，用于后续验证迁移结果

---

## 二、执行迁移

### 2.1 按顺序执行迁移文件

**在 `backend/migrations/` 目录下按顺序执行：**

```bash
cd backend/migrations

# 1. 创建 tikhub_credentials 表
psql -h localhost -U postgres -d mcn_m1 -f 010_tikhub_credentials.sql

# 2. 创建 tikhub_call_logs 表
psql -h localhost -U postgres -d mcn_m1 -f 011_tikhub_call_logs.sql

# 3. 迁移数据
psql -h localhost -U postgres -d mcn_m1 -f 012_migrate_tikhub_to_dedicated_pool.sql
```

### 2.2 验证迁移结果

```sql
-- 验证 tikhub_credentials 表有数据
SELECT COUNT(*) FROM tikhub_credentials;

-- 验证 tikhub_call_logs 表创建成功
SELECT COUNT(*) FROM tikhub_call_logs;

-- 验证迁移的数据
SELECT id, label, status, max_concurrent FROM tikhub_credentials;

-- 验证 service_credentials 中的 TikHub 记录是否还在
SELECT id, label, status FROM service_credentials WHERE provider = 'tikhub';
```

**预期结果：**
- `tikhub_credentials` 表的记录数应该等于迁移前的 `service_credentials` 中 TikHub 记录数
- `tikhub_call_logs` 表为空（刚创建，还没有调用日志）
- `service_credentials` 中的 TikHub 记录应该还存在（迁移脚本默认不删除）

---

## 三、清理旧数据（可选）

### 3.1 确认新配置正常工作后，删除旧记录

**⚠️ 警告：删除前必须确保后端接口已验证通过！**

```sql
-- 删除 service_credentials 中的 TikHub 记录
DELETE FROM service_credentials WHERE provider = 'tikhub';

-- 验证删除结果
SELECT COUNT(*) FROM service_credentials WHERE provider = 'tikhub';
-- 应该返回 0
```

### 3.2 验证清理结果

```sql
-- 验证 service_credentials 表只剩其他 provider
SELECT DISTINCT provider FROM service_credentials;

-- 应该返回：oss、asr 等，但不包括 tikhub
```

---

## 四、后端服务重启

### 4.1 重启后端服务

```bash
# 如果使用 pm2
pm2 restart mcn-backend

# 如果使用 systemd
sudo systemctl restart mcn-backend

# 如果使用 docker
docker-compose restart backend
```

### 4.2 检查后端日志

```bash
# 检查启动日志
pm2 logs mcn-backend --lines 50

# 或
journalctl -u mcn-backend -n 50
```

**预期结果：**
- 无数据库连接错误
- 无模型导入错误
- FastAPI 服务正常启动

---

## 五、功能验证

### 5.1 验证 TikHub 接口可访问

**使用 curl 或 Postman 测试：**

```bash
# 测试统计接口（需要 admin token）
curl -X GET "http://localhost:8000/api/admin/tikhub/stats" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# 预期返回：
# {
#   "overview": { "total_calls": 0, "today_calls": 0, ... },
#   "endpoints": [],
#   "users": [],
#   "trend": []
# }
```

### 5.2 验证 Key 管理接口

```bash
# 测试 Key 列表接口
curl -X GET "http://localhost:8000/api/admin/tikhub/keys" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# 预期返回迁移后的 Key 列表
```

### 5.3 验证并发控制

**通过前端或 curl 调用 TikHub 接口，观察并发计数：**

```sql
-- 查看并发计数
SELECT id, label, active_requests, max_concurrent FROM tikhub_credentials;
```

**预期结果：**
- `active_requests` 应该随调用增加
- 调用结束后应该减少（释放）

---

## 六、数据回滚方案

如果迁移后出现问题，执行回滚：

### 6.1 恢复旧数据结构

```sql
-- 1. 停止后端服务

-- 2. 删除新表
DROP TABLE IF EXISTS tikhub_call_logs;
DROP TABLE IF EXISTS tikhub_credentials;

-- 3. 恢复数据库备份
psql -h localhost -U postgres -d mcn_m1 < backup_before_tikhub_migration_XXX.sql

-- 4. 重启后端服务
```

### 6.2 验证回滚结果

```sql
-- 验证 service_credentials 中的 TikHub 记录已恢复
SELECT COUNT(*) FROM service_credentials WHERE provider = 'tikhub';
```

---

## 七、前端部署

### 7.1 前端无需特殊部署

TikHub 配置页面重构是纯前端修改，无数据库变更。

**正常部署即可：**

```bash
cd frontend

# 安装依赖（如果有新依赖）
npm install

# 构建生产版本
npm run build

# 部署到服务器（根据实际部署方式）
# 例如：scp -r dist/* user@server:/path/to/frontend/
```

### 7.2 验证前端功能

**访问 TikHub 配置页面：**

1. 登录管理员账号
2. 进入「工具配置」→「TikHub 配置」
3. 验证页面布局：
   - ✅ 统计卡片区域显示
   - ✅ 图表区域显示
   - ✅ 过滤器可使用
   - ✅ Key 列表显示迁移后的数据
   - ✅ 接口统计表格显示
   - ✅ 用户排行表格显示

---

## 八、监控和日志

### 8.1 监控 TikHub 调用情况

**部署后持续监控 24 小时：**

```sql
-- 查看调用日志
SELECT
  endpoint,
  status,
  COUNT(*) AS calls,
  AVG(latency_ms) AS avg_latency
FROM tikhub_call_logs
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY endpoint, status
ORDER BY calls DESC;
```

### 8.2 检查错误日志

```sql
-- 查看失败的调用
SELECT
  endpoint,
  error_message,
  COUNT(*) AS fail_count
FROM tikhub_call_logs
WHERE status = 'failure'
  AND created_at >= NOW() - INTERVAL '24 hours'
GROUP BY endpoint, error_message
ORDER BY fail_count DESC;
```

---

## 九、回传 PM 内容

完成后回传以下信息：

1. ✅ 数据库备份已完成
2. ✅ 迁移文件已执行（010/011/012）
3. ✅ 迁移结果已验证
4. ✅ 旧数据已删除（可选）
5. ✅ 后端服务已重启
6. ✅ 功能验证通过
7. ✅ 前端已部署
8. ✅ 监控日志已开启

并告知：
- 迁移了多少条 TikHub 配置记录
- 是否删除了 service_credentials 中的旧记录
- 是否遇到错误或需要回滚
- 24 小时监控结果（如果已观察）

---

**PM 备注：**
- 执行迁移前必须备份数据库
- 建议在测试环境先验证迁移流程
- 删除旧数据前必须确保新功能正常工作
- 保留备份文件至少 7 天
- 如遇到问题立即回滚并通知 PM
