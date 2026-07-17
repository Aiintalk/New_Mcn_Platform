import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { App } from 'antd';

// ── Mock API ─────────────────────────────────────────────────────────────────

const mockExtractValues = vi.fn();
const mockEmotionDirectionStream = vi.fn();
const mockWriteStream = vi.fn();
const mockIterateStream = vi.fn();

vi.mock('../../../api/valuesWriter', () => ({
  extractValues: (...args: unknown[]) => mockExtractValues(...args),
  emotionDirectionStream: (...args: unknown[]) => mockEmotionDirectionStream(...args),
  writeStream: (...args: unknown[]) => mockWriteStream(...args),
  iterateStream: (...args: unknown[]) => mockIterateStream(...args),
  getConfig: vi.fn().mockResolvedValue({
    id: 1,
    config_key: 'default',
    extract_values_prompt: null,
    emotion_direction_prompt: null,
    writing_prompt: null,
    iteration_prompt: null,
    model_id: null,
    is_active: true,
    updated_at: null,
  }),
  updateConfig: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../../api/request', () => ({
  get: vi.fn().mockResolvedValue([]),
  post: vi.fn().mockResolvedValue({}),
  put: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../../api/ai', () => ({
  getAiModels: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: { getState: () => ({ token: 'mock-token' }) },
}));

// ── 渲染 helper ───────────────────────────────────────────────────────────────

import { ValuesWriterModule } from '../../../pages/operator/ValuesWriterPage';

function renderModule(kolId = 1) {
  return render(
    <App>
      <ValuesWriterModule kolId={kolId} />
    </App>,
  );
}

// ── 常量 ─────────────────────────────────────────────────────────────────────

const SAMPLE_VALUES = ['真实', '治愈', '共鸣'];

