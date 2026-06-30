/**
 * SubtitleExtractorPage — 字幕提取（Sprint 19 迁移自旧架构 subtitle-extractor-web）
 *
 * Sprint 20 改造（完整复制旧架构布局）：
 * - 单页面布局（删除 AntD Tabs）
 * - 视频封面图 + 3 列元信息板（作者/点赞数/视频ID）
 * - 同容器内 字幕↔思维导图 视图切换
 * - 自定义 SVG 思维导图（独立组件 MindmapView.tsx）
 * - XMind 客户端导出（exportXmind.ts）
 * - 批量 Excel 拖拽上传（Phase 6 加入 react-dropzone）
 */
import { useEffect, useRef, useState } from 'react';
import { Input, Button, Typography, Space, App, Alert, Dropdown, Card } from 'antd';
import { DownOutlined, CopyOutlined, DownloadOutlined, InboxOutlined } from '@ant-design/icons';
import * as XLSX from 'xlsx';
import JSZip from 'jszip';
import { useDropzone } from 'react-dropzone';
import {
  extractSubtitle,
  generateMindmap,
  createBatch,
  getBatchByJobCode,
  listHistory,
  saveOutput,
} from '../../api/subtitle';
import type {
  ExtractResponse,
  MindmapResult,
  SubtitleItem,
} from '../../api/subtitle';
import MindmapView from './subtitle/MindmapView';
import { exportXmind } from './subtitle/exportXmind';
import HistoryList from './subtitle/HistoryList';

const { TextArea } = Input;
const { Paragraph, Title, Text } = Typography;

function formatCount(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return '-';
  return n >= 10000 ? `${(n / 10000).toFixed(1)}万` : n.toLocaleString();
}

type ViewMode = 'subtitle' | 'mindmap';

