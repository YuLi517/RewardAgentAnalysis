// src/scenario/ScenarioPage.tsx
// v1.0.2: 顶层组件 - 翻译原 scenario.html + scenario.js 为 React
import { useCallback, useState } from 'react';
import { ScenarioForm } from './ScenarioForm';
import { TreeCanvas } from './TreeCanvas';
import { CommissionCards } from './CommissionCards';
import { Heatmap } from './Heatmap';
import { postScenario, getOverview, getOverviewAll } from './api';
import { initialFormState } from './types';
import type { FormState, Overview, HeatmapData } from './types';

export function ScenarioPage() {
  const [formState, setFormState] = useState<FormState>(initialFormState);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null);
  const [scenarioId, setScenarioId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);

  const showToast = useCallback((msg: string, type: 'success' | 'error') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  const handleSubmit = useCallback(async () => {
    setSubmitting(true);
    try {
      const { id } = await postScenario(formState);
      setScenarioId(id);
      const ov = await getOverview(id, 14);
      setOverview(ov);
      try {
        const all = await getOverviewAll(id, 14);
        setHeatmap(all);
      } catch (e) {
        console.warn('overview/all failed (热图 14月累计):', e);
      }
      showToast(`scenario ${id} 计算完成`, 'success');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      showToast(`提交失败: ${msg}`, 'error');
    } finally {
      setSubmitting(false);
    }
  }, [formState, showToast]);

  const handlePreview = useCallback(() => {
    // 树形预览: 当前 TreeCanvas 已经画了 L0-L3, 业务上 "👁 树形预览" 主要是看 root.eff 算得对不对
    // 这里简单: 弹 toast 提示当前 fork_type + total_target
    showToast(`树形: ${formState.tree_shape.fork_type}, ${formState.tree_shape.max_level} 层, ${Object.values(formState.tree_shape.layer_counts).reduce((a, b) => a + b, 0)} 节点`, 'success');
  }, [formState, showToast]);

  return (
    <div className="p3-container">
      <h1 className="p3-title">📐 SCENARIO 招商/路演实时计算器</h1>
      <div className="p3-layout">
        <ScenarioForm formState={formState} onChange={setFormState} />
        <div className="p3-right">
          <h2>🌲 树形图 (Canvas 2D)</h2>
          <TreeCanvas totalNodes={Object.values(formState.tree_shape.layer_counts).reduce((a, b) => a + b, 0)} />

          <h2>💎 8 种报酬 — 月 14 累计</h2>
          <CommissionCards overview={overview} />

          <div className="p3-submit-row">
            <button id="btn-preview" className="p3-preview-btn" onClick={handlePreview}>👁 树形预览</button>
            <button id="btn-submit" className="p3-submit-btn" onClick={handleSubmit} disabled={submitting}>
              {submitting ? '提交中...' : '🎲 提交场景 + 算报酬'}
            </button>
          </div>

          {toast && (
            <div className={`p3-toast ${toast.type}`} style={{ display: 'block' }}>
              {toast.msg}
            </div>
          )}

          <Heatmap data={heatmap} scenarioId={scenarioId} />
        </div>
      </div>
    </div>
  );
}
