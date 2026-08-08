// src/scenario/api.ts
// v1.0.2: API 调用 (POST /api/scenarios + GET overview + GET overview/all)
import type { FormState, Overview, HeatmapData } from './types';

export async function postScenario(body: FormState): Promise<{ id: number }> {
  // Pydantic v2 要求 Dict[str, int] 字符串 key, 这里 copy + 转 key 为 str
  const payload = JSON.parse(JSON.stringify(body));
  payload.tree_shape.layer_counts = Object.fromEntries(
    Object.entries(payload.tree_shape.layer_counts).map(([k, v]) => [String(k), v]),
  );
  for (const k of [
    'team_bonus_tier_rates', 'pair_bonus_ratios',
    'leader_dividend_tiers', 'horizontal_leader_tiers',
  ]) {
    if (payload.commission_config[k]) {
      payload.commission_config[k] = Object.fromEntries(
        Object.entries(payload.commission_config[k]).map(([kk, vv]) => [String(kk), vv]),
      );
    }
  }
  const resp = await fetch('/api/scenarios', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error('POST failed: ' + (err.detail || resp.status));
  }
  return resp.json();
}

export async function getOverview(scenarioId: number, month: number): Promise<Overview> {
  const resp = await fetch(`/api/scenarios/${scenarioId}/overview?month=${month}`);
  if (!resp.ok) throw new Error('overview failed: ' + resp.status);
  return resp.json();
}

export async function getOverviewAll(scenarioId: number, totalMonths = 14): Promise<HeatmapData> {
  const resp = await fetch(`/api/scenarios/${scenarioId}/overview/all?total_months=${totalMonths}`);
  if (!resp.ok) throw new Error('overview/all failed: ' + resp.status);
  return resp.json();
}