export default function SubtitleExtractorPage() {
  const { message } = App.useApp();

  // 单条提取（异步任务 + 轮询）
  const [shareText, setShareText] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [extractElapsed, setExtractElapsed] = useState(0); // 已等待秒数（用于按钮提示）
  const [result, setResult] = useState<SubtitleItem | null>(null);
  const [coverError, setCoverError] = useState(false);
  const extractTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const singleJobCodeRef = useRef<string | null>(null);
  const singlePollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 字幕 / 思维导图视图切换（同一容器内）
  const [viewMode, setViewMode] = useState<ViewMode>('subtitle');
  const [mindmap, setMindmap] = useState<MindmapResult | null>(null);
  const [mmZoom, setMmZoom] = useState(1);
  const [generatingMM, setGeneratingMM] = useState(false);
  const [exportingXmind, setExportingXmind] = useState(false);

  // 保存到产出中心
  const [saving, setSaving] = useState(false);

  // 批量提取
  const [batchInput, setBatchInput] = useState('');
  const [creatingBatch, setCreatingBatch] = useState(false);
  const [parsingExcel, setParsingExcel] = useState(false);

  // 历史记录刷新信号（每次创建任务后递增，触发 HistoryList 重新拉取）
  const [historyRefreshSignal, setHistoryRefreshSignal] = useState(0);

  // Excel 拖拽上传：解析后填充 batchInput TextArea
  const onDrop = async (accepted: File[]) => {
    const file = accepted[0];
    if (!file) return;
    setParsingExcel(true);
    try {
      const buf = await file.arrayBuffer();
      const wb = XLSX.read(buf, { type: 'array' });
      const sheet = wb.Sheets[wb.SheetNames[0]];
      // header:1 模式返回二维数组，自动跳过标题行（不含链接）
      const rows = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1, defval: '' });
      const links: string[] = [];
      for (const row of rows) {
        const cell = String(row[0] ?? '').trim();
        if (cell && /https?:\/\//.test(cell)) links.push(cell);
      }
      if (links.length === 0) {
        message.warning('未在 A 列检测到任何链接（应包含 http 开头的抖音分享链接）');
      } else {
        // 追加到现有 TextArea 末尾
        const prev = batchInput.trim();
        setBatchInput(prev ? `${prev}\n${links.join('\n')}` : links.join('\n'));
        message.success(`已解析 ${links.length} 条链接，可在上方编辑后再提交`);
      }
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : 'Excel 解析失败');
    } finally {
      setParsingExcel(false);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
    },
    multiple: false,
    noKeyboard: true, // TextArea 已经处理键盘输入，dropzone 不抢键盘焦点
  });

  // 清理轮询
  useEffect(() => {
    return () => {
      if (singlePollRef.current) clearInterval(singlePollRef.current);
      if (extractTimerRef.current) clearInterval(extractTimerRef.current);
    };
  }, []);

  // ── 单条提取（异步任务：创建 job → 轮询 → 完成后展示） ──────────────
  const doExtract = async () => {
    const text = shareText.trim();
    if (!text) {
      message.warning('请粘贴抖音分享文本');
      return;
    }
    setExtracting(true);
    setExtractElapsed(0);
    setResult(null);
    setMindmap(null);
    setCoverError(false);
    setViewMode('subtitle');
    // 启动已等待秒数计时（每秒 +1），方便用户感知 ASR 进度
    if (extractTimerRef.current) clearInterval(extractTimerRef.current);
    extractTimerRef.current = setInterval(() => {
      setExtractElapsed((s) => s + 1);
    }, 1000);
    try {
      const resp: ExtractResponse = await extractSubtitle({ share_text: text });
      singleJobCodeRef.current = resp.job_code;
      startSinglePolling(resp.job_code);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '提取失败';
      message.error(msg);
      stopExtractTimer();
      setExtracting(false);
    }
  };

  const stopExtractTimer = () => {
    if (extractTimerRef.current) {
      clearInterval(extractTimerRef.current);
      extractTimerRef.current = null;
    }
  };

  const stopSinglePolling = () => {
    if (singlePollRef.current) {
      clearInterval(singlePollRef.current);
      singlePollRef.current = null;
    }
  };

  const pollSingle = async (jobCode: string) => {
    try {
      const job = await getBatchByJobCode(jobCode);
      if (job.status === 'completed' || job.status === 'failed') {
        stopSinglePolling();
        stopExtractTimer();
        setExtracting(false);
        const item = job.items?.[0];
        if (job.status === 'completed' && item && item.status === 'success') {
          setResult(item);
          message.success(`字幕生成成功（${item.transcript.length} 字符）`);
        } else {
          const errMsg = item?.error || '字幕提取失败';
          message.error(errMsg);
        }
      }
    } catch {
      // 静默失败，下次轮询会重试
    }
  };

  const startSinglePolling = (jobCode: string) => {
    stopSinglePolling();
    // 立即拉一次，然后每 3 秒轮询
    pollSingle(jobCode);
    singlePollRef.current = setInterval(() => {
      pollSingle(jobCode);
    }, 3000);
  };

  // 切换 字幕 / 思维导图（同容器内）
  const handleToggleMindmap = async () => {
    if (viewMode === 'mindmap') {
      setViewMode('subtitle');
      return;
    }
    if (mindmap) {
      setViewMode('mindmap');
      return;
    }
    if (!result?.transcript) return;
    setGeneratingMM(true);
    try {
      const data = await generateMindmap(result.transcript);
      setMindmap(data);
      setViewMode('mindmap');
      message.success('思维导图生成成功');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '生成失败');
    } finally {
      setGeneratingMM(false);
    }
  };

  const handleExportXmind = async () => {
    if (!mindmap) return;
    setExportingXmind(true);
    try {
      const blob = await exportXmind(mindmap);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `mindmap_${Date.now()}.xmind`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      message.success('XMind 文件已下载');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '导出失败');
    } finally {
      setExportingXmind(false);
    }
  };

  const handleCopy = () => {
    if (!result?.transcript) return;
    navigator.clipboard
      .writeText(result.transcript)
      .then(() => message.success('已复制到剪贴板'));
  };

  const doSaveOutput = async () => {
    if (!result?.text) {
      message.warning('请先生成字幕');
      return;
    }
    setSaving(true);
    try {
      const title = result.title || '未命名字幕';
      await saveOutput({ title, transcript: result.transcript, mindmap: mindmap ?? undefined });
      message.success(`已保存到产出中心：${title}`);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  // ── 导出工具（SRT / Excel / Zip）────────────────────────────────────
  const downloadBlob = (data: Blob, filename: string) => {
    const url = URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportSrt = () => {
    if (!result?.transcript) return;
    const lines = result.transcript
      .split(/[。\n！？!?]/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    const srt = lines
      .map((line, i) => `${i + 1}\n00:00:${String(i * 3).padStart(2, '0')},000 --> 00:00:${String(i * 3 + 3).padStart(2, '0')},000\n${line}\n`)
      .join('\n');
    downloadBlob(new Blob([srt], { type: 'text/plain;charset=utf-8' }), `${result.title || '字幕'}.srt`);
  };

  const exportExcel = () => {
    if (!result?.transcript) return;
    const wb = XLSX.utils.book_new();
    const subtitleRows = result.transcript
      .split('\n')
      .map((line, i) => ({ 行号: i + 1, 内容: line.trim() }))
      .filter((r) => r.内容.length > 0);
    const ws1 = XLSX.utils.json_to_sheet(subtitleRows);
    XLSX.utils.book_append_sheet(wb, ws1, '字幕');
    if (mindmap) {
      const mmRows: { 分支: string; 要点: string }[] = [];
      mindmap.branches.forEach((b) => {
        if (b.children?.length > 0) {
          b.children.forEach((c) => mmRows.push({ 分支: b.title, 要点: c }));
        } else {
          mmRows.push({ 分支: b.title, 要点: '' });
        }
      });
      const ws2 = XLSX.utils.json_to_sheet([{ 核心主题: mindmap.rootTitle, 总结: mindmap.summary }]);
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
    if (!result?.transcript) return;
    const zip = new JSZip();
    zip.file('字幕.txt', result.transcript);
    if (mindmap) zip.file('思维导图.json', JSON.stringify(mindmap, null, 2));
    const lines = result.transcript
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

  // ── 批量任务 ────────────────────────────────────────────────────────
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
    try {
      const data = await createBatch(items.map((share_text) => ({ share_text })));
      message.success(`批量任务已创建（${data.total} 条），任务码：${data.job_code}`);
      // 通知历史记录组件刷新（同时它会自动轮询直到任务完成）
      setHistoryRefreshSignal((s) => s + 1);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '批量任务创建失败');
    } finally {
      setCreatingBatch(false);
    }
  };

  // 字幕容器高度（思维导图模式更高）
  const subtitleBoxHeight = viewMode === 'mindmap'
    ? 'clamp(320px, 48vh, 520px)'
    : 'clamp(260px, 32vh, 300px)';

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>字幕提取</Title>
      <Paragraph type="secondary">
        粘贴抖音视频分享链接，提取视频封面、基础信息和字幕文案 · 支持批量 Excel 导入。
      </Paragraph>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* ── 单条提取 ── */}
        <Card styles={{ body: { padding: 20 } }}>
          <Title level={5} style={{ marginTop: 0, marginBottom: 4 }}>单条视频 ASR 转换</Title>
          <Paragraph type="secondary" style={{ marginBottom: 16, fontSize: 13 }}>
            粘贴抖音视频分享链接，提取视频封面、基础信息和字幕文案。
          </Paragraph>

          {/* 输入行 */}
          <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
            <Input
              placeholder="粘贴抖音视频分享链接，例如：https://v.douyin.com/xxx/"
              value={shareText}
              onChange={(e) => setShareText(e.target.value)}
              onPressEnter={doExtract}
              disabled={extracting}
              size="large"
              style={{ flex: 1 }}
            />
            <Button
              type="primary"
              size="large"
              loading={extracting}
              onClick={doExtract}
              style={{ marginLeft: 8 }}
            >
              {extracting ? `解析中… ${extractElapsed}s（ASR 约 1-3 分钟）` : '提取视频内容'}
            </Button>
          </Space.Compact>

          {/* 解析进度提示（loading 时显示在按钮下方）*/}
          {extracting && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--gray-500)' }}>
              正在调用 TikHub 解析视频 + 阿里云 ASR 转写音频，请耐心等待（最长 10 分钟）…
            </div>
          )}

          {/* 结果区：封面 + 视频 info + 字幕/思维导图容器 */}
          {result && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(280px, 360px) 1fr',
                gap: 20,
                marginTop: 8,
              }}
            >
              {/* 封面图 */}
              <div
                style={{
                  position: 'relative',
                  minHeight: 480,
                  borderRadius: 12,
                  overflow: 'hidden',
                  border: '1px solid var(--gray-200)',
                  background: 'var(--gray-100)',
                }}
              >
                {result.cover_url && !coverError ? (
                  <img
                    src={result.cover_url}
                    alt="封面"
                    style={{
                      position: 'absolute',
                      inset: 0,
                      width: '100%',
                      height: '100%',
                      objectFit: 'cover',
                    }}
                    onError={() => setCoverError(true)}
                  />
                ) : (
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'var(--gray-300)',
                      fontSize: 64,
                    }}
                  >
                    ▶
                  </div>
                )}
                <div
                  style={{
                    position: 'absolute',
                    left: 12,
                    bottom: 12,
                    padding: '4px 10px',
                    borderRadius: 999,
                    background: 'rgba(0,0,0,0.6)',
                    color: '#fff',
                    fontSize: 12,
                  }}
                >
                  ▶ 视频封面
                </div>
              </div>

              {/* 右列：视频信息 + 字幕/思维导图 */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
                {/* 视频信息卡 */}
                <div
                  style={{
                    border: '1px solid var(--gray-200)',
                    borderRadius: 12,
                    padding: 16,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                    <Text strong style={{ fontSize: 15, lineHeight: 1.4, flex: 1 }}>
                      {result.title || '（未命名字幕）'}
                    </Text>
                    {result.play_url && (
                      <a href={result.play_url} target="_blank" rel="noopener noreferrer">
                        <Button size="small">下载视频</Button>
                      </a>
                    )}
                  </div>

                  {/* 3 列元信息板 */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, 1fr)',
                      gap: 8,
                    }}
                  >
                    <MetaCard label="作者" value={result.nickname || '-'} />
                    <MetaCard label="点赞数" value={formatCount(result.digg_count)} />
                    <MetaCard label="视频 ID" value={result.aweme_id || '-'} mono />
                  </div>
                </div>

                {/* 字幕 / 思维导图容器（同容器内切换）*/}
                <div
                  style={{
                    border: '1px solid var(--gray-200)',
                    borderRadius: 12,
                    padding: 16,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12,
                  }}
                >
                  {/* Header：标题 + 操作按钮 */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                    <Text strong style={{ fontSize: 13 }}>字幕内容</Text>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <Button size="small" icon={<CopyOutlined />} onClick={handleCopy}>
                        复制
                      </Button>
                      <Button size="small" onClick={handleToggleMindmap} loading={generatingMM}>
                        {generatingMM ? '生成中...' : viewMode === 'mindmap' ? '文案' : '思维导图'}
                      </Button>
                      {viewMode === 'mindmap' && mindmap && (
                        <>
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              border: '1px solid var(--gray-300)',
                              borderRadius: 6,
                              overflow: 'hidden',
                            }}
                          >
                            <Button size="small" type="text" onClick={() => setMmZoom(Math.max(0.5, mmZoom - 0.1))}>−</Button>
                            <span style={{ fontSize: 11, color: 'var(--gray-500)', width: 40, textAlign: 'center', userSelect: 'none' }}>
                              {Math.round(mmZoom * 100)}%
                            </span>
                            <Button size="small" type="text" onClick={() => setMmZoom(Math.min(2, mmZoom + 0.1))}>+</Button>
                          </div>
                          <Button
                            size="small"
                            icon={<DownloadOutlined />}
                            onClick={handleExportXmind}
                            loading={exportingXmind}
                          >
                            {exportingXmind ? '导出中...' : '导出 XMind'}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* 内容盒（字幕 or 思维导图） */}
                  <div
                    style={{
                      border: '1px solid var(--gray-100)',
                      borderRadius: 8,
                      backgroundColor: 'var(--gray-50)',
                      height: subtitleBoxHeight,
                      position: 'relative',
                    }}
                  >
                    {viewMode === 'subtitle' && (
                      <div style={{ padding: 12, height: '100%', overflowY: 'auto' }}>
                        {result.transcript ? (
                          <pre
                            style={{
                              margin: 0,
                              fontSize: 13,
                              color: 'var(--gray-800)',
                              lineHeight: 1.7,
                              whiteSpace: 'pre-wrap',
                              fontFamily: 'var(--font-sans)',
                              wordBreak: 'break-word',
                            }}
                          >
                            {result.transcript}
                          </pre>
                        ) : (
                          <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: '32px 0' }}>
                            暂无字幕文本
                          </Text>
                        )}
                      </div>
                    )}

                    {viewMode === 'mindmap' && mindmap && (
                      <MindmapView mindmap={mindmap} zoom={mmZoom} onZoomChange={setMmZoom} />
                    )}
                  </div>

                  {/* 保存到产出中心 + 导出菜单 */}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <Button size="small" loading={saving} onClick={doSaveOutput}>
                      保存到产出中心
                    </Button>
                    <Dropdown menu={{ items: exportMenuItems }}>
                      <Button size="small">
                        导出 <DownOutlined />
                      </Button>
                    </Dropdown>
                  </div>
                </div>
              </div>
            </div>
          )}
        </Card>

        {/* ── 批量提取 ── */}
        <Card styles={{ body: { padding: 20 } }}>
          <Title level={5} style={{ marginTop: 0, marginBottom: 4 }}>批量提取</Title>
          <Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 13 }}>
            每行一条抖音分享文本，提交后后台批量执行（5-30 分钟/条）。任务与你的账号绑定，下方「我的批量任务」可随时查看进度。
          </Paragraph>

          {/* Excel 格式说明 */}
          <div
            style={{
              padding: 12,
              backgroundColor: 'var(--gray-50)',
              border: '1px solid var(--gray-100)',
              borderRadius: 8,
              marginBottom: 12,
              fontSize: 12,
              color: 'var(--gray-500)',
            }}
          >
            <div style={{ fontWeight: 500, color: 'var(--gray-600)', marginBottom: 4 }}>Excel 格式说明</div>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              <li>A 列填写抖音视频分享链接，每行一条</li>
              <li>首行为标题行时自动跳过（不含链接则忽略）</li>
              <li>支持 .xlsx / .xls 格式，最多 200 条</li>
            </ul>
          </div>

          {/* TextArea 输入 */}
          <TextArea
            value={batchInput}
            onChange={(e) => setBatchInput(e.target.value)}
            placeholder={'每行一条抖音分享文本，例如：\n7.69 复制打开抖音... https://v.douyin.com/aaa/\n3.21 复制打开抖音... https://v.douyin.com/bbb/'}
            rows={6}
            disabled={creatingBatch}
            style={{ marginBottom: 12 }}
          />

          {/* Excel 拖拽上传区（与 TextArea 共存） */}
          <div
            {...getRootProps()}
            style={{
              padding: '24px 16px',
              marginBottom: 12,
              borderRadius: 12,
              border: `2px dashed ${isDragActive ? 'var(--brand)' : 'var(--gray-300)'}`,
              backgroundColor: isDragActive ? 'var(--brand-light)' : 'var(--gray-50)',
              cursor: 'pointer',
              textAlign: 'center',
              transition: 'border-color 0.2s, background-color 0.2s',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <input {...getInputProps()} />
            <InboxOutlined style={{ fontSize: 28, color: 'var(--gray-400)' }} />
            <Text type="secondary" style={{ fontSize: 13 }}>
              {parsingExcel
                ? '解析中...'
                : isDragActive
                  ? '松开鼠标即可上传'
                  : '拖拽 Excel 到此处，或点击选择文件'}
            </Text>
            <Text type="secondary" style={{ fontSize: 11 }}>
              支持 .xlsx / .xls，A 列为链接，最多 200 条；解析后填充到上方文本框
            </Text>
          </div>

          {/* 操作行 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <Text type="secondary" style={{ fontSize: 13 }}>
              {parseBatchItems().length} 条待提交
            </Text>
            <Button
              type="primary"
              loading={creatingBatch}
              onClick={doCreateBatch}
            >
              提交批量任务
            </Button>
          </div>
        </Card>

        {/* ── 历史记录（单条 + 批量统一） ── */}
        <HistoryList refreshSignal={historyRefreshSignal} />
      </Space>
    </div>
  );
}

// ── 内联组件：3 列元信息板单元 ─────────────────────────────────────────
interface MetaCardProps {
  label: string;
  value: string;
  mono?: boolean;
}

function MetaCard({ label, value, mono }: MetaCardProps) {
  if (!value) return null;
  return (
    <div
      style={{
        padding: 10,
        border: '1px solid var(--gray-100)',
        borderRadius: 8,
        backgroundColor: 'var(--gray-50)',
      }}
    >
      <div style={{ fontSize: 12, color: 'var(--gray-400)', marginBottom: 4 }}>{label}</div>
      <div
        style={{
          fontSize: 13,
          fontWeight: 500,
          color: 'var(--gray-800)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          fontFamily: mono ? 'var(--font-mono)' : undefined,
        }}
      >
        {value}
      </div>
    </div>
  );
}
