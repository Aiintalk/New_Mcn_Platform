/**
 * exportXmind 单元测试
 *
 * 测试策略：
 * - buildContent 直接验证结构（不依赖 Blob.arrayBuffer，jsdom 不支持）
 * - exportXmind 只做 smoke test（返回 Blob，size > 0）
 *
 * 覆盖：
 * - buildContent 返回 { sheets: [{ rootTopic }] }
 * - rootTopic.title = mindmap.rootTitle
 * - branches map to rootTopic.children.attached[]
 * - summary 写入 rootTopic.notes.plain.content
 * - exportXmind 返回 Blob，size > 0
 */
import { describe, it, expect } from 'vitest';

import { exportXmind, buildContent } from '../../../pages/operator/subtitle/exportXmind';
import type { MindmapResult } from '../../../api/subtitle';

const sampleMindmap: MindmapResult = {
  rootTitle: '短视频运营',
  summary: '本视频讲解运营技巧',
  branches: [
    { title: '内容创作', children: ['选题', '脚本', '拍摄'] },
    { title: '账号定位', children: ['垂直领域'] },
  ],
};

describe('buildContent', () => {
  it('returns sheets array with one sheet', () => {
    const content = buildContent(sampleMindmap);
    expect(content.sheets).toBeDefined();
    expect(content.sheets).toHaveLength(1);
  });

  it('rootTopic.title matches mindmap.rootTitle', () => {
    const content = buildContent(sampleMindmap);
    expect(content.sheets[0].rootTopic.title).toBe('短视频运营');
  });

  it('branches map to children.attached[]', () => {
    const content = buildContent(sampleMindmap);
    const attached = content.sheets[0].rootTopic.children!.attached;
    expect(attached).toHaveLength(2);
    expect(attached[0].title).toBe('内容创作');
    expect(attached[0].children!.attached).toHaveLength(3);
    expect(attached[0].children!.attached[0].title).toBe('选题');
    expect(attached[1].title).toBe('账号定位');
  });

  it('summary stored in rootTopic.notes.plain.content', () => {
    const content = buildContent(sampleMindmap);
    expect(content.sheets[0].rootTopic.notes!.plain!.content).toBe('本视频讲解运营技巧');
  });

  it('empty summary → no notes field', () => {
    const empty: MindmapResult = {
      rootTitle: '空',
      summary: '',
      branches: [],
    };
    const content = buildContent(empty);
    expect(content.sheets[0].rootTopic.notes).toBeUndefined();
  });

  it('branch with no children → no children field on topic', () => {
    const noKids: MindmapResult = {
      rootTitle: '根',
      summary: '',
      branches: [{ title: '空分支', children: [] }],
    };
    const content = buildContent(noKids);
    const branch = content.sheets[0].rootTopic.children!.attached[0];
    expect(branch.children).toBeUndefined();
  });
});

describe('exportXmind', () => {
  it('returns a Blob with non-zero size', async () => {
    const blob = await exportXmind(sampleMindmap);
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.size).toBeGreaterThan(0);
  });
});
