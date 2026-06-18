# M2 Sprint 12 — 前端任务：千川爆文合集（qianchuan-collection）v1

> 状态：待开发
> 对应需求文档：`docs/pm/M2_Sprint12_qianchuan-collection_需求文档.md`

---

## 一、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| F1 | 类型定义 | `src/types/qianchuanCollection.ts` | ⬜ 待做 |
| F2 | API 模块 | `src/api/qianchuanCollection.ts` | ⬜ 待做 |
| F3 | 运营端页面 | `src/pages/operator/QianchuanCollectionPage.tsx` | ⬜ 待做 |
| F4 | 路由注册 | `src/App.tsx` | ⬜ 待做 |
| F5 | 单元测试 | `src/__tests__/unit/api/qianchuanCollection.test.ts` | ⬜ 待做 |

> 无管理端专属 Tab（工具无 AI，无需 Prompt/模型配置，workspace_tools 已由 migration 025 注册）

---

## 二、类型定义（F1）

`src/types/qianchuanCollection.ts`

```typescript
export interface CollectionPersona {
  name: string;
  script_count: number;
}

export interface CollectionScript {
  id: number;
  pool: 'global' | 'persona';
  persona_name: string | null;
  title: string;
  content: string;
  likes: number | null;
  source: string | null;
  source_account: string | null;
  script_date: string | null;
  created_at: string;
}

export interface ScriptListResponse {
  scripts: CollectionScript[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateScriptBody {
  pool: 'global' | 'persona';
  persona_name?: string;
  title: string;
  content: string;
  likes?: number;
  source?: string;
  source_account?: string;
  script_date?: string;
}
```

---

## 三、API 封装（F2）

`src/api/qianchuanCollection.ts`

所有 JSON 接口走 `request.ts`（get/post/del）；文件上传为 FormData 例外，原生 fetch 手动解包。

| 函数 | HTTP | 例外 | 说明 |
|------|------|------|------|
| `getPersonas()` | GET | 无 | 获取达人列表 |
| `createPersona(name)` | POST | 无 | 新建达人 |
| `deletePersona(name)` | DELETE | 无 | 删除达人 |
| `getScripts(params)` | GET | 无 | 分页获取脚本列表 |
| `createScript(body)` | POST | 无 | 新增脚本 |
| `deleteScript(id)` | DELETE | 无 | 软删脚本 |
| `parseFile(file)` | POST | FormData | 文件解析 |

---

## 四、页面结构（F3）

`src/pages/operator/QianchuanCollectionPage.tsx`

```
QianchuanCollectionPage
├── Header（页面标题：千川爆文合集 + 描述）
├── 模式切换 Tab（全网爆款 / 达人爆款）
│
├── [全网爆款模式]
│   ├── 工具栏（搜索框 + 添加脚本按钮）
│   └── 脚本列表（Table，分页）
│       └── 展开行（全文 + 复制/下载）
│
└── [达人爆款模式]
    ├── 达人选择区（Select 下拉 + 新建达人按钮）
    ├── [选中达人后] 工具栏（搜索框 + 添加脚本按钮）
    └── [选中达人后] 脚本列表（Table，分页）
        └── 展开行（全文 + 复制/下载）

--- 弹窗 ---
├── 添加脚本 Modal
│   ├── 标题输入（必填）
│   ├── 点赞数输入（选填）
│   ├── 来源平台输入（选填）
│   ├── 来源账号输入（选填）
│   ├── 文件上传按钮（.docx/.pdf/.txt/.md → 解析填充内容框）
│   └── 内容 textarea（必填）
└── 删除确认 Modal（二次确认）
```

---

## 五、关键约束

### CSS 规范（红线）

- **禁止 Tailwind**：所有样式使用 `var(--brand)` / `var(--gray-*)` / `card` / `btn-primary` 等 CSS 变量体系
- **禁止硬编码色值**：不写 `#f59a23`，用 `var(--brand)`

### request.ts 规范（红线 #3）

- 所有 JSON 接口必须走 `import { get, post, del } from './request'`
- `parseFile` 为 FormData 例外，使用原生 fetch，需在文件顶部注释中明确标注

### 布局规范（红线 #1）

- 工具入口在「创作中心」侧边栏，不新增顶级菜单
- 路由：`/workspace/qianchuan-collection`（与 workspace_tools.tool_code 对应）

### 无产出中心接入（红线 #2）

- 本工具是纯素材收集库，无 AI 产出，不需要接入产出中心（outputs）

### 分页

- 使用 Ant Design `<Table>` 组件，`pagination={{ pageSize: 20, total, current: page }}`
- 切换页码时重新调用 `getScripts()`，不做前端全量加载

### 表格展开行

- 使用 `expandable.expandedRowRender` 展示全文
- 展开行包含：复制全文按钮、下载 .txt 按钮
- 复制使用 `navigator.clipboard.writeText()`
- 下载通过前端创建 Blob 实现（无需后端接口）

---

## 六、路由注册（F4）

`src/App.tsx` 中新增懒加载路由（遵循项目约定）：

```typescript
const QianchuanCollectionPage = lazy(() => import('./pages/operator/QianchuanCollectionPage'));

// 在 operator 路由组内添加
<Route path="qianchuan-collection" element={<QianchuanCollectionPage />} />
```

---

## 七、测试要求（F5）

`src/__tests__/unit/api/qianchuanCollection.test.ts`

守卫测试（对齐 `conventionGuard.test.ts` 规范）：

| 测试用例 | 说明 |
|---------|------|
| getPersonas 使用 request.ts `get` | |
| createPersona 使用 request.ts `post` | |
| deletePersona 使用 request.ts `del` | |
| getScripts 使用 request.ts `get` | |
| createScript 使用 request.ts `post` | |
| deleteScript 使用 request.ts `del` | |
| parseFile 为 FormData 例外，有明确注释标注 | |
