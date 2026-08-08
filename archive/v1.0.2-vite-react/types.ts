// src/scenario/types.ts
// v1.0.2: formState + Overview 类型定义 (跟 scenario_routes.py 对齐)

export interface TreeShape {
  fork_type: 'binary' | 'ternary' | 'quaternary';
  max_level: number;
  layer_counts: Record<number, number>;
}

export interface Growth {
  nodes_per_region_per_week: number;
  n_regions: number;
  join_strategy: string;
  weeks_per_month: number;
}

export interface Revenue {
  initial_pv: number;
  monthly_renew_pv: number;
  color_rule: string;
  color_names: string[];
}

export interface CommissionConfig {
  enable_retail_profit: boolean;
  enable_team_bonus: boolean;
  team_bonus_tier_rates: Record<string, number>;
  team_bonus_window_weeks: number;
  enable_own_basic: boolean;
  own_basic_rate: number;
  own_basic_line_pv_cap: number;
  enable_savings: boolean;
  savings_usd_threshold: number;
  savings_rate: number;
  savings_cap_usd: number;
  enable_pair_bonus: boolean;
  pair_bonus_ratios: Record<string, number>;
  pair_bonus_4th_usd_threshold: number;
  pair_bonus_5th_usd_threshold: number;
  enable_leader_dividend: boolean;
  leader_dividend_threshold_pv: number;
  leader_dividend_share_usd: number;
  leader_dividend_tiers: Record<string, number>;
  enable_horizontal_leader: boolean;
  horizontal_leader_share_usd: number;
  horizontal_leader_tiers: Record<string, number>;
  enable_opportunity_points: boolean;
}

export interface FormState {
  name: string;
  tree_shape: TreeShape;
  growth: Growth;
  revenue: Revenue;
  commission_config: CommissionConfig;
}

export const initialFormState: FormState = {
  name: 'live_scenario',
  tree_shape: {
    fork_type: 'binary',
    max_level: 10,
    layer_counts: { 0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99 },
  },
  growth: { nodes_per_region_per_week: 9, n_regions: 4, join_strategy: 'round_robin', weeks_per_month: 4 },
  revenue: { initial_pv: 1500, monthly_renew_pv: 100, color_rule: '4_color_cycle', color_names: ['红', '紫', '青绿', '蓝'] },
  commission_config: {
    enable_retail_profit: false,
    enable_team_bonus: true,
    team_bonus_tier_rates: { 200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30 },
    team_bonus_window_weeks: 4,
    enable_own_basic: true,
    own_basic_rate: 0.15,
    own_basic_line_pv_cap: 13334,
    enable_savings: true,
    savings_usd_threshold: 250.0,
    savings_rate: 0.15,
    savings_cap_usd: 500.0,
    enable_pair_bonus: true,
    pair_bonus_ratios: { 1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05 },
    pair_bonus_4th_usd_threshold: 500.0,
    pair_bonus_5th_usd_threshold: 1000.0,
    enable_leader_dividend: true,
    leader_dividend_threshold_pv: 13334,
    leader_dividend_share_usd: 500.0,
    leader_dividend_tiers: { 1: 2, 2: 4, 3: 6, 4: 8 },
    enable_horizontal_leader: true,
    horizontal_leader_share_usd: 250.0,
    horizontal_leader_tiers: { 1: 2, 2: 2, 3: 4, 4: 6 },
    enable_opportunity_points: false,
  },
};

export interface Overview {
  scenario_id: number;
  month: number;
  ownBasic: string;
  pairBonus: string;
  teamBonus: string;
  savings: string;
  leader: string;
  horizontal: string;
  retail: string;
  total: string;
}

export interface HeatmapData {
  fields: string[];
  months: number[];
  matrix: Record<string, string[]>;
}
