// src/types/kolWorkspaceConfig.ts
// 红人工作台个性化配置类型定义（Sprint 23）

export type WorkspaceTabCode =
  | 'dashboard' | 'persona' | 'references' | 'products'
  | 'qianchuan-writer' | 'seeding-writer' | 'persona-writer'
  | 'livestream-writer' | 'livestream-review' | 'values-writer'
  | 'script-review' | 'retrospective';

export const ALL_TABS: WorkspaceTabCode[] = [
  'dashboard', 'persona', 'references', 'products',
  'qianchuan-writer', 'seeding-writer', 'persona-writer',
  'livestream-writer', 'livestream-review', 'values-writer',
  'script-review', 'retrospective',
];

export type ToolCode =
  | 'qianchuan-writer' | 'persona-writer' | 'seeding-writer'
  | 'livestream-writer' | 'livestream-review' | 'values-writer'
  | 'script-review' | 'retrospective';

// 各工具的 prompt_key 结构
export interface ToolPromptFields {
  'qianchuan-writer':  { system_prompt?: string | null };
  'persona-writer':    { evaluation_prompt?: string | null; analysis_prompt?: string | null; writing_prompt?: string | null; iteration_prompt?: string | null };
  'seeding-writer':    { sp_system?: string | null; parse_product?: string | null; structure_analysis?: string | null; ai_recommend?: string | null; writing?: string | null; iteration?: string | null };
  'livestream-writer': { system_prompt?: string | null };
  'livestream-review': { with_excel_prompt?: string | null; without_excel_prompt?: string | null };
  'values-writer':     { extract_values_prompt?: string | null; emotion_direction_prompt?: string | null; writing_prompt?: string | null; iteration_prompt?: string | null };
  'script-review':     { direct_prompt?: string | null; value_prompt?: string | null };
  'retrospective':     { system_prompt?: string | null };
}

export type PromptOverrides = {
  [K in ToolCode]?: ToolPromptFields[K];
};

export interface KolWorkspaceConfig {
  kol_id: number;
  enabled_tabs: WorkspaceTabCode[];
  prompt_overrides: PromptOverrides;
  global_prompts: { [K in ToolCode]: ToolPromptFields[K] };
}

// 工具显示名
export const TOOL_LABELS: Record<ToolCode, string> = {
  'qianchuan-writer':  '千川仿写',
  'persona-writer':    '人设仿写',
  'seeding-writer':    '种草仿写',
  'livestream-writer': '直播仿写',
  'livestream-review': '直播复盘',
  'values-writer':     '价值观仿写',
  'script-review':     '千川脚本预审',
  'retrospective':     '复盘',
};

// 各工具 prompt_key 的中文标签
export const PROMPT_KEY_LABELS: Record<string, string> = {
  system_prompt:             'System Prompt',
  evaluation_prompt:         '开头评估 Prompt',
  analysis_prompt:           '结构拆解 Prompt',
  writing_prompt:            '写作 Prompt',
  iteration_prompt:          '迭代 Prompt',
  sp_system:                 'System Prompt',
  parse_product:             '产品解析 Prompt',
  structure_analysis:        '结构拆解 Prompt',
  ai_recommend:              'AI 推荐 Prompt',
  writing:                   '写作 Prompt',
  iteration:                 '迭代 Prompt',
  with_excel_prompt:         '含投放数据 Prompt',
  without_excel_prompt:      '无投放数据 Prompt',
  extract_values_prompt:     '提炼价值观 Prompt',
  emotion_direction_prompt:  '情绪方向 Prompt',
  direct_prompt:             '千川直销 Prompt',
  value_prompt:              '价值观 Prompt',
};
