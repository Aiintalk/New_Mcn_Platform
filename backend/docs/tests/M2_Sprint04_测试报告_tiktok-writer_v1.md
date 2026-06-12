# M2 Sprint 04 · 测试报告 · tiktok-writer · v1

> 测试时间：2026-06-12
> 测试执行：自动化（pytest + vitest）
> 状态：✅ 通过

---

## 一、测试范围

| 层级 | 测试集 | 覆盖内容 |
|------|--------|---------|
| 后端单元 | `tests/unit/services/test_word_export.py` | Markdown→docx 转换（Heading/Bullet/Bold/空行/有序列表/空content）|
| 后端集成 | `tests/integration/routers/test_operator_tiktok_writer.py` | 3 个接口的 Auth/正常路径/异常路径 |
| 前端单元 | `src/__tests__/unit/api/tiktokWriter.test.ts` | API 函数（getPersonas/chatStream/exportWord） |
| 全量回归 | 后端 unit + integration | 确认无回归 |
| 全量回归 | 前端 vitest run | 确认无新增失败 |

---

## 二、测试结果

### 后端

| 测试文件 | 通过 / 总数 |
|---------|------------|
| test_word_export.py | 11 / 11 ✅ |
| test_operator_tiktok_writer.py | 13 / 13 ✅ |
| **全量回归（unit + integration）** | **317 / 317 ✅** |

覆盖率：
- `word_export.py`：95%（未覆盖 3 行为 List Bullet 样式降级路径）
- `operator_tiktok_writer.py`：41%（streaming generator 内部路径难以追踪，主路径集成测试已覆盖）

### 前端

| 测试集 | 通过 / 总数 |
|--------|------------|
| tiktokWriter.test.ts | 4 / 4 ✅ |
| **全量（vitest run）** | **69 / 69 ✅**（2 个预存失败文件与本次无关） |
| TypeScript 编译 | 零错误 ✅ |

---

## 三、已知遗留问题

| 问题 | 说明 | 处理 |
|------|------|------|
| `persona.test.ts` 失败 | localStorage mock 问题，预存于上一 Sprint，与本次无关 | 不处理，记录 |
| `authStore.test.ts` 失败 | 同上 | 不处理，记录 |
| router 覆盖率 41% | streaming generator 路径未被集成测试追踪 | 后续补充单元测试 |

---

## 四、未执行测试

| 测试类型 | 原因 |
|---------|------|
| 浏览器 E2E 功能测试 | 需要真实 AI Key 调用，人工验证 |
| Word 导出内容验证 | 集成测试验证了 MIME 类型和文件名，内容正确性需人工打开文件确认 |
