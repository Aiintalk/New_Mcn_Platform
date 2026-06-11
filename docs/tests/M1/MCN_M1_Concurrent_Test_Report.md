# MCN Platform · M1 并发多用户测试报告

**测试日期：** 2026-06-11 21:40  
**并发用户数：** 20  
**测试环境：** http://localhost:8000  

---

## 一、数据隔离

| 编号 | 场景 | 结论 | 说明 |
|------|------|------|------|
| ISO-001 | 并发查询任务列表 — 各自只见自己的任务 | ❌ | op_0 请求失败: None; op_1 请求失败: None; op_2 请求失败: None; op_3 请求失败: None; op_4 请求失败: None; op_5 请求失败: None; op_6 请求失败: None; op_7 请求失败: None; op_8 请求失败: None; op_9 请求失败: None; op_10 请求失败: None; op_11 请求失败: None; op_12 请求失败: None; op_13 请求失败: None; op_14 请求失败: None; op_15 请求失败: None; op_16 请求失败: None; op_17 请求失败: None; op_18 请求失败: None; op_19 请求失败: None |
| ISO-002 | 并发查询产出列表 — 各自只见自己的产出 | ❌ | op_0 请求失败: None; op_1 请求失败: None; op_2 请求失败: None; op_3 请求失败: None; op_4 请求失败: None; op_5 请求失败: None; op_6 请求失败: None; op_7 请求失败: None; op_8 请求失败: None; op_9 请求失败: None; op_10 请求失败: None; op_11 请求失败: None; op_12 请求失败: None; op_13 请求失败: None; op_14 请求失败: None; op_15 请求失败: None; op_16 请求失败: None; op_17 请求失败: None; op_18 请求失败: None; op_19 请求失败: None |
| ISO-003 | 跨用户访问 task — 全部 403 | ❌ | op_1 返回 （预期 PERMISSION_DENIED）; op_2 返回 （预期 PERMISSION_DENIED）; op_3 返回 （预期 PERMISSION_DENIED）; op_4 返回 （预期 PERMISSION_DENIED）; op_5 返回 （预期 PERMISSION_DENIED）; op_6 返回 （预期 PERMISSION_DENIED）; op_7 返回 （预期 PERMISSION_DENIED）; op_8 返回 （预期 PERMISSION_DENIED）; op_9 返回 （预期 PERMISSION_DENIED）; op_10 返回 （预期 PERMISSION_DENIED）; op_11 返回 （预期 PERMISSION_DENIED）; op_12 返回 （预期 PERMISSION_DENIED）; op_13 返回 （预期 PERMISSION_DENIED）; op_14 返回 （预期 PERMISSION_DENIED）; op_15 返回 （预期 PERMISSION_DENIED）; op_16 返回 （预期 PERMISSION_DENIED）; op_17 返回 （预期 PERMISSION_DENIED）; op_18 返回 （预期 PERMISSION_DENIED）; op_19 返回 （预期 PERMISSION_DENIED） |
| ISO-004 | 跨用户访问 output — 全部 403 | ❌ | op_1 返回 （预期 PERMISSION_DENIED）; op_2 返回 （预期 PERMISSION_DENIED）; op_3 返回 （预期 PERMISSION_DENIED）; op_4 返回 （预期 PERMISSION_DENIED）; op_5 返回 （预期 PERMISSION_DENIED）; op_6 返回 （预期 PERMISSION_DENIED）; op_7 返回 （预期 PERMISSION_DENIED）; op_8 返回 （预期 PERMISSION_DENIED）; op_9 返回 （预期 PERMISSION_DENIED）; op_10 返回 （预期 PERMISSION_DENIED）; op_11 返回 （预期 PERMISSION_DENIED）; op_12 返回 （预期 PERMISSION_DENIED）; op_13 返回 （预期 PERMISSION_DENIED）; op_14 返回 （预期 PERMISSION_DENIED）; op_15 返回 （预期 PERMISSION_DENIED）; op_16 返回 （预期 PERMISSION_DENIED）; op_17 返回 （预期 PERMISSION_DENIED）; op_18 返回 （预期 PERMISSION_DENIED）; op_19 返回 （预期 PERMISSION_DENIED） |

## 二、竞态条件

| 编号 | 场景 | 结论 | 说明 |
|------|------|------|------|

## 三、性能基线

| 接口 | P50 | P95 | P99 | 错误率 | 结论 |
|------|-----|-----|-----|--------|------|

---

## 汇总

| 统计 | 值 |
|------|-----|
| 总计 | 4 项 |
| 通过 | 0 项 |
| 失败 | 4 项 |
| 并发用户数 | 20 |

**测试结论：❌ 不通过（4 项失败）**
