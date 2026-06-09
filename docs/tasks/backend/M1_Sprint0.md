# MCN_Backend_Agent — M1 Sprint 0 任务指令

> 角色：MCN_Backend_Agent（后端开发 Claude）  
> 工作目录：`backend/`（项目根目录下）  
> PM 生成时间：2026-06-05  
> 前置条件：无（本节点为第一个节点）  
> 完成后：验收通过，再执行 `tasks/M1_Sprint1.md`

---

## 必读文档（执行前请先阅读，路径相对于项目根目录）

1. `../MCN_M1_Base_基层文档包/MCN_M1_Base_API_utf8_bom.md` ← **最高优先级，接口契约**
2. `../project_docs/MCN_M1_部署与容量评估.md` ← 启动参数参考（第六节）

---

## 硬性约束（违反即返工）

| 约束 | 说明 |
|---|---|
| 所有接口以 `/api` 开头 | 不允许临时路径 |
| 返回结构统一 | `success/code/message/data` 四个字段必须存在 |
| 字段 `snake_case` | 无论请求还是响应 |
| 不开发业务逻辑 | 本节点只做骨架，不建表、不做 JWT |

---

## 本次任务：后端项目初始化

### 要做什么

1. 在 `backend/` 初始化 FastAPI 项目，目录结构：
   ```
   backend/
   ├── app/
   │   ├── main.py
   │   ├── core/
   │   │   ├── config.py      # 读取环境变量（DATABASE_URL / JWT_SECRET / JWT_EXPIRE_HOURS）
   │   │   ├── database.py    # SQLAlchemy async engine + session
   │   │   └── response.py    # 统一响应结构 ApiResponse
   │   ├── models/            # 空目录
   │   ├── schemas/           # 空目录
   │   ├── routers/
   │   │   └── health.py      # /api/health + /api/version
   │   ├── middlewares/       # 空目录
   │   └── adapters/
   │       ├── ai.py          # 占位（docstring + 函数签名，raise NotImplementedError）
   │       ├── tikhub.py      # 占位
   │       ├── oss.py         # 占位
   │       └── asr.py         # 占位
   ├── requirements.txt
   └── .env.example
   ```

2. `requirements.txt`：
   ```
   fastapi
   uvicorn[standard]
   sqlalchemy[asyncio]
   asyncpg
   python-dotenv
   passlib[bcrypt]
   python-jose[cryptography]
   pydantic-settings
   ```

3. `GET /api/health`（PUBLIC），返回：
   ```json
   {
     "success": true,
     "code": "OK",
     "message": "success",
     "data": {
       "status": "ok",
       "service": "mcn-api",
       "database": "ok",
       "time": "<ISO8601>"
     }
   }
   ```
   > 真实检测 DB 连接；DB 未就绪时 `database` 返回 `"error"`，接口仍返回 200

4. `GET /api/version`（PUBLIC），返回 `service/version/stage`

5. `app/core/response.py` 实现：
   - `ApiResponse[T]` Pydantic 模型（`success/code/message/data`）
   - `success_response(data, message)` 工厂函数
   - `error_response(code, message)` 工厂函数
   - 完整错误码常量，与 `MCN_M1_Base_API` 第 3 节**完全一致**

6. `.env.example`：
   ```
   DATABASE_URL=postgresql+asyncpg://postgres:admin123@localhost:5432/mcn_m1
   JWT_SECRET=change-me-in-production
   JWT_EXPIRE_HOURS=24
   INITIAL_ADMIN_USERNAME=admin
   INITIAL_ADMIN_PASSWORD=Admin@123456
   ENCRYPTION_KEY=change-me-32-chars-encryption-key
   ```

### 不做什么

- 不实现业务接口（users/workspace/tasks 等）
- 不建任何数据库表
- 不实现 JWT 鉴权

---

## 验收标准

1. `uvicorn app.main:app --reload` 无报错启动
2. `GET /api/health` 返回 `{"success":true,"data":{"status":"ok",...}}`
3. `GET /api/version` 返回 `{"success":true,"data":{"version":"0.1.0","stage":"m1-base"}}`
4. 目录结构符合上述规范
5. 错误码常量与 `MCN_M1_Base_API` 第 3 节完全一致

---

## 完成后输出格式

```
# 后端 Claude 执行结果 — M1 Sprint 0
## 1. 本次任务
## 2. 完成内容
## 3. 新增 API 清单（/api/health、/api/version）
## 4. 修改文件清单
## 5. 数据表变更情况（本次无）
## 6. 权限校验说明（本次无）
## 7. 自测结果（curl /api/health 实际响应）
## 8. 未完成事项
## 9. 需要 PM 决策的问题
## 10. 建议下一步
```

> ⚠️ 如需修改 `MCN_M1_Base_API` 中的接口定义，必须先停下回传 PM。
