import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Switch, Collapse, Input, Button, message, Badge, Skeleton, Avatar } from 'antd';
import { ArrowLeftOutlined, UserOutlined, SaveOutlined } from '@ant-design/icons';
import { getKolWorkspaceConfig, updateKolWorkspaceConfig } from '../../api/kolWorkspaceConfig';
import { getKol } from '../../api/kols';
import type { KolWorkspaceConfig, WorkspaceTabCode, ToolCode, PromptOverrides } from '../../types/kolWorkspaceConfig';
import { ALL_TABS, TOOL_LABELS, PROMPT_KEY_LABELS } from '../../types/kolWorkspaceConfig';

const { Panel } = Collapse;
const { TextArea } = Input;

// 工作台 tab 的中文名称（对应 KolWorkspacePage 的 NAV_ITEMS）
const TAB_LABELS: Record<WorkspaceTabCode, string> = {
  'dashboard':         '工作台首页',
  'persona':           '人物档案',
  'references':        '素材库',
  'products':          '产品库',
  'qianchuan-writer':  '千川仿写',
  'seeding-writer':    '种草仿写',
  'persona-writer':    '人设仿写',
  'livestream-writer': '直播仿写',
  'livestream-review': '直播复盘',
  'values-writer':     '价值观仿写',
  'script-review':     '千川脚本预审',
  'retrospective':     '复盘',
};

// 8 个有 AI Prompt 的模块，按工具顺序
const AI_TOOLS: ToolCode[] = [
  'qianchuan-writer', 'persona-writer', 'seeding-writer',
  'livestream-writer', 'livestream-review', 'values-writer',
  'script-review', 'retrospective',
];

// 各工具的 prompt_key 列表（决定渲染哪些 TextArea）
const TOOL_PROMPT_KEYS: Record<ToolCode, string[]> = {
  'qianchuan-writer':  ['system_prompt'],
  'persona-writer':    ['evaluation_prompt', 'analysis_prompt', 'writing_prompt', 'iteration_prompt'],
  'seeding-writer':    ['sp_system', 'parse_product', 'structure_analysis', 'ai_recommend', 'writing', 'iteration'],
  'livestream-writer': ['system_prompt'],
  'livestream-review': ['with_excel_prompt', 'without_excel_prompt'],
  'values-writer':     ['extract_values_prompt', 'emotion_direction_prompt', 'writing_prompt', 'iteration_prompt'],
  'script-review':     ['direct_prompt', 'value_prompt'],
  'retrospective':     ['system_prompt'],
};

