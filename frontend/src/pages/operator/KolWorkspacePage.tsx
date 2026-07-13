import { useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  HomeOutlined,
  UserOutlined,
  ShoppingOutlined,
  ScissorOutlined,
  HeartOutlined,
  SearchOutlined,
  VideoCameraOutlined,
  BarChartOutlined,
  FolderOutlined,
  ArrowLeftOutlined,
  EditOutlined,
  UserSwitchOutlined,
  AudioOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import type { WorkspaceTab } from '../../types/kolWorkspace';
import { getKolWorkspaceConfig } from '../../api/kolWorkspaceConfig';
import type { WorkspaceTabCode } from '../../types/kolWorkspaceConfig';
import WorkspaceDashboard from './workspace/WorkspaceDashboard';
import QianchuanProductsModule from './workspace/QianchuanProductsModule';
import WorkspacePersona from './workspace/WorkspacePersona';
import WorkspaceReferences from './workspace/WorkspaceReferences';
import { QianchuanWriterModule } from './QianchuanWriterPage';
import { SeedingWriterModule } from './SeedingWriterPage';
import { PersonaWriterModule } from './PersonaWriterPage';
import { LivestreamWriterModule } from './LivestreamWriterPage';
import { LivestreamReviewModule } from './LivestreamReviewPage';
import { ValuesWriterModule } from './ValuesWriterPage';
import { QianchuanScriptReviewModule } from './QianchuanScriptReviewPage';
import { FilmReviewModule } from './FilmReviewPage';
import WorkspaceRetrospective from './workspace/WorkspaceRetrospective';

interface NavItem {
  tab: WorkspaceTab;
  label: string;
  icon: ReactNode;
  disabled?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { tab: 'dashboard',         label: '工作台首页', icon: <HomeOutlined /> },
  { tab: 'persona',           label: '人物档案',   icon: <UserOutlined /> },
  { tab: 'references',        label: '素材库',     icon: <FolderOutlined /> },
  { tab: 'products',          label: '产品库',     icon: <ShoppingOutlined /> },
  { tab: 'qianchuan-writer',  label: '千川仿写',   icon: <ScissorOutlined /> },
  { tab: 'seeding-writer',    label: '种草仿写',   icon: <EditOutlined /> },
  { tab: 'persona-writer',    label: '人设仿写',   icon: <UserSwitchOutlined /> },
  { tab: 'livestream-writer', label: '直播仿写',   icon: <AudioOutlined /> },
  { tab: 'livestream-review', label: '直播复盘',   icon: <PlayCircleOutlined /> },
  { tab: 'values-writer',     label: '价值观仿写', icon: <HeartOutlined /> },
  { tab: 'script-review',     label: '千川脚本预审', icon: <SearchOutlined /> },
  { tab: 'film-review',       label: '千川成片预审', icon: <VideoCameraOutlined /> },
  { tab: 'retrospective',     label: '复盘',       icon: <BarChartOutlined /> },
];

export default function KolWorkspacePage() {
  const { kol_id } = useParams<{ kol_id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const kolId = Number(kol_id);

  const [activeTab, setActiveTab] = useState<WorkspaceTab>('dashboard');
  const [kolName, setKolName] = useState('');
  const [kolAvatar, setKolAvatar] = useState<string | null>(null);
  const [enabledTabs, setEnabledTabs] = useState<WorkspaceTabCode[] | null>(null);

  useEffect(() => {
    const tab = searchParams.get('tab') as WorkspaceTab | null;
    if (tab && NAV_ITEMS.some((item) => item.tab === tab && !item.disabled)) {
      setActiveTab(tab);
    }
  }, [searchParams]);

  useEffect(() => {
    getKolWorkspaceConfig(kolId)
      .then(cfg => setEnabledTabs(cfg.enabled_tabs as WorkspaceTabCode[]))
      .catch(() => setEnabledTabs(null)); // 失败时降级显示全部 tab
  }, [kolId]);

  // kol_id 非法处理
  if (!kol_id || isNaN(kolId)) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', flexDirection: 'column', gap: 16 }}>
        <div style={{ fontSize: 48, fontWeight: 700, color: 'var(--gray-200)' }}>404</div>
        <div style={{ fontSize: 16, color: 'var(--gray-500)' }}>无效的红人 ID</div>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/admin/kols')}>返回红人列表</button>
      </div>
    );
  }

  function handleNavClick(item: NavItem) {
    if (item.disabled) return;
    setActiveTab(item.tab);
  }

  return (
    <div className="workspace-shell">
      {/* 顶部栏 */}
      <div
        data-testid="workspace-topbar"
        className="workspace-topbar"
      >
        <button
          className="btn btn-ghost btn-sm workspace-back-btn"
          onClick={() => navigate('/admin/kols')}
        >
          <ArrowLeftOutlined />
          返回红人列表
        </button>

        <div className="workspace-topbar-divider" />

        {/* 红人头像 + 姓名 */}
        <div className="workspace-kol-meta">
          <img
            src={kolAvatar || '/default-avatar.svg'}
            alt={kolName || '红人'}
            onError={(e) => { e.currentTarget.src = '/default-avatar.svg'; }}
            className="workspace-kol-avatar"
          />
          <span className="workspace-kol-name">
            {kolName || '加载中...'}
          </span>
          <span className="workspace-kol-label">工作台</span>
        </div>

        <div className="workspace-status">
          <span className="workspace-status-dot" />
          <span>系统运行中</span>
        </div>
      </div>

      {/* 主体区：左侧导航 + 右侧内容 */}
      <div className="workspace-body">
        {/* 左侧导航 */}
        <aside
          data-testid="workspace-sidebar"
          className="workspace-sidebar"
        >
          {NAV_ITEMS.filter(item =>
            !enabledTabs || enabledTabs.includes(item.tab as WorkspaceTabCode)
          ).map((item) => {
            const isActive = activeTab === item.tab;
            const navClassName = [
              'workspace-nav-item',
              isActive ? 'active' : '',
              item.disabled ? 'disabled' : '',
            ].filter(Boolean).join(' ');
            return (
              <div
                key={item.tab}
                data-testid={`nav-item-${item.tab}`}
                onClick={() => handleNavClick(item)}
                className={navClassName}
                aria-current={isActive ? 'page' : undefined}
              >
                <span className="workspace-nav-icon">{item.icon}</span>
                <span className="workspace-nav-label">{item.label}</span>
              </div>
            );
          })}
        </aside>

        {/* 主内容区 */}
        <main className="workspace-main">
          {activeTab === 'dashboard' && (
            <WorkspaceDashboard
              kolId={kolId}
              onKolLoaded={(kol) => {
                setKolName(kol.name);
                setKolAvatar(kol.avatar_url);
              }}
            />
          )}
          {activeTab === 'products' && <QianchuanProductsModule />}
          {activeTab === 'persona' && <WorkspacePersona kolId={kolId} />}
          {activeTab === 'references' && <WorkspaceReferences kolId={kolId} />}
          {activeTab === 'qianchuan-writer' && <QianchuanWriterModule kolId={kolId} />}
          {activeTab === 'seeding-writer' && <SeedingWriterModule kolId={kolId} />}
          {activeTab === 'persona-writer' && <PersonaWriterModule kolId={kolId} />}
          {activeTab === 'livestream-writer' && <LivestreamWriterModule kolId={kolId} />}
          {activeTab === 'livestream-review' && <LivestreamReviewModule kolId={kolId} />}
          {activeTab === 'values-writer' && <ValuesWriterModule kolId={kolId} />}
          {activeTab === 'script-review' && <QianchuanScriptReviewModule />}
          {activeTab === 'film-review' && <FilmReviewModule kolId={kolId} />}
          {activeTab === 'retrospective' && <WorkspaceRetrospective kolId={kolId} />}
        </main>
      </div>
    </div>
  );
}
