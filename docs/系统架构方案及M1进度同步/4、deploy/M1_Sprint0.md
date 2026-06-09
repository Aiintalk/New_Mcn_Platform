# MCN_DevOps_Agent — M1 Sprint 0 任务指令

> 角色：MCN_DevOps_Agent（运维 Claude）  
> 工作目录：`deploy/`（项目根目录下）  
> PM 生成时间：2026-06-05  
> 前置条件：无（本节点为第一个节点）  
> 完成后：验收通过，再执行 `tasks/M1_Sprint1.md`

---

## 必读文档（执行前请先阅读，路径相对于项目根目录）

1. `../project_docs/MCN_M1_部署与容量评估.md` ← **最高优先级**
2. `../MCN_M1_Base_基层文档包/MCN_M1_Base_API_utf8_bom.md` ← 健康检查接口定义（第 4 节）

---

## 硬性约束（违反即返工）

| 约束 | 说明 |
|---|---|
| 密钥不硬编码 | 全部通过环境变量，`.env` 不入 git |
| PostgreSQL 不对外暴露 | 仅绑 `127.0.0.1` |
| SSE 必须关闭 buffering | `proxy_buffering off` |
| 不修改业务代码 | 只操作 `deploy/` 目录及项目根目录 `.gitignore` |

---

## 本次任务：运维基础配置文件

### 要做什么

1. 在 `deploy/` 创建以下结构：
   ```
   deploy/
   ├── nginx/
   │   └── mcn-m1.conf
   ├── scripts/
   │   ├── start.sh
   │   ├── stop.sh
   │   └── health-check.sh
   ├── sql/              # 预留目录
   └── README.md
   ```

2. `deploy/nginx/mcn-m1.conf`：
   ```nginx
   server {
       listen 80;
       server_name _;
       client_max_body_size 10m;

       location /api/ {
           proxy_pass http://127.0.0.1:8000;
           proxy_buffering off;
           proxy_read_timeout 300s;
           proxy_http_version 1.1;
           proxy_set_header Connection '';
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }

       location / {
           root /var/www/mcn;
           try_files $uri /index.html;
       }

       # HTTPS 预留（Sprint 4 配置）
       # listen 443 ssl;
   }
   ```

3. `deploy/scripts/health-check.sh`：
   ```bash
   #!/bin/bash
   RESPONSE=$(curl -s http://localhost:8000/api/health)
   echo "$RESPONSE" | python3 -m json.tool
   STATUS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('status',''))")
   if [ "$STATUS" != "ok" ]; then
     echo "ERROR: health check failed (status=$STATUS)"
     exit 1
   fi
   echo "OK: service is healthy"
   ```

4. `deploy/README.md` 包含：
   - 环境要求（Python 3.11+、Node 20.x、PostgreSQL 14+、Nginx）
   - 本地开发启动步骤
   - 测试服部署步骤（预留章节，Sprint 4 补充）
   - 健康检查命令
   - 回滚方式

5. 项目根目录 `.gitignore`：
   ```
   .env
   .env.local
   .env.*.local
   __pycache__/
   *.py[cod]
   .venv/
   venv/
   node_modules/
   dist/
   build/
   *.log
   logs/
   *.pyc
   ```

### 不做什么

- 不部署到真实服务器（Sprint 4 任务）
- 不修改 `frontend/` 或 `backend/` 代码
- 不配置 SSL/HTTPS

---

## 验收标准

1. `deploy/` 目录结构符合规范
2. `nginx/mcn-m1.conf` 包含 `proxy_buffering off`
3. `bash -n deploy/scripts/health-check.sh` 语法检查通过
4. `deploy/README.md` 包含环境要求和本地启动步骤
5. 根目录 `.gitignore` 包含 `.env` 规则

---

## 完成后输出格式

```
# 运维 Claude 执行结果 — M1 Sprint 0
## 1. 本次任务
## 2. 配置文件清单
## 3. 健康检查脚本验证结果（bash -n 输出）
## 4. 风险提示
## 5. 需要 PM 决策的问题
## 6. 建议下一步
```
