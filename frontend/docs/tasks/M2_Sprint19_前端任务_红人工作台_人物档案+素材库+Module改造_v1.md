# M2 Sprint19 前端任务 — 人物档案 + 素材库 + 工具 Module 改造（v1）

> 编写时间：2026-06-25
> 需求来源：`docs/pm/M2_Sprint18-22_红人工作台_需求文档.md` § Sprint 19
> 前端规范：`frontend/docs/前端规范.md`（必读）
> 分支：`feature/kol-workspace`

---

## 一、任务范围

| # | 内容 | 文件 |
|---|------|------|
| 1 | 人物档案编辑器 | `pages/operator/workspace/WorkspacePersona.tsx`（新建） |
| 2 | 素材库 | `pages/operator/workspace/WorkspaceReferences.tsx`（新建） |
| 3 | QianchuanWriterPage 拆 Module | `pages/operator/QianchuanWriterPage.tsx`（改造） |
| 4 | SeedingWriterPage 拆 Module | `pages/operator/SeedingWriterPage.tsx`（改造） |
| 5 | PersonaWriterPage 拆 Module | `pages/operator/PersonaWriterPage.tsx`（改造） |
| 6 | LivestreamWriterPage 拆 Module | `pages/operator/LivestreamWriterPage.tsx`（改造） |
| 7 | LivestreamReviewPage 拆 Module | `pages/operator/LivestreamReviewPage.tsx`（改造） |
| 8 | 工作台接入上述 Module | `pages/operator/KolWorkspacePage.tsx`（改造） |
| 9 | 单元测试补充 | `__tests__/components/pages/KolWorkspacePage.test.tsx`（改造） |

**不做清单：**
- 不做价值观仿写、复盘、千川脚本预审（后续 Sprint）
- 不做抖音链接导入素材（已在 seeding-writer 工具页，工作台素材库只支持手动粘贴）
- 不改工具页的业务逻辑，只做「拆 Module」结构改造

---

## 二、API 来源（全部复用已有接口，无需新建）

| 功能 | 接口 | 来源 |
|------|------|------|
| 人物档案读 | GET `/api/operator/kols/{kol_id}/persona-details` | Sprint 18 |
| 人物档案写 | PUT `/api/operator/kols/{kol_id}/persona-details` | Sprint 18 |
| 素材库列表 | GET `/api/tools/seeding-writer/references?kol_id=xx` | Sprint 16 |
| 素材库新增 | POST `/api/tools/seeding-writer/references` | Sprint 16 |
| 素材库删除 | DELETE `/api/tools/seeding-writer/references/{id}` | Sprint 16 |

---

## 三、人物档案编辑器（WorkspacePersona）

### 3.1 5 分区结构

| 分区 | 字段 | hint |
|------|------|------|
| 基本身份 | `background` | 年龄、职业、背景、性格 |
| 真实经历 | `experience` | 可替换脚本人物经历的素材 |
| 关系网 | `relationships` | 朋友/闺蜜/家人名单，替换脚本人名 |
| 独家经历 | `unique_story` | 只有该达人有的人生故事，越细越好 |
| 其他补充 | `extra_notes` | 习惯、口头禅、禁区 |

### 3.2 交互

- 初始化：GET persona-details，所有字段为 null 时展示空态提示
- 每个分区：标题 + hint + 查看态（文本展示）
- 鼠标悬停分区 → 右上角出现「编辑」按钮
- 点击「编辑」→ textarea inline 展开，显示「保存」「取消」
- 「保存」→ PUT persona-details（只传该分区字段，其他字段不传）→ 更新本地状态
- 底部显示「上次更新：{updated_at}」

### 3.3 Props

```typescript
interface WorkspacePersonaProps {
  kolId: number;
}
```

---

## 四、素材库（WorkspaceReferences）

### 4.1 素材分类（6 类，沿用旧版）

| 分组 | 类型值 |
|------|--------|
| 人设仿写素材 | `红人爆款文案` / `红人喜欢的内容` / `风格参考` |
| 千川仿写素材 | `千川爆款文案` / `千川喜欢的内容` / `千川风格参考` |

### 4.2 功能

- 首页：6 块分类入口卡片（图标 + 名称 + 已有数量）
- 点击分类 → 进入该类型的「添加 + 列表」视图
- 添加：标题（必填）+ 数据/点赞数（选填）+ 正文（必填）→ POST references
- 列表：标题 + 数据标注 + 内容折叠/展开 + 删除按钮（Popconfirm）
- 「← 返回」回到分类首页

### 4.3 Props

```typescript
interface WorkspaceReferencesProps {
  kolId: number;
}
```

---

## 五、工具页 Module 改造模式

每个工具页的改造遵循同一模式，以 `QianchuanWriterPage` 为例：

