/**
 * HistoryList — 字幕提取统一历史记录（Sprint 21）
 *
 * 单条 + 批量统一展示，按 created_at 倒序。
 * 操作（用户已确认）：
 *   - 单条：查看完整字幕 + 重新生成思维导图 + 复制 + 删除
 *   - 批量：查看任务详情（items 列表）+ 删除
 *
 * 数据来源：listHistory（GET /api/tools/subtitle/batches）
 * 详情按需懒加载：getBatchByJobCode（GET /api/tools/subtitle/batch/{job_code}）
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Card,
  List,
  Tag,
  Typography,
  Button,
  Space,
  Alert,
  Progress,
  Empty,
  App,
} from 'antd';
import {
  CopyOutlined,
  DeleteOutlined,
  ReloadOutlined,
  DownOutlined,
  UpOutlined,
} from '@ant-design/icons';
import {
  listHistory,
  getBatchByJobCode,
  deleteHistory,
  generateMindmap,
} from '../../../api/subtitle';
import type {
  SubtitleJob,
  SubtitleItem,
  MindmapResult,
} from '../../../api/subtitle';
import MindmapView from './MindmapView';

const { Text, Paragraph } = Typography;

const JOB_STATUS_COLORS: Record<string, string> = {
  processing: 'processing',
  completed: 'success',
  failed: 'error',
};

const JOB_STATUS_LABELS: Record<string, string> = {
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
};

const ITEM_STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  processing: 'processing',
  success: 'success',
  failed: 'error',
};

const ITEM_STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  processing: '处理中',
  success: '成功',
  failed: '失败',
};

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '';
  return iso.replace('T', ' ').slice(0, 19);
}

interface HistoryListProps {
  /** 递增触发刷新（外部新建任务后递增即可拉取最新） */
  refreshSignal?: number;
}

