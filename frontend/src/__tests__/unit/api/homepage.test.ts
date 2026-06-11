import { describe, it, expect, vi, beforeEach } from 'vitest';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('../../../api/request', () => ({
  get: mockGet,
}));

import { getHomepageStats, getHomepageTrend } from '../../../api/homepage';

describe('homepage API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getHomepageStats calls GET /api/operator/homepage/stats', async () => {
    const stats = {
      today_outputs: 5,
      today_outputs_change: '+10%',
      week_outputs: 30,
      week_outputs_change: null,
      in_progress_tasks: 2,
      week_token_usage: null,
      week_tool_count: 3,
      tool_usage_breakdown: [],
      recent_tools: [],
      last_login_at: null,
    };
    mockGet.mockResolvedValue(stats);
    const result = await getHomepageStats();
    expect(mockGet).toHaveBeenCalledWith('/api/operator/homepage/stats');
    expect(result.today_outputs).toBe(5);
    expect(result.week_outputs).toBe(30);
  });

  it('getHomepageTrend calls GET /api/operator/homepage/trend', async () => {
    const trend = {
      trend: [
        { date: '06-05', count: 3 },
        { date: '06-06', count: 0 },
      ],
    };
    mockGet.mockResolvedValue(trend);
    const result = await getHomepageTrend();
    expect(mockGet).toHaveBeenCalledWith('/api/operator/homepage/trend');
    expect(result.trend).toHaveLength(2);
    expect(result.trend[0].date).toBe('06-05');
  });
});
