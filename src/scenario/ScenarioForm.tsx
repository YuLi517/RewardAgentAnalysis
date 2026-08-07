// src/scenario/ScenarioForm.tsx
// v1.0.2: 4 个 beam-wrap 的 input/select 表单 (受控组件, 同步到 formState)
import { useCallback } from 'react';
import { BeamCard } from './BeamCard';
import type { FormState } from './types';

interface ScenarioFormProps {
  formState: FormState;
  onChange: (next: FormState) => void;
}

/** 重新按 fork_type 算 layer_counts, 末层 leftover */
function rebuildLayerCounts(totalTarget: number, forkType: 'binary' | 'ternary' | 'quaternary'): Record<number, number> {
  const base = forkType === 'binary' ? 2 : forkType === 'ternary' ? 3 : 4;
  const counts: Record<number, number> = { 0: 1 };
  let sum = 1;
  for (let lv = 1; lv <= 10; lv++) {
    const next = (counts[lv - 1] ?? 0) * base;
    if (sum + next > totalTarget) {
      counts[lv] = totalTarget - sum;
      return counts;
    }
    counts[lv] = next;
    sum += next;
  }
  return counts;
}

/** 路径映射: section + key -> formState 嵌套路径 setter */
function applyInput(state: FormState, section: string, key: string, value: string | number): FormState {
  const next = { ...state };
  if (section === 'tree') {
    if (key === 'fork_type') {
      const ft = value as 'binary' | 'ternary' | 'quaternary';
      const total = Object.values(next.tree_shape.layer_counts).reduce((a, b) => a + b, 0);
      next.tree_shape = {
        ...next.tree_shape,
        fork_type: ft,
        layer_counts: rebuildLayerCounts(total, ft),
      };
    } else if (key === 'max_level') {
      const lv = Number(value);
      const filtered = Object.fromEntries(
        Object.entries(next.tree_shape.layer_counts).filter(([k]) => Number(k) <= lv),
      );
      next.tree_shape = { ...next.tree_shape, max_level: lv, layer_counts: filtered };
    } else if (key === 'total_target') {
      const total = Number(value);
      next.tree_shape = {
        ...next.tree_shape,
        layer_counts: rebuildLayerCounts(total, next.tree_shape.fork_type),
      };
    }
  } else if (section === 'growth') {
    next.growth = { ...next.growth, [key]: Number(value) };
  } else if (section === 'revenue') {
    next.revenue = { ...next.revenue, [key]: Number(value) };
  } else if (section === 'commission') {
    if (key === 'own_basic_rate') {
      next.commission_config = { ...next.commission_config, own_basic_rate: Number(value) };
    } else if (key === 'pair_bonus_ratio_1gen') {
      next.commission_config = {
        ...next.commission_config,
        pair_bonus_ratios: { ...next.commission_config.pair_bonus_ratios, 1: Number(value) },
      };
    }
  }
  return next;
}

/** 受控 input 解析: rate 用 float, 其余 int */
function parseValue(key: string, raw: string): number | null {
  const isFloat = /rate|ratio/.test(key);
  const num = isFloat ? parseFloat(raw) : parseInt(raw, 10);
  return isNaN(num) || num < 0 ? null : num;
}

export function ScenarioForm({ formState, onChange }: ScenarioFormProps) {
  const handleInput = useCallback((section: string, key: string, raw: string) => {
    const num = parseValue(key, raw);
    if (num === null) return;  // 忽略非法输入 (但保留 input 值, 让用户改)
    onChange(applyInput(formState, section, key, num));
  }, [formState, onChange]);

  return (
    <div className="p3-left">
      {/* ===== TreeShape ===== */}
      <BeamCard title="🌳 TreeShape (树形)" section="tree">
        <div className="form-row">
          <span>fork_type</span>
          <select
            className="val-input"
            value={formState.tree_shape.fork_type}
            onChange={(e) => onChange(applyInput(formState, 'tree', 'fork_type', e.target.value))}
          >
            <option value="binary">binary (2 叉)</option>
            <option value="ternary">ternary (3 叉)</option>
            <option value="quaternary">quaternary (4 叉)</option>
          </select>
        </div>
        <div className="form-row">
          <span>max_level</span>
          <input
            className="val-input" type="text" inputMode="numeric"
            value={formState.tree_shape.max_level}
            onChange={(e) => handleInput('tree', 'max_level', e.target.value)}
          />
        </div>
        <div className="form-row">
          <span>total_target</span>
          <input
            className="val-input" type="text" inputMode="numeric"
            value={Object.values(formState.tree_shape.layer_counts).reduce((a, b) => a + b, 0)}
            onChange={(e) => handleInput('tree', 'total_target', e.target.value)}
          />
        </div>
      </BeamCard>

      {/* ===== Growth ===== */}
      <BeamCard title="📈 Growth (增长)" section="growth" colorVariant="colorful">
        <div className="form-row">
          <span>per_region/week</span>
          <input
            className="val-input" type="text" inputMode="numeric"
            value={formState.growth.nodes_per_region_per_week}
            onChange={(e) => handleInput('growth', 'nodes_per_region_per_week', e.target.value)}
          />
        </div>
        <div className="form-row">
          <span>n_regions</span>
          <input
            className="val-input" type="text" inputMode="numeric"
            value={formState.growth.n_regions}
            onChange={(e) => handleInput('growth', 'n_regions', e.target.value)}
          />
        </div>
        <div className="form-row">
          <span>weeks/month</span>
          <input
            className="val-input" type="text" inputMode="numeric"
            value={formState.growth.weeks_per_month}
            onChange={(e) => handleInput('growth', 'weeks_per_month', e.target.value)}
          />
        </div>
      </BeamCard>

      {/* ===== Revenue ===== */}
      <BeamCard title="💰 Revenue (收入)" section="revenue" colorVariant="sunset">
        <div className="form-row">
          <span>initial_pv</span>
          <input
            className="val-input" type="text" inputMode="numeric"
            value={formState.revenue.initial_pv}
            onChange={(e) => handleInput('revenue', 'initial_pv', e.target.value)}
          />
        </div>
        <div className="form-row">
          <span>monthly_renew</span>
          <input
            className="val-input" type="text" inputMode="numeric"
            value={formState.revenue.monthly_renew_pv}
            onChange={(e) => handleInput('revenue', 'monthly_renew_pv', e.target.value)}
          />
        </div>
      </BeamCard>

      {/* ===== Commission ===== */}
      <BeamCard title="🎁 Commission (报酬)" section="commission" colorVariant="mono">
        <div className="form-row">
          <span>own_basic_rate</span>
          <input
            className="val-input" type="text" inputMode="numeric"
            value={formState.commission_config.own_basic_rate}
            onChange={(e) => handleInput('commission', 'own_basic_rate', e.target.value)}
          />
        </div>
        <div className="form-row">
          <span>pair_bonus 1代</span>
          <input
            className="val-input" type="text" inputMode="numeric"
            value={formState.commission_config.pair_bonus_ratios['1'] ?? 0.15}
            onChange={(e) => handleInput('commission', 'pair_bonus_ratio_1gen', e.target.value)}
          />
        </div>
        <div className="form-row">
          <span>team_bonus 4档</span>
          <span className="val readonly" title="200→15% / 500→20% / 1000→25% / 1500→30%">15-30%</span>
        </div>
      </BeamCard>
    </div>
  );
}
