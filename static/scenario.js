// static/scenario.js
// P3 PR1: 招商/路演实时计算器 (2026-08-07)

(function() {
  'use strict';

  const formState = {
    name: 'live_scenario',
    tree_shape: { fork_type: 'binary', max_level: 10,
                  layer_counts: {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99} },
    growth: { nodes_per_region_per_week: 9, n_regions: 4, join_strategy: 'round_robin', weeks_per_month: 4 },
    revenue: { initial_pv: 1500, monthly_renew_pv: 100, color_rule: '4_color_cycle', color_names: ['红', '紫', '青绿', '蓝'] },
    commission_config: {
      enable_retail_profit: false, enable_team_bonus: true,
      team_bonus_tier_rates: {200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30},
      team_bonus_window_weeks: 4,
      enable_own_basic: true, own_basic_rate: 0.15, own_basic_line_pv_cap: 13334,
      enable_savings: true, savings_usd_threshold: 250.0, savings_rate: 0.15, savings_cap_usd: 500.0,
      enable_pair_bonus: true,
      pair_bonus_ratios: {1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05},
      pair_bonus_4th_usd_threshold: 500.0, pair_bonus_5th_usd_threshold: 1000.0,
      enable_leader_dividend: true, leader_dividend_threshold_pv: 13334,
      leader_dividend_share_usd: 500.0, leader_dividend_tiers: {1: 2, 2: 4, 3: 6, 4: 8},
      enable_horizontal_leader: true, horizontal_leader_share_usd: 250.0,
      horizontal_leader_tiers: {1: 2, 2: 2, 3: 4, 4: 6},
      enable_opportunity_points: false,
    },
  };

  // 公开 API, 后续 Task 3-4 替换 stub
  window.P3 = {
    formState,
    getFormState() { return formState; },
    showToast(msg, type) { console.log(`[toast-${type}]`, msg); },
  };
})();
