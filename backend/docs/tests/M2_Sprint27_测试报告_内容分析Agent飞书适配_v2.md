# M2 Sprint27 测试报告：内容分析 Agent 飞书适配 v2

> 日期：2026-09-04
> 分支：`codex/content-analysis-agent-dev`
> 基线：`5cceb2f8e22cf0fa2ea7279f9e7fc669b590b0f3`

## 一、结论

v1.8 飞书适配与阶段一内部合同收敛的开发侧测试通过。最终返修关闭了空日报混入全局既有跨项目候选、自动入库误要求四个项目适配维度齐全两个阻断。内容分析专项 391/391 通过，专项覆盖率 91%；最终代码的正式覆盖率门禁收集 2405 条，2404 通过、1 跳过、0 失败，整体覆盖率 80.5%，六个分层全部达标。

真实飞书只读冒烟未执行：仓库中没有可直接复用且安全的只读客户端配置。本报告不把模拟测试写成真实联调成功。

## 二、测试先行证据

1. 新增飞书适配测试首次收集因缺少 `FeishuRecordPage` 失败，证明测试先于实现。
2. 分页总数完整性测试首次收集因分页对象不支持 `total` 失败，随后补最小总数合同与结束校验。
3. 旧专项首次回归出现视觉枚举、媒体字段和逐条同步状态的收集/断言失败；按 v1.8 删除旧正向路径并更新回归口径。
4. 空日报与单维度适配两个返修测试先运行并出现 2 个预期失败：前者实际挂载 1 个既有跨项目候选，后者实际生成 0 个入库候选。最小修复后，两个新用例与既有无适配理由硬门槛用例合计 9/9 通过。

## 三、命令与结果

### 1. 内容分析专项

```bash
cd backend
env DATABASE_URL='<本地测试库连接>' JWT_SECRET='<仅测试用密钥>' .venv/bin/pytest -q tests/unit/services/content_analysis --disable-warnings --maxfail=10 --override-ini=addopts=
```

结果：391 通过、0 失败、0 跳过，1.13 秒，退出码 0。

### 2. 内容分析专项覆盖率

```bash
cd backend
.venv/bin/coverage erase
env DATABASE_URL='<本地测试库连接>' JWT_SECRET='<仅测试用密钥>' .venv/bin/coverage run --source=app/services/content_analysis -m pytest -q tests/unit/services/content_analysis --disable-warnings --override-ini=addopts=
.venv/bin/coverage report -m
```

结果：391 通过；专项总覆盖率 91%。分文件：公开入口 100%、标准适配 88%、分析边界 94%、确定性逻辑 95%、领域模型 92%、引擎 91%、飞书适配 88%。

### 3. 仓库完整后端测试尝试

```bash
cd backend
/opt/homebrew/bin/timeout 1200 env DATABASE_URL='<本地测试库连接>' JWT_SECRET='<仅测试用密钥>' PYTEST_ADDOPTS='-o faulthandler_timeout=300' .venv/bin/pytest tests/ -q --disable-warnings --override-ini=addopts=
```

结果：收集阶段 1 个既有错误，未进入业务测试。原因是 `tests/intake/conftest.py` 在非顶层声明 `pytest_plugins`，pytest 9 已不再支持。测试插件还自动改写了一次既有并发报告时间戳，已立即恢复，最终没有范围外差异。

### 4. 最大可执行后端回归

```bash
cd backend
/opt/homebrew/bin/timeout 1200 env DATABASE_URL='<本地测试库连接>' JWT_SECRET='<仅测试用密钥>' PYTEST_ADDOPTS='-o faulthandler_timeout=300' .venv/bin/pytest tests/unit tests/integration -q --disable-warnings --override-ini=addopts=
```

最终同一集合由下方正式覆盖率门禁完整执行，不再用较早的中间回归数据作为交付结论。

### 5. 正式覆盖率门禁

```bash
cd backend
/opt/homebrew/bin/timeout 1200 env DATABASE_URL='<本地测试库连接>' JWT_SECRET='<仅测试用密钥>' PYTEST_ADDOPTS='-o faulthandler_timeout=300' .venv/bin/python scripts/run_coverage.py --gate
```

结果：收集 2405 条；2404 通过、1 跳过、0 失败、14 条警告，464.19 秒，退出码 0。覆盖率：`app/core` 100.0%、`app/models` 100.0%、`app/services` 88.8%、`app/routers` 73.0%、`app/adapters` 80.2%、`app/middlewares` 100.0%、整体 80.5%，全部通过。

### 6. 静态检查

```bash
cd backend
.venv/bin/python -m compileall -q app/services/content_analysis tests/unit/services/content_analysis
git diff --check
```

结果：两项退出码均为 0。

## 四、数据与外部调用

- 飞书客户端全部由模拟对象注入；未读取、写入、下载或修改真实飞书记录。
- 匿名 fixture 仍只有 2 条合成内容、1 条匿名关系和 1 份匿名上下文，未增加真实账号、项目、长转写、内网地址或凭据。
- 未调用真实或付费模型，未连接生产数据库，未执行迁移、部署或发布。
- 飞书正式字段清单尚无业务来源平台；现阶段只保留作品编号/链接追溯，不把采集入口写成抖音等平台事实。
