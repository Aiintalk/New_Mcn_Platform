# 前端测试修复报告

**日期：** 2026-06-11  
**范围：** 全量单元测试修复  
**结果：** ✅ 71/71 通过

---

## 一、问题根因

### 问题 1：vi.mock hoisting 导致 mockFn 未初始化（5 个 API 测试文件全部 FAILED）

**现象：**
```
ReferenceError: Cannot access 'mockGet' before initialization
```

**根因：**  
Vitest（和 Jest）会将 `vi.mock(...)` 调用 **提升（hoist）** 到文件顶部，在所有 `import` 和变量声明之前执行。因此：

```ts
// ❌ 错误写法
const mockGet = vi.fn();          // 声明在 vi.mock 之后才执行
vi.mock('../api/request', () => ({
  get: mockGet,                   // hoisting 后此时 mockGet 还未初始化 → ReferenceError
}));
```

factory 函数在 hoisting 后运行时，`mockGet` 尚未被赋值，引用 TDZ（Temporal Dead Zone）变量。

**修复：**  
使用 `vi.hoisted()` 将 mock 函数的创建也提升到同一阶段：

```ts
// ✅ 正确写法
const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('../api/request', () => ({
  get: mockGet,   // 此时 mockGet 已初始化
}));
```

**影响文件：**
- `src/__tests__/unit/api/homepage.test.ts`
- `src/__tests__/unit/api/workspace.test.ts`
- `src/__tests__/unit/api/tasks.test.ts`
- `src/__tests__/unit/api/outputs.test.ts`
- `src/__tests__/unit/api/intake.test.ts`

---

### 问题 2：authStore 测试的 localStorage mock 无效（1 个断言 FAILED）

**现象：**
```
AssertionError: expected undefined to be 'test-token-123'
```

**根因：**  
原测试用 `vi.hoisted()` 创建了一个自定义 `store` 对象，并尝试将其挂载为 `globalThis.localStorage`：

```ts
const localStorageStore = vi.hoisted(() => {
  const store = {};
  if (typeof globalThis.localStorage === 'undefined' || ...) {
    // 挂载自定义 localStorage
  }
  return store;
});
```

但 Vitest 的测试环境（jsdom）已经提供了完整的 `localStorage` 实现，条件 `typeof globalThis.localStorage === 'undefined'` 为 **false**，自定义 mock 从未被挂载。导致 `localStorageStore` 始终是空对象 `{}`，而 `authStore.setAuth()` 实际写入了 jsdom 的 localStorage，两者不是同一个对象。

**修复：**  
去掉自定义 mock，直接使用 jsdom 提供的 `localStorage`：

```ts
// ✅ 直接用 jsdom 的 localStorage
expect(localStorage.getItem('mcn_token')).toBe('test-token-123');
```

---

## 二、修改文件清单

| 文件 | 变更内容 |
|------|---------|
| `src/__tests__/unit/api/homepage.test.ts` | mockGet 改用 `vi.hoisted()` |
| `src/__tests__/unit/api/workspace.test.ts` | mockGet/mockPatch 改用 `vi.hoisted()` |
| `src/__tests__/unit/api/tasks.test.ts` | mockGet 改用 `vi.hoisted()` |
| `src/__tests__/unit/api/outputs.test.ts` | mockGet/mockDel 改用 `vi.hoisted()` |
| `src/__tests__/unit/api/intake.test.ts` | 全部 mock 改用 `vi.hoisted()` |
| `src/__tests__/unit/store/authStore.test.ts` | 去掉自定义 localStorage mock，使用 jsdom localStorage |

---

## 三、最终测试结果

```
Test Files  9 passed (9)
Tests      71 passed (71)
```
