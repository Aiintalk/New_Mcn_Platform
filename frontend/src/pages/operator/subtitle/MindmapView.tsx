/**
 * MindmapView — SVG 思维导图渲染（移植自旧架构 subtitle-extractor-web/app/page.tsx）
 *
 * 特性：
 * - 贝塞尔曲线连接 root → branch → children
 * - 拖拽平移（document-level mouse events，防止鼠标移出元素丢失）
 * - Ctrl+滚轮缩放（非被动监听，可 preventDefault）
 * - ±按钮缩放（0.5–2.0 范围）
 *
 * 样式翻译对照（Tailwind → inline CSS variables）：
 * - bg-gray-800 text-white → backgroundColor: var(--gray-800), color: #fff
 * - bg-blue-50 border-blue-200 text-blue-700 → backgroundColor: var(--brand-50), border, color
 * - bg-white border-gray-200 → backgroundColor: #fff, border
 */
import { useEffect, useRef, useState } from 'react';
import type { MindmapResult } from '../../../api/subtitle';

// Layout constants（与旧架构完全一致）
const MM_LINE_H = 18;
const MM_BRANCH_PAD = 12;
const MM_CHILD_PAD = 8;
const MM_BRANCH_CHARS = 10;
const MM_CHILD_CHARS = 13;
const MM_BRANCH_GAP = 8;
const MM_CHILD_GAP = 4;
const MM_CURVE_W = 44;
const MM_CCURVE_W = 28;

function mmBranchH(title: string): number {
  return MM_BRANCH_PAD + Math.max(1, Math.ceil(title.length / MM_BRANCH_CHARS)) * MM_LINE_H;
}

function mmChildH(text: string): number {
  return MM_CHILD_PAD + Math.max(1, Math.ceil(text.length / MM_CHILD_CHARS)) * MM_LINE_H;
}

interface MindmapViewProps {
  mindmap: MindmapResult;
  /** 缩放百分比变化时通知父组件（用于显示在控件中），双向同步 */
  zoom?: number;
  onZoomChange?: (zoom: number) => void;
}

