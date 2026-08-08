// src/scenario/Heatmap.tsx
// v1.0.2: 8 种报酬 × 14 月 累计热图 (Canvas 2D + tooltip + 月份详情)
import { useEffect, useRef, useState, useCallback } from 'react';
import { getOverview } from './api';
import type { HeatmapData, Overview } from './types';

const HEATMAP_COLORS: Record<string, string> = {
  ownBasic: '#5AA4AE', pairBonus: '#758A99', teamBonus: '#F0C239',
  savings: '#C0EBD7', leader: '#5AA4AE80', horizontal: '#758A9980',
  retail: '#C0EBD780', total: '#5AA4AE',
};
const HEATMAP_ROWS = ['ownBasic', 'pairBonus', 'teamBonus', 'savings',
  'leader', 'horizontal', 'retail', 'total'];
const CELL_W = 32, CELL_H = 24, CELL_GAP = 4;
const LABEL_W = 70, LABEL_H = 20;

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.length === 9 ? hex.slice(0, 7) : hex;
  const r = parseInt(h.slice(1, 3), 16);
  const g = parseInt(h.slice(3, 5), 16);
  const b = parseInt(h.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

interface HeatmapProps {
  data: HeatmapData | null;
  scenarioId: number | null;
}

export function Heatmap({ data, scenarioId }: HeatmapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const [monthDetail, setMonthDetail] = useState<{ month: number; row: number; loading: boolean; data: Overview | null } | null>(null);

  // 画热图
  useEffect(() => {
    if (!data || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const totalCols = data.months.length;
    const totalRows = HEATMAP_ROWS.length;
    canvas.width = LABEL_W + totalCols * (CELL_W + CELL_GAP) + CELL_GAP;
    canvas.height = LABEL_H + totalRows * (CELL_H + CELL_GAP) + CELL_GAP;
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = '#0a0a14';
    ctx.fillRect(0, 0, w, h);

    // 行 label
    ctx.fillStyle = '#758A99';
    ctx.font = '11px monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    HEATMAP_ROWS.forEach((f, i) => {
      const y = LABEL_H + i * (CELL_H + CELL_GAP) + CELL_H / 2;
      ctx.fillText(f, LABEL_W - 6, y);
    });
    // 列 label
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    data.months.forEach((m, j) => {
      const x = LABEL_W + j * (CELL_W + CELL_GAP) + CELL_W / 2;
      ctx.fillText('M' + m, x, LABEL_H - 4);
    });

    // 单元格
    HEATMAP_ROWS.forEach((f, i) => {
      const rowValues = (data.matrix[f] ?? []).map((v) => parseFloat(String(v)) || 0);
      const maxV = Math.max(...rowValues, 0.01);
      rowValues.forEach((v, j) => {
        const x = LABEL_W + j * (CELL_W + CELL_GAP);
        const y = LABEL_H + i * (CELL_H + CELL_GAP);
        const alpha = Math.min(1.0, Math.max(0.1, v / maxV));
        ctx.fillStyle = hexToRgba(HEATMAP_COLORS[f], alpha);
        ctx.fillRect(x, y, CELL_W, CELL_H);
      });
    });
  }, [data]);

  const onMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!data) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    if (x < LABEL_W || y < LABEL_H) { setTooltip(null); return; }
    const j = Math.floor((x - LABEL_W) / (CELL_W + CELL_GAP));
    const i = Math.floor((y - LABEL_H) / (CELL_H + CELL_GAP));
    if (i < 0 || i >= HEATMAP_ROWS.length || j < 0 || j >= data.months.length) {
      setTooltip(null); return;
    }
    const f = HEATMAP_ROWS[i];
    const m = data.months[j];
    const v = data.matrix[f]?.[m] ?? '0';
    setTooltip({
      x: e.clientX + 12,
      y: e.clientY + 12,
      text: `${f}, M${m}, $${parseFloat(String(v)).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    });
  }, [data]);

  const onClick = useCallback(async (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!data || !scenarioId) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    if (x < LABEL_W || y < LABEL_H) return;
    const j = Math.floor((x - LABEL_W) / (CELL_W + CELL_GAP));
    const i = Math.floor((y - LABEL_H) / (CELL_H + CELL_GAP));
    if (i < 0 || i >= HEATMAP_ROWS.length || j < 0 || j >= data.months.length) return;
    const m = data.months[j];
    setMonthDetail({ month: m, row: i, loading: true, data: null });
    try {
      const ov = await getOverview(scenarioId, m);
      setMonthDetail({ month: m, row: i, loading: false, data: ov });
    } catch (err) {
      setMonthDetail({ month: m, row: i, loading: false, data: null });
      console.error('month detail failed', err);
    }
  }, [data, scenarioId]);

  if (!data) return null;

  return (
    <section className="p3-heatmap">
      <h2>📊 8 种报酬 × 14 月累计热图</h2>
      <div className="heatmap-container">
        <canvas
          ref={canvasRef}
          id="heatmap-canvas"
          onMouseMove={onMouseMove}
          onMouseLeave={() => setTooltip(null)}
          onClick={onClick}
        />
      </div>
      <div className="heatmap-legend">
        <span className="legend-low">低</span>
        <span className="legend-grad"></span>
        <span className="legend-high">高</span>
        <span className="legend-hint">(颜色深 = 金额高)</span>
      </div>
      {tooltip && (
        <div className="heatmap-tooltip" style={{ left: tooltip.x, top: tooltip.y, display: 'block' }}>
          {tooltip.text}
        </div>
      )}
      {monthDetail && (
        <div className="month-detail" style={{ display: 'block' }}>
          <h3>📅 M{monthDetail.month} 月份详情</h3>
          <div className="month-detail-body">
            {monthDetail.loading ? (
              <p>加载中... (≤ 60s)</p>
            ) : monthDetail.data ? (
              HEATMAP_ROWS.map((f) => (
                <div key={f} style={{ display: 'contents' }}>
                  <div className="field">{f}</div>
                  <div className="val">${parseFloat(String(monthDetail.data?.[f as keyof Overview] ?? '0')).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                </div>
              ))
            ) : (
              <p style={{ color: '#EF4444' }}>加载失败</p>
            )}
          </div>
          <button className="month-detail-close" onClick={() => setMonthDetail(null)}>✕ 关闭</button>
        </div>
      )}
    </section>
  );
}
