# M2 Sprint24 运维端任务 - 外部 KOL 只读 API 部署配置 v1

> 日期：2026-08-05
> 目标：把外部 KOL 只读 API 在阿里云环境中安全暴露给指定项目访问。
> 相关后端任务：`backend/docs/tasks/M2_Sprint24_后端任务_外部KOL只读API_v1.md`

---

## 一、部署结论

该接口可以在阿里云部署后继续使用。推荐方式是：

- 后端 uvicorn 仍监听内网或本机地址，例如 `127.0.0.1:8000`。
- Nginx 对外暴露 `https://<domain>/api/external/kols`。
- 另一个项目通过 HTTPS + `X-API-Key` 调用接口。
- 不开放 PostgreSQL 端口，不给外部项目数据库账号。

---

## 二、环境变量

后端 `.env` 必须包含：

```env
EXTERNAL_KOLS_API_KEY=<强随机密钥>
CORS_ORIGINS=https://<本系统前端域名>,https://<需要浏览器直连本接口的调用方域名>
```

生成密钥示例：

```bash
openssl rand -hex 32
```

注意：

- 真实密钥只放服务器 `.env` 或环境变量管理系统。
- 不提交 `.env`。
- 修改 `.env` 后必须重启后端进程。

---

## 三、Nginx 和安全组

推荐开放：

| 端口 | 是否公网开放 | 说明 |
|------|--------------|------|
| 80 | 是 | HTTP 跳 HTTPS |
| 443 | 是 | 对外 API 和前端访问 |
| 8000 | 否 | uvicorn 内部端口，由 Nginx 反代 |
| 5432 | 否 | PostgreSQL 仅本机或内网访问 |

如公司有固定出口 IP，可在 Nginx 或阿里云安全组中限制调用来源 IP。

---

## 四、调用方配置

调用方不要把地址和密钥硬写死在代码里，建议用环境变量：

```env
MCN_KOLS_API_BASE_URL=https://<domain>/api/external/kols
MCN_KOLS_API_KEY=<与后端 EXTERNAL_KOLS_API_KEY 一致的密钥>
```

本地联调可改为：

```env
MCN_KOLS_API_BASE_URL=http://localhost:8000/api/external/kols
```

---

## 五、部署后验证

在服务器本机验证：

```bash
curl -H "X-API-Key: <密钥>" \
  "http://127.0.0.1:8000/api/external/kols?page=1&page_size=20"
```

通过公网域名验证：

```bash
curl -H "X-API-Key: <密钥>" \
  "https://<domain>/api/external/kols?page=1&page_size=20"
```

错误密钥验证：

```bash
curl -i -H "X-API-Key: wrong" \
  "https://<domain>/api/external/kols?page=1&page_size=20"
```

预期返回：

```json
{
  "success": false,
  "code": "EXTERNAL_API_KEY_INVALID",
  "message": "外部 API 密钥无效",
  "data": null
}
```

---

## 六、CORS 说明

- 如果调用方是后端服务调用本接口，CORS 不影响。
- 如果调用方是浏览器前端直接调用本接口，需要把调用方前端域名加入后端 `CORS_ORIGINS`。
- 本地 Vite 端口可能是 `5173`、`5174`、`5175`，本地测试时 `CORS_ORIGINS` 要包含实际端口。

---

## 七、回滚

如需临时关闭外部接口访问：

1. 删除或清空服务器 `.env` 中的 `EXTERNAL_KOLS_API_KEY`。
2. 重启后端。
3. 接口会返回 `503 EXTERNAL_API_KEY_NOT_CONFIGURED`，外部调用无法继续读取数据。