export default function MindmapView({ mindmap, zoom, onZoomChange }: MindmapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [internalZoom, setInternalZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef({ startX: 0, startY: 0, panX: 0, panY: 0 });

  // 外部受控 / 内部非受控兼容
  const mmZoom = zoom ?? internalZoom;
  const setMmZoom = (next: number) => {
    const clamped = Math.max(0.5, Math.min(2, +(+next).toFixed(1)));
    if (onZoomChange) onZoomChange(clamped);
    if (!onZoomChange || zoom === undefined) setInternalZoom(clamped);
  };

  // mindmap 变化时重置 zoom/pan
  useEffect(() => {
    setInternalZoom(1);
    setPan({ x: 0, y: 0 });
    if (onZoomChange) onZoomChange(1);
  }, [mindmap, onZoomChange]);

  // Ctrl+Wheel 缩放（非被动监听）
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      const d = e.deltaY > 0 ? -0.1 : 0.1;
      setMmZoom(mmZoom + d);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mmZoom]);

  // 拖拽：document-level 监听，防止鼠标移出元素丢失
  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => {
      setPan({
        x: dragStart.current.panX + (e.clientX - dragStart.current.startX),
        y: dragStart.current.panY + (e.clientY - dragStart.current.startY),
      });
    };
    const onUp = () => {
      setDragging(false);
      if (containerRef.current) containerRef.current.style.cursor = 'grab';
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, [dragging]);

  const mmZoomIn = () => setMmZoom(mmZoom + 0.1);
  const mmZoomOut = () => setMmZoom(mmZoom - 0.1);

  const onMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    dragStart.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
    setDragging(true);
    if (containerRef.current) containerRef.current.style.cursor = 'grabbing';
    e.preventDefault();
  };

  // 计算行高 & 贝塞尔锚点（算法与旧架构一致）
  const branches = mindmap.branches;
  let runningTop = 0;
  const rows = branches.map((b, i) => {
    const bh = mmBranchH(b.title);
    const childHeights = (b.children || []).map(mmChildH);
    const childrenH =
      childHeights.length > 0
        ? childHeights.reduce((s, h, j) => s + h + (j > 0 ? MM_CHILD_GAP : 0), 0)
        : 0;
    const h = Math.max(bh, childrenH);
    const top = runningTop;
    runningTop += h + (i < branches.length - 1 ? MM_BRANCH_GAP : 0);
    return { height: h, centerY: top + h / 2, childHeights, childrenH };
  });

  const totalH = runningTop || 30;
  const midY = totalH / 2;

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        cursor: dragging ? 'grabbing' : 'grab',
        userSelect: 'none',
        position: 'relative',
      }}
      onMouseDown={onMouseDown}
    >
      <div
        style={{
          display: 'inline-block',
          padding: 16,
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${mmZoom})`,
          transformOrigin: '0 0',
        }}
      >
        <div style={{ display: 'inline-flex', alignItems: 'center' }}>
          {/* 根节点 */}
          <div
            style={{
              flexShrink: 0,
              padding: '10px 12px',
              backgroundColor: 'var(--gray-800)',
              color: '#fff',
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 700,
              textAlign: 'center',
              width: 100,
              lineHeight: 1.4,
            }}
          >
            {mindmap.rootTitle}
          </div>

          {/* 根 → 分支 贝塞尔连线 */}
          <svg
            width={MM_CURVE_W}
            height={totalH}
            style={{ flexShrink: 0, overflow: 'visible', display: 'block' }}
          >
            {rows.map((row, i) => {
              const cy = row.centerY;
              const d = `M 0 ${midY} C ${MM_CURVE_W * 0.6} ${midY} ${MM_CURVE_W * 0.4} ${cy} ${MM_CURVE_W} ${cy}`;
              return (
                <path
                  key={i}
                  d={d}
                  fill="none"
                  stroke="var(--gray-300)"
                  strokeWidth={1.5}
                  strokeLinecap="round"
                />
              );
            })}
          </svg>

          {/* 分支列表 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: MM_BRANCH_GAP }}>
            {branches.map((branch, i) => {
              const row = rows[i];
              const { childHeights, childrenH } = row;
              const cMidY = childrenH / 2;

              let childTop = 0;
              const childCenterYs = childHeights.map((ch) => {
                const cy = childTop + ch / 2;
                childTop += ch + MM_CHILD_GAP;
                return cy;
              });

              return (
                <div
                  key={i}
                  style={{ height: row.height, display: 'flex', alignItems: 'center' }}
                >
                  {/* 分支节点 */}
                  <div
                    style={{
                      flexShrink: 0,
                      padding: '6px 10px',
                      borderRadius: 6,
                      backgroundColor: 'var(--brand-light)',
                      border: '1px solid var(--brand-border)',
                      color: 'var(--brand-dark)',
                      fontSize: 12,
                      fontWeight: 600,
                      maxWidth: 140,
                      lineHeight: 1.4,
                    }}
                  >
                    {branch.title}
                  </div>

                  {/* 分支 → 子项 贝塞尔连线 */}
                  {childHeights.length > 0 && (
                    <>
                      <svg
                        width={MM_CCURVE_W}
                        height={childrenH}
                        style={{
                          flexShrink: 0,
                          overflow: 'visible',
                          display: 'block',
                          alignSelf: 'center',
                        }}
                      >
                        {childCenterYs.map((cy, j) => {
                          const d = `M 0 ${cMidY} C ${MM_CCURVE_W * 0.6} ${cMidY} ${MM_CCURVE_W * 0.4} ${cy} ${MM_CCURVE_W} ${cy}`;
                          return (
                            <path
                              key={j}
                              d={d}
                              fill="none"
                              stroke="var(--gray-200)"
                              strokeWidth={1.5}
                              strokeLinecap="round"
                            />
                          );
                        })}
                      </svg>

                      {/* 子项列表 */}
                      <div
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          gap: MM_CHILD_GAP,
                          alignSelf: 'center',
                        }}
                      >
                        {(branch.children || []).map((child, j) => (
                          <div
                            key={j}
                            style={{
                              padding: '4px 10px',
                              display: 'flex',
                              alignItems: 'center',
                              border: '1px solid var(--gray-200)',
                              borderRadius: 4,
                              backgroundColor: '#fff',
                              color: 'var(--gray-600)',
                              fontSize: 12,
                              height: childHeights[j],
                              maxWidth: 180,
                              lineHeight: 1.4,
                            }}
                          >
                            {child}
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 缩放控件（右上角浮层） */}
      <div
        style={{
          position: 'absolute',
          top: 8,
          right: 8,
          display: 'flex',
          alignItems: 'center',
          border: '1px solid var(--gray-300)',
          borderRadius: 6,
          overflow: 'hidden',
          backgroundColor: '#fff',
        }}
      >
        <button
          onClick={mmZoomOut}
          style={{
            width: 32,
            height: 28,
            border: 'none',
            background: 'none',
            cursor: 'pointer',
            color: 'var(--gray-600)',
            fontSize: 14,
          }}
        >
          −
        </button>
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
        <button
          onClick={mmZoomIn}
          style={{
            width: 32,
            height: 28,
            border: 'none',
            background: 'none',
            cursor: 'pointer',
            color: 'var(--gray-600)',
            fontSize: 14,
          }}
        >
          +
        </button>
      </div>
    </div>
  );
}
