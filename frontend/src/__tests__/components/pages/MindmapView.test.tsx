/**
 * MindmapView 单元测试
 *
 * 覆盖：
 * - 渲染根节点 + 分支 + 子项
 * - ±按钮缩放（0.5–2.0 范围）
 * - onZoomChange 回调
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import MindmapView from '../../../pages/operator/subtitle/MindmapView';
import type { MindmapResult } from '../../../api/subtitle';

const sampleMindmap: MindmapResult = {
  rootTitle: '核心主题',
  summary: '总结',
  branches: [
    { title: '分支一', children: ['要点 1', '要点 2'] },
    { title: '分支二', children: ['要点 3'] },
    { title: '短分支', children: [] },
  ],
};

describe('MindmapView', () => {
  it('renders root title and all branches', () => {
    render(<MindmapView mindmap={sampleMindmap} />);

    expect(screen.getByText('核心主题')).toBeInTheDocument();
    expect(screen.getByText('分支一')).toBeInTheDocument();
    expect(screen.getByText('分支二')).toBeInTheDocument();
    expect(screen.getByText('短分支')).toBeInTheDocument();
    expect(screen.getByText('要点 1')).toBeInTheDocument();
    expect(screen.getByText('要点 2')).toBeInTheDocument();
    expect(screen.getByText('要点 3')).toBeInTheDocument();
  });

  it('displays initial zoom 100%', () => {
    render(<MindmapView mindmap={sampleMindmap} />);
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('increases zoom on + click', () => {
    const onZoomChange = vi.fn();
    render(<MindmapView mindmap={sampleMindmap} onZoomChange={onZoomChange} />);

    const buttons = screen.getAllByRole('button');
    // 最后一个 button 是 +
    fireEvent.click(buttons[buttons.length - 1]);

    expect(onZoomChange).toHaveBeenCalledWith(1.1);
  });

  it('decreases zoom on − click', () => {
    const onZoomChange = vi.fn();
    render(<MindmapView mindmap={sampleMindmap} zoom={1} onZoomChange={onZoomChange} />);

    const buttons = screen.getAllByRole('button');
    // 第一个 button 是 −
    fireEvent.click(buttons[0]);

    expect(onZoomChange).toHaveBeenCalledWith(0.9);
  });

  it('clamps zoom to [0.5, 2]', () => {
    const onZoomChange = vi.fn();
    render(<MindmapView mindmap={sampleMindmap} zoom={2} onZoomChange={onZoomChange} />);

    const buttons = screen.getAllByRole('button');
    // 点 +（buttons[length-1]）应被 clamp
    fireEvent.click(buttons[buttons.length - 1]);
    expect(onZoomChange).toHaveBeenLastCalledWith(2);
  });

  it('renders empty mindmap without crash', () => {
    const empty: MindmapResult = {
      rootTitle: '空',
      summary: '',
      branches: [],
    };
    render(<MindmapView mindmap={empty} />);
    expect(screen.getByText('空')).toBeInTheDocument();
  });
});