describe('ValuesWriterPage — ValuesWriterModule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Test 1: Step 2 初始化：mock extractValues 返回 values → 渲染 Tags
  // ────────────────────────────────────────────────────────────────────────────
  it('Step 2: 调 extractValues 后渲染价值观 Tag 列表', async () => {
    mockExtractValues.mockResolvedValue({ values: SAMPLE_VALUES });

    renderModule();

    // 等待加载完成，3 个 Tag 都渲染出来
    await waitFor(() => {
      expect(screen.getByText('真实')).toBeInTheDocument();
      expect(screen.getByText('治愈')).toBeInTheDocument();
      expect(screen.getByText('共鸣')).toBeInTheDocument();
    });

    expect(mockExtractValues).toHaveBeenCalledWith(1);
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Test 2: 选 Tag 高亮，超过 3 个无法选中
  // ────────────────────────────────────────────────────────────────────────────
  it('Step 2: 选 Tag 高亮，超过 3 个无法选中', async () => {
    const moreValues = ['真实', '治愈', '共鸣', '温暖', '力量'];
    mockExtractValues.mockResolvedValue({ values: moreValues });

    renderModule();

    await waitFor(() => {
      expect(screen.getByText('真实')).toBeInTheDocument();
    });

    // 已选 0 个
    expect(screen.getByText('已选 0 / 3')).toBeInTheDocument();

    // 选第 1 个
    await act(async () => {
      screen.getByText('真实').click();
    });
    await waitFor(() => expect(screen.getByText('已选 1 / 3')).toBeInTheDocument());

    // 选第 2 个
    await act(async () => {
      screen.getByText('治愈').click();
    });
    await waitFor(() => expect(screen.getByText('已选 2 / 3')).toBeInTheDocument());

    // 选第 3 个
    await act(async () => {
      screen.getByText('共鸣').click();
    });
    await waitFor(() => expect(screen.getByText('已选 3 / 3')).toBeInTheDocument());

    // 尝试选第 4 个：count 依然 3
    await act(async () => {
      screen.getByText('温暖').click();
    });
    // 数量不应超过 3
    expect(screen.getByText('已选 3 / 3')).toBeInTheDocument();
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Test 3: 至少选 1 个后「确认」按钮可点
  // ────────────────────────────────────────────────────────────────────────────
  it('Step 2: 未选时确认按钮 disabled，选 1 个后可点', async () => {
    mockExtractValues.mockResolvedValue({ values: SAMPLE_VALUES });

    renderModule();

    await waitFor(() => screen.getByText('真实'));

    // 未选：disabled
    const confirmBtn = screen.getByRole('button', { name: /确认，生成情绪方向/ });
    expect(confirmBtn).toBeDisabled();

    // 选 1 个
    await act(async () => {
      screen.getByText('真实').click();
    });

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /确认，生成情绪方向/ }),
      ).not.toBeDisabled();
    });
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Test 4: Step 3：mock emotionDirectionStream → onDelta 回调 → TextArea 更新
  // ────────────────────────────────────────────────────────────────────────────
  it('Step 3: emotionDirectionStream 回调更新情绪方向 TextArea', async () => {
    mockExtractValues.mockResolvedValue({ values: SAMPLE_VALUES });

    const emotionText = '轻松真实，有温度，贴近生活';
    mockEmotionDirectionStream.mockImplementation(
      async (_body: unknown, onDelta: (text: string) => void) => {
        onDelta(emotionText);
        return emotionText;
      },
    );

    renderModule();

    // 进入 Step 2
    await waitFor(() => screen.getByText('真实'));

    // 选 1 个
    await act(async () => {
      screen.getByText('真实').click();
    });

    // 进入 Step 3
    await act(async () => {
      screen.getByRole('button', { name: /确认，生成情绪方向/ }).click();
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '生成情绪方向' })).toBeInTheDocument();
    });

    // 点击生成
    await act(async () => {
      screen.getByRole('button', { name: '生成情绪方向' }).click();
    });

    await waitFor(() => {
      expect(screen.getByDisplayValue(emotionText)).toBeInTheDocument();
    });

    expect(mockEmotionDirectionStream).toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Test 5: Step 4：mock writeStream → 内容区更新
  // ────────────────────────────────────────────────────────────────────────────
  it('Step 4: writeStream 回调更新内容区 TextArea', async () => {
    mockExtractValues.mockResolvedValue({ values: SAMPLE_VALUES });

    const emotionText = '轻松真实，有温度，贴近生活';
    mockEmotionDirectionStream.mockImplementation(
      async (_body: unknown, onDelta: (text: string) => void) => {
        onDelta(emotionText);
        return emotionText;
      },
    );

    const generatedContent = '这是生成的价值观仿写内容，充满了真实感和温度。';
    mockWriteStream.mockImplementation(
      async (_body: unknown, onDelta: (text: string) => void) => {
        onDelta(generatedContent);
        return generatedContent;
      },
    );

    renderModule();

    // Step 2: 选价值观
    await waitFor(() => screen.getByText('真实'));
    await act(async () => {
      screen.getByText('真实').click();
    });

    // Step 3: 进入
    await act(async () => {
      screen.getByRole('button', { name: /确认，生成情绪方向/ }).click();
    });
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '生成情绪方向' })).toBeInTheDocument();
    });

    // Step 3: 生成情绪方向
    await act(async () => {
      screen.getByRole('button', { name: '生成情绪方向' }).click();
    });
    await waitFor(() => screen.getByDisplayValue(emotionText));

    // Step 4: 进入
    await act(async () => {
      screen.getByRole('button', { name: /下一步：生成内容/ }).click();
    });
    await waitFor(() => screen.getByRole('button', { name: '开始生成' }));

    // Step 4: 生成内容
    await act(async () => {
      screen.getByRole('button', { name: '开始生成' }).click();
    });

    await waitFor(() => {
      expect(screen.getByDisplayValue(generatedContent)).toBeInTheDocument();
    });

    expect(mockWriteStream).toHaveBeenCalled();
  });
});
