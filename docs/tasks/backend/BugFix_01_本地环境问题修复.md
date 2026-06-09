# 后端任务单 · BugFix-01 本地环境问题修复

> 发现时间：2026-06-09
> 触发场景：Mac 本地下载代码后初次运行
> 负责人：后端
> 优先级：Bug 1 & Bug 2 高优先级，Bug 3 顺手修
> **修复完成时间：2026-06-09**
> **整体状态：✅ Bug 1 / 2 / 3 已修复验证通过，Bug 4 待复核**

---

## Bug 1 — TikHub Key 无法保存【高优先级】

### 问题描述

在「服务配置 → TikHub 配置」页面点击「+ 新增 Key」，填写后提交无任何反应，Key 未被保存。

### 根因

前端表单提交字段名为 `api_key`，但后端 Pydantic schema 定义的字段名为 `secret`，字段名不匹配导致 FastAPI 返回 HTTP 422 验证错误。  
前端 `handleResponse` 无法解析 422 的错误体格式（422 返回 `{"detail":[...]}` 而非标准 `{"success":false,...}`），最终 toast 显示为空白，用户无任何提示。

**附带问题：** 前端调用 `POST /enable` 和 `POST /disable` 端点，但后端未实现这两个路由，导致启用/停用操作静默失败。

### 修复方案

**文件：`backend/app/routers/admin_credentials.py`**

**修改 1：CreateCredentialRequest 字段名**

```python
# 修改前
class CreateCredentialRequest(BaseModel):
    provider: str
    label: str
    secret: str          # ← 错误
    weight: int = 1
    quota_limit: int | None = None
    config: dict | None = None

# 修改后
class CreateCredentialRequest(BaseModel):
    provider: str
    label: str
    api_key: str         # ← 与前端保持一致
    weight: int = 1
    quota_limit: int | None = None
    config: dict | None = None
```

**修改 2：create_credential 函数里替换字段引用**

```python
# 修改前
secret_enc = body.secret
secret_tail = body.secret[-4:] if len(body.secret) >= 4 else body.secret

# 修改后
secret_enc = body.api_key
secret_tail = body.api_key[-4:] if len(body.api_key) >= 4 else body.api_key
```

**修改 3：新增 enable / disable 路由**

参考现有 PATCH 路由写法，在文件末尾添加：

```python
@router.post("/admin/config/credentials/{credential_id}/enable", response_model=ApiResponse)
async def enable_credential(
    credential_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        cred = (await session.execute(
            select(ServiceCredential).where(ServiceCredential.id == credential_id)
        )).scalar_one_or_none()
        if cred is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "密钥不存在")
        await session.execute(
            update(ServiceCredential)
            .where(ServiceCredential.id == credential_id)
            .values(status="enabled")
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="enable_credential",
            target_type="credential",
            target_id=credential_id,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()
        await session.refresh(cred)
    return success_response(data=_cred_to_dict(cred))


@router.post("/admin/config/credentials/{credential_id}/disable", response_model=ApiResponse)
async def disable_credential(
    credential_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        cred = (await session.execute(
            select(ServiceCredential).where(ServiceCredential.id == credential_id)
        )).scalar_one_or_none()
        if cred is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "密钥不存在")
        await session.execute(
            update(ServiceCredential)
            .where(ServiceCredential.id == credential_id)
            .values(status="disabled")
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="disable_credential",
            target_type="credential",
            target_id=credential_id,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()
        await session.refresh(cred)
    return success_response(data=_cred_to_dict(cred))
```

### 验收结果 ✅ 2026-06-09

| 验收项 | 结果 |
|--------|------|
| 字段改名 + create 函数 2 处引用 | ✅ 创建成功，`secret_tail="7890"` |
| 新增 enable/disable 路由 | ✅ disable → `"status":"disabled"`，enable → `"status":"enabled"` |

---

## Bug 2 — 添加红人被 TikHub 未配置阻塞【高优先级】

### 问题描述

在「红人管理」页面点击「+ 新增红人」，填写信息后提交，因 TikHub 未配置导致接口报错，添加失败。

### 根因

`create_kol` 接口在创建红人记录时，内部自动调用了 TikHub 抓取粉丝数据的逻辑。TikHub 未配置时此调用失败，整个创建操作被阻断。

**这是错误的设计**：红人的基本信息（姓名、分类、账号ID等）入库不应依赖 TikHub。TikHub 数据是附加的数据丰富操作，应由运营人员在创建完成后手动点击「重新抓取」触发。

