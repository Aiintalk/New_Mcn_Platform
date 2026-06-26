import { useState, useEffect, useRef } from 'react';
import { Input, Button, Tabs, Typography, Space, App, Card, List, Tag, Divider, Progress, Alert, Dropdown } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import * as XLSX from 'xlsx';
import JSZip from 'jszip';
import {
  extractSubtitle,
  generateMindmap,
  createBatch,
  getBatchByJobCode,
  saveOutput,
} from '../../api/subtitle';
import type {
  ExtractResult,
  MindmapResult,
  SubtitleJob,
} from '../../api/subtitle';

const { TextArea } = Input;
const { Paragraph, Title, Text } = Typography;

const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  processing: 'processing',
  success: 'success',
  failed: 'error',
};

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  processing: '处理中',
  success: '成功',
  failed: '失败',
};

const JOB_STATUS_LABELS: Record<string, string> = {
  processing: '处理中',
  completed: '已完成',
  failed: '全部失败',
};

export default function SubtitleExtractorPage() {
  const { message } = App.useApp();

  // 单条提取状态
  const [shareText, setShareText] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [result, setResult] = useState<ExtractResult | null>(null);

  // 思维导图状态（基于 result.text）
  const [mindmap, setMindmap] = useState<MindmapResult | null>(null);
  const [generatingMM, setGeneratingMM] = useState(false);

  // 批量提取状态
  const [batchInput, setBatchInput] = useState('');
  const [creatingBatch, setCreatingBatch] = useState(false);
  const [batchJob, setBatchJob] = useState<SubtitleJob | null>(null);
  const [accessCode, setAccessCode] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 清理轮询
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const doExtract = async () => {
    const text = shareText.trim();
    if (!text) {
      message.warning('请粘贴抖音分享文本');
      return;
    }
    setExtracting(true);
    setResult(null);
    setMindmap(null);
    try {
      const data = await extractSubtitle({ share_text: text });
      setResult(data);
      message.success(`字幕生成成功（${data.text.length} 字符）`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '提取失败';
      message.error(msg);
    } finally {
      setExtracting(false);
    }
  };

  const doGenerateMindmap = async () => {
    const transcript = result?.text || '';
    if (!transcript) {
      message.warning('请先生成字幕');
      return;
    }
    setGeneratingMM(true);
    try {
      const data = await generateMindmap(transcript);
      setMindmap(data);
      message.success('思维导图生成成功');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '生成失败';
      message.error(msg);
    } finally {
      setGeneratingMM(false);
    }
  };

  // 保存到产出中心
  const [saving, setSaving] = useState(false);
  const doSaveOutput = async () => {
    if (!result?.text) {
      message.warning('请先生成字幕');
      return;
    }
    setSaving(true);
    try {
      const title = result.title || '未命名字幕';
      await saveOutput({ title, transcript: result.text, mindmap: mindmap ?? undefined });
      message.success(`已保存到产出中心：${title}`);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  // 导出工具
  const downloadBlob = (data: Blob, filename: string) => {
    const url = URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportSrt = () => {
    if (!result?.text) {
      message.warning('请先生成字幕');
      return;
    }
    // 简单策略：按句号/换行切分，生成带占位时间轴的 SRT
    const lines = result.text
      .split(/[。\n！？!?]/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    const srt = lines
      .map((line, i) => `${i + 1}\n00:00:${String(i * 3).padStart(2, '0')},000 --> 00:00:${String(i * 3 + 3).padStart(2, '0')},000\n${line}\n`)
      .join('\n');
    downloadBlob(new Blob([srt], { type: 'text/plain;charset=utf-8' }), `${result.title || '字幕'}.srt`);
  };

  const exportExcel = () => {
    if (!result?.text) {
      message.warning('请先生成字幕');
      return;
    }
    const wb = XLSX.utils.book_new();
    // Sheet 1: 字幕
    const subtitleRows = result.text
      .split('\n')
      .map((line, i) => ({ 行号: i + 1, 内容: line.trim() }))
      .filter((r) => r.内容.length > 0);
    const ws1 = XLSX.utils.json_to_sheet(subtitleRows);
    XLSX.utils.book_append_sheet(wb, ws1, '字幕');
    // Sheet 2: 思维导图（如有）
    if (mindmap) {
      const mmRows: { 分支: string; 要点: string }[] = [];
      mindmap.branches.forEach((b) => {
        if (b.children?.length > 0) {
          b.children.forEach((c) => mmRows.push({ 分支: b.title, 要点: c }));
        } else {
          mmRows.push({ 分支: b.title, 要点: '' });
        }
      });
      const ws2 = XLSX.utils.json_to_sheet([
        { 核心主题: mindmap.rootTitle, 总结: mindmap.summary },
      ]);
      XLSX.utils.book_append_sheet(wb, ws2, '主题');
      if (mmRows.length > 0) {
        const ws3 = XLSX.utils.json_to_sheet(mmRows);
        XLSX.utils.book_append_sheet(wb, ws3, '思维导图');
      }
    }
    const buf = XLSX.write(wb, { type: 'array', bookType: 'xlsx' });
    downloadBlob(new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), `${result.title || '字幕'}.xlsx`);
  };

  const exportZip = async () => {
    if (!result?.text) {
      message.warning('请先生成字幕');
      return;
    }
    const zip = new JSZip();
    zip.file('字幕.txt', result.text);
    if (mindmap) {
      zip.file('思维导图.json', JSON.stringify(mindmap, null, 2));
    }
    // 把字幕也按 SRT 加进去
    const lines = result.text
      .split(/[。\n！？!?]/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    const srt = lines
      .map((line, i) => `${i + 1}\n00:00:${String(i * 3).padStart(2, '0')},000 --> 00:00:${String(i * 3 + 3).padStart(2, '0')},000\n${line}\n`)
      .join('\n');
    zip.file('字幕.srt', srt);
    const blob = await zip.generateAsync({ type: 'blob' });
    downloadBlob(blob, `${result.title || '字幕'}.zip`);
  };

  const exportMenuItems = [
    { key: 'srt', label: '导出 SRT', onClick: exportSrt },
    { key: 'excel', label: '导出 Excel', onClick: exportExcel },
    { key: 'zip', label: '导出 Zip', onClick: exportZip },
  ];

  // 批量：解析 textarea 每行一个 share_text
  const parseBatchItems = (): string[] =>
    batchInput
      .split('\n')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

  const doCreateBatch = async () => {
    const items = parseBatchItems();
    if (items.length === 0) {
      message.warning('请输入至少一条抖音分享文本（每行一条）');
      return;
    }
    setCreatingBatch(true);
    setBatchJob(null);
    try {
      const data = await createBatch(items.map((share_text) => ({ share_text })));
      message.success(`批量任务已创建（${data.total} 条），access_code: ${data.access_code}`);
      setAccessCode(data.access_code);
      // 立刻拉一次 + 启动轮询
      await pollBatch(data.job_code);
      startPolling(data.job_code);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '批量任务创建失败';
      message.error(msg);
    } finally {
      setCreatingBatch(false);
    }
  };

  const pollBatch = async (jobCode: string) => {
    try {
      const job = await getBatchByJobCode(jobCode);
      setBatchJob(job);
      if (job.status !== 'processing') {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    } catch {
      // 静默失败，下次轮询继续
    }
  };

  const startPolling = (jobCode: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => {
      pollBatch(jobCode);
    }, 5000);
  };

  // 按 access_code 查询（跨设备）
  const doQueryByAccess = async () => {
    const code = accessCode.trim();
    if (!code) {
      message.warning('请输入 access_code');
      return;
    }
    try {
      const { getBatchByAccessCode } = await import('../../api/subtitle');
      const job = await getBatchByAccessCode(code);
      setBatchJob(job);
      if (job.status === 'processing') {
        startPolling(job.job_code);
      }
      message.success('查询成功');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '查询失败';
      message.error(msg);
    }
  };

  const batchProgress =
    batchJob && batchJob.total > 0
      ? Math.round(((batchJob.success + batchJob.failed) / batchJob.total) * 100)
      : 0;

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>字幕提取</Title>
      <Paragraph type="secondary">
        粘贴抖音分享文本，自动提取视频字幕（基于阿里云 ASR）+ AI 生成思维导图。
      </Paragraph>

      <Tabs
        defaultActiveKey="single"
        items={[
          {
            key: 'single',
            label: '单条提取',
            children: (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <TextArea
                  value={shareText}
                  onChange={(e) => setShareText(e.target.value)}
                  placeholder="粘贴抖音分享文本（如：7.69 复制打开抖音... https://v.douyin.com/xxx/）"
                  rows={4}
                  disabled={extracting}
                />
                <Space>
                  <Button type="primary" loading={extracting} onClick={doExtract}>
                    {extracting ? '提取中（约 5-10 分钟）' : '提取字幕'}
                  </Button>
                  {result && (
                    <Button onClick={() => navigator.clipboard.writeText(result.text)}>
                      复制字幕
                    </Button>
                  )}
                  {result && (
                    <Button loading={saving} onClick={doSaveOutput}>
                      保存到产出中心
                    </Button>
                  )}
                  {result && (
                    <Dropdown menu={{ items: exportMenuItems }}>
                      <Button>
                        导出 <DownOutlined />
                      </Button>
                    </Dropdown>
                  )}
                </Space>

                {result && (
                  <div>
                    {result.title && (
                      <Paragraph type="secondary">视频标题：{result.title}</Paragraph>
                    )}
                    <TextArea
                      value={result.text}
                      readOnly
                      autoSize={{ minRows: 6, maxRows: 20 }}
                    />
                  </div>
                )}
              </Space>
            ),
          },
          {
            key: 'mindmap',
            label: '思维导图',
            children: (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Paragraph type="secondary">
                  基于当前字幕生成思维导图（rootTitle + summary + branches）。
                  {!result?.text && <Text type="warning"> 请先在「单条提取」生成字幕。</Text>}
                </Paragraph>
                <Space>
                  <Button
                    type="primary"
                    loading={generatingMM}
                    onClick={doGenerateMindmap}
                    disabled={!result?.text}
                  >
                    生成思维导图
                  </Button>
                </Space>

                {mindmap && (
                  <Card title={`核心主题：${mindmap.rootTitle}`} size="small">
                    <Paragraph type="secondary">总结：{mindmap.summary}</Paragraph>
                    <Divider style={{ margin: '8px 0' }} />
                    <List
                      itemLayout="vertical"
                      dataSource={mindmap.branches}
                      renderItem={(branch, idx) => (
                        <List.Item key={idx}>
                          <Space direction="vertical" size="small" style={{ width: '100%' }}>
                            <Text strong>
                              <Tag color="blue">分支 {idx + 1}</Tag>
                              {branch.title}
                            </Text>
                            {branch.children?.length > 0 && (
                              <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                                {branch.children.map((c, ci) => (
                                  <li key={ci}><Text>{c}</Text></li>
                                ))}
                              </ul>
                            )}
                          </Space>
                        </List.Item>
                      )}
                    />
                  </Card>
                )}
              </Space>
            ),
          },
          {
            key: 'batch',
            label: '批量提取',
            children: (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Paragraph type="secondary">
                  每行一条抖音分享文本，提交后后台批量执行（5-30 分钟/条）。
                  提交后会返回 <Text code>access_code</Text>，可跨设备继续查询进度。
                </Paragraph>

                <TextArea
                  value={batchInput}
                  onChange={(e) => setBatchInput(e.target.value)}
                  placeholder={'每行一条抖音分享文本，例如：\n7.69 复制打开抖音... https://v.douyin.com/aaa/\n3.21 复制打开抖音... https://v.douyin.com/bbb/'}
                  rows={6}
                  disabled={creatingBatch}
                />

                <Space>
                  <Button
                    type="primary"
                    loading={creatingBatch}
                    onClick={doCreateBatch}
                  >
                    提交批量任务
                  </Button>
                  <Text type="secondary">
                    {parseBatchItems().length} 条待提交
                  </Text>
                </Space>

                <Divider style={{ margin: '8px 0' }} />

                <Paragraph type="secondary" style={{ marginBottom: 4 }}>
                  用 access_code 跨设备查询：
                </Paragraph>
                <Space>
                  <Input
                    value={accessCode}
                    onChange={(e) => setAccessCode(e.target.value)}
                    placeholder="XXXX-XXXX"
                    style={{ width: 200 }}
                  />
                  <Button onClick={doQueryByAccess}>查询</Button>
                </Space>

                {batchJob && (
                  <Card
                    title={
                      <Space>
                        <Text>任务进度</Text>
                        <Tag color={batchJob.status === 'completed' ? 'success' : 'processing'}>
                          {JOB_STATUS_LABELS[batchJob.status] ?? batchJob.status}
                        </Tag>
                      </Space>
                    }
                    size="small"
                  >
                    <Paragraph style={{ marginBottom: 8 }}>
                      <Text code>{batchJob.job_code}</Text>
                      <Text type="secondary" style={{ marginLeft: 8 }}>
                        access_code: <Text code>{batchJob.access_code}</Text>
                      </Text>
                    </Paragraph>
                    <Progress percent={batchProgress} status={batchJob.status === 'failed' ? 'exception' : 'active'} />
                    <Paragraph type="secondary" style={{ marginTop: 8 }}>
                      共 {batchJob.total} 条 · 成功 {batchJob.success} · 失败 {batchJob.failed}
                    </Paragraph>
                    {batchJob.items && batchJob.items.length > 0 && (
                      <List
                        size="small"
                        dataSource={batchJob.items}
                        renderItem={(item) => (
                          <List.Item>
                            <Space direction="vertical" size={2} style={{ width: '100%' }}>
                              <Space>
                                <Tag color={STATUS_COLORS[item.status]}>
                                  {STATUS_LABELS[item.status] ?? item.status}
                                </Tag>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  #{item.row_number}
                                </Text>
                                {item.title && <Text strong>{item.title}</Text>}
                              </Space>
                              <Text type="secondary" style={{ fontSize: 11, wordBreak: 'break-all' }}>
                                {item.original_url}
                              </Text>
                              {item.status === 'success' && item.transcript && (
                                <Text style={{ fontSize: 12 }}>
                                  {item.transcript.slice(0, 120)}
                                  {item.transcript.length > 120 ? '...' : ''}
                                </Text>
                              )}
                              {item.status === 'failed' && item.error && (
                                <Alert type="error" message={item.error} style={{ marginTop: 4 }} banner />
                              )}
                            </Space>
                          </List.Item>
                        )}
                      />
                    )}
                  </Card>
                )}
              </Space>
            ),
          },
        ]}
      />
    </div>
  );
}
