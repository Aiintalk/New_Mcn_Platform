# M2 Sprint 5 · 测试报告 · selling-point-extractor v1

> 测试日期：2026-06-13
> 测试环境：本地 Mac，Python 3.10，PostgreSQL 15（mcn_m1），Node 20

---

## 一、测试结果汇总

| 层级 | 测试文件 | 用例数 | 通过 | 失败 |
|------|---------|--------|------|------|
| 单元（service） | `test_selling_point_file_parser.py` | 15 | 15 | 0 |
| 集成（router） | `test_operator_selling_point.py` | 20 | 20 | 0 |
| 集成（admin router） | `test_admin_selling_point.py` | 8 | 8 | 0 |
| 前端 | vitest run（全量） | 86 | 86 | 0 |
| **合计** | | **129** | **129** | **0** |

---

## 二、覆盖率

| 模块 | 覆盖率 | 目标 | 状态 |
|------|--------|------|------|
| `app/routers/operator_selling_point.py` | **71%** | ≥70% | ✅ |
| `app/routers/admin_selling_point.py` | **71%** | ≥70% | ✅ |
| `app/services/file_parser.py`（含旧测试） | **82%** | ≥80% | ✅ |

---

## 三、单元测试覆盖场景（file_parser）

| 场景 | 覆盖 |
|------|------|
| .txt / .md UTF-8 解码 | ✅ |
| .txt 无截断（与旧函数区别） | ✅ |
| .docx 段落提取（真实 docx）| ✅ |
| .docx 损坏抛 ValueError | ✅ |
| .pdf pdfplumber 单页/多页 | ✅ |
| .doc 返回提示文本 | ✅ |
| .pages 中文提取 | ✅ |
| .pages 短中文过滤（<5）| ✅ |
| .pages 不过滤日历型中文 | ✅ |
| .pages 缺 IWA / 坏 ZIP | ✅ |
| .pages snappy 解压 fallback | ✅ |
| 未知扩展名 UTF-8 fallback | ✅ |

---

## 四、集成测试覆盖场景

### 运营端（20 个）
- Auth 401（5 个接口各 1 条）
- chat：400 空 messages / 503 配置未激活 / 正常流式 / error marker
- parse-file：txt / doc hint / docx
- history：空列表 / 保存+查列表 / 保存+查单条 / 404 / 软删除 / 400 空 result / 默认产品名 / 重复删除 404

### 管理端（8 个）
- GET 401 / 403（operator）/ 200 含字段验证
- PUT 401 / 200 更新 + DB 验证 / 404 不存在 key / 恢复原始 prompt

---

## 五、回归说明

后端全量测试中 4 个并发隔离测试（`test_iso_001~004`）失败，确认为历史遗留问题，与本次 Sprint 5 新增模块无关。本次新增代码未引入新的测试失败。
