-- 047_workspace_tools_register_pr13.sql
-- 补 PR #13 三个工具的 workspace_tools 注册（PR #13 上线时遗漏，导致管理端「工具列表」缺统一治理视图）
-- 涉及：values-writer（Sprint 20）/ qianchuan-script-review（Sprint 21）/ retrospective（Sprint 22）
-- 幂等：ON CONFLICT (tool_code) DO NOTHING

INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, sort_order)
VALUES
  (
    'values-writer',
    '价值观仿写',
    '脚本创作',
    '基于达人人设提炼价值观关键词，AI 流式生成情绪方向与价值观内容，支持迭代优化；2026-07-01 新增保存到历史 + 页内历史抽屉',
    'online',
    122
  ),
  (
    'qianchuan-script-review',
    '千川脚本预审',
    '千川',
    '千川直销/价值观双模式脚本预审，AI 对比原版与仿写输出结构化评分（pass/minor/fail）+ must_fix + 建议；2026-07-01 新增保存到历史 + 页内历史抽屉',
    'online',
    5
  ),
  (
    'retrospective',
    '复盘',
    'review',
    '红人工作台复盘子模块：多维材料录入（直播数据/素材/评价/脚本），AI 流式生成复盘报告，支持历史管理 + Word 导出',
    'online',
    24
  )
ON CONFLICT (tool_code) DO NOTHING;
