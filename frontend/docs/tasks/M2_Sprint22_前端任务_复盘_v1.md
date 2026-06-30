# M2 Sprint22 前端任务 — 复盘（retrospective）v1

> 编写时间：2026-06-27
> 分支：`feature/kol-workspace`

---

## 一、任务范围

| # | 内容 | 文件 |
|---|------|------|
| 1 | 类型 + API | `src/types/retrospective.ts`、`src/api/retrospective.ts` |
| 2 | 管理端 ConfigTab | `src/pages/admin/RetrospectiveConfigTab.tsx` |
| 3 | 运营端复盘模块 | `src/pages/operator/workspace/WorkspaceRetrospective.tsx` |
| 4 | 工作台接入 | `KolWorkspacePage.tsx` |
| 5 | 测试 | `__tests__/components/pages/WorkspaceRetrospective.test.tsx` |

---

## 二、类型定义

```typescript
// src/types/retrospective.ts
export type SessionStatus = 'draft' | 'done';

export interface RetrospectiveSession {
  id: number;
  kol_id: number;
  title: string;
  status: SessionStatus;
  live_data: string | null;
  material_data: string | null;
  review_text: string | null;
  live_script: string | null;
  material_scripts: { name: string; text: string }[] | null;
  result: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RetrospectiveConfig {
  id: number;
  config_key: string;
  system_prompt: string | null;
  ai_model_id: number | null;
  is_active: boolean;
  updated_at: string | null;
}
```

---

## 三、复盘 Module（WorkspaceRetrospective）三视图

### 视图 1：历史列表
- 卡片列表（标题 + 状态 + 更新时间），点击进入详情
- 状态 Badge：`draft` 草稿（橙色）/ `done` 已完成（绿色）
- 「+ 新建复盘」按钮 → 切换到编辑视图
- 「删除」按钮（Popconfirm）

### 视图 2：编辑/分析
- 标题输入（必填）
- 5 类材料上传区（上传即解析）：
  - 直播汇总数据（xlsx/csv）
  - 素材明细数据（xlsx/csv）
  - 团队复盘文字（docx/txt）
  - 直播间脚本（docx/txt）
  - 千川素材脚本（多文件，docx/txt）
- 「保存草稿」+ 「开始复盘分析」按钮
- 分析时流式显示 Markdown 结果

### 视图 3：详情
- 渲染 Markdown 复盘结果
- 「导出 Word」「复制全文」「重新复盘」按钮

---

## 四、Props

```typescript
interface WorkspaceRetrospectiveProps {
  kolId: number;
}
```

---

## 五、工作台接入

`KolWorkspacePage.tsx`：
- `retrospective` 导航项移除 `disabled: true`
- 主内容区追加：`{activeTab === 'retrospective' && <WorkspaceRetrospective kolId={kolId} />}`

---

## 六、验收口径

1. 工作台点「复盘」→ 显示当前达人的复盘历史列表
2. 新建复盘 → 上传材料 → 开始分析 → 流式结果显示
3. 详情页可导出 Word
4. 测试 ≥ 210 passed
