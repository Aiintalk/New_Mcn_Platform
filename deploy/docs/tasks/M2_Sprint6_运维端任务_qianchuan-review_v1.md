# M2 Sprint6 运维端任务 — qianchuan-review 上线

## 1. Nginx 超时配置

为 `/api/tools/qianchuan-review/generate` 接口单独配置长超时，防止 AI 生成超 60s 时连接被 Nginx 强制断开。

在 Nginx 配置文件（通常为 `/etc/nginx/sites-available/mcn_platform`）的 `/api/` location 块之前，添加：

```nginx
location /api/tools/qianchuan-review/generate {
    proxy_pass http://127.0.0.1:8000;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 10s;
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

完成后：
```bash
nginx -t && systemctl reload nginx
```

## 2. python-snappy 系统依赖

.pages 文件解析依赖 python-snappy，需要系统级 libsnappy 库。

```bash
# Ubuntu / Debian
apt-get install -y libsnappy-dev

# 确认 python-snappy 已在 requirements.txt
grep -i snappy /opt/mcn_platform/backend/requirements.txt
```

若 requirements.txt 中无 python-snappy，执行：
```bash
cd /opt/mcn_platform/backend
source .venv/bin/activate
pip install python-snappy
pip freeze | grep snappy >> requirements.txt
```

## 3. 旧数据迁移（一次性，上线后旧系统下线前执行）

```bash
cd /opt/mcn_platform/backend
source .venv/bin/activate

# 先 dry-run 确认条数
python scripts/migrate_qianchuan_reports.py \
    --reports-dir /opt/qianchuan-review/reports/ \
    --dry-run

# 确认无误后正式迁移
python scripts/migrate_qianchuan_reports.py \
    --reports-dir /opt/qianchuan-review/reports/
```

迁移后旧报告归属 admin 账号，其他 operator 账号不可见。

## 4. 重启后端服务

```bash
pm2 restart mcn-backend
pm2 logs mcn-backend --lines 20
```
