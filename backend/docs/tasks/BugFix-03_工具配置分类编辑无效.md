# MCN_Backend_Agent — BugFix-03 任务指令（工具配置分类编辑无效）

> 角色：MCN_Backend_Agent（后端开发 Claude）
> 工作目录：`backend/`
> PM 生成时间：2026-06-10
> 优先级：P1（影响用户使用）
> 完成后：回传 PM

---

## Bug 描述

**现象：** 工具配置页面中，编辑分类字段后保存成功，但数据没有变化。

**影响：** 运营人员无法修改工具分类，影响工具管理。

---

## 根因分析

**文件：** `backend/app/routers/admin_workspace.py`

**问题1：** `UpdateToolRequest` 模型缺少 `category` 字段定义（38-44 行）

**问题2：** `admin_update_tool` 函数缺少 `category` 字段的更新逻辑（91-103 行）

---

## 修复方案

### 1. 更新 `UpdateToolRequest` 模型

**位置：** `backend/app/routers/admin_workspace.py` 第 38-44 行

**修改前：**
```python
class UpdateToolRequest(BaseModel):
    tool_name: str | None = None
    description: str | None = None
    status: str | None = None
    tags: list | None = None
    config: dict | None = None
    sort_order: int | None = None
```

**修改后：**
```python
class UpdateToolRequest(BaseModel):
    tool_name: str | None = None
    description: str | None = None
    category: str | None = None  # 新增：支持修改分类
    status: str | None = None
    tags: list | None = None
    config: dict | None = None
    sort_order: int | None = None
```

### 2. 更新 `admin_update_tool` 函数

**位置：** `backend/app/routers/admin_workspace.py` 第 91-103 行

**修改前：**
```python
values: dict = {}
if body.tool_name is not None:
    values["tool_name"] = body.tool_name
if body.description is not None:
    values["description"] = body.description
if body.status is not None:
    values["status"] = body.status
if body.tags is not None:
    values["tags"] = body.tags
if body.config is not None:
    values["config"] = body.config
if body.sort_order is not None:
    values["sort_order"] = body.sort_order
```

**修改后：**
```python
values: dict = {}
if body.tool_name is not None:
    values["tool_name"] = body.tool_name
if body.description is not None:
    values["description"] = body.description
if body.category is not None:  # 新增：支持修改分类
    values["category"] = body.category
if body.status is not None:
    values["status"] = body.status
if body.tags is not None:
    values["tags"] = body.tags
if body.config is not None:
    values["config"] = body.config
if body.sort_order is not None:
    values["sort_order"] = body.sort_order
```

---

## 测试验证

### 1. 手动测试

1. 启动后端服务
2. 登录管理员账号
3. 进入「工具配置」页面
4. 点击某个工具的「编辑」按钮
5. 修改「分类」字段（例如改为"测试分类"）
6. 点击「保存」
7. 刷新页面，验证分类字段是否更新成功

### 2. API 测试

```bash
# 测试更新接口
curl -X PUT "http://localhost:8000/api/admin/workspace/tools/:tool_code" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "测试分类"
  }'

# 预期返回：更新成功
```

---

## 回传 PM 内容

完成后回传以下信息：

1. ✅ UpdateToolRequest 模型已添加 category 字段
2. ✅ admin_update_tool 函数已添加 category 更新逻辑
3. ✅ 手动测试通过（分类字段保存成功）
4. ✅ API 测试通过

---

**PM 备注：**
- 这是简单字段缺失问题，修复后立即测试验证
- 确保前端发送的字段名和后端接收的字段名一致（都是 `category`）
- 修复后不需要数据库迁移
