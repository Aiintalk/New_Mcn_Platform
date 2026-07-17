import { useEffect, useState } from 'react';
import { App, Input, Select, Steps } from 'antd';
import {
  deriveDirections,
  generateValueScript,
  iterateValueScript,
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

interface ValueScriptRevision {
  instruction: string;
  result: ValueScriptResult;
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
  const [revisionInstruction, setRevisionInstruction] = useState('');
  const [revisionHistory, setRevisionHistory] = useState<ValueScriptRevision[]>([]);
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

  async function handleGenerate(selectedDirection = direction) {
    if (!selectedDirection) return;
    setLoading(true);
    setError('');
    setRawResult('');
    setResult(null);
    setRevisionHistory([]);
    try {
      const content = await generateValueScript({
        kol_id: kolId,
        opening_line: openingLine,
        original_script: originalScript,
        direction: selectedDirection,
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

  async function handleIteration() {
    if (!result || !direction || !revisionInstruction.trim()) return;
    setLoading(true);
    setError('');
    setRawResult('');
    const instruction = revisionInstruction.trim();
    try {
      const content = await iterateValueScript({
        kol_id: kolId,
        opening_line: openingLine,
        original_script: originalScript,
        direction,
        current_result: result,
        instruction,
        history: revisionHistory,
      }, setRawResult);
      const parsed = parseValueScriptResult(content);
      if (!parsed) {
        setError('修改结果缺少结构分析、改写脚本或情绪检测报告，请重新发送要求');
        return;
      }
      setRevisionHistory((items) => [...items, { instruction, result: parsed }]);
      setResult(parsed);
      setRevisionInstruction('');
      setActiveResult('script');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '脚本修改失败');
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
        <div style={{ background: 'var(--brand-light)', borderLeft: '3px solid var(--brand)', padding: 'var(--sp-3)', marginTop: 16 }}><strong>锁定开头</strong><div style={{ fontSize: 12, marginTop: 4 }}>这句话会逐字保留在生成脚本开头。</div><TextArea id="value-opening" aria-label="锁定开头" rows={2} value={openingLine} onChange={(event) => setOpeningLine(event.target.value)} placeholder="粘贴爆款的第一句话" style={{ marginTop: 8 }} /></div>
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
        <h2 className="card-title">选择情绪方向</h2>
        <p>点击方向卡后立即生成脚本和情绪检测报告。</p>
        <div style={{ display: 'grid', gap: 12 }}>{directions.map((item) => <button key={`${item.type}-${item.title}`} className="card" style={{ width: '100%', textAlign: 'left', borderColor: direction?.title === item.title ? 'var(--brand)' : undefined }} onClick={() => { setDirection(item); void handleGenerate(item); }} disabled={loading}><strong>{item.type} · {item.title}</strong><p>{item.description}</p><small>情绪锚点：{item.anchor}</small></button>)}</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}><button className="btn btn-ghost" onClick={() => setStep(1)}>← 换商品</button><span style={{ fontSize: 12, color: 'var(--gray-500)' }}>点击方向卡即开始生成</span></div>
      </div></div>}

      {step === 3 && <div className="card"><div className="card-body">
        <div style={{ display: 'flex', justifyContent: 'space-between' }}><h2 className="card-title">脚本和情绪检测报告</h2><div><button className="btn btn-ghost btn-sm" onClick={() => setStep(2)}>重新选择方向</button><button className="btn btn-ghost btn-sm" onClick={handleSave}>保存到产出中心</button></div></div>
        {result && <div style={{ margin: '12px 0', background: 'var(--info-light)', borderLeft: '3px solid var(--info)', padding: 'var(--sp-3)' }}><strong>原文结构分析</strong><div style={{ marginTop: 4 }}>{result.analysis}</div></div>}
        {similarity !== null && <p>与原文相似度：<strong style={{ color: similarity > 50 ? 'var(--danger)' : similarity > 35 ? 'var(--warning)' : 'var(--success)' }}>{similarity}%</strong>（{similarityText}）</p>}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}><button className="btn btn-ghost btn-sm" onClick={() => setActiveResult('script')}>脚本</button><button className="btn btn-ghost btn-sm" onClick={() => setActiveResult('report')}>情绪检测报告</button></div>
        {activeResult === 'script' ? <TextArea aria-label="改写脚本" rows={14} value={result?.rewrite ?? rawResult} onChange={(event) => result && setResult({ ...result, rewrite: event.target.value })} /> : <TextArea aria-label="情绪检测报告" rows={14} value={result?.report ?? rawResult} onChange={(event) => result && setResult({ ...result, report: event.target.value })} />}
        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
          <Input id="value-revision" aria-label="修改要求" value={revisionInstruction} onChange={(event) => setRevisionInstruction(event.target.value)} onPressEnter={() => void handleIteration()} placeholder="例如：把语气改得更克制，保留原有节奏" />
          <button className="btn btn-primary" disabled={loading || !revisionInstruction.trim()} onClick={handleIteration}>{loading ? '修改中...' : '发送'}</button>
        </div>
        <details aria-label="修改历史" style={{ marginTop: 16 }}><summary>修改历史（{revisionHistory.length + 1}）</summary><div style={{ marginTop: 8 }}><strong>初稿</strong><p>相似度：{calculateBigramSimilarity(originalScript, result?.rewrite ?? '')}%</p>{revisionHistory.map((item, index) => <div key={`${index}-${item.instruction}`}><strong>第 {index + 1} 次人工智能修改</strong><p>修改要求：{item.instruction}；相似度：{calculateBigramSimilarity(originalScript, item.result.rewrite)}%</p></div>)}</div></details>
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
