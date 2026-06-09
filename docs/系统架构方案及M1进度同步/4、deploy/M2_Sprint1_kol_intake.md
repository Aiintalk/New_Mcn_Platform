# MCN_DevOps_Agent — M2 Sprint 1 任务指令（红人入驻问卷）

> 角色：MCN_DevOps_Agent（运维 Claude）  
> PM 生成时间：2026-06-08  
> 前置条件：M1 全部迁移文件（001-005）已执行，后端 M2 Sprint 1 代码已部署  
> 完成后：回传 PM

---

## M2 Sprint 1 运维任务

### 1. 执行数据库迁移

```bash
# 执行文件：backend/migrations/006_kol_intake.sql
psql -U <db_user> -d <db_name> -f backend/migrations/006_kol_intake.sql
```

执行后确认以下内容：

**4 张新表已创建：**
- `kol_intake_questions`
- `kol_intake_configs`
- `kol_intake_links`
- `kol_intake_submissions`

**初始数据验证：**
```sql
-- 应返回 24 条题目
SELECT COUNT(*) FROM kol_intake_questions;

-- 应返回 2 条配置记录：conversation_bridge / report_generation
SELECT config_key FROM kol_intake_configs;

-- 应返回 1 条工具记录
SELECT tool_code, status FROM workspace_tools WHERE tool_code = 'kol-intake';
```

---

### 2. 安装 Python 依赖

```bash
cd backend
pip install python-docx weasyprint
pip show python-docx weasyprint  # 确认版本号
```

将两个包版本加入 `requirements.txt`：
```
python-docx==<version>
weasyprint==<version>
```

**依赖说明：**
- `python-docx`：生成 `.docx` 格式报告
- `weasyprint`：将报告 HTML 转为 `.pdf` 格式

> ⚠️ weasyprint 在部分 Linux 环境需要额外系统依赖：
> ```bash
> # Ubuntu/Debian
> apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0
> # CentOS/RHEL
> yum install -y pango cairo gdk-pixbuf2
> ```

---

### 3. 创建报告存储目录

```bash
mkdir -p backend/storage/intake_reports
# 确认后端进程用户有读写权限
chmod 755 backend/storage/intake_reports
```

---

### 4. 重启后端服务

```bash
# 依实际部署方式执行：
systemctl restart mcn-backend
# 或
pm2 restart mcn-backend
```

---

## 验收标准

| 检查项 | 验证命令 / 方法 | 预期结果 |
|--------|----------------|---------|
| 4张表已创建 | `\dt kol_intake_*`（psql） | 4张表存在 |
| 题目数量正确 | `SELECT COUNT(*) FROM kol_intake_questions` | 返回 24 |
| AI 配置已初始化 | `SELECT config_key FROM kol_intake_configs` | conversation_bridge / report_generation |
| 工具已注册 | `SELECT status FROM workspace_tools WHERE tool_code='kol-intake'` | dev |
| python-docx 安装成功 | `python -c "import docx; print('ok')"` | ok |
| weasyprint 安装成功 | `python -c "import weasyprint; print('ok')"` | ok |
| 存储目录可写 | `touch backend/storage/intake_reports/test.txt` | 无报错 |
| 路由注册成功 | `GET /api/intake/invalid_token` | 返回 404 |