```tsx
// 改造前
export default function QianchuanWriterPage() {
  // Step 1: 下拉选达人
  const [selectedPersona, setSelectedPersona] = useState(null);
  // ... 其他 state
  
  // 完整流程（包含 Step 1）
}

// 改造后
// ── 核心 Module（无选达人，接受外部 kolId）──────────────────
export function QianchuanWriterModule({ kolId }: { kolId: number }) {
  // 直接用 kolId 加载达人数据，无 Step 1
  // 其他 state 和业务逻辑完全不变
}

// ── 独立页面（保留完整选达人流程）────────────────────────────
export default function QianchuanWriterPage() {
  const [kolId, setKolId] = useState<number | null>(null);
  
  if (!kolId) {
    // 原来的 Step 1 选达人 UI
    return <KolSelector onSelect={setKolId} />;
  }
  return <QianchuanWriterModule kolId={kolId} />;
}
```

**关键约束：**
- 业务逻辑代码（Step 2 起）**一行不改**，只移动到 Module 组件里
- 原有独立页面路由（`/workspace/qianchuan-writer` 等）继续正常工作
- 每个工具页改造量约 30-40 行

### 5.1 需要改造的 5 个工具页

| 工具页 | 导出的 Module | 说明 |
|--------|--------------|------|
| QianchuanWriterPage | `QianchuanWriterModule` | Step 1 = 选达人 |
| SeedingWriterPage | `SeedingWriterModule` | Step 1 = 选达人 |
| PersonaWriterPage | `PersonaWriterModule` | Step 1 = 选达人（加载风格） |
| LivestreamWriterPage | `LivestreamWriterModule` | Step 1 = 选达人 |
| LivestreamReviewPage | `LivestreamReviewModule` | Step 1 = 选达人 |

---

## 六、KolWorkspacePage 接入 Module

在 Sprint 18 的 Shell 基础上，扩展主内容区的条件渲染：

```tsx
// 新增 import
import WorkspacePersona from './workspace/WorkspacePersona';
import WorkspaceReferences from './workspace/WorkspaceReferences';
import { QianchuanWriterModule } from './QianchuanWriterPage';
import { SeedingWriterModule } from './SeedingWriterPage';
import { PersonaWriterModule } from './PersonaWriterPage';
import { LivestreamWriterModule } from './LivestreamWriterPage';
import { LivestreamReviewModule } from './LivestreamReviewPage';

// 激活导航项（去掉 disabled）
{ tab: 'persona',          label: '人物档案',   icon: <UserOutlined /> },           // disabled 移除
{ tab: 'qianchuan-writer', label: '千川仿写',   icon: <ScissorOutlined /> },        // disabled 移除
{ tab: 'references',       label: '素材库',     icon: <FolderOutlined /> },         // disabled 移除
// 直播仿写、直播复盘、种草仿写、人设仿写也激活（视对应 Module 是否在本 Sprint 做完）

// 主内容区扩展
{activeTab === 'persona'          && <WorkspacePersona kolId={kolId} />}
{activeTab === 'references'       && <WorkspaceReferences kolId={kolId} />}
{activeTab === 'qianchuan-writer' && <QianchuanWriterModule kolId={kolId} />}
{activeTab === 'seeding-writer'   && <SeedingWriterModule kolId={kolId} />}
{activeTab === 'persona-writer'   && <PersonaWriterModule kolId={kolId} />}
{activeTab === 'livestream-writer' && <LivestreamWriterModule kolId={kolId} />}
{activeTab === 'livestream-review' && <LivestreamReviewModule kolId={kolId} />}
```

同时在 NAV_ITEMS 中补充缺失的导航项：
```tsx
{ tab: 'seeding-writer',    label: '种草仿写',   icon: <EditOutlined /> },
{ tab: 'persona-writer',    label: '人设仿写',   icon: <UserSwitchOutlined /> },
{ tab: 'livestream-writer', label: '直播仿写',   icon: <AudioOutlined /> },
{ tab: 'livestream-review', label: '直播复盘',   icon: <PlayCircleOutlined /> },
```

---

## 七、验收口径

1. 工作台左侧导航：人物档案、素材库、千川仿写、种草仿写、人设仿写、直播仿写、直播复盘均可点击进入
2. 人物档案：5 分区可独立编辑保存，刷新后数据持久
3. 素材库：6 种类型均可添加素材，可折叠展开，可删除
4. 工具（千川仿写等）：从工作台进入时，达人已自动锁定，无需再选达人
5. 原有工具独立路由（`/workspace/qianchuan-writer`）仍可正常使用，Step 1 选达人流程完整
6. `npx vitest run` 全部通过（现有 197 + 新增测试）
7. `npx tsc --noEmit` 无报错