export default function KolWorkspaceConfigPage() {
  const { kolId } = useParams<{ kolId: string }>();
  const navigate = useNavigate();
  const kolIdNum = Number(kolId);

  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);
  const [kol, setKol]           = useState<{ name: string; avatar_url: string | null } | null>(null);
  const [config, setConfig]     = useState<KolWorkspaceConfig | null>(null);

  // 本地状态
  const [enabledTabs, setEnabledTabs]       = useState<WorkspaceTabCode[]>(ALL_TABS);
  const [promptOverrides, setPromptOverrides] = useState<Record<string, Record<string, string>>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [kolData, cfg] = await Promise.all([
        getKol(kolIdNum),
        getKolWorkspaceConfig(kolIdNum),
      ]);
      setKol({ name: kolData.name, avatar_url: kolData.avatar_url ?? null });
      setConfig(cfg);
      setEnabledTabs(cfg.enabled_tabs as WorkspaceTabCode[]);
      // 将 prompt_overrides 展开为本地 string state（null → ''）
      const flat: Record<string, Record<string, string>> = {};
      for (const [tool, prompts] of Object.entries(cfg.prompt_overrides || {})) {
        flat[tool] = {};
        for (const [key, val] of Object.entries(prompts || {})) {
          flat[tool][key] = val ?? '';
        }
      }
      setPromptOverrides(flat);
    } catch {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  }, [kolIdNum]);

  useEffect(() => { load(); }, [load]);

  function toggleTab(tab: WorkspaceTabCode, checked: boolean) {
    setEnabledTabs(prev =>
      checked ? [...prev, tab] : prev.filter(t => t !== tab)
    );
  }

  function setPromptValue(tool: ToolCode, key: string, value: string) {
    setPromptOverrides(prev => ({
      ...prev,
      [tool]: { ...(prev[tool] || {}), [key]: value },
    }));
  }

  function countOverrides(tool: ToolCode): number {
    const overrides = promptOverrides[tool] || {};
    return Object.values(overrides).filter(v => v && v.trim()).length;
  }

  async function handleSave() {
    setSaving(true);
    try {
      // 构建 prompt_overrides，空字符串不提交
      const overrides: PromptOverrides = {};
      for (const tool of AI_TOOLS) {
        const toolOverrides = promptOverrides[tool] || {};
        const cleaned: Record<string, string | null> = {};
        for (const key of TOOL_PROMPT_KEYS[tool]) {
          const val = toolOverrides[key];
          cleaned[key] = (val && val.trim()) ? val : null;
        }
        (overrides as Record<string, Record<string, string | null>>)[tool] = cleaned;
      }
      await updateKolWorkspaceConfig(kolIdNum, {
        enabled_tabs: enabledTabs,
        prompt_overrides: overrides as never,
      });
      message.success('配置已保存');
    } catch {
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 32 }}>
        <Skeleton active />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 20px' }}>
      {/* 顶部 Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 28 }}>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => navigate('/admin/kols')}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <ArrowLeftOutlined /> 返回红人列表
        </button>
        <Avatar size={36} src={kol?.avatar_url ?? undefined} icon={<UserOutlined />} />
        <div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>{kol?.name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>工作台配置</div>
        </div>
        <div style={{ flex: 1 }} />
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={handleSave}
        >
          保存
        </Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 20, alignItems: 'start' }}>
        {/* Section 1：模块开关 */}
        <div style={{ background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)', padding: 20, border: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>模块开关</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => setEnabledTabs([...ALL_TABS])}>全选</button>
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => setEnabledTabs([])}>全不选</button>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {ALL_TABS.map(tab => (
              <div key={tab} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 13 }}>{TAB_LABELS[tab]}</span>
                <Switch
                  size="small"
                  checked={enabledTabs.includes(tab)}
                  onChange={checked => toggleTab(tab, checked)}
                />
              </div>
            ))}
          </div>
          <div style={{ marginTop: 16, padding: '10px 12px', background: 'var(--bg-secondary)', borderRadius: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
            未配置时显示全部模块
          </div>
        </div>

        {/* Section 2：AI Prompt 覆盖 */}
        <div style={{ background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border)' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontWeight: 600, fontSize: 14 }}>
            AI Prompt 覆盖
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 400, marginLeft: 8 }}>
              填写后将优先于全局配置，留空则使用全局默认
            </span>
          </div>
          <Collapse ghost>
            {AI_TOOLS.map(tool => {
              const overrideCount = countOverrides(tool);
              return (
                <Panel
                  key={tool}
                  header={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontWeight: 500 }}>{TOOL_LABELS[tool]}</span>
                      {overrideCount > 0
                        ? <Badge count={`已覆盖 ${overrideCount} 项`} style={{ backgroundColor: 'var(--brand)' }} />
                        : <span style={{ fontSize: 11, color: 'var(--text-secondary)', background: 'var(--bg-secondary)', padding: '1px 6px', borderRadius: 4 }}>全局默认</span>
                      }
                    </div>
                  }
                  style={{ borderBottom: '1px solid var(--border)' }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '4px 0' }}>
                    {TOOL_PROMPT_KEYS[tool].map(key => {
                      const globalVal = (config?.global_prompts?.[tool] as Record<string, string | null> | undefined)?.[key];
                      return (
                        <div key={key}>
                          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>
                            {PROMPT_KEY_LABELS[key] ?? key}
                          </div>
                          <TextArea
                            rows={4}
                            value={promptOverrides[tool]?.[key] ?? ''}
                            onChange={e => setPromptValue(tool, key, e.target.value)}
                            placeholder="留空使用全局默认"
                          />
                          {globalVal && (
                            <div style={{ marginTop: 6, padding: '8px 10px', background: 'var(--bg-secondary)', borderRadius: 4, fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                              <span style={{ fontWeight: 500 }}>全局默认：</span>
                              {globalVal}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </Panel>
              );
            })}
          </Collapse>
        </div>
      </div>
    </div>
  );
}
