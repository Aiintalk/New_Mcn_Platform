# M2 Sprint24 后端任务 - 外部 KOL 只读 API v1

> 日期：2026-08-05
> 需求来源：本地新增接口，用于让另一个项目通过密钥只读访问红人数据。
> 契约来源：`backend/docs/base/MCN_M2_Base_API.md` §6B，`backend/docs/base/MCN_M2_Base_Database.md` 顶部说明。

---

## 一、目标

新增一个给外部项目使用的只读 KOL API：

- 只读取现有 `kols` 表，不开放数据库账号、不暴露 PostgreSQL 端口。
- 使用请求头 `X-API-Key` 鉴权，密钥从后端环境变量 `EXTERNAL_KOLS_API_KEY` 读取。
- 支持本地测试，后续可通过阿里云 Nginx + HTTPS 暴露给另一台电脑或另一个项目访问。
- 不改前端页面，不新增写接口。

---

## 二、范围

### 做

| 模块 | 文件 | 内容 |
|------|------|------|
| 配置 | `backend/app/core/config.py` | 新增 `external_kols_api_key`，读取 `EXTERNAL_KOLS_API_KEY` |
| 路由 | `backend/app/routers/external_kols.py` | 新增 `GET /api/external/kols` 和 `GET /api/external/kols/{kol_id}` |
| 入口 | `backend/app/main.py` | 注册 `external_kols_router` |
| 模型 | `backend/app/models/kol.py` | ORM 补齐 `external_id` 字段，与既有 `kols.external_id` 对齐 |
| 示例配置 | `backend/.env.example` | 增加 `EXTERNAL_KOLS_API_KEY=` |
| 测试 | `backend/tests/unit/routers/test_external_kols_unit.py` | helper、鉴权、状态计算、空数据、详情边界 |
| 测试 | `backend/tests/integration/routers/test_external_kols.py` | API 鉴权、列表筛选分页、详情、404 |

### 不做

- 不新增数据库表。
- 不新增写入、更新、删除接口。
- 不把数据库端口或数据库账号暴露给外部项目。
- 不把真实密钥写入 Git。
- 不在调用方硬写死生产地址；调用方应按环境读取 API base URL。

---

## 三、接口清单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/external/kols` | 红人列表，支持分页、关键词、平台、计算状态筛选 |
| GET | `/api/external/kols/{kol_id}` | 单个红人详情 |

鉴权方式：

```http
X-API-Key: <EXTERNAL_KOLS_API_KEY>
```

响应格式统一为标准信封：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {}
}
```

---

## 四、数据说明

数据来源为现有 `kols` 表。接口默认排除软删数据：

```sql
WHERE deleted_at IS NULL
```

本任务不新增 migration。`external_id` 是 M1 `kols` 表既有字段，ORM 补齐是为了让接口字段与数据库契约一致。

---

## 五、部署注意事项

- 本地测试地址：`http://localhost:8000/api/external/kols`
- 阿里云生产地址：由运维配置域名和 Nginx 反代，例如 `https://<domain>/api/external/kols`
- 后端 `.env` 必须设置 `EXTERNAL_KOLS_API_KEY=<强随机密钥>`
- `.env` 修改后必须重启后端，热重载不保证重新读取环境变量
- 生产环境只开放 `80/443`，不直接开放 `8000` 或 `5432`
- 如果另一个项目的浏览器前端直接调用本接口，需要把该前端域名加入 `CORS_ORIGINS`
- 如果另一个项目是后端服务调用本接口，CORS 不影响服务端请求

---

## 六、验收要求

- [x] 正常密钥可读取列表和详情
- [x] 缺少或错误 `X-API-Key` 返回 401 标准信封
- [x] 未配置 `EXTERNAL_KOLS_API_KEY` 返回 503 标准信封
- [x] 空数据列表返回空数组和分页信息
- [x] 详情不存在返回 404 标准信封
- [x] 不返回软删红人
- [x] 默认不返回列表 `tikhub_raw`，避免响应过大
- [x] 契约文档、README、测试报告、PM 记忆已同步
