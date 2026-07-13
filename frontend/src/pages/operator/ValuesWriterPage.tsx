import { useEffect, useState } from 'react';
import { App, Input, Select, Steps } from 'antd';
import {
  deriveDirections,
  generateValueScript,
  saveOutput,
  type EmotionDirection,
} from '../../api/valuesWriter';
import { getActiveProducts, updateActiveProducts } from '../../api/kolWorkspace';
import { getQianchuanProducts } from '../../api/qianchuanProducts';
import { get } from '../../api/request';
import type { QianchuanProduct } from '../../types/kolWorkspace';
import type { QianchuanWriterPersona } from '../../types/qianchuanWriter';

const { TextArea } = Input;

export interface ValueScriptResult {
  analysis: string;
  rewrite: string;
  report: string;
}

export function calculateBigramSimilarity(original: string, rewritten: string): number {
  const pairs = (value: string) => {
    const cleaned = value.replace(/\s/g, '');
    return new Set(Array.from({ length: Math.max(cleaned.length - 1, 0) }, (_, index) => cleaned.slice(index, index + 2)));
  };
  const left = pairs(original);
  const right = pairs(rewritten);
  const overlap = [...left].filter((pair) => right.has(pair)).length;
  const union = left.size + right.size - overlap;
  return union ? Math.round((overlap / union) * 100) : 0;
}

export function similarityStatus(similarity: number): string {
  return similarity > 50 ? '需要继续改写' : similarity > 35 ? '接近安全线' : '安全';
}

