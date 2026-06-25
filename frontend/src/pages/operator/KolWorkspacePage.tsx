import { useState } from 'react';
import type { ReactNode } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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
  { tab: 'script-review',     label: '千川脚本预审', icon: <SearchOutlined />,       disabled: true },
  { tab: 'film-review',       label: '千川成片预审', icon: <VideoCameraOutlined />,  disabled: true },
  { tab: 'retrospective',     label: '复盘',       icon: <BarChartOutlined />,      disabled: true },
];

export default function KolWorkspacePage() {
  const { kol_id } = useParams<{ kol_id: string }>();
  const navigate = useNavigate();
  const kolId = Number(kol_id);

  const [activeTab, setActiveTab] = useState<WorkspaceTab>('dashboard');
  const [kolName, setKolName] = useState('');
  const [kolAvatar, setKolAvatar] = useState<string | null>(null);

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
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg-page)' }}>
      {/* 顶部栏 */}
      <div
        data-testid="workspace-topbar"
        style={{
          height: 52,
          background: 'var(--bg-card)',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 var(--sp-6)',
          gap: 'var(--sp-4)',
          flexShrink: 0,
        }}
      >
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => navigate('/admin/kols')}
          style={{ display: 'flex', alignItems: 'center', gap: 4 }}
        >
          <ArrowLeftOutlined />
          返回红人列表
        </button>

        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />

        {/* 红人头像 + 姓名 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
          <img
            src={kolAvatar || '/default-avatar.svg'}
            alt={kolName || '红人'}
            onError={(e) => { e.currentTarget.src = '/default-avatar.svg'; }}
            style={{ width: 28, height: 28, borderRadius: '50%', objectFit: 'cover' }}
          />
          <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--gray-800)' }}>
            {kolName || '加载中...'}
          </span>
          <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>工作台</span>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              display: 'inline-block',
              width: 8, height: 8, borderRadius: '50%',
              background: 'var(--success)',
            }}
          />
          <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>系统运行中</span>
        </div>
      </div>

      {/* 主体区：左侧导航 + 右侧内容 */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* 左侧导航 */}
        <aside
          data-testid="workspace-sidebar"
          style={{
            width: 160,
            background: 'var(--bg-sidebar)',
            borderRight: '1px solid rgba(255,255,255,0.05)',
            display: 'flex',
            flexDirection: 'column',
            padding: 'var(--sp-4) 0',
            flexShrink: 0,
          }}
        >
          {NAV_ITEMS.map((item) => {
            const isActive = activeTab === item.tab;
            return (
              <div
                key={item.tab}
                data-testid={`nav-item-${item.tab}`}
                onClick={() => handleNavClick(item)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--sp-2)',
                  padding: '10px var(--sp-4)',
                  fontSize: 13,
                  cursor: item.disabled ? 'not-allowed' : 'pointer',
                  opacity: item.disabled ? 0.4 : 1,
                  color: isActive ? 'var(--sidebar-active)' : 'var(--sidebar-text)',
                  background: isActive ? 'rgba(245,149,35,0.12)' : 'transparent',
                  borderLeft: isActive ? '3px solid var(--brand)' : '3px solid transparent',
                  transition: 'all 0.15s',
                  userSelect: 'none',
                }}
              >
                <span style={{ fontSize: 14 }}>{item.icon}</span>
                <span>{item.label}</span>
              </div>
            );
          })}
        </aside>

        {/* 主内容区 */}
        <main
          style={{
            flex: 1,
            overflow: 'auto',
            padding: 'var(--sp-6)',
          }}
        >
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
        </main>
      </div>
    </div>
  );
}