### 修复方案

**文件：`backend/app/routers/admin_kols.py`（确认文件名）**

在 `create_kol` 函数中，移除自动调用 TikHub 抓取的代码段。  
创建成功后直接返回 `success_response`，不触发任何外部 API 调用。

TikHub 抓取逻辑**仅保留**在「重新抓取」对应的独立接口中（如 `POST /admin/kols/{id}/fetch-tikhub`）。

### 验收结果 ✅ 2026-06-09

| 验收项 | 结果 |
|--------|------|
| create_kol 删除 TikHub 自动调用（删除 4 行） | ✅ 无 tikhub 字段，直接返回红人基本信息 |

---

## Bug 3 — AI 管理页两个字段名返回错误【中优先级】

### 问题描述

- AI 配置页的 Key 列表，「并发」列显示为 `undefined/5`
- AI 统计页的「模型使用占比」甜甜圈图全部显示 0%

### 根因

后端返回字段名与前端接口类型定义不一致：

| 接口 | 后端实际返回字段 | 前端期望字段 | 影响 |
|------|----------------|------------|------|
| `GET /admin/ai/keys` 每条记录 | `active_requests` | `concurrency` | 并发数显示 undefined |
| `GET /admin/ai/stats` by_model | `percentage`（0~1 小数） | `pct`（0~100 整数） | 占比图全显 0% |

### 修复方案

**文件：`backend/app/routers/admin_ai.py`**

**修改 1：list_keys — 在每条 item 中补充 `concurrency` 字段**

在 `GET /keys` 接口构建每条记录时，新增一行：

```python
# 在现有 "active_requests": r.active_requests 旁边加上：
"concurrency": r.active_requests,   # 前端 AiKeyRecord 用 concurrency
```

**修改 2：ai_stats — by_model 字段名和值修正**

```python
# 修改前
"percentage": round(int(r.tokens) / total_tokens, 4) if total_tokens else 0,

# 修改后
"pct": round(int(r.tokens) / total_tokens * 100, 1) if total_tokens else 0,
```

### 验收结果 ✅ 2026-06-09

| 验收项 | 结果 |
|--------|------|
| list_keys 加 concurrency 字段 | ✅ `"concurrency":0` / `"concurrency":5` 正常返回 |
| by_model.percentage → pct（乘以100取整） | ✅ `"pct":68` / `"pct":32`，无 percentage 字段 |

---

## Bug 4 — 修改密码旧密码错误无提示【待复核，暂不修改代码】

### 问题描述

新用户首次登录强制修改密码时，输入错误的当前密码后提交，页面无任何提示。

### 排查结论

经过完整代码链路排查，**前后端代码逻辑均正确**：
- 后端返回 `{"success": false, "code": "AUTH_INVALID_PASSWORD", "message": "旧密码错误"}`
- 前端 `handleResponse` 正确抛出 `Error("旧密码错误")`
- `ChangePasswordPage.tsx` catch 块正确调用 `message.error(err.message)`

**可能的非代码原因：**
- 用户不知道新账号初始密码（由管理员设置），输错后误以为无提示
- Antd toast 默认 3 秒消失，被用户忽略

### 后续动作

由测试同学手动复核：
1. 创建新 operator 账号（保持 `password_changed_at = NULL`）
2. 用该账号登录，进入强制修改密码页
3. 「当前密码」故意输错，观察是否出现 toast 提示
4. 若确认无提示，反馈给后端排查是否有全局中间件干扰

---

## 修复记录汇总

| Bug | 状态 | 修复时间 |
|-----|------|---------|
| Bug 1a — TikHub 字段名 secret→api_key | ✅ 已修复 | 2026-06-09 |
| Bug 1b — enable/disable 路由缺失 | ✅ 已修复 | 2026-06-09 |
| Bug 2 — 添加红人被 TikHub 阻塞 | ✅ 已修复 | 2026-06-09 |
| Bug 3a — concurrency 字段缺失 | ✅ 已修复 | 2026-06-09 |
| Bug 3b — by_model.pct 字段名/值错误 | ✅ 已修复 | 2026-06-09 |
| Bug 4 — 改密码无提示 | ⏳ 待复核 | — |

## 后续待办

- [ ] Bug 4：测试同学手动复核改密码错误提示是否正常
- [ ] 本地重新执行 `seed_local.sql`，验证 TikHub Key 可正常录入
- [ ] 修复代码 push 到 GitHub，团队成员拉取最新代码