export function parseValueScriptResult(content: string): ValueScriptResult | null {
  const take = (tag: string) => content.match(new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`))?.[1].trim();
  const analysis = take('analysis');
  const rewrite = take('rewrite');
  const report = take('report');
  return analysis && rewrite && report ? { analysis, rewrite, report } : null;
}

function productSummary(product: QianchuanProduct): string {
  return [product.core_selling_point, product.mechanism, product.unique_selling].filter(Boolean).join('；');
}

function downloadText(content: string, productName: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `价值观仿写_${productName || '终稿'}.txt`;
  link.click();
  URL.revokeObjectURL(url);
}

export function ValuesWriterModule({ kolId }: { kolId: number }) {
  const { message } = App.useApp();
  const [step, setStep] = useState(0);
  const [openingLine, setOpeningLine] = useState('');
  const [originalScript, setOriginalScript] = useState('');
  const [products, setProducts] = useState<QianchuanProduct[]>([]);
  const [currentProduct, setCurrentProduct] = useState<QianchuanProduct | null>(null);
  const [directions, setDirections] = useState<EmotionDirection[]>([]);
  const [direction, setDirection] = useState<EmotionDirection | null>(null);
  const [loading, setLoading] = useState(false);
  const [rawResult, setRawResult] = useState('');
  const [result, setResult] = useState<ValueScriptResult | null>(null);
  const [activeResult, setActiveResult] = useState<'script' | 'report'>('script');
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([getActiveProducts(kolId), getQianchuanProducts({ page_size: 50 })])
      .then(([active, page]) => {
        setCurrentProduct(active[0] ?? null);
        setProducts(page.items ?? []);
      })
      .catch(() => setError('商品信息加载失败，请刷新后重试'));
  }, [kolId]);

  async function selectProduct(productId: number) {
    try {
      await updateActiveProducts(kolId, [productId]);
      setCurrentProduct(products.find((product) => product.id === productId) ?? null);
      message.success('当前商品已更新');
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '切换当前商品失败');
    }
  }

  async function handleDirections() {
    if (!currentProduct) {
      setError('请先在产品库选择当前商品');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const response = await deriveDirections({ kol_id: kolId, opening_line: openingLine, original_script: originalScript });
      setDirections(response.directions);
      setDirection(null);
      setStep(2);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '情绪方向生成失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerate() {
    if (!direction) return;
    setLoading(true);
    setError('');
    setRawResult('');
    setResult(null);
    try {
      const content = await generateValueScript({
        kol_id: kolId,
        opening_line: openingLine,
        original_script: originalScript,
        direction,
      }, setRawResult);
      const parsed = parseValueScriptResult(content);
      if (!parsed) {
        setError('生成结果缺少结构分析、改写脚本或情绪检测报告，请重新生成');
        return;
      }
      setResult(parsed);
      setActiveResult('script');
      setStep(3);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '脚本生成失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!result) return;
    await saveOutput({
      content: `=== 价值观脚本 ===\n\n${result.rewrite}\n\n=== 情绪检测报告 ===\n\n${result.report}`,
      title: `价值观仿写 · ${currentProduct?.nickname ?? ''}`.trim(),
      topic: direction?.title ?? null,
    });
    message.success('已保存到产出中心');
  }

  const similarity = result ? calculateBigramSimilarity(originalScript, result.rewrite) : null;
  const similarityText = similarity === null ? '' : similarityStatus(similarity);

  return (
    <div>
      <div className="page-header" style={{ marginBottom: 'var(--sp-4)' }}>
        <div>
          <h1 className="page-title">价值观仿写</h1>
          <p className="page-desc">锁定开头、选择当前商品、人工确认情绪方向后生成脚本</p>
        </div>
      </div>
      <Steps current={step} size="small" style={{ marginBottom: 'var(--sp-6)' }} items={[
        { title: '输入爆款原文' }, { title: '选择产品' }, { title: '选择情绪方向' }, { title: '脚本和报告' },
      ]} />
      {error && <div role="alert" className="card" style={{ marginBottom: 16, color: 'var(--danger)' }}>{error}</div>}

      {step === 0 && <div className="card"><div className="card-body">
        <h2 className="card-title">输入爆款原文</h2>
        <label htmlFor="value-opening" style={{ display: 'block', marginTop: 16 }}>锁定开头</label>
        <TextArea id="value-opening" aria-label="锁定开头" rows={2} value={openingLine} onChange={(event) => setOpeningLine(event.target.value)} placeholder="粘贴爆款的第一句话，生成时将逐字保留" />
        <label htmlFor="value-original" style={{ display: 'block', marginTop: 16 }}>爆款全文</label>
        <TextArea id="value-original" aria-label="爆款全文" rows={10} value={originalScript} onChange={(event) => setOriginalScript(event.target.value)} placeholder="粘贴完整爆款原文" />
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}><button className="btn btn-primary" disabled={!openingLine.trim() || !originalScript.trim()} onClick={() => setStep(1)}>下一步：选择产品 →</button></div>
      </div></div>}

      {step === 1 && <div className="card"><div className="card-body">
        <h2 className="card-title">选择当前商品</h2>
        <p>当前商品只用来推导情绪方向，最终脚本不会出现商品名称和直接商品信息。</p>
        <Select aria-label="当前商品" value={currentProduct?.id} placeholder="请选择当前商品" style={{ width: '100%', marginTop: 12 }} onChange={selectProduct} options={products.map((product) => ({ value: product.id, label: product.nickname }))} />
        {currentProduct && <div className="card" style={{ marginTop: 16 }}><div className="card-body"><strong>{currentProduct.nickname}</strong><p>{productSummary(currentProduct) || '暂无补充卖点'}</p></div></div>}
        {!currentProduct && <p style={{ color: 'var(--danger)' }}>请先选择当前商品；没有商品时请到产品库新建后再返回。</p>}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}><button className="btn btn-ghost" onClick={() => setStep(0)}>← 返回</button><button className="btn btn-primary" disabled={loading || !currentProduct} onClick={handleDirections}>{loading ? '推导中...' : '生成情绪方向'}</button></div>
      </div></div>}

      {step === 2 && <div className="card"><div className="card-body">
        <h2 className="card-title">选择并调整情绪方向</h2>
        <p>先选择 AI 分析，再按实际内容调整说明或情绪锚点。</p>
        {directions.map((item) => <button key={`${item.type}-${item.title}`} className="card" style={{ width: '100%', textAlign: 'left', marginTop: 12, borderColor: direction === item ? 'var(--primary)' : undefined }} onClick={() => setDirection({ ...item })}><strong>{item.type} · {item.title}</strong><p>{item.description}</p><small>情绪锚点：{item.anchor}</small></button>)}
        {direction && <><label htmlFor="value-direction-title" style={{ display: 'block', marginTop: 16 }}>方向标题</label><Input id="value-direction-title" aria-label="方向标题" value={direction.title} onChange={(event) => setDirection({ ...direction, title: event.target.value })} /><label htmlFor="value-direction" style={{ display: 'block', marginTop: 12 }}>人工调整方向说明</label><TextArea id="value-direction" aria-label="人工调整方向说明" rows={3} value={direction.description} onChange={(event) => setDirection({ ...direction, description: event.target.value })} /><label htmlFor="value-anchor" style={{ display: 'block', marginTop: 12 }}>情绪锚点</label><Input id="value-anchor" aria-label="情绪锚点" value={direction.anchor} onChange={(event) => setDirection({ ...direction, anchor: event.target.value })} /></>}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}><button className="btn btn-ghost" onClick={() => setStep(1)}>← 换商品</button><button className="btn btn-primary" disabled={!direction || loading} onClick={handleGenerate}>{loading ? '生成中...' : '生成脚本和报告'}</button></div>
      </div></div>}

      {step === 3 && <div className="card"><div className="card-body">
        <div style={{ display: 'flex', justifyContent: 'space-between' }}><h2 className="card-title">脚本和情绪检测报告</h2><div><button className="btn btn-ghost btn-sm" onClick={() => setStep(2)}>重新选择方向</button><button className="btn btn-ghost btn-sm" onClick={handleSave}>保存到产出中心</button></div></div>
        {similarity !== null && <p>与原文相似度：<strong>{similarity}%</strong>（{similarityText}）</p>}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}><button className="btn btn-ghost btn-sm" onClick={() => setActiveResult('script')}>脚本</button><button className="btn btn-ghost btn-sm" onClick={() => setActiveResult('report')}>情绪检测报告</button></div>
        {activeResult === 'script' ? <TextArea aria-label="改写脚本" rows={14} value={result?.rewrite ?? rawResult} onChange={(event) => result && setResult({ ...result, rewrite: event.target.value })} /> : <TextArea aria-label="情绪检测报告" rows={14} value={result?.report ?? rawResult} onChange={(event) => result && setResult({ ...result, report: event.target.value })} />}
        {result && <p style={{ marginTop: 12 }}>原文结构分析：{result.analysis}</p>}
        <button className="btn btn-primary" style={{ marginTop: 12 }} disabled={!result} onClick={() => result && downloadText(`=== 价值观脚本 ===\n\n${result.rewrite}\n\n=== 情绪检测报告 ===\n\n${result.report}`, currentProduct?.nickname ?? '')}>导出文本</button>
      </div></div>}
    </div>
  );
}

export default function ValuesWriterPage() {
  const { message } = App.useApp();
  const [personas, setPersonas] = useState<QianchuanWriterPersona[]>([]);
  const [selectedKolId, setSelectedKolId] = useState<number | null>(null);

  useEffect(() => {
    get<QianchuanWriterPersona[]>('/api/tools/qianchuan-writer/kols/personas').then(setPersonas).catch(() => message.error('加载达人列表失败'));
  }, [message]);

  return selectedKolId === null ? <div className="card"><div className="card-body"><h1 className="page-title">价值观仿写</h1><Select aria-label="选择达人" style={{ width: '100%', marginTop: 16 }} placeholder="请选择达人" onChange={setSelectedKolId} options={personas.map((persona) => ({ value: persona.id, label: persona.name }))} /></div></div> : <ValuesWriterModule kolId={selectedKolId} />;
}