export default function HistoryList({ refreshSignal = 0 }: HistoryListProps) {
  const { message } = App.useApp();

  const [jobs, setJobs] = useState<SubtitleJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedCode, setExpandedCode] = useState<string | null>(null);
  const [detailedJob, setDetailedJob] = useState<SubtitleJob | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 单条任务展开后的本地状态（每个 job 一份 mindmap 缓存，避免重复调用）
  const [mindmapCache, setMindmapCache] = useState<Record<string, MindmapResult>>({});
  const [generatingMmFor, setGeneratingMmFor] = useState<string | null>(null);
  const [mmZoom, setMmZoom] = useState(1);

  // 轮询：处理中的任务每 5 秒拉一次
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await listHistory(1, 20);
      setJobs(resp.items);
    } catch (err: unknown) {
      // 静默失败，不打扰用户（首次进入或网络抖动）
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList, refreshSignal]);

  // 自动轮询：列表里只要有 processing 状态的任务，就持续拉取
  useEffect(() => {
    const hasActive = jobs.some((j) => j.status === 'processing');
    if (hasActive && !pollRef.current) {
      pollRef.current = setInterval(loadList, 5000);
    } else if (!hasActive && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [jobs, loadList]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const toggleExpand = async (job: SubtitleJob) => {
    if (expandedCode === job.job_code) {
      setExpandedCode(null);
      setDetailedJob(null);
      return;
    }
    setExpandedCode(job.job_code);
    setDetailedJob(null);
    setDetailLoading(true);
    try {
      const detail = await getBatchByJobCode(job.job_code);
      setDetailedJob(detail);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '加载详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDelete = async (jobCode: string) => {
    try {
      await deleteHistory(jobCode);
      message.success('已删除');
      if (expandedCode === jobCode) {
        setExpandedCode(null);
        setDetailedJob(null);
      }
      await loadList();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).then(() => message.success('已复制'));
  };

  const handleRegenerateMindmap = async (jobCode: string, transcript: string) => {
    setGeneratingMmFor(jobCode);
    try {
      const mm = await generateMindmap(transcript);
      setMindmapCache((prev) => ({ ...prev, [jobCode]: mm }));
      message.success('思维导图生成成功');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '生成失败');
    } finally {
      setGeneratingMmFor(null);
    }
  };

  // 单条任务取 items[0]（item 含视频元信息 + transcript）
  const singleItem: SubtitleItem | null =
    detailedJob?.kind === 'single' && detailedJob.items && detailedJob.items.length > 0
      ? detailedJob.items[0]
      : null;

  const batchProgress =
    detailedJob && detailedJob.total > 0
      ? Math.round(((detailedJob.success + detailedJob.failed) / detailedJob.total) * 100)
      : 0;

  return (
    <Card
      title={
        <Space>
          <Text strong>历史记录</Text>
          <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
            单条 + 批量统一展示
          </Text>
        </Space>
      }
      extra={
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={loadList}
          loading={loading}
        >
          刷新
        </Button>
      }
      styles={{ body: { padding: 16 } }}
    >
      {jobs.length === 0 ? (
        <Empty description="还没有历史记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          loading={detailLoading && !detailedJob}
          dataSource={jobs}
          renderItem={(job) => {
            const isExpanded = expandedCode === job.job_code;
            const isSingle = job.kind === 'single';
            return (
              <List.Item style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                    flexWrap: 'wrap',
                    width: '100%',
                  }}
                >
                  <Space size={6} wrap>
                    <Tag color={isSingle ? 'blue' : 'purple'}>
                      {isSingle ? '单条' : '批量'}
                    </Tag>
                    <Tag color={JOB_STATUS_COLORS[job.status]}>
                      {JOB_STATUS_LABELS[job.status] ?? job.status}
                    </Tag>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {formatTime(job.created_at)}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {job.success}/{job.total} 成功 · {job.failed} 失败
                    </Text>
                  </Space>
                  <Space size={4}>
                    <Button
                      size="small"
                      type="link"
                      onClick={() => toggleExpand(job)}
                    >
                      {isExpanded ? (
                        <>
                          收起 <UpOutlined />
                        </>
                      ) : (
                        <>
                          详情 <DownOutlined />
                        </>
                      )}
                    </Button>
                    <Button
                      size="small"
                      type="link"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => handleDelete(job.job_code)}
                    >
                      删除
                    </Button>
                  </Space>
                </div>

                {isExpanded && (
                  <div
                    style={{
                      marginTop: 12,
                      padding: 12,
                      backgroundColor: 'var(--gray-50)',
                      borderRadius: 8,
                      border: '1px solid var(--gray-100)',
                    }}
                  >
                    {detailLoading && (
                      <Text type="secondary">加载中…</Text>
                    )}

                    {/* 单条任务详情 */}
                    {isSingle && singleItem && (
                      <Space direction="vertical" size={12} style={{ width: '100%' }}>
                        <div>
                          <Text strong>{singleItem.title || '（未命名字幕）'}</Text>
                          <div style={{ marginTop: 4, fontSize: 12, color: 'var(--gray-500)' }}>
                            来源：{singleItem.original_url}
                          </div>
                        </div>

                        {singleItem.status === 'success' && (
                          <>
                            <div
                              style={{
                                padding: 12,
                                backgroundColor: '#fff',
                                border: '1px solid var(--gray-100)',
                                borderRadius: 6,
                                maxHeight: 300,
                                overflowY: 'auto',
                              }}
                            >
                              <pre
                                style={{
                                  margin: 0,
                                  whiteSpace: 'pre-wrap',
                                  wordBreak: 'break-word',
                                  fontSize: 13,
                                  lineHeight: 1.7,
                                  fontFamily: 'var(--font-sans)',
                                }}
                              >
                                {singleItem.transcript}
                              </pre>
                            </div>
                            <Space wrap>
                              <Button
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={() => handleCopy(singleItem.transcript)}
                              >
                                复制字幕
                              </Button>
                              <Button
                                size="small"
                                onClick={() =>
                                  handleRegenerateMindmap(job.job_code, singleItem.transcript)
                                }
                                loading={generatingMmFor === job.job_code}
                              >
                                {generatingMmFor === job.job_code
                                  ? '生成中...'
                                  : mindmapCache[job.job_code]
                                    ? '重新生成思维导图'
                                    : '生成思维导图'}
                              </Button>
                              {mindmapCache[job.job_code] && (
                                <Space size={4}>
                                  <Button
                                    size="small"
                                    type="text"
                                    onClick={() => setMmZoom(Math.max(0.5, mmZoom - 0.1))}
                                  >
                                    −
                                  </Button>
                                  <span
                                    style={{
                                      fontSize: 11,
                                      color: 'var(--gray-500)',
                                      width: 40,
                                      textAlign: 'center',
                                      userSelect: 'none',
                                    }}
                                  >
                                    {Math.round(mmZoom * 100)}%
                                  </span>
                                  <Button
                                    size="small"
                                    type="text"
                                    onClick={() => setMmZoom(Math.min(2, mmZoom + 0.1))}
                                  >
                                    +
                                  </Button>
                                </Space>
                              )}
                            </Space>
                            {mindmapCache[job.job_code] && (
                              <div
                                style={{
                                  height: 'clamp(320px, 48vh, 520px)',
                                  backgroundColor: '#fff',
                                  border: '1px solid var(--gray-100)',
                                  borderRadius: 6,
                                }}
                              >
                                <MindmapView
                                  mindmap={mindmapCache[job.job_code]}
                                  zoom={mmZoom}
                                  onZoomChange={setMmZoom}
                                />
                              </div>
                            )}
                          </>
                        )}

                        {singleItem.status === 'failed' && singleItem.error && (
                          <Alert type="error" message={singleItem.error} banner />
                        )}
                      </Space>
                    )}

                    {/* 批量任务详情 */}
                    {!isSingle && detailedJob && (
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <Paragraph style={{ marginBottom: 0 }}>
                          <Text code>{detailedJob.job_code}</Text>
                        </Paragraph>
                        <Progress
                          percent={batchProgress}
                          status={detailedJob.status === 'failed' ? 'exception' : 'active'}
                        />
                        {detailedJob.items && detailedJob.items.length > 0 && (
                          <List
                            size="small"
                            dataSource={detailedJob.items}
                            renderItem={(item) => (
                              <List.Item>
                                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                                  <Space>
                                    <Tag color={ITEM_STATUS_COLORS[item.status]}>
                                      {ITEM_STATUS_LABELS[item.status] ?? item.status}
                                    </Tag>
                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                      #{item.row_number}
                                    </Text>
                                    {item.title && <Text strong>{item.title}</Text>}
                                  </Space>
                                  <Text
                                    type="secondary"
                                    style={{ fontSize: 11, wordBreak: 'break-all' }}
                                  >
                                    {item.original_url}
                                  </Text>
                                  {item.status === 'success' && item.transcript && (
                                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                      <div
                                        style={{
                                          padding: '8px 10px',
                                          backgroundColor: '#fff',
                                          border: '1px solid var(--gray-100)',
                                          borderRadius: 6,
                                          maxHeight: 200,
                                          overflowY: 'auto',
                                        }}
                                      >
                                        <pre
                                          style={{
                                            margin: 0,
                                            fontSize: 12,
                                            lineHeight: 1.7,
                                            whiteSpace: 'pre-wrap',
                                            wordBreak: 'break-word',
                                            fontFamily: 'var(--font-sans)',
                                          }}
                                        >
                                          {item.transcript}
                                        </pre>
                                      </div>
                                      <Button
                                        size="small"
                                        icon={<CopyOutlined />}
                                        onClick={() => handleCopy(item.transcript)}
                                      >
                                        复制文本
                                      </Button>
                                    </Space>
                                  )}
                                  {item.status === 'failed' && item.error && (
                                    <Alert type="error" message={item.error} banner />
                                  )}
                                </Space>
                              </List.Item>
                            )}
                          />
                        )}
                      </Space>
                    )}
                  </div>
                )}
              </List.Item>
            );
          }}
        />
      )}
    </Card>
  );
}
